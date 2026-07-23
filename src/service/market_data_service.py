from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from common.exceptions import DataQualityError
from common.models import (
    AdjustType,
    AssetType,
    DataFetchCommand,
    DataUpdateResult,
    FetchResult,
)
from common.validators import (
    infer_exchange,
    normalize_symbol,
    parse_date,
    resolve_adjust,
    resolve_asset_type,
    validate_date_range,
)
from service.ports import CsvRepository, MarketDataGateway


class MarketDataService:
    def __init__(
        self,
        *,
        gateway: MarketDataGateway,
        repository: CsvRepository,
    ) -> None:
        self._gateway = gateway
        self._repository = repository

    def fetch_and_save(
        self,
        *,
        symbol_input: str,
        asset_type_input: str,
        start_date_input: str | date | datetime,
        end_date_input: str | date | datetime,
        adjust_input: str,
    ) -> FetchResult:
        symbol = normalize_symbol(symbol_input)
        asset_type = resolve_asset_type(asset_type_input, symbol)
        adjust, fqt = resolve_adjust(adjust_input)
        start_date = parse_date(start_date_input, "开始日期")
        end_date = parse_date(end_date_input, "结束日期")
        validate_date_range(start_date, end_date)

        command = DataFetchCommand(
            symbol=symbol,
            asset_type=asset_type,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            fqt=fqt,
        )
        market_data = self._gateway.fetch_daily(command)

        dates = pd.to_datetime(market_data.data["trade_date"], errors="coerce")
        within_range = (
            dates.notna()
            & (dates.dt.date >= start_date)
            & (dates.dt.date <= end_date)
        )
        data = market_data.data.loc[within_range].reset_index(drop=True)
        if data.empty:
            raise DataQualityError("数据源有返回，但指定日期范围内没有有效交易日。")

        exchange = infer_exchange(symbol)
        csv_path = self._repository.save(data, command, exchange)
        return FetchResult(
            data=data,
            csv_path=csv_path,
            symbol=symbol,
            instrument_name=market_data.instrument_name,
            exchange=exchange,
            resolved_asset_type=asset_type,
            adjust=adjust,
            source_version=market_data.source_version,
            warnings=market_data.warnings,
        )

    def update_latest(
        self,
        *,
        symbol_input: str,
        end_date_input: str | date | datetime,
    ) -> DataUpdateResult:
        symbol = normalize_symbol(symbol_input)
        end_date = parse_date(end_date_input, "更新截止日期")
        csv_path = self._repository.find_latest(symbol)
        existing = self._repository.read(csv_path)
        if existing.empty:
            raise DataQualityError("本地 CSV 没有可更新的数据。")

        self._validate_local_symbol(existing, symbol)
        asset_type = self._resolve_local_asset_type(existing)
        adjust = self._resolve_local_adjust(existing)
        fqt = {
            "raw": 0,
            "qfq": 1,
            "hfq": 2,
        }[adjust.value]

        if "trade_date" not in existing.columns:
            raise DataQualityError("本地 CSV 缺少 trade_date 字段，无法更新。")
        existing_dates = pd.to_datetime(
            existing["trade_date"],
            errors="coerce",
        )
        if existing_dates.isna().any():
            raise DataQualityError("本地 CSV 的 trade_date 存在空值或无效日期。")
        previous_last_date = existing_dates.max().date()
        validate_date_range(previous_last_date, end_date)

        command = DataFetchCommand(
            symbol=symbol,
            asset_type=asset_type,
            start_date=previous_last_date,
            end_date=end_date,
            adjust=adjust,
            fqt=fqt,
        )
        market_data = self._gateway.fetch_daily(command)
        incoming_dates = pd.to_datetime(
            market_data.data.get("trade_date"),
            errors="coerce",
        )
        within_range = (
            incoming_dates.notna()
            & (incoming_dates.dt.date >= previous_last_date)
            & (incoming_dates.dt.date <= end_date)
        )
        incoming = market_data.data.loc[within_range].copy()
        if incoming.empty:
            raise DataQualityError("数据源未返回可用于增量更新的有效交易日。")

        existing = existing.copy()
        existing["trade_date"] = existing_dates.dt.strftime("%Y-%m-%d")
        incoming["trade_date"] = pd.to_datetime(
            incoming["trade_date"],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")

        existing_date_values = set(existing["trade_date"].dropna())
        incoming_date_values = set(incoming["trade_date"].dropna())
        added_rows = len(incoming_date_values - existing_date_values)

        if added_rows:
            merged_columns = list(
                dict.fromkeys([*existing.columns.tolist(), *incoming.columns.tolist()])
            )
            merged = pd.concat(
                [
                    existing.reindex(columns=merged_columns),
                    incoming.reindex(columns=merged_columns),
                ],
                ignore_index=True,
            )
            merged["trade_date"] = pd.to_datetime(
                merged["trade_date"],
                errors="coerce",
            )
            merged = (
                merged.dropna(subset=["trade_date"])
                .sort_values("trade_date")
                .drop_duplicates(subset=["trade_date"], keep="last")
                .reset_index(drop=True)
            )
            merged["trade_date"] = merged["trade_date"].dt.strftime("%Y-%m-%d")
            self._repository.replace(csv_path, merged)
            result_data = merged
        else:
            result_data = (
                existing.sort_values("trade_date")
                .drop_duplicates(subset=["trade_date"], keep="last")
                .reset_index(drop=True)
            )

        exchange = self._resolve_local_exchange(existing, symbol)
        latest_date = str(result_data["trade_date"].iloc[-1])
        warnings = list(market_data.warnings)
        if not added_rows:
            warnings.append("本地 CSV 已包含数据源返回的最新交易日。")
        return DataUpdateResult(
            data=result_data,
            csv_path=csv_path,
            symbol=symbol,
            instrument_name=market_data.instrument_name,
            exchange=exchange,
            resolved_asset_type=asset_type,
            adjust=adjust,
            source_version=market_data.source_version,
            previous_last_date=previous_last_date.isoformat(),
            latest_date=latest_date,
            added_rows=added_rows,
            updated=bool(added_rows),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _validate_local_symbol(data: pd.DataFrame, symbol: str) -> None:
        if "symbol" not in data.columns:
            return
        symbols = (
            data["symbol"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.zfill(6)
            .unique()
            .tolist()
        )
        if symbols and symbols != [symbol]:
            raise DataQualityError(
                f"本地 CSV 的证券代码与输入代码不一致：{', '.join(symbols)}。"
            )

    @staticmethod
    def _resolve_local_asset_type(data: pd.DataFrame) -> AssetType:
        if "asset_type" not in data.columns:
            raise DataQualityError("本地 CSV 缺少 asset_type 字段，无法安全更新。")
        values = (
            data["asset_type"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.lower()
            .unique()
            .tolist()
        )
        if len(values) != 1:
            raise DataQualityError("本地 CSV 必须且只能包含一种 asset_type。")
        try:
            return AssetType(values[0])
        except ValueError as exc:
            raise DataQualityError(
                f"本地 CSV 的 asset_type 无效：{values[0]}。"
            ) from exc

    @staticmethod
    def _resolve_local_adjust(data: pd.DataFrame) -> AdjustType:
        if "adjust" not in data.columns:
            raise DataQualityError("本地 CSV 缺少 adjust 字段，无法安全更新。")
        values = (
            data["adjust"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.lower()
            .unique()
            .tolist()
        )
        if len(values) != 1:
            raise DataQualityError("本地 CSV 必须且只能包含一种 adjust。")
        try:
            return AdjustType(values[0])
        except ValueError as exc:
            raise DataQualityError(
                f"本地 CSV 的 adjust 无效：{values[0]}。"
            ) from exc

    @staticmethod
    def _resolve_local_exchange(data: pd.DataFrame, symbol: str) -> str:
        if "exchange" in data.columns:
            values = (
                data["exchange"]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
            if len(values) == 1:
                return values[0]
        return infer_exchange(symbol)
