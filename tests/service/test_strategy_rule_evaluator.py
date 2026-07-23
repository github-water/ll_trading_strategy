import numpy as np
import pandas as pd

from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from service.strategy_indicator_engine import StrategyIndicatorEngine
from service.strategy_rule_evaluator import StrategyRuleEvaluator


def sample_data(rows: int = 320) -> pd.DataFrame:
    close = pd.Series(np.linspace(10.0, 30.0, rows))
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "pre_close": close.shift(1).fillna(close.iloc[0]),
            "volume": np.linspace(1_000_000, 2_000_000, rows),
            "amount": np.linspace(10_000_000, 20_000_000, rows),
        }
    )


def make_rule(left, operator, right, group="default", group_operator="AND"):
    return StrategyRule.create(
        group=group,
        group_operator=group_operator,
        left=left,
        operator=operator,
        right=right,
    )


def test_indicator_engine_materializes_supported_indicators():
    operands = [
        Operand.indicator("SMA", {"field": "close", "period": 20}),
        Operand.indicator("EMA", {"field": "close", "period": 20}),
        Operand.indicator("HHV", {"field": "high", "period": 5, "exclude_current": True}),
        Operand.indicator("LLV", {"field": "low", "period": 5}),
        Operand.indicator("MA_SLOPE", {"field": "close", "period": 20, "lookback": 5}),
        Operand.indicator("MACD_DIF", {"field": "close", "fast": 12, "slow": 26, "signal": 9}),
        Operand.indicator("MACD_DEA", {"field": "close", "fast": 12, "slow": 26, "signal": 9}),
        Operand.indicator("MACD_HIST", {"field": "close", "fast": 12, "slow": 26, "signal": 9}),
        Operand.indicator("RSI", {"field": "close", "period": 14}),
        Operand.indicator("BOLL_UPPER", {"field": "close", "period": 20, "std": 2.0}),
        Operand.indicator("BOLL_MIDDLE", {"field": "close", "period": 20, "std": 2.0}),
        Operand.indicator("BOLL_LOWER", {"field": "close", "period": 20, "std": 2.0}),
        Operand.indicator("BOLL_BANDWIDTH", {"field": "close", "period": 20, "std": 2.0}),
        Operand.indicator("ATR", {"period": 14}),
        Operand.indicator("ADX", {"period": 14}),
        Operand.indicator("PLUS_DI", {"period": 14}),
        Operand.indicator("MINUS_DI", {"period": 14}),
        Operand.indicator("VOLUME_MA", {"period": 20, "multiplier": 1.15}),
    ]
    rules = [make_rule(item, ">", Operand.constant(0)) for item in operands]
    strategy = TradingStrategy.new(name="测试策略")
    strategy.entry_rule = RuleSet(operator="AND", rules=rules)

    prepared = StrategyIndicatorEngine().prepare(sample_data(), strategy)

    for operand in operands:
        column = StrategyIndicatorEngine.column_name(operand)
        assert column in prepared.columns
    volume_operand = operands[-1]
    volume_column = StrategyIndicatorEngine.column_name(volume_operand)
    expected = prepared["volume"].rolling(20, min_periods=20).mean() * 1.15
    pd.testing.assert_series_equal(prepared[volume_column], expected, check_names=False)


def test_hhv_excludes_current_day_when_requested():
    data = sample_data(10)
    operand = Operand.indicator(
        "HHV", {"field": "high", "period": 3, "exclude_current": True}
    )
    strategy = TradingStrategy.new(name="测试策略")
    strategy.entry_rule.rules = [make_rule(Operand.field("close"), ">", operand)]
    prepared = StrategyIndicatorEngine().prepare(data, strategy)
    result = prepared[StrategyIndicatorEngine.column_name(operand)]
    assert result.iloc[3] == data["high"].iloc[0:3].max()


def test_rule_evaluator_supports_cross_and_two_level_group_logic():
    data = sample_data(8)
    data["fast"] = [1, 1, 1, 3, 4, 3, 2, 1]
    data["slow"] = [2, 2, 2, 2, 2, 2, 2, 2]
    rules = RuleSet(
        operator="AND",
        rules=[
            make_rule(Operand.field("fast"), "CROSS_ABOVE", Operand.field("slow"), "cross", "OR"),
            make_rule(Operand.field("close"), ">", Operand.constant(1000), "cross", "OR"),
            make_rule(Operand.field("volume"), ">", Operand.constant(0), "liquidity", "AND"),
        ],
    )
    result = StrategyRuleEvaluator().evaluate_ruleset(data, rules)
    assert result.tolist() == [False, False, False, True, False, False, False, False]


def test_disabled_rules_are_ignored():
    data = sample_data(5)
    enabled = make_rule(Operand.field("volume"), ">", Operand.constant(0))
    disabled = make_rule(Operand.field("close"), ">", Operand.constant(1000))
    disabled.enabled = False
    result = StrategyRuleEvaluator().evaluate_ruleset(
        data, RuleSet(operator="AND", rules=[enabled, disabled])
    )
    assert result.all()
