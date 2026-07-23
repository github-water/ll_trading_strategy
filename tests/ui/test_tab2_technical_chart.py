from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from common.config import Settings
from common.exceptions import DataQualityError
from common.models import TechnicalAnalysisResult
from ui.app_builder import build_app
from ui.tabs.tab2_technical_chart import create_technical_chart_handler


class FakeMarketDataService:
    def fetch_and_save(self, **kwargs):
        raise AssertionError("not used")


class FakeTechnicalAnalysisService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    def analyze(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


def make_result(tmp_path):
    figure = go.Figure()
    return TechnicalAnalysisResult(
        data=pd.DataFrame({"trade_date": pd.to_datetime(["2024-01-02"])}),
        figure=figure,
        symbol="510300",
        source_path=tmp_path / "510300.csv",
        first_date="2024-01-02",
        last_date="2024-12-31",
        row_count=250,
    )


def test_handler_returns_figure_and_status(tmp_path):
    service = FakeTechnicalAnalysisService(result=make_result(tmp_path))
    handler = create_technical_chart_handler(service)

    figure, status = handler(
        "510300",
        None,
        "2024-01-01",
        "2024-12-31",
        250,
        12,
        26,
        9,
        20,
        2.0,
        14,
    )

    assert figure is service.result.figure
    assert "生成成功" in status
    assert "510300" in status
    assert service.requests[0].max_rows == 250
    assert service.requests[0].boll_std == 2.0


def test_handler_formats_domain_errors_without_raising():
    service = FakeTechnicalAnalysisService(
        error=DataQualityError("CSV 缺少必要字段")
    )
    handler = create_technical_chart_handler(service)

    figure, status = handler(
        "510300", None, "", "", 250, 12, 26, 9, 20, 2.0, 14
    )

    assert figure is None
    assert "生成失败" in status
    assert "CSV 缺少必要字段" in status


def test_app_contains_tab2_technical_chart_label():
    app = build_app(
        FakeMarketDataService(),
        Settings(),
        technical_analysis_service=FakeTechnicalAnalysisService(),
    )

    config_text = str(app.get_config_file())
    assert "数据获取" in config_text
    assert "技术图表" in config_text
