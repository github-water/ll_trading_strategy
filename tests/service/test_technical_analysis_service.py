from pathlib import Path

import pandas as pd
import pytest

from common.exceptions import DataQualityError, InputValidationError
from common.models import TechnicalAnalysisRequest
from service.technical_analysis_service import TechnicalAnalysisService
from service.technical_indicator_service import TechnicalIndicatorService


class FakeRepository:
    def __init__(self, frames: dict[str, pd.DataFrame], latest: Path | None = None):
        self.frames = frames
        self.latest = latest
        self.read_calls = []
        self.find_calls = []

    def read(self, path):
        key = str(path)
        self.read_calls.append(key)
        return self.frames[key].copy()

    def find_latest(self, symbol):
        self.find_calls.append(symbol)
        if self.latest is None:
            raise AssertionError("find_latest should not be called")
        return self.latest


class FakeChartBuilder:
    def __init__(self):
        self.calls = []

    def build(self, data, *, title):
        self.calls.append((data.copy(), title))
        return {"title": title, "rows": len(data)}


def daily_frame(rows=320, symbol="510300"):
    dates = pd.bdate_range("2023-01-02", periods=rows)
    close = pd.Series([3.0 + i * 0.005 + (i % 7) * 0.002 for i in range(rows)])
    return pd.DataFrame(
        {
            "instrument_id": [f"{symbol}.SSE"] * rows,
            "symbol": [symbol] * rows,
            "trade_date": dates.strftime("%Y-%m-%d"),
            "open": close - 0.01,
            "high": close + 0.03,
            "low": close - 0.04,
            "close": close,
            "volume": [1_000_000 + i * 1000 for i in range(rows)],
        }
    )


def build_service(repo):
    chart_builder = FakeChartBuilder()
    service = TechnicalAnalysisService(
        repository=repo,
        indicators=TechnicalIndicatorService(),
        chart_builder=chart_builder,
    )
    return service, chart_builder


def test_uploaded_csv_has_priority_and_result_is_limited(tmp_path):
    upload = tmp_path / "uploaded.csv"
    repo = FakeRepository({str(upload): daily_frame()})
    service, builder = build_service(repo)

    result = service.analyze(
        TechnicalAnalysisRequest(
            symbol="510300",
            csv_path=upload,
            max_rows=120,
        )
    )

    assert repo.find_calls == []
    assert repo.read_calls == [str(upload)]
    assert len(result.data) == 120
    assert result.symbol == "510300"
    assert result.source_path == upload
    assert result.data["trade_date"].is_monotonic_increasing
    assert {"macd", "boll_upper", "rsi"}.issubset(result.data.columns)
    assert builder.calls[0][1] == "510300 技术图表"


def test_code_lookup_uses_latest_repository_csv(tmp_path):
    latest = tmp_path / "510300_latest.csv"
    repo = FakeRepository({str(latest): daily_frame()}, latest=latest)
    service, _ = build_service(repo)

    result = service.analyze(TechnicalAnalysisRequest(symbol="510300"))

    assert repo.find_calls == ["510300"]
    assert result.source_path == latest


def test_blank_symbol_is_inferred_when_csv_contains_one_symbol(tmp_path):
    upload = tmp_path / "single.csv"
    repo = FakeRepository({str(upload): daily_frame(symbol="600519")})
    service, _ = build_service(repo)

    result = service.analyze(
        TechnicalAnalysisRequest(symbol="", csv_path=upload, max_rows=100)
    )

    assert result.symbol == "600519"


def test_service_filters_symbol_date_range_then_limits_rows(tmp_path):
    upload = tmp_path / "multi.csv"
    mixed = pd.concat(
        [daily_frame(rows=320, symbol="510300"), daily_frame(rows=320, symbol="600519")],
        ignore_index=True,
    )
    repo = FakeRepository({str(upload): mixed})
    service, _ = build_service(repo)

    result = service.analyze(
        TechnicalAnalysisRequest(
            symbol="510300",
            csv_path=upload,
            start_date="2023-08-01",
            end_date="2023-12-29",
            max_rows=50,
        )
    )

    assert len(result.data) == 50
    assert result.data["symbol"].unique().tolist() == ["510300"]
    assert result.data["trade_date"].min() >= pd.Timestamp("2023-08-01")
    assert result.data["trade_date"].max() <= pd.Timestamp("2023-12-29")


def test_service_rejects_missing_required_columns(tmp_path):
    upload = tmp_path / "bad.csv"
    repo = FakeRepository({str(upload): pd.DataFrame({"trade_date": ["2024-01-01"]})})
    service, _ = build_service(repo)

    with pytest.raises(DataQualityError, match="缺少必要字段"):
        service.analyze(TechnicalAnalysisRequest(csv_path=upload))


def test_service_rejects_blank_symbol_without_upload():
    service, _ = build_service(FakeRepository({}))

    with pytest.raises(InputValidationError, match="请输入证券代码"):
        service.analyze(TechnicalAnalysisRequest())


def test_service_rejects_invalid_max_rows(tmp_path):
    upload = tmp_path / "data.csv"
    service, _ = build_service(FakeRepository({str(upload): daily_frame()}))

    with pytest.raises(InputValidationError, match="显示条数"):
        service.analyze(
            TechnicalAnalysisRequest(symbol="510300", csv_path=upload, max_rows=10)
        )
