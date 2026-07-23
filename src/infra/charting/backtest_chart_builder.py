from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from common.backtest_models import BacktestResult


class PlotlyBacktestChartBuilder:
    def build_price(self, result: BacktestResult) -> go.Figure:
        data = result.data.copy()
        dates = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
        figure = go.Figure()
        figure.add_trace(
            go.Candlestick(
                x=dates,
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                name="K线",
                increasing_line_color="#ef5350",
                decreasing_line_color="#26a69a",
            )
        )
        if "active_stop" in data.columns:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=data["active_stop"],
                    mode="lines",
                    name="ATR止损线",
                    connectgaps=False,
                    line={"dash": "dot", "width": 1.4},
                )
            )

        buy_dates: list[str] = []
        buy_prices: list[float] = []
        sell_dates: list[str] = []
        sell_prices: list[float] = []
        sell_text: list[str] = []
        if not result.trades.empty:
            for _, trade in result.trades.iterrows():
                buy_dates.append(str(trade["buy_date"]))
                buy_prices.append(float(trade["buy_price"]))
                if pd.notna(trade.get("sell_date")):
                    sell_dates.append(str(trade["sell_date"]))
                    sell_prices.append(float(trade["sell_price"]))
                    sell_text.append(str(trade.get("exit_reason") or "卖出"))
        if result.open_position:
            buy_dates.append(str(result.open_position["buy_date"]))
            buy_prices.append(float(result.open_position["buy_price"]))

        figure.add_trace(
            go.Scatter(
                x=buy_dates,
                y=buy_prices,
                mode="markers",
                name="买入",
                marker={"symbol": "triangle-up", "size": 12},
                hovertemplate="买入 %{x}<br>价格 %{y:.4f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=sell_dates,
                y=sell_prices,
                mode="markers",
                name="卖出",
                text=sell_text,
                marker={"symbol": "triangle-down", "size": 12},
                hovertemplate="卖出 %{x}<br>价格 %{y:.4f}<br>%{text}<extra></extra>",
            )
        )
        self._category_axis(figure, dates.tolist())
        figure.update_layout(
            title=f"{result.symbol} 买卖点｜{result.strategy_name}",
            height=620,
            hovermode="x unified",
            xaxis_rangeslider_visible=False,
            legend={"orientation": "h", "y": 1.04, "x": 0},
            margin={"l": 55, "r": 25, "t": 85, "b": 45},
        )
        figure.update_yaxes(title_text="价格")
        return figure

    def build_equity(self, result: BacktestResult) -> go.Figure:
        strategy = result.equity_curve
        benchmark = result.benchmark_curve
        dates = pd.to_datetime(strategy["trade_date"]).dt.strftime("%Y-%m-%d")
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=strategy["equity"],
                mode="lines",
                name="策略权益",
                line={"width": 2},
            )
        )
        benchmark_dates = pd.to_datetime(benchmark["trade_date"]).dt.strftime("%Y-%m-%d")
        figure.add_trace(
            go.Scatter(
                x=benchmark_dates,
                y=benchmark["equity"],
                mode="lines",
                name="买入并持有基准",
                line={"width": 1.6, "dash": "dash"},
            )
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=[result.config.initial_cash] * len(dates),
                mode="lines",
                name="初始资金",
                line={"width": 1, "dash": "dot"},
            )
        )
        self._category_axis(figure, dates.tolist())
        figure.update_layout(
            title="策略权益与买入并持有基准",
            height=480,
            hovermode="x unified",
            legend={"orientation": "h", "y": 1.05, "x": 0},
            margin={"l": 65, "r": 25, "t": 80, "b": 45},
        )
        figure.update_yaxes(title_text="账户权益（元）")
        return figure

    def build_drawdown(self, result: BacktestResult) -> go.Figure:
        drawdown = result.drawdown_curve
        dates = pd.to_datetime(drawdown["trade_date"]).dt.strftime("%Y-%m-%d")
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=drawdown["drawdown"] * 100.0,
                mode="lines",
                fill="tozeroy",
                name="策略回撤",
                hovertemplate="%{x}<br>回撤 %{y:.2f}%<extra></extra>",
            )
        )
        self._category_axis(figure, dates.tolist())
        figure.update_layout(
            title="策略回撤曲线",
            height=360,
            hovermode="x unified",
            margin={"l": 60, "r": 25, "t": 70, "b": 45},
        )
        figure.update_yaxes(title_text="回撤（%）")
        return figure

    @staticmethod
    def _category_axis(figure: go.Figure, categories: list[str]) -> None:
        figure.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=categories,
            nticks=min(12, len(categories)),
        )
