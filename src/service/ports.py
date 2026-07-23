from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from common.models import DataFetchCommand, MarketDataFrame
from common.strategy_models import TradingStrategy


class MarketDataGateway(Protocol):
    def fetch_daily(self, command: DataFetchCommand) -> MarketDataFrame:
        """Fetch and normalize daily market data for one instrument."""


class CsvRepository(Protocol):
    def save(
        self,
        data: pd.DataFrame,
        command: DataFetchCommand,
        exchange: str,
    ) -> Path:
        """Persist a standardized daily-bar frame as a CSV file."""

    def find_latest(self, symbol: str) -> Path:
        """Return the newest downloaded CSV for a six-digit symbol."""

    def read(self, path: str | Path) -> pd.DataFrame:
        """Read a CSV artifact into a pandas DataFrame."""

    def replace(self, path: str | Path, data: pd.DataFrame) -> Path:
        """Atomically replace an existing CSV artifact."""


class TechnicalChartBuilder(Protocol):
    def build(self, data: pd.DataFrame, *, title: str):
        """Build an interactive technical-analysis figure."""


class StrategyRepository(Protocol):
    def list_all(self) -> list[TradingStrategy]:
        """Return all persisted strategies."""

    def get(self, strategy_id: str) -> TradingStrategy:
        """Load one strategy by immutable ID."""

    def save(self, strategy: TradingStrategy) -> Path:
        """Atomically persist one strategy."""

    def delete(self, strategy_id: str) -> None:
        """Delete one strategy artifact."""

    def name_exists(self, name: str, *, excluding_id: str | None = None) -> bool:
        """Check normalized global name uniqueness."""

    def path_for(self, strategy_id: str) -> Path:
        """Return the JSON path for one strategy."""


class BacktestChartBuilder(Protocol):
    def build_price(self, result):
        """Build the price chart with buy/sell markers and active stop."""

    def build_equity(self, result):
        """Build strategy and benchmark equity curves."""

    def build_drawdown(self, result):
        """Build the strategy drawdown curve."""
