from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from common.exceptions import (
    StrategyNameConflictError,
    StrategyNotFoundError,
    StrategyReadOnlyError,
    StrategyStorageError,
)
from common.strategy_models import TradingStrategy, utc_now_iso
from service.ports import StrategyRepository
from service.strategy_validator import StrategyValidator


class StrategyManagementService:
    def __init__(
        self,
        repository: StrategyRepository,
        validator: StrategyValidator | None = None,
    ) -> None:
        self.repository = repository
        self.validator = validator or StrategyValidator()

    def list_strategies(self) -> list[TradingStrategy]:
        return self.repository.list_all()

    def get_strategy(self, strategy_id: str) -> TradingStrategy:
        return self.repository.get(strategy_id)

    def new_strategy(self) -> TradingStrategy:
        return TradingStrategy.new(name=self._unique_name("新策略"))

    def save_strategy(self, strategy: TradingStrategy) -> TradingStrategy:
        strategy = deepcopy(strategy)
        strategy.name = str(strategy.name).strip()

        existing: TradingStrategy | None = None
        try:
            existing = self.repository.get(strategy.strategy_id)
        except StrategyNotFoundError:
            existing = None

        if (existing and existing.is_builtin) or strategy.is_builtin:
            raise StrategyReadOnlyError("预置策略为只读，请先复制后再编辑。")
        if self.repository.name_exists(strategy.name, excluding_id=strategy.strategy_id):
            raise StrategyNameConflictError(
                f"策略名称“{strategy.name}”已存在，请使用其他名称。"
            )

        if existing:
            strategy.created_at = existing.created_at
        strategy.is_builtin = False
        strategy.updated_at = utc_now_iso()
        self.validator.validate(strategy)
        self.repository.save(strategy)
        return self.repository.get(strategy.strategy_id)

    def copy_strategy(self, strategy_id: str) -> TradingStrategy:
        source = self.repository.get(strategy_id)
        copied = TradingStrategy.from_dict(source.to_dict())
        copied.strategy_id = str(uuid4())
        copied.name = self._unique_name(f"{source.name} - 副本", base_name=source.name)
        copied.is_builtin = False
        copied.enabled = False
        copied.created_at = utc_now_iso()
        copied.updated_at = copied.created_at
        self.validator.validate(copied)
        self.repository.save(copied)
        return self.repository.get(copied.strategy_id)

    def delete_strategy(self, strategy_id: str) -> None:
        strategy = self.repository.get(strategy_id)
        if strategy.is_builtin:
            raise StrategyReadOnlyError("预置策略不能删除。")
        self.repository.delete(strategy_id)

    def toggle_strategy(self, strategy_id: str) -> TradingStrategy:
        strategy = self.repository.get(strategy_id)
        if strategy.is_builtin:
            raise StrategyReadOnlyError("预置策略状态不可修改，请复制后操作。")
        strategy.enabled = not strategy.enabled
        strategy.updated_at = utc_now_iso()
        self.validator.validate(strategy)
        self.repository.save(strategy)
        return self.repository.get(strategy_id)

    def import_strategy(self, source_path: str | Path) -> TradingStrategy:
        path = Path(source_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StrategyStorageError(f"导入策略失败：{exc}") from exc
        if not isinstance(payload, dict):
            raise StrategyStorageError("导入策略失败：JSON 根节点必须是对象。")

        imported = TradingStrategy.from_dict(payload)
        original_name = str(imported.name).strip() or "导入策略"
        imported.strategy_id = str(uuid4())
        imported.name = self._unique_name(original_name, base_name=original_name)
        imported.is_builtin = False
        imported.enabled = False
        imported.created_at = utc_now_iso()
        imported.updated_at = imported.created_at
        self.validator.validate(imported)
        self.repository.save(imported)
        return self.repository.get(imported.strategy_id)

    def export_strategy(self, strategy_id: str, destination_dir: str | Path) -> Path:
        strategy = self.repository.get(strategy_id)
        destination = Path(destination_dir)
        try:
            destination.mkdir(parents=True, exist_ok=True)
            output = destination / f"{strategy.strategy_id}.json"
            output.write_text(
                json.dumps(strategy.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return output
        except OSError as exc:
            raise StrategyStorageError(f"导出策略失败：{exc}") from exc

    def _unique_name(self, candidate: str, *, base_name: str | None = None) -> str:
        candidate = candidate.strip()
        if not self.repository.name_exists(candidate):
            return candidate
        root = (base_name or candidate.removesuffix(" - 副本")).strip()
        first_copy = f"{root} - 副本"
        if not self.repository.name_exists(first_copy):
            return first_copy
        index = 2
        while self.repository.name_exists(f"{root} - 副本 {index}"):
            index += 1
        return f"{root} - 副本 {index}"
