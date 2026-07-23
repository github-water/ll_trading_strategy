from pathlib import Path

import pandas as pd
import pytest

from common.exceptions import DataQualityError
from common.models import MarketDataFrame
from service.market_data_service import MarketDataService


class FakeGateway:
    def __init__(self, frame: MarketDataFrame):
        self.frame = frame
        self.commands = []

    def fetch_daily(self, command):
        self.commands.append(command)
        return self.frame


class FakeRepository:
    def __init__(self, path: Path):
        self.path = path
        self.saved = []

    def save(self, data, command, exchange):
        self.saved.append((data.copy(), command, exchange))
        return self.path


def make_frame():
    return MarketDataFrame(
        data=pd.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [1.0, 1.1, 1.2],
            }
        ),
        instrument_name="沪深300ETF",
        source_version="test-version",
        warnings=("provider warning",),
    )


def test_service_validates_orchestrates_filters_and_saves(tmp_path):
    gateway = FakeGateway(make_frame())
    repository = FakeRepository(tmp_path / "result.csv")
    service = MarketDataService(gateway=gateway, repository=repository)

    result = service.fetch_and_save(
        symbol_input="510300.SH",
        asset_type_input="自动识别",
        start_date_input="2024-01-02",
        end_date_input="2024-01-03",
        adjust_input="不复权",
    )

    command = gateway.commands[0]
    assert command.symbol == "510300"
    assert command.asset_type.value == "etf"
    assert command.adjust.value == "raw"
    assert command.fqt == 0
    assert result.exchange == "SSE"
    assert result.instrument_name == "沪深300ETF"
    assert result.source_version == "test-version"
    assert result.warnings == ("provider warning",)
    assert result.data["trade_date"].tolist() == ["2024-01-02", "2024-01-03"]
    assert repository.saved[0][2] == "SSE"


def test_service_rejects_empty_data_after_date_filter(tmp_path):
    gateway = FakeGateway(make_frame())
    repository = FakeRepository(tmp_path / "result.csv")
    service = MarketDataService(gateway=gateway, repository=repository)

    with pytest.raises(DataQualityError, match="指定日期范围"):
        service.fetch_and_save(
            symbol_input="510300",
            asset_type_input="ETF",
            start_date_input="2024-02-01",
            end_date_input="2024-02-02",
            adjust_input="不复权",
        )

    assert repository.saved == []


class UpdateRepository:
    def __init__(self, path: Path, existing: pd.DataFrame):
        self.path = path
        self.existing = existing.copy()
        self.replaced = []

    def find_latest(self, symbol):
        return self.path

    def read(self, path):
        return self.existing.copy()

    def replace(self, path, data):
        self.replaced.append((Path(path), data.copy()))
        self.existing = data.copy()
        return Path(path)


def make_update_existing():
    return pd.DataFrame(
        {
            "symbol": ["510300", "510300"],
            "exchange": ["SSE", "SSE"],
            "asset_type": ["etf", "etf"],
            "adjust": ["raw", "raw"],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "close": [3.0, 3.1],
        }
    )


def test_update_latest_merges_new_days_and_prefers_incoming_overlap(tmp_path):
    incoming = MarketDataFrame(
        data=pd.DataFrame(
            {
                "symbol": ["510300", "510300"],
                "exchange": ["SSE", "SSE"],
                "asset_type": ["etf", "etf"],
                "adjust": ["raw", "raw"],
                "trade_date": ["2024-01-03", "2024-01-04"],
                "close": [3.15, 3.2],
            }
        ),
        instrument_name="沪深300ETF",
        source_version="test-version",
    )
    repository = UpdateRepository(tmp_path / "510300.csv", make_update_existing())
    gateway = FakeGateway(incoming)

    result = MarketDataService(gateway=gateway, repository=repository).update_latest(
        symbol_input="510300",
        end_date_input="2024-01-04",
    )

    assert gateway.commands[0].start_date.isoformat() == "2024-01-03"
    assert gateway.commands[0].end_date.isoformat() == "2024-01-04"
    assert result.added_rows == 1
    assert result.updated is True
    assert result.latest_date == "2024-01-04"
    assert repository.replaced[0][1]["trade_date"].tolist() == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]
    assert repository.replaced[0][1].loc[1, "close"] == pytest.approx(3.15)


def test_update_latest_does_not_rewrite_when_no_new_trade_day(tmp_path):
    incoming = MarketDataFrame(
        data=pd.DataFrame(
            {
                "symbol": ["510300"],
                "exchange": ["SSE"],
                "asset_type": ["etf"],
                "adjust": ["raw"],
                "trade_date": ["2024-01-03"],
                "close": [3.15],
            }
        ),
        instrument_name="沪深300ETF",
        source_version="test-version",
    )
    repository = UpdateRepository(tmp_path / "510300.csv", make_update_existing())

    result = MarketDataService(
        gateway=FakeGateway(incoming),
        repository=repository,
    ).update_latest(
        symbol_input="510300",
        end_date_input="2024-01-03",
    )

    assert result.added_rows == 0
    assert result.updated is False
    assert repository.replaced == []
    assert "已包含" in result.warnings[-1]
