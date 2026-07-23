import pytest

from common.backtest_models import BacktestConfig, PositionSizingMode
from common.exceptions import BacktestValidationError
from service.position_sizing_service import PositionSizingService


def test_full_position_reserves_minimum_commission_and_lot_size():
    config = BacktestConfig(position_mode=PositionSizingMode.FULL)
    quantity = PositionSizingService().calculate_quantity(
        cash=100_000,
        equity=100_000,
        execution_price=2.0,
        atr=None,
        config=config,
        initial_atr_multiple=None,
    )
    assert quantity == 49_900
    total = quantity * 2.0
    commission = max(total * config.commission_rate, config.minimum_commission)
    assert total + commission <= 100_000


def test_atr_risk_quantity_uses_smallest_of_risk_position_and_cash_limits():
    config = BacktestConfig(
        position_mode=PositionSizingMode.ATR_RISK,
        risk_per_trade=0.01,
        maximum_position=0.30,
    )
    quantity = PositionSizingService().calculate_quantity(
        cash=100_000,
        equity=100_000,
        execution_price=2.0,
        atr=0.10,
        config=config,
        initial_atr_multiple=2.5,
    )
    # Risk cap = 1000 / 0.25 = 4000 shares; max position allows 15000.
    assert quantity == 4_000


def test_atr_risk_requires_valid_atr():
    config = BacktestConfig(position_mode=PositionSizingMode.ATR_RISK)
    with pytest.raises(BacktestValidationError, match="ATR"):
        PositionSizingService().calculate_quantity(
            cash=100_000,
            equity=100_000,
            execution_price=2.0,
            atr=None,
            config=config,
            initial_atr_multiple=2.5,
        )


def test_backtest_config_rejects_invalid_cost_parameters():
    with pytest.raises(BacktestValidationError):
        BacktestConfig(initial_cash=0)
    with pytest.raises(BacktestValidationError):
        BacktestConfig(commission_rate=-0.1)
