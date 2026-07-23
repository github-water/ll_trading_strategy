from __future__ import annotations

from datetime import date
from typing import Callable

import gradio as gr
import pandas as pd

from common.config import Settings
from common.constants import OUTPUT_COLUMNS
from common.exceptions import MarketDataError
from common.models import AdjustType, AssetType, DataUpdateResult, FetchResult
from service.market_data_service import MarketDataService


def ten_years_ago(today: date) -> date:
    try:
        return today.replace(year=today.year - 10)
    except ValueError:
        return today.replace(year=today.year - 10, day=28)


def build_status(result: FetchResult) -> str:
    first_date = result.data["trade_date"].iloc[0]
    last_date = result.data["trade_date"].iloc[-1]
    asset_label = (
        "ETF/场内基金"
        if result.resolved_asset_type is AssetType.ETF
        else "股票"
    )
    adjustment_label = {
        AdjustType.RAW: "不复权",
        AdjustType.QFQ: "前复权",
        AdjustType.HFQ: "后复权",
    }[result.adjust]
    lines = [
        "### 获取成功",
        f"- 标的：**{result.instrument_name}** "
        f"`{result.symbol}.{result.exchange}`（{asset_label}）",
        f"- 区间：`{first_date}` 至 `{last_date}`",
        f"- 交易日：**{len(result.data):,}**",
        f"- 复权：{adjustment_label}",
        f"- 数据源：efinance / 东方财富，efinance `{result.source_version}`",
        f"- CSV：`{result.csv_path.name}`",
    ]
    if result.warnings:
        lines.append("- 提示：" + "；".join(result.warnings))
    return "\n".join(lines)


def build_update_status(result: DataUpdateResult) -> str:
    heading = "### 更新成功" if result.updated else "### 已是最新"
    asset_label = (
        "ETF/场内基金"
        if result.resolved_asset_type is AssetType.ETF
        else "股票"
    )
    adjustment_label = {
        AdjustType.RAW: "不复权",
        AdjustType.QFQ: "前复权",
        AdjustType.HFQ: "后复权",
    }[result.adjust]
    lines = [
        heading,
        f"- 标的：**{result.instrument_name}** "
        f"`{result.symbol}.{result.exchange}`（{asset_label}）",
        f"- 原最新交易日：`{result.previous_last_date}`",
        f"- 当前最新交易日：`{result.latest_date}`",
        f"- 新增交易日：**{result.added_rows:,}**",
        f"- 复权：{adjustment_label}（沿用本地 CSV）",
        f"- 数据源：efinance / 东方财富，efinance `{result.source_version}`",
        f"- CSV：`{result.csv_path.name}`",
    ]
    if result.warnings:
        lines.append("- 提示：" + "；".join(result.warnings))
    return "\n".join(lines)


def _build_preview(data: pd.DataFrame) -> pd.DataFrame:
    return (
        data.tail(200)
        .sort_values("trade_date", ascending=False)
        .reset_index(drop=True)
    )


def create_data_update_handler(
    service: MarketDataService,
    *,
    today_fn: Callable[[], date] = date.today,
) -> Callable[[str], tuple[pd.DataFrame, str, str | None]]:
    def handle(symbol: str) -> tuple[pd.DataFrame, str, str | None]:
        try:
            result = service.update_latest(
                symbol_input=symbol,
                end_date_input=today_fn(),
            )
            return (
                _build_preview(result.data),
                build_update_status(result),
                str(result.csv_path),
            )
        except MarketDataError as exc:
            return (
                pd.DataFrame(columns=OUTPUT_COLUMNS),
                f"### 更新失败\n\n{exc}",
                None,
            )
        except Exception as exc:
            return (
                pd.DataFrame(columns=OUTPUT_COLUMNS),
                f"### 系统错误\n\n{type(exc).__name__}: {exc}",
                None,
            )

    return handle


def create_data_fetch_handler(
    service: MarketDataService,
) -> Callable[[str, str, str, str, str], tuple[pd.DataFrame, str, str | None]]:
    def handle(
        symbol: str,
        asset_type: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> tuple[pd.DataFrame, str, str | None]:
        try:
            result = service.fetch_and_save(
                symbol_input=symbol,
                asset_type_input=asset_type,
                start_date_input=start_date,
                end_date_input=end_date,
                adjust_input=adjust,
            )
            preview = _build_preview(result.data)
            return preview, build_status(result), str(result.csv_path)
        except MarketDataError as exc:
            return (
                pd.DataFrame(columns=OUTPUT_COLUMNS),
                f"### 获取失败\n\n{exc}",
                None,
            )
        except Exception as exc:
            return (
                pd.DataFrame(columns=OUTPUT_COLUMNS),
                f"### 系统错误\n\n{type(exc).__name__}: {exc}",
                None,
            )

    return handle


def build_data_fetch_tab(service: MarketDataService, settings: Settings) -> None:
    del settings  # Reserved for future tab-specific presentation settings.
    today = date.today()
    default_start = ten_years_ago(today).isoformat()
    default_end = today.isoformat()

    with gr.Tab("数据获取"):
        gr.Markdown(
            """
## 获取 A 股 ETF / 个股日线行情

输入六位证券代码和日期范围，系统通过 **efinance** 获取日线数据，
标准化为 CSV，并提供最近 200 条记录预览。

- 支持：A 股 ETF、场内基金、沪深京 A 股个股
- 周期：日线
- 复权：不复权、前复权、后复权
- 成交量：将 efinance 返回的“手”统一换算为股/基金份额
- 增量更新：按证券代码读取最新本地 CSV，并沿用文件中的资产类型和复权方式更新至今天
"""
        )
        with gr.Row():
            symbol_input = gr.Textbox(
                label="证券代码",
                value="510300",
                placeholder="例如 510300、600519、000001",
                scale=2,
            )
            asset_type_input = gr.Dropdown(
                choices=["自动识别", "ETF", "股票"],
                value="自动识别",
                label="资产类型",
                scale=1,
            )
            adjust_input = gr.Dropdown(
                choices=["不复权", "前复权", "后复权"],
                value="不复权",
                label="复权方式",
                scale=1,
            )
        with gr.Row():
            start_date_input = gr.Textbox(
                label="开始日期",
                value=default_start,
                placeholder="YYYY-MM-DD",
            )
            end_date_input = gr.Textbox(
                label="结束日期",
                value=default_end,
                placeholder="YYYY-MM-DD",
            )

        with gr.Row():
            fetch_button = gr.Button("获取并生成 CSV", variant="primary")
            update_button = gr.Button("更新至最新")
        status_output = gr.Markdown("尚未获取数据。")
        preview_output = gr.Dataframe(
            headers=OUTPUT_COLUMNS,
            value=pd.DataFrame(columns=OUTPUT_COLUMNS),
            label="数据预览（最近 200 条，按日期倒序）",
            interactive=False,
            wrap=True,
        )
        download_output = gr.File(label="下载完整 CSV", interactive=False)

        gr.Examples(
            examples=[
                ["510300", "ETF", default_start, default_end, "不复权"],
                ["600519", "股票", default_start, default_end, "前复权"],
                ["000001", "股票", default_start, default_end, "不复权"],
            ],
            inputs=[
                symbol_input,
                asset_type_input,
                start_date_input,
                end_date_input,
                adjust_input,
            ],
        )
        fetch_button.click(
            fn=create_data_fetch_handler(service),
            inputs=[
                symbol_input,
                asset_type_input,
                start_date_input,
                end_date_input,
                adjust_input,
            ],
            outputs=[preview_output, status_output, download_output],
            api_name="fetch_daily_data",
        )
        update_button.click(
            fn=create_data_update_handler(service),
            inputs=[symbol_input],
            outputs=[preview_output, status_output, download_output],
            api_name="update_daily_data",
        )
