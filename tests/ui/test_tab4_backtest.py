from common.config import Settings
from ui.app_builder import build_app
from ui.tabs.tab4_backtest import position_mode_from_label


class FakeMarketDataService:
    pass


class FakeBacktestService:
    def list_strategy_choices(self):
        return [("测试策略", "strategy-1")]


def test_position_mode_labels_are_mapped():
    assert position_mode_from_label("全仓交易").value == "full"
    assert position_mode_from_label("ATR风险仓位").value == "atr_risk"


def test_app_contains_backtest_tab_controls_and_event():
    app = build_app(
        FakeMarketDataService(),
        Settings(),
        backtest_service=FakeBacktestService(),
    )
    config = str(app.get_config_file())
    assert "数据回测" in config
    assert "全仓交易" in config
    assert "ATR风险仓位" in config
    assert "100000" in config
    assert "运行回测" in config
    assert "run_backtest" in config
