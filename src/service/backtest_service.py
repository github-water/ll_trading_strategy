from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common.backtest_models import (
    BacktestConfig,
    BacktestRequest,
    BacktestResult,
    PositionSizingMode,
)
from common.exceptions import BacktestValidationError, DataQualityError
from common.validators import normalize_symbol, parse_date, validate_date_range
from service.backtest_engine import BacktestEngine
from service.ports import BacktestChartBuilder, CsvRepository, StrategyRepository
from service.position_sizing_service import PositionSizingService
from service.strategy_indicator_engine import StrategyIndicatorEngine
from service.strategy_rule_evaluator import StrategyRuleEvaluator


class BacktestService:
    def __init__(
        self,
        *,
        csv_repository: CsvRepository,
        strategy_repository: StrategyRepository,
        indicator_engine: StrategyIndicatorEngine,
        rule_evaluator: StrategyRuleEvaluator,
        engine: BacktestEngine,
        chart_builder: BacktestChartBuilder,
        position_sizing: PositionSizingService | None = None,
    ) -> None:
        self._csv_repository = csv_repository
        self._strategy_repository = strategy_repository
        self._indicator_engine = indicator_engine
        self._rule_evaluator = rule_evaluator
        self._engine = engine
        self._chart_builder = chart_builder
        self._position_sizing = position_sizing or PositionSizingService()

    def list_strategy_choices(self) -> list[tuple[str, str]]:
        return [
            (strategy.name, strategy.strategy_id)
            for strategy in self._strategy_repository.list_all()
        ]

    def run(self, request: BacktestRequest) -> BacktestResult:
        if not str(request.strategy_id).strip():
            raise BacktestValidationError("请选择交易策略。")
        requested_symbol = self._optional_symbol(request.symbol)
        source_path = self._resolve_source(request.csv_path, requested_symbol)
        raw = self._csv_repository.read(source_path)
        data = self._prepare_data(raw)
        symbol, data = self._resolve_symbol(data, requested_symbol)
        strategy = self._strategy_repository.get(request.strategy_id)

        extra_atr_periods: set[int] = set()
        if request.config.atr_period_override is not None:
            extra_atr_periods.add(request.config.atr_period_override)
        prepared = self._indicator_engine.prepare(
            data,
            strategy,
            extra_atr_periods=extra_atr_periods,
        )
        prepared["entry_signal"] = self._rule_evaluator.evaluate_ruleset(
            prepared, strategy.entry_rule
        )
        prepared["exit_signal"] = self._rule_evaluator.evaluate_ruleset(
            prepared, strategy.exit_rule
        )
        visible = self._filter_dates(
            prepared,
            request.start_date,
            request.end_date,
        ).reset_index(drop=True)
        if len(visible) < 2:
            raise BacktestValidationError("回测区间至少需要两个有效交易日。")

        result = self._engine.run(
            visible,
            strategy,
            request.config,
            symbol=symbol,
            source_path=source_path,
        )
        result.benchmark_curve = self._benchmark(visible, request.config)
        benchmark_final = float(result.benchmark_curve.iloc[-1]["equity"])
        benchmark_return = benchmark_final / request.config.initial_cash - 1.0
        result.metrics["benchmark_final_equity"] = benchmark_final
        result.metrics["benchmark_cumulative_return"] = benchmark_return
        result.metrics["excess_return"] = (
            result.metrics["cumulative_return"] - benchmark_return
        )
        result.metrics["price_adjustment"] = self._adjustment_label(visible)
        result.metrics["dividend_included"] = False
        result.price_figure = self._chart_builder.build_price(result)
        result.equity_figure = self._chart_builder.build_equity(result)
        result.drawdown_figure = self._chart_builder.build_drawdown(result)
        return result

    def _resolve_source(
        self,
        csv_path: str | Path | None,
        symbol: str | None,
    ) -> Path:
        if csv_path is not None and str(csv_path).strip():
            return Path(csv_path)
        if symbol is None:
            raise BacktestValidationError("请输入证券代码，或上传一个CSV文件。")
        return self._csv_repository.find_latest(symbol)

    @staticmethod
    def _prepare_data(raw: pd.DataFrame) -> pd.DataFrame:
        data = raw.copy()
        data.columns = [str(column).strip().lower() for column in data.columns]
        required = {"trade_date", "open", "high", "low", "close", "volume"}
        missing = required.difference(data.columns)
        if missing:
            raise DataQualityError("CSV缺少必要字段：" + ", ".join(sorted(missing)))
        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
        for column in ("open", "high", "low", "close", "pre_close", "volume", "amount"):
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors="coerce")
        if "pre_close" not in data.columns:
            data["pre_close"] = data["close"].shift(1)
        data = data.dropna(subset=["trade_date", "open", "high", "low", "close", "volume"])
        data = data.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
        invalid = (
            (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (data["volume"] < 0)
            | (data["high"] < data[["open", "low", "close"]].max(axis=1))
            | (data["low"] > data[["open", "high", "close"]].min(axis=1))
        )
        if invalid.any():
            raise DataQualityError("CSV中存在不符合OHLC约束的行情。")
        if data.empty:
            raise DataQualityError("CSV中没有有效行情数据。")
        return data.reset_index(drop=True)

    def _resolve_symbol(
        self,
        data: pd.DataFrame,
        requested_symbol: str | None,
    ) -> tuple[str, pd.DataFrame]:
        symbols = self._extract_symbols(data)
        if requested_symbol is None:
            if symbols is None:
                raise BacktestValidationError("CSV不含证券代码，请输入证券代码。")
            unique = sorted(symbols.dropna().unique().tolist())
            if len(unique) != 1:
                raise BacktestValidationError("CSV包含多个证券，请输入一个证券代码。")
            requested_symbol = unique[0]
        if symbols is not None:
            selected = data.loc[symbols == requested_symbol].copy()
            if selected.empty:
                raise DataQualityError(f"CSV中未找到代码 {requested_symbol}。")
            data = selected
        return requested_symbol, data.reset_index(drop=True)

    @staticmethod
    def _extract_symbols(data: pd.DataFrame) -> pd.Series | None:
        if "symbol" in data.columns:
            return (
                data["symbol"].astype("string").str.strip().str.extract(r"(\d{6})", expand=False)
            )
        if "instrument_id" in data.columns:
            return data["instrument_id"].astype("string").str.extract(r"(\d{6})", expand=False)
        return None

    @staticmethod
    def _filter_dates(
        data: pd.DataFrame,
        start_value: str | date | datetime | None,
        end_value: str | date | datetime | None,
    ) -> pd.DataFrame:
        start = parse_date(start_value, "开始日期") if start_value and str(start_value).strip() else None
        end = parse_date(end_value, "结束日期") if end_value and str(end_value).strip() else None
        if start is not None and end is not None:
            validate_date_range(start, end)
        result = data
        if start is not None:
            result = result.loc[result["trade_date"].dt.date >= start]
        if end is not None:
            result = result.loc[result["trade_date"].dt.date <= end]
        return result.copy()

    def _benchmark(self, data: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
        full_config = replace(config, position_mode=PositionSizingMode.FULL)
        cash = float(config.initial_cash)
        quantity = 0
        bought = False
        rows: list[dict[str, float | pd.Timestamp]] = []
        for _, row in data.iterrows():
            if not bought and BacktestEngine.can_buy(row, full_config):
                base_price = float(row["open"])
                price = base_price * (1.0 + full_config.buy_slippage)
                quantity = self._position_sizing.calculate_quantity(
                    cash=cash,
                    equity=cash,
                    execution_price=price,
                    atr=None,
                    config=full_config,
                    initial_atr_multiple=None,
                )
                if quantity > 0:
                    amount = quantity * price
                    commission = max(
                        amount * full_config.commission_rate,
                        full_config.minimum_commission,
                    ) if amount > 0 else 0.0
                    cash -= amount + commission
                    bought = True
            equity = cash + quantity * float(row["close"])
            rows.append({"trade_date": row["trade_date"], "equity": equity})
        return pd.DataFrame(rows)

    @staticmethod
    def _adjustment_label(data: pd.DataFrame) -> str:
        if "adjust" not in data.columns:
            return "未知（严格使用CSV价格）"
        values = data["adjust"].dropna().astype(str).str.strip().unique().tolist()
        return values[0] if len(values) == 1 else "混合/未知"

    @staticmethod
    def _optional_symbol(value: str) -> str | None:
        text = str(value or "").strip()
        return normalize_symbol(text) if text else None
