from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from common.constants import TECHNICAL_NUMERIC_COLUMNS, TECHNICAL_REQUIRED_COLUMNS
from common.exceptions import DataQualityError, InputValidationError
from common.models import TechnicalAnalysisRequest, TechnicalAnalysisResult
from common.validators import normalize_symbol, parse_date, validate_date_range
from service.ports import CsvRepository, TechnicalChartBuilder
from service.technical_indicator_service import TechnicalIndicatorService


class TechnicalAnalysisService:
    """Load a daily-bar CSV, calculate indicators and build a chart."""

    def __init__(
        self,
        *,
        repository: CsvRepository,
        indicators: TechnicalIndicatorService,
        chart_builder: TechnicalChartBuilder,
    ) -> None:
        self._repository = repository
        self._indicators = indicators
        self._chart_builder = chart_builder

    def analyze(
        self,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisResult:
        self._validate_max_rows(request.max_rows)
        requested_symbol = self._optional_symbol(request.symbol)
        source_path = self._resolve_source_path(request.csv_path, requested_symbol)
        raw_data = self._repository.read(source_path)
        data = self._prepare_data(raw_data)
        symbol, data = self._resolve_and_filter_symbol(data, requested_symbol)
        data = self._validate_prices(data)

        calculated = self._indicators.calculate(
            data,
            macd_fast=request.macd_fast,
            macd_slow=request.macd_slow,
            macd_signal=request.macd_signal,
            boll_period=request.boll_period,
            boll_std=request.boll_std,
            rsi_period=request.rsi_period,
        )
        visible = self._filter_dates(
            calculated,
            request.start_date,
            request.end_date,
        )
        visible = visible.tail(request.max_rows).reset_index(drop=True)
        if visible.empty:
            raise DataQualityError("筛选后没有可用于绘图的数据。")

        title = f"{symbol} 技术图表"
        figure = self._chart_builder.build(visible, title=title)
        first_date = visible["trade_date"].iloc[0].strftime("%Y-%m-%d")
        last_date = visible["trade_date"].iloc[-1].strftime("%Y-%m-%d")
        return TechnicalAnalysisResult(
            data=visible,
            figure=figure,
            symbol=symbol,
            source_path=source_path,
            first_date=first_date,
            last_date=last_date,
            row_count=len(visible),
        )

    def _resolve_source_path(
        self,
        csv_path: str | Path | None,
        requested_symbol: str | None,
    ) -> Path:
        if csv_path is not None and str(csv_path).strip():
            return Path(csv_path)
        if requested_symbol is None:
            raise InputValidationError("请输入证券代码，或上传一个 CSV 文件。")
        return self._repository.find_latest(requested_symbol)

    @staticmethod
    def _prepare_data(raw_data: pd.DataFrame) -> pd.DataFrame:
        data = raw_data.copy()
        data.columns = [str(column).strip().lower() for column in data.columns]
        missing = TECHNICAL_REQUIRED_COLUMNS.difference(data.columns)
        if missing:
            raise DataQualityError(
                "CSV 缺少必要字段：" + ", ".join(sorted(missing))
            )

        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
        for column in TECHNICAL_NUMERIC_COLUMNS:
            data[column] = pd.to_numeric(data[column], errors="coerce")
        data = data.dropna(subset=["trade_date", *TECHNICAL_NUMERIC_COLUMNS])
        data = data.sort_values("trade_date")
        return data

    def _resolve_and_filter_symbol(
        self,
        data: pd.DataFrame,
        requested_symbol: str | None,
    ) -> tuple[str, pd.DataFrame]:
        symbol_series = self._extract_symbols(data)
        if requested_symbol is None:
            if symbol_series is None:
                raise InputValidationError(
                    "CSV 不含 symbol 或 instrument_id 字段，请输入证券代码。"
                )
            unique_symbols = sorted(symbol_series.dropna().unique().tolist())
            if len(unique_symbols) != 1:
                raise InputValidationError(
                    "CSV 包含多个证券，请输入一个六位证券代码。"
                )
            requested_symbol = unique_symbols[0]

        if symbol_series is not None:
            data = data.loc[symbol_series == requested_symbol].copy()
            if data.empty:
                raise DataQualityError(
                    f"CSV 中未找到代码 {requested_symbol} 的行情。"
                )
        return requested_symbol, data

    @staticmethod
    def _extract_symbols(data: pd.DataFrame) -> pd.Series | None:
        if "symbol" in data.columns:
            return (
                data["symbol"]
                .astype("string")
                .str.strip()
                .str.extract(r"(\d{6})", expand=False)
            )
        if "instrument_id" in data.columns:
            return (
                data["instrument_id"]
                .astype("string")
                .str.extract(r"(\d{6})", expand=False)
            )
        return None

    @staticmethod
    def _validate_prices(data: pd.DataFrame) -> pd.DataFrame:
        data = data.drop_duplicates(subset=["trade_date"], keep="last").copy()
        invalid = (
            (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (data["volume"] < 0)
            | (data["high"] < data[["open", "low", "close"]].max(axis=1))
            | (data["low"] > data[["open", "high", "close"]].min(axis=1))
        )
        if invalid.any():
            examples = (
                data.loc[invalid, "trade_date"]
                .dt.strftime("%Y-%m-%d")
                .head(5)
                .tolist()
            )
            raise DataQualityError(
                "CSV 行情约束校验失败，示例日期：" + ", ".join(examples)
            )
        if data.empty:
            raise DataQualityError("CSV 中没有有效行情数据。")
        return data.reset_index(drop=True)

    @staticmethod
    def _filter_dates(
        data: pd.DataFrame,
        start_value: str | date | datetime | None,
        end_value: str | date | datetime | None,
    ) -> pd.DataFrame:
        start = (
            parse_date(start_value, "开始日期")
            if start_value is not None and str(start_value).strip()
            else None
        )
        end = (
            parse_date(end_value, "结束日期")
            if end_value is not None and str(end_value).strip()
            else None
        )
        if start is not None and end is not None:
            validate_date_range(start, end)

        visible = data
        if start is not None:
            visible = visible.loc[visible["trade_date"].dt.date >= start]
        if end is not None:
            visible = visible.loc[visible["trade_date"].dt.date <= end]
        return visible.copy()

    @staticmethod
    def _optional_symbol(value: str) -> str | None:
        text = str(value or "").strip()
        return normalize_symbol(text) if text else None

    @staticmethod
    def _validate_max_rows(value: int) -> None:
        if not isinstance(value, int) or not 50 <= value <= 3000:
            raise InputValidationError("显示条数必须是50到3000之间的整数。")
