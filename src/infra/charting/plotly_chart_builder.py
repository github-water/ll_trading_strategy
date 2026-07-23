from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


RISING_COLOR = "#ef232a"
FALLING_COLOR = "#00a800"
MA_PERIODS = (5, 10, 20, 60, 250, 360)


class PlotlyTechnicalChartBuilder:
    """Build a five-panel interactive A-share technical chart."""

    def build(self, data: pd.DataFrame, *, title: str) -> go.Figure:
        # A category axis follows the CSV rows exactly and removes non-trading gaps.
        dates = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
        price_change = data["close"].diff()
        volume_colors = [
            RISING_COLOR
            if (index == 0 and data["close"].iloc[index] >= data["open"].iloc[index])
            or (index > 0 and price_change.iloc[index] >= 0)
            else FALLING_COLOR
            for index in range(len(data))
        ]
        macd_colors = [
            RISING_COLOR if value >= 0 else FALLING_COLOR
            for value in data["macd_hist"].fillna(0)
        ]

        figure = make_subplots(
            rows=5,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=[0.34, 0.18, 0.14, 0.19, 0.15],
        )

        figure.add_trace(
            go.Candlestick(
                x=dates,
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                name="K线",
                increasing_line_color=RISING_COLOR,
                decreasing_line_color=FALLING_COLOR,
                increasing_fillcolor=RISING_COLOR,
                decreasing_fillcolor=FALLING_COLOR,
            ),
            row=1,
            col=1,
        )
        for period in MA_PERIODS:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=data[f"ma{period}"],
                    mode="lines",
                    name=f"MA{period}",
                    line={"width": 1.2},
                    connectgaps=False,
                ),
                row=1,
                col=1,
            )

        figure.add_trace(
            go.Candlestick(
                x=dates,
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                name="BOLL K线",
                increasing_line_color=RISING_COLOR,
                decreasing_line_color=FALLING_COLOR,
                increasing_fillcolor=RISING_COLOR,
                decreasing_fillcolor=FALLING_COLOR,
                showlegend=False,
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["boll_upper"],
                mode="lines",
                name="BOLL上轨",
                line={"width": 1.2},
                connectgaps=False,
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["boll_mid"],
                mode="lines",
                name="BOLL中轨",
                line={"width": 1.2},
                connectgaps=False,
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["boll_lower"],
                mode="lines",
                name="BOLL下轨",
                line={"width": 1.2},
                connectgaps=False,
            ),
            row=2,
            col=1,
        )

        figure.add_trace(
            go.Bar(
                x=dates,
                y=data["volume"],
                name="成交量",
                marker={"color": volume_colors},
            ),
            row=3,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["macd"],
                mode="lines",
                name="MACD",
                line={"width": 1.3},
            ),
            row=4,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["macd_signal"],
                mode="lines",
                name="Signal",
                line={"width": 1.3},
            ),
            row=4,
            col=1,
        )
        figure.add_trace(
            go.Bar(
                x=dates,
                y=data["macd_hist"],
                name="MACD柱",
                marker={"color": macd_colors},
            ),
            row=4,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=data["rsi"],
                mode="lines",
                name="RSI",
                line={"width": 1.4},
                connectgaps=False,
            ),
            row=5,
            col=1,
        )

        figure.add_hline(
            y=70,
            row=5,
            col=1,
            line_dash="dash",
            line_width=1,
            opacity=0.6,
        )
        figure.add_hline(
            y=30,
            row=5,
            col=1,
            line_dash="dash",
            line_width=1,
            opacity=0.6,
        )
        figure.update_yaxes(title_text="价格", row=1, col=1)
        figure.update_yaxes(title_text="BOLL", row=2, col=1)
        figure.update_yaxes(title_text="成交量", row=3, col=1)
        figure.update_yaxes(title_text="MACD", row=4, col=1)
        figure.update_yaxes(title_text="RSI", range=[0, 100], row=5, col=1)
        figure.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=dates.tolist(),
            rangeslider_visible=False,
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            nticks=min(12, len(dates)),
        )
        figure.update_layout(
            title=title,
            height=1180,
            hovermode="x unified",
            legend={"orientation": "h", "y": 1.02, "x": 0},
            margin={"l": 55, "r": 25, "t": 95, "b": 40},
            bargap=0.05,
        )
        return figure
