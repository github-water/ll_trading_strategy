from datetime import datetime

import pandas as pd
import pytest

from common.backtest_models import BacktestConfig, PositionSizingMode
from common.strategy_models import TradingStrategy
from service.backtest_engine import BacktestEngine
from service.strategy_indicator_engine import StrategyIndicatorEngine


def frame(rows):
    data = pd.DataFrame(rows)
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    defaults = {
        "volume": 1_000_000,
        "entry_signal": False,
        "exit_signal": False,
    }
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
    if "pre_close" not in data:
        data["pre_close"] = data["close"].shift(1).fillna(data["close"])
    return data


def strategy_with_stops(initial=True, trailing=True, initial_multiple=2.0, trailing_multiple=3.0):
    strategy = TradingStrategy.new(name="回测策略")
    strategy.risk_rules = {
        "initial_atr_stop": {"enabled": initial, "period": 2, "multiple": initial_multiple},
        "trailing_atr_stop": {"enabled": trailing, "period": 2, "multiple": trailing_multiple},
    }
    return strategy


def add_atr(data, values, period=2):
    data[StrategyIndicatorEngine.atr_column(period)] = values
    return data


def zero_cost_config(**kwargs):
    return BacktestConfig(
        initial_cash=100_000,
        position_mode=PositionSizingMode.FULL,
        commission_rate=0,
        minimum_commission=0,
        buy_slippage=0,
        sell_slippage=0,
        **kwargs,
    )


def test_signals_execute_at_next_open_and_last_day_signal_is_not_executed():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10},
            {"trade_date": "2024-01-03", "open": 12, "high": 13, "low": 11, "close": 12, "exit_signal": True},
            {"trade_date": "2024-01-04", "open": 12, "high": 13, "low": 11, "close": 12, "entry_signal": True},
        ]
    )
    result = BacktestEngine().run(data, strategy_with_stops(False, False), zero_cost_config())
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["buy_date"] == "2024-01-02"
    assert trade["sell_date"] == "2024-01-04"
    assert result.open_position == {}


def test_pending_buy_is_cancelled_when_entry_condition_becomes_false():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 10, "low": 10, "close": 10, "pre_close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 11, "high": 11, "low": 11, "close": 11, "pre_close": 10, "entry_signal": False},
            {"trade_date": "2024-01-03", "open": 10, "high": 11, "low": 9, "close": 10, "pre_close": 11, "entry_signal": False},
        ]
    )
    result = BacktestEngine().run(data, strategy_with_stops(False, False), zero_cost_config())
    assert result.trades.empty
    assert "待买订单因入场条件失效而取消" in result.events["message"].tolist()


def test_pending_sell_persists_until_tradeable_even_if_exit_signal_recovers():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "pre_close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "pre_close": 10, "exit_signal": True},
            {"trade_date": "2024-01-03", "open": 9, "high": 9, "low": 9, "close": 9, "pre_close": 10, "exit_signal": False},
            {"trade_date": "2024-01-04", "open": 9.5, "high": 10, "low": 9, "close": 9.5, "pre_close": 9, "exit_signal": False},
        ]
    )
    result = BacktestEngine().run(data, strategy_with_stops(False, False), zero_cost_config())
    assert result.trades.iloc[0]["sell_date"] == "2024-01-04"
    assert result.trades.iloc[0]["exit_reason"] == "策略退出"


def test_sell_day_cooldown_prevents_same_day_reentry_signal():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "exit_signal": True},
            {"trade_date": "2024-01-03", "open": 11, "high": 12, "low": 10, "close": 11, "entry_signal": True},
            {"trade_date": "2024-01-04", "open": 11, "high": 12, "low": 10, "close": 11, "entry_signal": True},
            {"trade_date": "2024-01-05", "open": 11, "high": 12, "low": 10, "close": 11},
        ]
    )
    result = BacktestEngine().run(data, strategy_with_stops(False, False), zero_cost_config())
    # First trade sells Jan 3. Jan 3 close entry is ignored; Jan 4 close creates order for Jan 5.
    assert result.trades.iloc[0]["sell_date"] == "2024-01-03"
    assert result.open_position["buy_date"] == "2024-01-05"


def test_gap_below_atr_stop_uses_open_and_intraday_touch_uses_stop_price():
    gap = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 10.5, "low": 9.5, "close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 10.5, "low": 9.5, "close": 10},
            {"trade_date": "2024-01-03", "open": 7, "high": 8, "low": 6, "close": 7},
        ]
    )
    add_atr(gap, [1, 1, 1])
    result = BacktestEngine().run(gap, strategy_with_stops(True, False, initial_multiple=2), zero_cost_config())
    assert result.trades.iloc[0]["sell_price"] == 7
    assert result.trades.iloc[0]["exit_reason"] == "ATR止损-跳空"

    touch = gap.astype({"open": float, "high": float, "low": float, "close": float}).copy()
    touch.loc[2, ["open", "high", "low", "close"]] = [9.0, 9.5, 7.5, 8.5]
    result = BacktestEngine().run(touch, strategy_with_stops(True, False, initial_multiple=2), zero_cost_config())
    assert result.trades.iloc[0]["sell_price"] == 8
    assert result.trades.iloc[0]["exit_reason"] == "ATR止损-盘中"


def test_trailing_stop_calculated_at_close_becomes_active_next_day():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 10, "low": 9, "close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 12, "low": 9, "close": 11},
            {"trade_date": "2024-01-03", "open": 11, "high": 11, "low": 9.5, "close": 10},
        ]
    )
    add_atr(data, [1, 1, 1])
    strategy = strategy_with_stops(True, True, initial_multiple=3, trailing_multiple=2)
    result = BacktestEngine().run(data, strategy, zero_cost_config())
    assert result.trades.iloc[0]["sell_date"] == "2024-01-03"
    assert result.trades.iloc[0]["sell_price"] == 10
    assert result.trades.iloc[0]["exit_reason"] == "ATR止损-盘中"


def test_end_of_backtest_marks_open_position_without_forced_sale_and_charges_costs():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10},
            {"trade_date": "2024-01-03", "open": 11, "high": 12, "low": 10, "close": 11},
        ]
    )
    config = BacktestConfig(position_mode=PositionSizingMode.FULL)
    result = BacktestEngine().run(data, strategy_with_stops(False, False), config)
    assert result.trades.empty
    assert result.open_position["quantity"] > 0
    assert result.open_position["market_value"] == pytest.approx(
        result.open_position["quantity"] * 11
    )
    assert result.metrics["final_equity"] == pytest.approx(result.equity_curve.iloc[-1]["equity"])
    assert result.metrics["commission_total"] >= 5


def test_transaction_costs_include_both_commissions_and_both_slippages():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "exit_signal": True},
            {"trade_date": "2024-01-03", "open": 12.0, "high": 13.0, "low": 11.0, "close": 12.0},
        ]
    )
    config = BacktestConfig(position_mode=PositionSizingMode.FULL)
    result = BacktestEngine().run(data, strategy_with_stops(False, False), config)
    trade = result.trades.iloc[0]
    quantity = int(trade["quantity"])
    expected_buy_slippage = (10.0 * config.buy_slippage) * quantity
    expected_sell_slippage = (12.0 * config.sell_slippage) * quantity
    assert result.metrics["slippage_cost"] == pytest.approx(
        expected_buy_slippage + expected_sell_slippage
    )
    assert result.metrics["commission_total"] == pytest.approx(
        trade["buy_commission"] + trade["sell_commission"]
    )


def test_atr_risk_signal_before_atr_is_ready_is_cancelled_not_fatal():
    data = frame(
        [
            {"trade_date": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "entry_signal": True},
            {"trade_date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
            {"trade_date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
        ]
    )
    add_atr(data, [float("nan"), 1.0, 1.0])
    config = BacktestConfig(
        position_mode=PositionSizingMode.ATR_RISK,
        commission_rate=0,
        minimum_commission=0,
        buy_slippage=0,
        sell_slippage=0,
    )
    result = BacktestEngine().run(data, strategy_with_stops(True, False), config)
    assert result.trades.empty
    assert not result.open_position
    assert "ATR尚未形成，取消待买订单" in result.events["message"].tolist()
