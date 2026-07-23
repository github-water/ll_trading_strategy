from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd


class AssetType(str, Enum):
    ETF = "etf"
    STOCK = "stock"


class AdjustType(str, Enum):
    RAW = "raw"
    QFQ = "qfq"
    HFQ = "hfq"


@dataclass(frozen=True)
class DataFetchCommand:
    symbol: str
    asset_type: AssetType
    start_date: date
    end_date: date
    adjust: AdjustType
    fqt: int


@dataclass(frozen=True)
class MarketDataFrame:
    data: pd.DataFrame
    instrument_name: str
    source_version: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FetchResult:
    data: pd.DataFrame
    csv_path: Path
    symbol: str
    instrument_name: str
    exchange: str
    resolved_asset_type: AssetType
    adjust: AdjustType
    source_version: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataUpdateResult:
    data: pd.DataFrame
    csv_path: Path
    symbol: str
    instrument_name: str
    exchange: str
    resolved_asset_type: AssetType
    adjust: AdjustType
    source_version: str
    previous_last_date: str
    latest_date: str
    added_rows: int
    updated: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TechnicalAnalysisRequest:
    symbol: str = ""
    csv_path: str | Path | None = None
    start_date: str | date | datetime | None = None
    end_date: str | date | datetime | None = None
    max_rows: int = 250
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    boll_period: int = 20
    boll_std: float = 2.0
    rsi_period: int = 14


@dataclass(frozen=True)
class TechnicalAnalysisResult:
    data: pd.DataFrame
    figure: Any
    symbol: str
    source_path: Path
    first_date: str
    last_date: str
    row_count: int
