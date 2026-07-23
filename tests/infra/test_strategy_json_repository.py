from pathlib import Path

import pytest

from common.config import Settings
from common.exceptions import StrategyNotFoundError
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from infra.storage.strategy_json_repository import LocalStrategyJsonRepository


def make_strategy(strategy_id: str, name: str) -> TradingStrategy:
    return TradingStrategy(
        strategy_id=strategy_id,
        name=name,
        entry_rule=RuleSet(
            operator="AND",
            rules=[
                StrategyRule.create(
                    group="默认组",
                    group_operator="AND",
                    left=Operand.field("close"),
                    operator=">",
                    right=Operand.indicator("SMA", {"field": "close", "period": 20}),
                )
            ],
        ),
        exit_rule=RuleSet(operator="OR", rules=[]),
    )


def test_repository_seeds_builtin_strategy(tmp_path: Path):
    repo = LocalStrategyJsonRepository(Settings(strategy_dir=tmp_path / "strategies"))
    strategies = repo.list_all()
    assert any(item.is_builtin and item.name == "ETF趋势突破策略" for item in strategies)


def test_repository_saves_loads_and_lists_strategy(tmp_path: Path):
    repo = LocalStrategyJsonRepository(Settings(strategy_dir=tmp_path / "strategies"))
    strategy = make_strategy("11111111-1111-4111-8111-111111111111", "测试策略")
    path = repo.save(strategy)
    assert path.name == f"{strategy.strategy_id}.json"
    assert repo.get(strategy.strategy_id).name == "测试策略"
    assert any(item.strategy_id == strategy.strategy_id for item in repo.list_all())


def test_repository_name_exists_is_trimmed_and_case_insensitive(tmp_path: Path):
    repo = LocalStrategyJsonRepository(Settings(strategy_dir=tmp_path / "strategies"))
    strategy = make_strategy("11111111-1111-4111-8111-111111111111", "ETF Alpha")
    repo.save(strategy)
    assert repo.name_exists("  etf alpha  ")
    assert not repo.name_exists("ETF Alpha", excluding_id=strategy.strategy_id)


def test_repository_delete_and_missing_lookup(tmp_path: Path):
    repo = LocalStrategyJsonRepository(Settings(strategy_dir=tmp_path / "strategies"))
    strategy = make_strategy("11111111-1111-4111-8111-111111111111", "测试策略")
    repo.save(strategy)
    repo.delete(strategy.strategy_id)
    with pytest.raises(StrategyNotFoundError):
        repo.get(strategy.strategy_id)
