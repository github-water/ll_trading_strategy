import json
from pathlib import Path

import pytest

from common.config import Settings
from common.exceptions import StrategyNameConflictError, StrategyReadOnlyError
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from infra.storage.strategy_json_repository import LocalStrategyJsonRepository
from service.strategy_management_service import StrategyManagementService


def build_service(tmp_path: Path) -> StrategyManagementService:
    return StrategyManagementService(
        LocalStrategyJsonRepository(Settings(strategy_dir=tmp_path / "strategies"))
    )


def make_strategy(name="策略A"):
    return TradingStrategy(
        strategy_id="11111111-1111-4111-8111-111111111111",
        name=name,
        entry_rule=RuleSet(
            operator="AND",
            rules=[
                StrategyRule.create(
                    group="趋势组",
                    group_operator="AND",
                    left=Operand.field("close"),
                    operator=">",
                    right=Operand.indicator("SMA", {"field": "close", "period": 20}),
                )
            ],
        ),
        exit_rule=RuleSet(operator="OR", rules=[]),
    )


def test_save_and_rename_preserves_strategy_id(tmp_path):
    service = build_service(tmp_path)
    saved = service.save_strategy(make_strategy())
    saved.name = "策略A优化版"
    renamed = service.save_strategy(saved)
    assert renamed.strategy_id == "11111111-1111-4111-8111-111111111111"
    assert service.get_strategy(renamed.strategy_id).name == "策略A优化版"


def test_duplicate_name_is_rejected_case_insensitively(tmp_path):
    service = build_service(tmp_path)
    service.save_strategy(make_strategy("ETF Alpha"))
    duplicate = make_strategy(" etf alpha ")
    duplicate.strategy_id = "22222222-2222-4222-8222-222222222222"
    with pytest.raises(StrategyNameConflictError):
        service.save_strategy(duplicate)


def test_copy_generates_new_id_and_unique_name(tmp_path):
    service = build_service(tmp_path)
    source = service.save_strategy(make_strategy("趋势策略"))
    first = service.copy_strategy(source.strategy_id)
    second = service.copy_strategy(source.strategy_id)
    assert first.strategy_id != source.strategy_id
    assert first.name == "趋势策略 - 副本"
    assert second.name == "趋势策略 - 副本 2"


def test_builtin_strategy_cannot_be_saved_or_deleted(tmp_path):
    service = build_service(tmp_path)
    builtin = next(item for item in service.list_strategies() if item.is_builtin)
    builtin.name = "改名"
    with pytest.raises(StrategyReadOnlyError):
        service.save_strategy(builtin)
    with pytest.raises(StrategyReadOnlyError):
        service.delete_strategy(builtin.strategy_id)


def test_toggle_and_import_assigns_new_identity(tmp_path):
    service = build_service(tmp_path)
    saved = service.save_strategy(make_strategy("导入源"))
    toggled = service.toggle_strategy(saved.strategy_id)
    assert toggled.enabled is False

    source_file = tmp_path / "import.json"
    source_file.write_text(json.dumps(saved.to_dict(), ensure_ascii=False), encoding="utf-8")
    imported = service.import_strategy(source_file)
    assert imported.strategy_id != saved.strategy_id
    assert imported.name == "导入源 - 副本"
    assert imported.is_builtin is False


def test_export_returns_existing_json_file(tmp_path):
    service = build_service(tmp_path)
    saved = service.save_strategy(make_strategy("导出策略"))
    path = service.export_strategy(saved.strategy_id, tmp_path / "exports")
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "导出策略"
