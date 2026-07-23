from __future__ import annotations

import gradio as gr

from common.config import Settings
from service.market_data_service import MarketDataService
from service.technical_analysis_service import TechnicalAnalysisService
from service.strategy_management_service import StrategyManagementService
from ui.tabs.tab1_data_fetch import build_data_fetch_tab
from ui.tabs.tab2_technical_chart import build_technical_chart_tab
from ui.tabs.tab3_strategy_management import build_strategy_management_tab


def build_app(
    service: MarketDataService,
    settings: Settings,
    *,
    technical_analysis_service: TechnicalAnalysisService | None = None,
    strategy_management_service: StrategyManagementService | None = None,
) -> gr.Blocks:
    with gr.Blocks(title="交易策略助手") as app:
        gr.Markdown(
            """
# 交易策略助手

提供行情数据获取与增量更新、基于 CSV 的交互式技术图表，以及技术指标策略管理。
"""
        )
        build_data_fetch_tab(service, settings)
        if technical_analysis_service is not None:
            build_technical_chart_tab(technical_analysis_service)
        if strategy_management_service is not None:
            build_strategy_management_tab(strategy_management_service)
    return app
