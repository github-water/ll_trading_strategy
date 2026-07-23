from pathlib import Path

from common.config import Settings
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from ui.app_builder import build_app
from ui.tabs.tab3_strategy_management import (
    append_or_update_rule,
    build_rule_table,
    parse_operand,
)


class FakeMarketDataService:
    pass


class FakeStrategyService:
    def list_strategies(self):
        return []


def test_parse_operand_builds_indicator_from_json():
    operand = parse_operand("SMA", '{"field":"close","period":20}')
    assert operand.kind == "indicator"
    assert operand.params["period"] == 20


def test_append_rule_adds_entry_condition_and_table_row():
    entry, exit_, status = append_or_update_rule(
        [],
        [],
        target="入场",
        rule_index=None,
        enabled=True,
        group="趋势组",
        group_operator="AND",
        left_name="close",
        left_params="{}",
        operator=">",
        right_name="SMA",
        right_params='{"field":"close","period":20}',
    )
    assert len(entry) == 1
    assert exit_ == []
    assert "已添加" in status
    table = build_rule_table(entry)
    assert table.iloc[0]["条件"] == "close > SMA(field=close, period=20)"


def test_app_contains_strategy_management_tab():
    app = build_app(
        FakeMarketDataService(),
        Settings(),
        strategy_management_service=FakeStrategyService(),
    )
    config = str(app.get_config_file())
    assert "交易策略" in config
    assert "保存策略" in config
    assert "add_or_update_strategy_rule" in config
