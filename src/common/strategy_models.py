from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_strategy_name(name: str) -> str:
    return str(name).strip().casefold()


@dataclass
class Operand:
    kind: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def field(cls, name: str) -> "Operand":
        return cls(kind="field", name=name, params={})

    @classmethod
    def indicator(cls, name: str, params: dict[str, Any] | None = None) -> "Operand":
        return cls(kind="indicator", name=name, params=dict(params or {}))

    @classmethod
    def constant(cls, value: int | float) -> "Operand":
        return cls(kind="constant", name="CONSTANT", params={"value": value})

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "name": self.name, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Operand":
        return cls(
            kind=str(payload.get("type") or payload.get("kind") or ""),
            name=str(payload.get("name") or ""),
            params=dict(payload.get("params") or {}),
        )


@dataclass
class StrategyRule:
    rule_id: str
    enabled: bool
    group: str
    group_operator: str
    left: Operand
    operator: str
    right: Operand

    @classmethod
    def create(
        cls,
        *,
        group: str,
        group_operator: str,
        left: Operand,
        operator: str,
        right: Operand,
        enabled: bool = True,
        rule_id: str | None = None,
    ) -> "StrategyRule":
        return cls(
            rule_id=rule_id or str(uuid4()),
            enabled=bool(enabled),
            group=group,
            group_operator=group_operator,
            left=left,
            operator=operator,
            right=right,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "enabled": self.enabled,
            "group": self.group,
            "group_operator": self.group_operator,
            "left": self.left.to_dict(),
            "operator": self.operator,
            "right": self.right.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategyRule":
        return cls.create(
            rule_id=str(payload.get("rule_id") or uuid4()),
            enabled=bool(payload.get("enabled", True)),
            group=str(payload.get("group") or "默认组"),
            group_operator=str(payload.get("group_operator") or "AND").upper(),
            left=Operand.from_dict(dict(payload.get("left") or {})),
            operator=str(payload.get("operator") or ">"),
            right=Operand.from_dict(dict(payload.get("right") or {})),
        )


@dataclass
class RuleSet:
    operator: str = "AND"
    rules: list[StrategyRule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "group",
            "operator": self.operator,
            "children": [rule.to_dict() for rule in self.rules],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuleSet":
        payload = payload or {}
        children = payload.get("children")
        if children is None:
            children = payload.get("rules") or []
        return cls(
            operator=str(payload.get("operator") or "AND").upper(),
            rules=[StrategyRule.from_dict(dict(item)) for item in children],
        )


@dataclass
class TradingStrategy:
    strategy_id: str
    name: str
    description: str = ""
    asset_type: str = "通用"
    direction: str = "long_only"
    timeframe: str = "1d"
    execution: str = "next_open"
    enabled: bool = True
    entry_rule: RuleSet = field(default_factory=lambda: RuleSet(operator="AND"))
    exit_rule: RuleSet = field(default_factory=lambda: RuleSet(operator="OR"))
    risk_rules: dict[str, Any] = field(default_factory=dict)
    is_builtin: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def new(cls, *, name: str = "新策略") -> "TradingStrategy":
        return cls(strategy_id=str(uuid4()), name=name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "asset_type": self.asset_type,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "execution": self.execution,
            "enabled": self.enabled,
            "entry_rule": self.entry_rule.to_dict(),
            "exit_rule": self.exit_rule.to_dict(),
            "risk_rules": dict(self.risk_rules),
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingStrategy":
        return cls(
            strategy_id=str(payload.get("strategy_id") or uuid4()),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            asset_type=str(payload.get("asset_type") or "通用"),
            direction=str(payload.get("direction") or "long_only"),
            timeframe=str(payload.get("timeframe") or "1d"),
            execution=str(payload.get("execution") or "next_open"),
            enabled=bool(payload.get("enabled", True)),
            entry_rule=RuleSet.from_dict(payload.get("entry_rule")),
            exit_rule=RuleSet.from_dict(payload.get("exit_rule")),
            risk_rules=dict(payload.get("risk_rules") or {}),
            is_builtin=bool(payload.get("is_builtin", False)),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
        )
