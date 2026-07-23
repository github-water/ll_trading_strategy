from __future__ import annotations

import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Callable

import pandas as pd

from common.config import Settings
from common.constants import OUTPUT_COLUMNS, SOURCE_NAME
from common.exceptions import DataFetchError, DataQualityError
from common.models import AdjustType, DataFetchCommand, MarketDataFrame
from common.validators import infer_asset_type, infer_exchange

_SOURCE_COLUMN_ALIASES = {
    "名称": "instrument_name",
    "股票名称": "instrument_name",
    "代码": "source_symbol",
    "股票代码": "source_symbol",
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "source_volume_lots",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover_rate",
}
_REQUIRED_COLUMNS = {
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "source_volume_lots",
    "amount",
}


class EfinanceMarketDataGateway:
    def __init__(
        self,
        *,
        settings: Settings,
        fetcher: Callable[..., pd.DataFrame] | None = None,
        version_getter: Callable[[], str] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._fetcher = fetcher
        self._version_getter = version_getter or self._get_efinance_version
        self._sleep = sleep_fn

    def fetch_daily(self, command: DataFetchCommand) -> MarketDataFrame:
        raw = self._fetch_with_retry(command)
        if raw.empty:
            raise DataFetchError(
                f"未取得代码 {command.symbol} 的行情。"
                "请检查代码、日期范围、网络或上游限流。"
            )
        return self._standardize(raw, command, self._version_getter())

    def _resolve_fetcher(self) -> Callable[..., pd.DataFrame]:
        if self._fetcher is not None:
            return self._fetcher
        try:
            import efinance as ef
        except ImportError as exc:
            raise DataFetchError(
                "未安装 efinance。请执行：pip install -e ."
            ) from exc
        return ef.stock.get_quote_history

    def _fetch_with_retry(self, command: DataFetchCommand) -> pd.DataFrame:
        fetcher = self._resolve_fetcher()
        last_error: Exception | None = None
        for attempt in range(1, self._settings.fetch_attempts + 1):
            try:
                result = fetcher(
                    command.symbol,
                    beg=command.start_date.strftime("%Y%m%d"),
                    end=command.end_date.strftime("%Y%m%d"),
                    klt=101,
                    fqt=command.fqt,
                    suppress_error=True,
                )
                return pd.DataFrame() if result is None else pd.DataFrame(result)
            except Exception as exc:
                last_error = exc
                if attempt < self._settings.fetch_attempts:
                    self._sleep(self._settings.retry_base_delay_seconds * attempt)
        raise DataFetchError(
            f"行情接口连续失败 {self._settings.fetch_attempts} 次：{last_error}"
        ) from last_error

    @staticmethod
    def _get_efinance_version() -> str:
        try:
            return version("efinance")
        except PackageNotFoundError:
            return "unknown"

    def _standardize(
        self,
        raw: pd.DataFrame,
        command: DataFetchCommand,
        source_version: str,
    ) -> MarketDataFrame:
        rename_map = {
            source: target
            for source, target in _SOURCE_COLUMN_ALIASES.items()
            if source in raw.columns
        }
        data = raw.rename(columns=rename_map).copy()
        missing = _REQUIRED_COLUMNS.difference(data.columns)
        if missing:
            raise DataQualityError(
                "efinance 返回结果缺少必要字段：" + ", ".join(sorted(missing))
            )

        warnings: list[str] = []
        inferred_type = infer_asset_type(command.symbol)
        if inferred_type is not command.asset_type:
            warnings.append(
                f"代码规则推断为 {inferred_type.value.upper()}，但按用户选择保存为 "
                f"{command.asset_type.value.upper()}。"
            )

        if "instrument_name" in data.columns and data["instrument_name"].notna().any():
            instrument_name = str(data["instrument_name"].dropna().iloc[0])
        else:
            instrument_name = command.symbol

        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "source_volume_lots",
            "amount",
            "amplitude",
            "pct_change",
            "change",
            "turnover_rate",
        ]
        for column in numeric_columns:
            if column not in data.columns:
                data[column] = pd.NA
            data[column] = pd.to_numeric(data[column], errors="coerce")

        original_rows = len(data)
        data = data.dropna(subset=["trade_date", "open", "high", "low", "close"])
        removed_rows = original_rows - len(data)
        if removed_rows:
            warnings.append(f"删除了 {removed_rows} 行缺少日期或 OHLC 的数据。")

        data = data.sort_values("trade_date")
        duplicate_count = int(data.duplicated(subset=["trade_date"]).sum())
        if duplicate_count:
            data = data.drop_duplicates(subset=["trade_date"], keep="last")
            warnings.append(f"删除了 {duplicate_count} 条重复交易日记录。")
        if data.empty:
            raise DataQualityError("清洗后没有可用行情数据。")

        invalid_price = (
            (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (data["high"] < data[["open", "low", "close"]].max(axis=1))
            | (data["low"] > data[["open", "high", "close"]].min(axis=1))
        )
        if invalid_price.any():
            bad_dates = (
                data.loc[invalid_price, "trade_date"]
                .dt.strftime("%Y-%m-%d")
                .head(5)
                .tolist()
            )
            raise DataQualityError(
                "OHLC 约束校验失败，示例日期：" + ", ".join(bad_dates)
            )
        if (data["source_volume_lots"].dropna() < 0).any():
            raise DataQualityError("成交量存在负值。")
        if (data["amount"].dropna() < 0).any():
            raise DataQualityError("成交额存在负值。")

        data["volume"] = data["source_volume_lots"] * self._settings.lot_size
        shifted_close = data["close"].shift(1)
        pre_close_from_change = data["close"] - data["change"]
        data["pre_close"] = pre_close_from_change.where(
            pre_close_from_change.notna() & (pre_close_from_change > 0),
            shifted_close,
        )
        data["vwap"] = data["amount"].div(data["volume"].where(data["volume"] > 0))

        if command.adjust is not AdjustType.RAW:
            warnings.append(
                "OHLC 为复权价格，但 amount/volume 仍代表真实成交口径；"
                "因此 vwap 不应与复权 OHLC 直接比较。"
            )

        for column in ("amplitude", "pct_change", "turnover_rate"):
            data[column] = data[column] / 100.0

        exchange = infer_exchange(command.symbol)
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        data.insert(0, "instrument_id", f"{command.symbol}.{exchange}")
        data.insert(1, "symbol", command.symbol)
        data.insert(2, "exchange", exchange)
        data.insert(3, "asset_type", command.asset_type.value.upper())
        data["trade_date"] = data["trade_date"].dt.strftime("%Y-%m-%d")
        data["adjust"] = command.adjust.value
        data["source"] = SOURCE_NAME
        data["source_version"] = source_version
        data["fetched_at"] = fetched_at
        data = data.reindex(columns=OUTPUT_COLUMNS)

        for column in ("open", "high", "low", "close", "pre_close", "vwap", "change"):
            data[column] = pd.to_numeric(data[column], errors="coerce").round(6)
        for column in ("amplitude", "pct_change", "turnover_rate"):
            data[column] = pd.to_numeric(data[column], errors="coerce").round(8)
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce").round(4)
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce").round().astype("Int64")
        data["source_volume_lots"] = (
            pd.to_numeric(data["source_volume_lots"], errors="coerce")
            .round()
            .astype("Int64")
        )
        return MarketDataFrame(
            data=data,
            instrument_name=instrument_name,
            source_version=source_version,
            warnings=tuple(warnings),
        )
