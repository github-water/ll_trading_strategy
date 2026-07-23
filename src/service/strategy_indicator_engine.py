from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import numpy as np
import pandas as pd

from common.exceptions import BacktestValidationError
from common.strategy_models import Operand, TradingStrategy


class StrategyIndicatorEngine:
    """Materialize every indicator referenced by a strategy into a DataFrame."""

    def prepare(
        self,
        data: pd.DataFrame,
        strategy: TradingStrategy,
        *,
        extra_atr_periods: Iterable[int] = (),
    ) -> pd.DataFrame:
        result = data.copy()
        self._ensure_base_fields(result)
        operands = list(self._strategy_operands(strategy))
        for operand in operands:
            if operand.kind == "indicator":
                column = self.column_name(operand)
                if column not in result.columns:
                    result[column] = self._calculate(result, operand)

        atr_periods = {int(period) for period in extra_atr_periods if int(period) > 0}
        for risk_name in ("initial_atr_stop", "trailing_atr_stop"):
            risk = strategy.risk_rules.get(risk_name) or {}
            if risk.get("enabled", False):
                atr_periods.add(int(risk.get("period", 14)))
        for period in atr_periods:
            operand = Operand.indicator("ATR", {"period": period})
            column = self.column_name(operand)
            if column not in result.columns:
                result[column] = self._calculate(result, operand)
        return result

    @staticmethod
    def column_name(operand: Operand) -> str:
        payload = json.dumps(
            {"name": operand.name, "params": operand.params},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
        return f"__indicator_{operand.name.lower()}_{digest}"

    @classmethod
    def atr_column(cls, period: int) -> str:
        return cls.column_name(Operand.indicator("ATR", {"period": int(period)}))

    @staticmethod
    def _strategy_operands(strategy: TradingStrategy) -> Iterable[Operand]:
        for rule_set in (strategy.entry_rule, strategy.exit_rule):
            for rule in rule_set.rules:
                yield rule.left
                yield rule.right

    @staticmethod
    def _ensure_base_fields(data: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close", "volume"}
        missing = required.difference(data.columns)
        if missing:
            raise BacktestValidationError(
                "行情数据缺少指标计算字段：" + ", ".join(sorted(missing))
            )
        for column in required.union({"pre_close", "amount"}).intersection(data.columns):
            data[column] = pd.to_numeric(data[column], errors="coerce")
        if "pre_close" not in data.columns:
            data["pre_close"] = data["close"].shift(1)
        if "pct_change" not in data.columns:
            denominator = data["pre_close"].replace(0, np.nan)
            data["pct_change"] = (data["close"] / denominator - 1.0) * 100.0

    def _calculate(self, data: pd.DataFrame, operand: Operand) -> pd.Series:
        name = operand.name
        params = operand.params
        field = str(params.get("field", "close"))
        if field not in data.columns:
            raise BacktestValidationError(f"指标 {name} 引用的字段 {field} 不存在。")
        source = pd.to_numeric(data[field], errors="coerce")

        if name == "SMA":
            period = int(params["period"])
            return source.rolling(period, min_periods=period).mean()
        if name == "EMA":
            period = int(params["period"])
            return source.ewm(span=period, adjust=False, min_periods=period).mean()
        if name in {"HHV", "LLV"}:
            period = int(params["period"])
            values = source.shift(1) if bool(params.get("exclude_current", False)) else source
            rolling = values.rolling(period, min_periods=period)
            return rolling.max() if name == "HHV" else rolling.min()
        if name == "MA_SLOPE":
            period = int(params["period"])
            lookback = int(params["lookback"])
            moving_average = source.rolling(period, min_periods=period).mean()
            return moving_average - moving_average.shift(lookback)
        if name in {"MACD_DIF", "MACD_DEA", "MACD_HIST"}:
            fast = int(params["fast"])
            slow = int(params["slow"])
            signal = int(params["signal"])
            fast_ema = source.ewm(span=fast, adjust=False, min_periods=fast).mean()
            slow_ema = source.ewm(span=slow, adjust=False, min_periods=slow).mean()
            dif = fast_ema - slow_ema
            dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
            if name == "MACD_DIF":
                return dif
            if name == "MACD_DEA":
                return dea
            return (dif - dea) * 2.0
        if name == "RSI":
            period = int(params["period"])
            delta = source.diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100.0 - 100.0 / (1.0 + rs)
            rsi = rsi.where(avg_loss != 0, 100.0)
            rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
            return rsi.clip(0, 100)
        if name.startswith("BOLL_"):
            period = int(params["period"])
            std_multiple = float(params["std"])
            middle = source.rolling(period, min_periods=period).mean()
            std = source.rolling(period, min_periods=period).std(ddof=0)
            upper = middle + std_multiple * std
            lower = middle - std_multiple * std
            if name == "BOLL_UPPER":
                return upper
            if name == "BOLL_MIDDLE":
                return middle
            if name == "BOLL_LOWER":
                return lower
            return (upper - lower) / middle.replace(0, np.nan)
        if name == "ATR":
            return self._atr(data, int(params["period"]))
        if name in {"ADX", "PLUS_DI", "MINUS_DI"}:
            adx, plus_di, minus_di = self._directional_indicators(data, int(params["period"]))
            if name == "ADX":
                return adx
            if name == "PLUS_DI":
                return plus_di
            return minus_di
        if name == "VOLUME_MA":
            period = int(params["period"])
            multiplier = float(params.get("multiplier", 1.0))
            return (
                pd.to_numeric(data["volume"], errors="coerce")
                .rolling(period, min_periods=period)
                .mean()
                * multiplier
            )
        raise BacktestValidationError(f"回测暂不支持指标 {name}。")

    @staticmethod
    def _true_range(data: pd.DataFrame) -> pd.Series:
        previous_close = pd.to_numeric(data["close"], errors="coerce").shift(1)
        high = pd.to_numeric(data["high"], errors="coerce")
        low = pd.to_numeric(data["low"], errors="coerce")
        return pd.concat(
            [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)

    def _atr(self, data: pd.DataFrame, period: int) -> pd.Series:
        return self._true_range(data).ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

    def _directional_indicators(
        self, data: pd.DataFrame, period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        high = pd.to_numeric(data["high"], errors="coerce")
        low = pd.to_numeric(data["low"], errors="coerce")
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=data.index,
            dtype=float,
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=data.index,
            dtype=float,
        )
        atr = self._atr(data, period)
        plus_smoothed = plus_dm.ewm(
            alpha=1 / period, adjust=False, min_periods=period
        ).mean()
        minus_smoothed = minus_dm.ewm(
            alpha=1 / period, adjust=False, min_periods=period
        ).mean()
        plus_di = 100.0 * plus_smoothed / atr.replace(0, np.nan)
        minus_di = 100.0 * minus_smoothed / atr.replace(0, np.nan)
        denominator = (plus_di + minus_di).replace(0, np.nan)
        dx = 100.0 * (plus_di - minus_di).abs() / denominator
        adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        return adx, plus_di, minus_di
