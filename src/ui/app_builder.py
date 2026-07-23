from __future__ import annotations

import gradio as gr

from common.config import Settings
from service.market_data_service import MarketDataService
from service.technical_analysis_service import TechnicalAnalysisService
from service.strategy_management_service import StrategyManagementService
from service.backtest_service import BacktestService
from ui.tabs.tab1_data_fetch import build_data_fetch_tab
from ui.tabs.tab2_technical_chart import build_technical_chart_tab
from ui.tabs.tab3_strategy_management import build_strategy_management_tab
from ui.tabs.tab4_backtest import build_backtest_tab


def build_app(
    service: MarketDataService,
    settings: Settings,
    *,
    technical_analysis_service: TechnicalAnalysisService | None = None,
    strategy_management_service: StrategyManagementService | None = None,
    backtest_service: BacktestService | None = None,
) -> gr.Blocks:
    with gr.Blocks(title="交易策略助手") as app:
        gr.Markdown(
            """
# 交易策略助手

提供行情数据获取与增量更新、技术图表、技术指标策略管理和单标的数据回测。
"""
        )
        build_data_fetch_tab(service, settings)
        if technical_analysis_service is not None:
            build_technical_chart_tab(technical_analysis_service)
        if strategy_management_service is not None:
            build_strategy_management_tab(strategy_management_service)
        if backtest_service is not None:
            build_backtest_tab(backtest_service)
    return app
