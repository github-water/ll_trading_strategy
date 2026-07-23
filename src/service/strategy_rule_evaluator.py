from __future__ import annotations

from collections import OrderedDict

import pandas as pd

from common.exceptions import BacktestValidationError
from common.strategy_models import Operand, RuleSet, StrategyRule
from service.strategy_indicator_engine import StrategyIndicatorEngine


class StrategyRuleEvaluator:
    def evaluate_ruleset(self, data: pd.DataFrame, rule_set: RuleSet) -> pd.Series:
        active_rules = [rule for rule in rule_set.rules if rule.enabled]
        if not active_rules:
            return pd.Series(False, index=data.index, dtype=bool)

        groups: OrderedDict[str, list[StrategyRule]] = OrderedDict()
        for rule in active_rules:
            groups.setdefault(rule.group, []).append(rule)

        group_results: list[pd.Series] = []
        for rules in groups.values():
            result = self._evaluate_rule(data, rules[0])
            operator = rules[0].group_operator.upper()
            for rule in rules[1:]:
                if rule.group_operator.upper() != operator:
                    raise BacktestValidationError("同一条件组内的逻辑运算符必须一致。")
                current = self._evaluate_rule(data, rule)
                result = result & current if operator == "AND" else result | current
            group_results.append(result)

        combined = group_results[0]
        outer = rule_set.operator.upper()
        for group_result in group_results[1:]:
            combined = combined & group_result if outer == "AND" else combined | group_result
        return combined.fillna(False).astype(bool)

    def _evaluate_rule(self, data: pd.DataFrame, rule: StrategyRule) -> pd.Series:
        left = self._operand_series(data, rule.left)
        right = self._operand_series(data, rule.right)
        operator = rule.operator
        if operator == ">":
            result = left > right
        elif operator == ">=":
            result = left >= right
        elif operator == "<":
            result = left < right
        elif operator == "<=":
            result = left <= right
        elif operator == "==":
            result = left == right
        elif operator == "CROSS_ABOVE":
            result = (left > right) & (left.shift(1) <= right.shift(1))
        elif operator == "CROSS_BELOW":
            result = (left < right) & (left.shift(1) >= right.shift(1))
        else:
            raise BacktestValidationError(f"回测暂不支持比较符 {operator}。")
        return result.fillna(False).astype(bool)

    @staticmethod
    def _operand_series(data: pd.DataFrame, operand: Operand) -> pd.Series:
        if operand.kind == "constant":
            return pd.Series(float(operand.params["value"]), index=data.index)
        if operand.kind == "field":
            if operand.name not in data.columns:
                raise BacktestValidationError(f"行情字段 {operand.name} 不存在。")
            return pd.to_numeric(data[operand.name], errors="coerce")
        if operand.kind == "indicator":
            column = StrategyIndicatorEngine.column_name(operand)
            if column not in data.columns:
                raise BacktestValidationError(f"指标 {operand.name} 尚未计算。")
            return pd.to_numeric(data[column], errors="coerce")
        raise BacktestValidationError(f"操作数类型 {operand.kind} 不受支持。")
