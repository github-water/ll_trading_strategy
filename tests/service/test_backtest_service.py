from pathlib import Path

import pandas as pd

from common.backtest_models import BacktestConfig, BacktestRequest
from common.strategy_models import Operand, RuleSet, StrategyRule, TradingStrategy
from service.backtest_engine import BacktestEngine
from service.backtest_service import BacktestService
from service.position_sizing_service import PositionSizingService
from service.strategy_indicator_engine import StrategyIndicatorEngine
from service.strategy_rule_evaluator import StrategyRuleEvaluator


class FakeCsvRepository:
    def __init__(self, latest_path: Path, frames: dict[Path, pd.DataFrame]):
        self.latest_path = latest_path
        self.frames = frames
        self.find_calls = []

    def find_latest(self, symbol: str) -> Path:
        self.find_calls.append(symbol)
        return self.latest_path

    def read(self, path):
        return self.frames[Path(path)].copy()


class FakeStrategyRepository:
    def __init__(self, strategy):
        self.strategy = strategy

    def list_all(self):
        return [self.strategy]

    def get(self, strategy_id):
        assert strategy_id == self.strategy.strategy_id
        return self.strategy


class FakeChartBuilder:
    def build_price(self, result):
        return "price"

    def build_equity(self, result):
        return "equity"

    def build_drawdown(self, result):
        return "drawdown"


def make_strategy():
    strategy = TradingStrategy.new(name="始终持有策略")
    strategy.entry_rule = RuleSet(
        operator="AND",
        rules=[
            StrategyRule.create(
                group="入场",
                group_operator="AND",
                left=Operand.field("close"),
                operator=">",
                right=Operand.constant(0),
            )
        ],
    )
    strategy.exit_rule = RuleSet(operator="OR", rules=[])
    strategy.risk_rules = {}
    return strategy


def make_frame(symbol="510300", start="2024-01-01", rows=10):
    dates = pd.date_range(start, periods=rows, freq="D")
    close = pd.Series(range(10, 10 + rows), dtype=float)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": dates,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "pre_close": close.shift(1).fillna(close.iloc[0]),
            "volume": 1_000_000,
            "amount": 10_000_000,
            "adjust": "raw",
        }
    )


def service(csv_repo, strategy):
    return BacktestService(
        csv_repository=csv_repo,
        strategy_repository=FakeStrategyRepository(strategy),
        indicator_engine=StrategyIndicatorEngine(),
        rule_evaluator=StrategyRuleEvaluator(),
        engine=BacktestEngine(PositionSizingService()),
        chart_builder=FakeChartBuilder(),
    )


def test_uploaded_csv_takes_priority_and_date_range_is_applied(tmp_path):
    latest = tmp_path / "latest.csv"
    uploaded = tmp_path / "uploaded.csv"
    repo = FakeCsvRepository(
        latest,
        {latest: make_frame(rows=5), uploaded: make_frame(rows=10)},
    )
    strategy = make_strategy()
    result = service(repo, strategy).run(
        BacktestRequest(
            symbol="510300",
            csv_path=uploaded,
            strategy_id=strategy.strategy_id,
            start_date="2024-01-03",
            end_date="2024-01-08",
            config=BacktestConfig(
                commission_rate=0,
                minimum_commission=0,
                buy_slippage=0,
                sell_slippage=0,
            ),
        )
    )
    assert repo.find_calls == []
    assert result.source_path == uploaded
    assert result.data["trade_date"].min() == pd.Timestamp("2024-01-03")
    assert result.data["trade_date"].max() == pd.Timestamp("2024-01-08")
    assert result.price_figure == "price"


def test_code_uses_latest_csv_and_builds_buy_hold_benchmark(tmp_path):
    latest = tmp_path / "510300_latest.csv"
    repo = FakeCsvRepository(latest, {latest: make_frame(rows=10)})
    strategy = make_strategy()
    result = service(repo, strategy).run(
        BacktestRequest(
            symbol="510300",
            strategy_id=strategy.strategy_id,
            config=BacktestConfig(
                commission_rate=0,
                minimum_commission=0,
                buy_slippage=0,
                sell_slippage=0,
            ),
        )
    )
    assert repo.find_calls == ["510300"]
    assert len(result.benchmark_curve) == len(result.data)
    assert result.metrics["benchmark_cumulative_return"] > 0
    assert result.metrics["excess_return"] == (
        result.metrics["cumulative_return"]
        - result.metrics["benchmark_cumulative_return"]
    )
    assert result.metrics["annualized_return"] > 0
    assert result.metrics["maximum_drawdown"] <= 0


def test_strategy_choices_include_name_and_id(tmp_path):
    latest = tmp_path / "latest.csv"
    strategy = make_strategy()
    repo = FakeCsvRepository(latest, {latest: make_frame()})
    assert service(repo, strategy).list_strategy_choices() == [
        (strategy.name, strategy.strategy_id)
    ]
