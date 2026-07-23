from __future__ import annotations

from numbers import Real
from typing import Any

from common.exceptions import StrategyValidationError
from common.strategy_models import Operand, TradingStrategy, normalize_strategy_name

FIELD_NAMES = {
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_change",
}

INDICATOR_NAMES = {
    "SMA",
    "EMA",
    "HHV",
    "LLV",
    "MA_SLOPE",
    "MACD_DIF",
    "MACD_DEA",
    "MACD_HIST",
    "RSI",
    "BOLL_UPPER",
    "BOLL_MIDDLE",
    "BOLL_LOWER",
    "BOLL_BANDWIDTH",
    "ATR",
    "ADX",
    "PLUS_DI",
    "MINUS_DI",
    "VOLUME_MA",
}

COMPARISON_OPERATORS = {">", ">=", "<", "<=", "==", "CROSS_ABOVE", "CROSS_BELOW"}
LOGICAL_OPERATORS = {"AND", "OR"}


class StrategyValidator:
    def validate(self, strategy: TradingStrategy) -> None:
        strategy.name = str(strategy.name).strip()
        if not 2 <= len(strategy.name) <= 50:
            raise StrategyValidationError("策略名称长度必须为 2-50 个字符。")
        if strategy.asset_type not in {"通用", "ETF", "股票"}:
            raise StrategyValidationError("资产类型必须是通用、ETF或股票。")
        if strategy.direction != "long_only":
            raise StrategyValidationError("当前版本仅支持仅做多策略。")
        if strategy.timeframe != "1d":
            raise StrategyValidationError("当前版本仅支持日线策略。")
        if strategy.execution != "next_open":
            raise StrategyValidationError("当前版本仅支持下一交易日开盘执行。")

        self._validate_rule_set(strategy.entry_rule, label="入场")
        self._validate_rule_set(strategy.exit_rule, label="退出", allow_empty=True)
        if not any(rule.enabled for rule in strategy.entry_rule.rules):
            raise StrategyValidationError("入场规则至少需要一个启用条件。")
        self._validate_risk_rules(strategy.risk_rules)

    def _validate_rule_set(self, rule_set, *, label: str, allow_empty: bool = False) -> None:
        if rule_set.operator not in LOGICAL_OPERATORS:
            raise StrategyValidationError(f"{label}规则组逻辑必须为 AND 或 OR。")
        if not allow_empty and not rule_set.rules:
            raise StrategyValidationError(f"{label}规则不能为空。")
        for index, rule in enumerate(rule_set.rules, start=1):
            if not str(rule.group).strip():
                raise StrategyValidationError(f"{label}规则第 {index} 条分组名称不能为空。")
            rule.group = str(rule.group).strip()
            rule.group_operator = str(rule.group_operator).upper()
            if rule.group_operator not in LOGICAL_OPERATORS:
                raise StrategyValidationError(f"{label}规则第 {index} 条组内逻辑必须为 AND 或 OR。")
            if rule.operator not in COMPARISON_OPERATORS:
                raise StrategyValidationError(f"{label}规则第 {index} 条比较符不受支持。")
            self._validate_operand(rule.left, f"{label}规则第 {index} 条左操作数")
            self._validate_operand(rule.right, f"{label}规则第 {index} 条右操作数")
            if (
                rule.operator in {"CROSS_ABOVE", "CROSS_BELOW"}
                and rule.left.kind == "constant"
                and rule.right.kind == "constant"
            ):
                raise StrategyValidationError("上穿或下穿不能比较两个常数。")

    def _validate_operand(self, operand: Operand, label: str) -> None:
        if operand.kind == "field":
            if operand.name not in FIELD_NAMES:
                raise StrategyValidationError(f"{label}字段 {operand.name!r} 不受支持。")
            return
        if operand.kind == "constant":
            value = operand.params.get("value")
            if not isinstance(value, Real) or isinstance(value, bool):
                raise StrategyValidationError(f"{label}常数 value 必须是数字。")
            return
        if operand.kind != "indicator" or operand.name not in INDICATOR_NAMES:
            raise StrategyValidationError(f"{label}指标 {operand.name!r} 不受支持。")

        params = operand.params
        if operand.name in {"SMA", "EMA", "HHV", "LLV", "RSI", "VOLUME_MA"}:
            self._positive_int(params, "period", label)
        elif operand.name == "MA_SLOPE":
            self._positive_int(params, "period", label)
            self._positive_int(params, "lookback", label)
        elif operand.name in {"MACD_DIF", "MACD_DEA", "MACD_HIST"}:
            fast = self._positive_int(params, "fast", label)
            slow = self._positive_int(params, "slow", label)
            self._positive_int(params, "signal", label)
            if fast >= slow:
                raise StrategyValidationError(f"{label}参数 fast 必须小于 slow。")
        elif operand.name.startswith("BOLL_"):
            self._positive_int(params, "period", label)
            std = self._positive_number(params, "std", label)
            if std <= 0:
                raise StrategyValidationError(f"{label}参数 std 必须大于 0。")
        elif operand.name in {"ATR", "ADX", "PLUS_DI", "MINUS_DI"}:
            self._positive_int(params, "period", label)

        if operand.name in {
            "SMA",
            "EMA",
            "HHV",
            "LLV",
            "MA_SLOPE",
            "MACD_DIF",
            "MACD_DEA",
            "MACD_HIST",
            "RSI",
            "BOLL_UPPER",
            "BOLL_MIDDLE",
            "BOLL_LOWER",
            "BOLL_BANDWIDTH",
        }:
            field_name = params.get("field", "close")
            if field_name not in FIELD_NAMES:
                raise StrategyValidationError(f"{label}参数 field 不受支持。")

        if operand.name == "RSI":
            for key in ("minimum", "maximum", "threshold"):
                if key in params:
                    value = params[key]
                    if not isinstance(value, Real) or not 0 <= float(value) <= 100:
                        raise StrategyValidationError(f"{label}参数 {key} 必须位于 0-100。")
        if "multiplier" in params:
            self._positive_number(params, "multiplier", label)

    @staticmethod
    def _positive_int(params: dict[str, Any], key: str, label: str) -> int:
        value = params.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise StrategyValidationError(f"{label}参数 {key} 必须是正整数。")
        return value

    @staticmethod
    def _positive_number(params: dict[str, Any], key: str, label: str) -> float:
        value = params.get(key)
        if not isinstance(value, Real) or isinstance(value, bool) or float(value) <= 0:
            raise StrategyValidationError(f"{label}参数 {key} 必须是正数。")
        return float(value)

    def _validate_risk_rules(self, risk_rules: dict[str, Any]) -> None:
        for name in ("initial_atr_stop", "trailing_atr_stop"):
            config = risk_rules.get(name)
            if not config or not config.get("enabled", False):
                continue
            self._positive_int(config, "period", name)
            self._positive_number(config, "multiple", name)
