from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from common.config import Settings
from common.exceptions import StrategyNotFoundError, StrategyStorageError
from common.strategy_models import (
    Operand,
    RuleSet,
    StrategyRule,
    TradingStrategy,
    normalize_strategy_name,
)

BUILTIN_STRATEGY_ID = "00000000-0000-4000-8000-000000000001"


def _rule(
    left: Operand,
    operator: str,
    right: Operand,
    *,
    group: str,
    group_operator: str = "AND",
) -> StrategyRule:
    return StrategyRule.create(
        group=group,
        group_operator=group_operator,
        left=left,
        operator=operator,
        right=right,
    )


def build_builtin_etf_trend_strategy() -> TradingStrategy:
    trend_rules = [
        _rule(Operand.field("close"), ">", Operand.indicator("SMA", {"field": "close", "period": 250}), group="长期趋势"),
        _rule(Operand.indicator("SMA", {"field": "close", "period": 60}), ">", Operand.indicator("SMA", {"field": "close", "period": 250}), group="长期趋势"),
        _rule(Operand.indicator("MA_SLOPE", {"field": "close", "period": 250, "lookback": 20}), ">", Operand.constant(0), group="长期趋势"),
        _rule(Operand.indicator("SMA", {"field": "close", "period": 20}), ">", Operand.indicator("SMA", {"field": "close", "period": 60}), group="均线排列"),
        _rule(Operand.field("close"), ">", Operand.indicator("SMA", {"field": "close", "period": 20}), group="均线排列"),
        _rule(Operand.field("close"), ">", Operand.indicator("HHV", {"field": "high", "period": 55, "exclude_current": True}), group="突破确认"),
        _rule(Operand.indicator("MACD_DIF", {"field": "close", "fast": 12, "slow": 26, "signal": 9}), ">", Operand.indicator("MACD_DEA", {"field": "close", "fast": 12, "slow": 26, "signal": 9}), group="动量确认"),
        _rule(Operand.indicator("MACD_HIST", {"field": "close", "fast": 12, "slow": 26, "signal": 9}), ">", Operand.constant(0), group="动量确认"),
        _rule(Operand.indicator("ADX", {"period": 14}), ">=", Operand.constant(20), group="趋势强度"),
        _rule(Operand.indicator("PLUS_DI", {"period": 14}), ">", Operand.indicator("MINUS_DI", {"period": 14}), group="趋势强度"),
        _rule(Operand.field("volume"), ">", Operand.indicator("VOLUME_MA", {"period": 20, "multiplier": 1.2}), group="成交量确认"),
    ]
    exit_rules = [
        _rule(Operand.field("close"), "<", Operand.indicator("SMA", {"field": "close", "period": 20}), group="趋势退出", group_operator="OR"),
        _rule(Operand.indicator("SMA", {"field": "close", "period": 20}), "CROSS_BELOW", Operand.indicator("SMA", {"field": "close", "period": 60}), group="趋势退出", group_operator="OR"),
    ]
    return TradingStrategy(
        strategy_id=BUILTIN_STRATEGY_ID,
        name="ETF趋势突破策略",
        description="中期趋势、55日突破、MACD、ADX与成交量共同确认的仅做多日线策略。",
        asset_type="ETF",
        direction="long_only",
        timeframe="1d",
        execution="next_open",
        enabled=True,
        entry_rule=RuleSet(operator="AND", rules=trend_rules),
        exit_rule=RuleSet(operator="OR", rules=exit_rules),
        risk_rules={
            "initial_atr_stop": {"enabled": True, "period": 14, "multiple": 2.0},
            "trailing_atr_stop": {"enabled": True, "period": 14, "multiple": 3.0},
        },
        is_builtin=True,
    )


class LocalStrategyJsonRepository:
    def __init__(self, settings: Settings) -> None:
        self.strategy_dir = Path(settings.strategy_dir)
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_builtin()

    def list_all(self) -> list[TradingStrategy]:
        strategies: list[TradingStrategy] = []
        for path in self.strategy_dir.glob("*.json"):
            try:
                strategies.append(self._read_path(path))
            except StrategyStorageError:
                raise
        return sorted(
            strategies,
            key=lambda item: (not item.is_builtin, normalize_strategy_name(item.name)),
        )

    def get(self, strategy_id: str) -> TradingStrategy:
        path = self.path_for(strategy_id)
        if not path.exists():
            raise StrategyNotFoundError(f"策略 {strategy_id} 不存在。")
        return self._read_path(path)

    def save(self, strategy: TradingStrategy) -> Path:
        path = self.path_for(strategy.strategy_id)
        payload = json.dumps(
            strategy.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.strategy_dir,
                prefix=f".{strategy.strategy_id}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.write("\n")
                temp_path = Path(handle.name)
            os.replace(temp_path, path)
        except OSError as exc:
            try:
                if "temp_path" in locals() and temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise StrategyStorageError(f"保存策略失败：{exc}") from exc
        return path

    def delete(self, strategy_id: str) -> None:
        path = self.path_for(strategy_id)
        if not path.exists():
            raise StrategyNotFoundError(f"策略 {strategy_id} 不存在。")
        try:
            path.unlink()
        except OSError as exc:
            raise StrategyStorageError(f"删除策略失败：{exc}") from exc

    def name_exists(self, name: str, *, excluding_id: str | None = None) -> bool:
        normalized = normalize_strategy_name(name)
        return any(
            item.strategy_id != excluding_id
            and normalize_strategy_name(item.name) == normalized
            for item in self.list_all()
        )

    def path_for(self, strategy_id: str) -> Path:
        safe_id = str(strategy_id).strip()
        if not safe_id or any(char in safe_id for char in ("/", "\\", "..")):
            raise StrategyStorageError("无效的策略 ID。")
        return self.strategy_dir / f"{safe_id}.json"

    def _read_path(self, path: Path) -> TradingStrategy:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("根节点必须是 JSON 对象")
            return TradingStrategy.from_dict(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise StrategyStorageError(f"读取策略文件 {path.name} 失败：{exc}") from exc

    def _ensure_builtin(self) -> None:
        path = self.path_for(BUILTIN_STRATEGY_ID)
        if not path.exists():
            self.save(build_builtin_etf_trend_strategy())
