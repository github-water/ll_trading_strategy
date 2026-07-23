from __future__ import annotations

from typing import Callable

import gradio as gr

from common.exceptions import MarketDataError
from common.models import TechnicalAnalysisRequest, TechnicalAnalysisResult
from service.technical_analysis_service import TechnicalAnalysisService


def build_status(result: TechnicalAnalysisResult) -> str:
    return "\n".join(
        [
            "### 图表生成成功",
            f"- 证券代码：`{result.symbol}`",
            f"- 数据文件：`{result.source_path.name}`",
            f"- 显示区间：`{result.first_date}` 至 `{result.last_date}`",
            f"- 显示交易日：**{result.row_count:,}**",
        ]
    )


def create_technical_chart_handler(
    service: TechnicalAnalysisService,
) -> Callable[..., tuple[object | None, str]]:
    def handle(
        symbol: str,
        csv_path: str | None,
        start_date: str,
        end_date: str,
        max_rows: int | float,
        macd_fast: int | float,
        macd_slow: int | float,
        macd_signal: int | float,
        boll_period: int | float,
        boll_std: int | float,
        rsi_period: int | float,
    ) -> tuple[object | None, str]:
        try:
            result = service.analyze(
                TechnicalAnalysisRequest(
                    symbol=symbol,
                    csv_path=csv_path,
                    start_date=start_date,
                    end_date=end_date,
                    max_rows=int(max_rows),
                    macd_fast=int(macd_fast),
                    macd_slow=int(macd_slow),
                    macd_signal=int(macd_signal),
                    boll_period=int(boll_period),
                    boll_std=float(boll_std),
                    rsi_period=int(rsi_period),
                )
            )
            return result.figure, build_status(result)
        except MarketDataError as exc:
            return None, f"### 图表生成失败\n\n{exc}"
        except Exception as exc:
            return None, f"### 系统错误\n\n{type(exc).__name__}: {exc}"

    return handle


def build_technical_chart_tab(service: TechnicalAnalysisService) -> None:
    with gr.Tab("技术图表"):
        gr.Markdown(
            """
## K线与技术指标

可直接输入证券代码，读取 `outputs/` 中该代码最新下载的 CSV；
也可以上传 CSV，上传文件优先。图表包含 K线与 MA5/10/20/60/250/360、
独立 BOLL K线、成交量、MACD 和 RSI。横轴严格按照 CSV 中的实际交易日排列。

CSV 至少需要：`trade_date, open, high, low, close, volume`。
"""
        )
        with gr.Row():
            symbol_input = gr.Textbox(
                label="证券代码",
                value="510300",
                placeholder="例如 510300、600519；上传单证券CSV时可留空",
                scale=2,
            )
            csv_input = gr.File(
                label="上传 CSV（可选，优先使用）",
                file_types=[".csv"],
                type="filepath",
                scale=3,
            )
        with gr.Row():
            start_date_input = gr.Textbox(
                label="开始日期（可选）",
                placeholder="YYYY-MM-DD",
            )
            end_date_input = gr.Textbox(
                label="结束日期（可选）",
                placeholder="YYYY-MM-DD",
            )
            max_rows_input = gr.Slider(
                minimum=50,
                maximum=3000,
                step=50,
                value=250,
                label="最近显示条数",
            )

        with gr.Accordion("指标参数", open=False):
            with gr.Row():
                macd_fast_input = gr.Number(
                    label="MACD 快线",
                    value=12,
                    precision=0,
                )
                macd_slow_input = gr.Number(
                    label="MACD 慢线",
                    value=26,
                    precision=0,
                )
                macd_signal_input = gr.Number(
                    label="MACD 信号线",
                    value=9,
                    precision=0,
                )
            with gr.Row():
                boll_period_input = gr.Number(
                    label="BOLL 周期",
                    value=20,
                    precision=0,
                )
                boll_std_input = gr.Number(
                    label="BOLL 标准差倍数",
                    value=2.0,
                )
                rsi_period_input = gr.Number(
                    label="RSI 周期",
                    value=14,
                    precision=0,
                )

        generate_button = gr.Button("生成技术图表", variant="primary")
        status_output = gr.Markdown("尚未生成图表。")
        chart_output = gr.Plot(label="技术图表")

        generate_button.click(
            fn=create_technical_chart_handler(service),
            inputs=[
                symbol_input,
                csv_input,
                start_date_input,
                end_date_input,
                max_rows_input,
                macd_fast_input,
                macd_slow_input,
                macd_signal_input,
                boll_period_input,
                boll_std_input,
                rsi_period_input,
            ],
            outputs=[chart_output, status_output],
            api_name="build_technical_chart",
        )
