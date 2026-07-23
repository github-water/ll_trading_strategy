import pytest

from common.exceptions import StrategyValidationError
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from service.strategy_validator import StrategyValidator, normalize_strategy_name


def make_rule(**overrides):
    values = {
        "group": "趋势组",
        "group_operator": "AND",
        "left": Operand.field("close"),
        "operator": ">",
        "right": Operand.indicator("SMA", {"field": "close", "period": 20}),
        "enabled": True,
    }
    values.update(overrides)
    return StrategyRule.create(**values)


def make_strategy(**overrides):
    values = {
        "strategy_id": "11111111-1111-4111-8111-111111111111",
        "name": "趋势策略",
        "entry_rule": RuleSet(operator="AND", rules=[make_rule()]),
        "exit_rule": RuleSet(operator="OR", rules=[]),
    }
    values.update(overrides)
    return TradingStrategy(**values)


def test_strategy_round_trip_preserves_rule_tree():
    strategy = make_strategy()
    restored = TradingStrategy.from_dict(strategy.to_dict())
    assert restored.to_dict() == strategy.to_dict()


def test_name_normalization_trims_and_ignores_case():
    assert normalize_strategy_name("  EtF趋势策略  ") == "etf趋势策略"


def test_validator_requires_an_enabled_entry_rule():
    strategy = make_strategy(entry_rule=RuleSet(operator="AND", rules=[make_rule(enabled=False)]))
    with pytest.raises(StrategyValidationError, match="入场规则至少需要一个启用条件"):
        StrategyValidator().validate(strategy)


def test_validator_rejects_invalid_indicator_period():
    strategy = make_strategy(
        entry_rule=RuleSet(
            operator="AND",
            rules=[make_rule(right=Operand.indicator("SMA", {"field": "close", "period": 0}))],
        )
    )
    with pytest.raises(StrategyValidationError, match="period"):
        StrategyValidator().validate(strategy)


def test_validator_rejects_macd_fast_not_less_than_slow():
    strategy = make_strategy(
        entry_rule=RuleSet(
            operator="AND",
            rules=[make_rule(right=Operand.indicator("MACD_DIF", {"field": "close", "fast": 26, "slow": 12, "signal": 9}))],
        )
    )
    with pytest.raises(StrategyValidationError, match="fast"):
        StrategyValidator().validate(strategy)


def test_validator_rejects_crossing_two_constants():
    strategy = make_strategy(
        entry_rule=RuleSet(
            operator="AND",
            rules=[make_rule(left=Operand.constant(1), operator="CROSS_ABOVE", right=Operand.constant(2))],
        )
    )
    with pytest.raises(StrategyValidationError, match="两个常数"):
        StrategyValidator().validate(strategy)


def test_validator_rejects_blank_group_name():
    strategy = make_strategy(entry_rule=RuleSet(operator="AND", rules=[make_rule(group="  ")]))
    with pytest.raises(StrategyValidationError, match="分组名称"):
        StrategyValidator().validate(strategy)
