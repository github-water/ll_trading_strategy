import pandas as pd

from infra.charting.plotly_chart_builder import PlotlyTechnicalChartBuilder
from service.technical_indicator_service import TechnicalIndicatorService


def chart_frame(rows=400):
    close = pd.Series([3.0 + i * 0.01 + (i % 4) * 0.005 for i in range(rows)])
    source = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-01-02", periods=rows),
            "open": close - 0.01,
            "high": close + 0.03,
            "low": close - 0.04,
            "close": close,
            "volume": [1_000_000 + i * 1000 for i in range(rows)],
        }
    )
    return TechnicalIndicatorService().calculate(source)


def test_builder_creates_expected_technical_traces():
    figure = PlotlyTechnicalChartBuilder().build(
        chart_frame(), title="510300 技术图表"
    )

    names = [trace.name for trace in figure.data]
    assert names == [
        "K线",
        "MA5",
        "MA10",
        "MA20",
        "MA60",
        "MA250",
        "MA360",
        "BOLL K线",
        "BOLL上轨",
        "BOLL中轨",
        "BOLL下轨",
        "成交量",
        "MACD",
        "Signal",
        "MACD柱",
        "RSI",
    ]
    assert figure.layout.title.text == "510300 技术图表"
    assert figure.layout.xaxis.rangeslider.visible is False
    assert figure.layout.xaxis.type == "category"
    assert figure.layout.hovermode == "x unified"


def test_builder_assigns_traces_to_five_panels_and_a_share_colors():
    figure = PlotlyTechnicalChartBuilder().build(chart_frame(), title="test")

    assert all(trace.yaxis == "y" for trace in figure.data[:7])
    assert all(trace.yaxis == "y2" for trace in figure.data[7:11])
    assert figure.data[11].yaxis == "y3"
    assert all(trace.yaxis == "y4" for trace in figure.data[12:15])
    assert figure.data[15].yaxis == "y5"
    assert figure.data[0].increasing.line.color == "#ef232a"
    assert figure.data[0].decreasing.line.color == "#00a800"
    assert figure.data[7].increasing.line.color == "#ef232a"
    assert figure.data[7].decreasing.line.color == "#00a800"
    assert set(figure.data[11].marker.color) == {"#ef232a", "#00a800"}
    assert len(figure.layout.shapes) == 2


def test_builder_uses_csv_dates_as_discrete_categories():
    data = chart_frame(rows=400).tail(3).reset_index(drop=True)
    data.loc[:, "trade_date"] = pd.to_datetime(
        ["2026-01-09", "2026-01-12", "2026-01-13"]
    )

    figure = PlotlyTechnicalChartBuilder().build(data, title="test")

    expected = ("2026-01-09", "2026-01-12", "2026-01-13")
    assert tuple(figure.layout.xaxis.categoryarray) == expected
    assert tuple(figure.data[0].x) == expected
