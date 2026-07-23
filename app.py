from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution with `python app.py` from an unpacked source tree.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common.config import Settings
from infra.charting.plotly_chart_builder import PlotlyTechnicalChartBuilder
from infra.charting.backtest_chart_builder import PlotlyBacktestChartBuilder
from infra.market_data.efinance_gateway import EfinanceMarketDataGateway
from infra.storage.csv_repository import LocalCsvRepository
from infra.storage.strategy_json_repository import LocalStrategyJsonRepository
from service.market_data_service import MarketDataService
from service.backtest_engine import BacktestEngine
from service.backtest_service import BacktestService
from service.position_sizing_service import PositionSizingService
from service.strategy_indicator_engine import StrategyIndicatorEngine
from service.strategy_rule_evaluator import StrategyRuleEvaluator
from service.technical_analysis_service import TechnicalAnalysisService
from service.technical_indicator_service import TechnicalIndicatorService
from service.strategy_management_service import StrategyManagementService
from ui.app_builder import build_app


def create_app():
    settings = Settings.from_env()
    repository = LocalCsvRepository(settings)
    market_data_service = MarketDataService(
        gateway=EfinanceMarketDataGateway(settings=settings),
        repository=repository,
    )
    strategy_repository = LocalStrategyJsonRepository(settings)
    strategy_management_service = StrategyManagementService(strategy_repository)
    technical_analysis_service = TechnicalAnalysisService(
        repository=repository,
        indicators=TechnicalIndicatorService(),
        chart_builder=PlotlyTechnicalChartBuilder(),
    )
    position_sizing_service = PositionSizingService()
    backtest_service = BacktestService(
        csv_repository=repository,
        strategy_repository=strategy_repository,
        indicator_engine=StrategyIndicatorEngine(),
        rule_evaluator=StrategyRuleEvaluator(),
        engine=BacktestEngine(position_sizing_service),
        chart_builder=PlotlyBacktestChartBuilder(),
        position_sizing=position_sizing_service,
    )
    return (
        build_app(
            market_data_service,
            settings,
            technical_analysis_service=technical_analysis_service,
            strategy_management_service=strategy_management_service,
            backtest_service=backtest_service,
        ),
        settings,
    )


demo, settings = create_app()

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=settings.server_name,
        server_port=settings.server_port,
        share=settings.gradio_share,
        show_error=True,
    )
