from pathlib import Path

import pandas as pd

from common.backtest_models import BacktestConfig, BacktestResult
from infra.charting.backtest_chart_builder import PlotlyBacktestChartBuilder


def result_fixture():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    data = pd.DataFrame(
        {
            "trade_date": dates,
            "open": [10, 11, 12, 11],
            "high": [11, 12, 13, 12],
            "low": [9, 10, 11, 10],
            "close": [10, 11, 12, 11],
            "active_stop": [None, 9, 10, None],
        }
    )
    equity = pd.DataFrame({"trade_date": dates, "equity": [100000, 101000, 102000, 101500]})
    benchmark = pd.DataFrame({"trade_date": dates, "equity": [100000, 102000, 104000, 103000]})
    drawdown = pd.DataFrame({"trade_date": dates, "drawdown": [0, 0, 0, -0.0049]})
    trades = pd.DataFrame(
        [
            {
                "buy_date": "2024-01-02",
                "buy_price": 11,
                "sell_date": "2024-01-04",
                "sell_price": 11,
                "exit_reason": "策略退出",
            }
        ]
    )
    return BacktestResult(
        symbol="510300",
        strategy_name="测试策略",
        source_path=Path("x.csv"),
        config=BacktestConfig(),
        data=data,
        equity_curve=equity,
        benchmark_curve=benchmark,
        drawdown_curve=drawdown,
        trades=trades,
        events=pd.DataFrame(),
        metrics={},
        open_position={},
    )


def test_price_chart_has_candles_buy_sell_and_category_axis():
    figure = PlotlyBacktestChartBuilder().build_price(result_fixture())
    names = [trace.name for trace in figure.data]
    assert "K线" in names
    assert "买入" in names
    assert "卖出" in names
    assert "ATR止损线" in names
    assert figure.layout.xaxis.type == "category"


def test_equity_chart_has_strategy_and_benchmark():
    figure = PlotlyBacktestChartBuilder().build_equity(result_fixture())
    assert [trace.name for trace in figure.data] == ["策略权益", "买入并持有基准", "初始资金"]
    assert figure.layout.xaxis.type == "category"


def test_drawdown_chart_uses_category_axis():
    figure = PlotlyBacktestChartBuilder().build_drawdown(result_fixture())
    assert figure.data[0].name == "策略回撤"
    assert figure.layout.xaxis.type == "category"
