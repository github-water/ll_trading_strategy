from datetime import date
from pathlib import Path

import pandas as pd

from common.config import Settings
from common.exceptions import DataFetchError
from common.models import AdjustType, AssetType, DataUpdateResult, FetchResult
from ui.app_builder import build_app
from ui.tabs.tab1_data_fetch import create_data_fetch_handler, create_data_update_handler


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def fetch_and_save(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result

    def update_latest(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def make_result(tmp_path: Path, rows: int = 250) -> FetchResult:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    return FetchResult(
        data=pd.DataFrame(
            {
                "trade_date": dates.strftime("%Y-%m-%d"),
                "close": range(rows),
            }
        ),
        csv_path=tmp_path / "data.csv",
        symbol="510300",
        instrument_name="沪深300ETF",
        exchange="SSE",
        resolved_asset_type=AssetType.ETF,
        adjust=AdjustType.RAW,
        source_version="test",
        warnings=("warning",),
    )


def test_handler_returns_descending_200_row_preview_and_download(tmp_path):
    service = FakeService(result=make_result(tmp_path))
    handler = create_data_fetch_handler(service)

    preview, status, download = handler(
        "510300", "自动识别", "2024-01-01", "2024-12-31", "不复权"
    )

    assert len(preview) == 200
    assert preview.iloc[0]["trade_date"] == "2024-09-06"
    assert "获取成功" in status
    assert "沪深300ETF" in status
    assert download == str(tmp_path / "data.csv")


def test_handler_formats_domain_errors_without_raising():
    handler = create_data_fetch_handler(
        FakeService(error=DataFetchError("upstream unavailable"))
    )
    preview, status, download = handler(
        "510300", "ETF", "2024-01-01", "2024-01-31", "不复权"
    )
    assert preview.empty
    assert "获取失败" in status
    assert "upstream unavailable" in status
    assert download is None


def test_app_contains_tab1_data_fetch_label():
    app = build_app(FakeService(), Settings())
    config_text = str(app.get_config_file())
    assert "数据获取" in config_text


def test_update_handler_uses_today_and_returns_updated_csv(tmp_path):
    data = pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03"],
            "close": [3.0, 3.1],
        }
    )
    result = DataUpdateResult(
        data=data,
        csv_path=tmp_path / "510300.csv",
        symbol="510300",
        instrument_name="沪深300ETF",
        exchange="SSE",
        resolved_asset_type=AssetType.ETF,
        adjust=AdjustType.RAW,
        source_version="test",
        previous_last_date="2024-01-02",
        latest_date="2024-01-03",
        added_rows=1,
        updated=True,
    )
    service = FakeService(result=result)
    handler = create_data_update_handler(
        service, today_fn=lambda: date(2024, 1, 3)
    )

    preview, status, download = handler("510300")

    assert service.calls == [
        {
            "symbol_input": "510300",
            "end_date_input": date(2024, 1, 3),
        }
    ]
    assert preview.iloc[0]["trade_date"] == "2024-01-03"
    assert "更新成功" in status
    assert download == str(tmp_path / "510300.csv")


def test_app_registers_clean_tab_labels_and_update_action():
    app = build_app(FakeService(), Settings())
    config_text = str(app.get_config_file())

    assert "数据获取" in config_text
    assert "Tab1 数据获取" not in config_text
    assert "更新至最新" in config_text
    assert "update_daily_data" in config_text
