from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.backtest_models import BacktestConfig, BacktestResult, TradeRecord
from common.exceptions import BacktestExecutionError, BacktestValidationError
from common.strategy_models import TradingStrategy
from service.position_sizing_service import PositionSizingService
from service.strategy_indicator_engine import StrategyIndicatorEngine


@dataclass
class _OpenTrade:
    trade_id: int
    buy_signal_date: str
    buy_date: str
    buy_index: int
    base_buy_price: float
    buy_price: float
    quantity: int
    buy_commission: float
    buy_slippage_cost: float
    total_cost: float
    highest_price: float
    stop_price: float | None


class BacktestEngine:
    """Execute precomputed daily signals with an event-driven order loop."""

    def __init__(self, position_sizing: PositionSizingService | None = None) -> None:
        self._position_sizing = position_sizing or PositionSizingService()

    def run(
        self,
        data: pd.DataFrame,
        strategy: TradingStrategy,
        config: BacktestConfig,
        *,
        symbol: str = "",
        source_path: str | Path = "",
    ) -> BacktestResult:
        frame = self._validate_data(data)
        initial_period, initial_multiple, initial_enabled = self._initial_stop(strategy, config)
        trailing_period, trailing_multiple, trailing_enabled = self._trailing_stop(strategy, config)
        if config.position_mode.value == "atr_risk" and not initial_enabled:
            raise BacktestValidationError("ATR风险仓位要求策略启用初始ATR止损。")

        cash = float(config.initial_cash)
        position: _OpenTrade | None = None
        pending_buy: dict[str, Any] | None = None
        pending_sell: dict[str, Any] | None = None
        completed: list[TradeRecord] = []
        events: list[dict[str, Any]] = []
        equity_rows: list[dict[str, Any]] = []
        stop_rows: list[float | None] = []
        total_commission = 0.0
        total_slippage = 0.0
        next_trade_id = 1

        for index, row in frame.iterrows():
            date_text = self._date_text(row["trade_date"])
            sold_today = False

            # Existing position: gap stop has priority over an ordinary pending sell.
            if position is not None and position.stop_price is not None:
                if float(row["open"]) <= position.stop_price and self._can_sell(row, config):
                    cash, record, commission, slippage = self._close_position(
                        position,
                        row,
                        index,
                        cash,
                        base_price=float(row["open"]),
                        signal_date=date_text,
                        reason="ATR止损-跳空",
                        config=config,
                    )
                    completed.append(record)
                    total_commission += commission
                    total_slippage += slippage
                    events.append(self._event(date_text, "SELL", "ATR跳空止损成交"))
                    position = None
                    pending_sell = None
                    sold_today = True

            # Ordinary exit orders are persistent once generated.
            if position is not None and pending_sell is not None and not sold_today:
                if self._can_sell(row, config):
                    cash, record, commission, slippage = self._close_position(
                        position,
                        row,
                        index,
                        cash,
                        base_price=float(row["open"]),
                        signal_date=str(pending_sell["signal_date"]),
                        reason=str(pending_sell["reason"]),
                        config=config,
                    )
                    completed.append(record)
                    total_commission += commission
                    total_slippage += slippage
                    events.append(self._event(date_text, "SELL", "待卖订单成交"))
                    position = None
                    pending_sell = None
                    sold_today = True
                else:
                    events.append(self._event(date_text, "WAIT_SELL", "无法卖出，订单继续顺延"))

            # Entry orders execute at the next tradeable open.
            if position is None and pending_buy is not None and not sold_today:
                if self._can_buy(row, config):
                    base_price = float(row["open"])
                    execution_price = base_price * (1.0 + config.buy_slippage)
                    atr_value = self._atr_at_signal(
                        frame,
                        int(pending_buy["signal_index"]),
                        initial_period,
                    ) if initial_enabled else None
                    if initial_enabled and atr_value is None:
                        events.append(
                            self._event(date_text, "CANCEL_BUY", "ATR尚未形成，取消待买订单")
                        )
                        pending_buy = None
                        quantity = 0
                    else:
                        quantity = self._position_sizing.calculate_quantity(
                            cash=cash,
                            equity=cash,
                            execution_price=execution_price,
                            atr=atr_value,
                            config=config,
                            initial_atr_multiple=initial_multiple if initial_enabled else None,
                        )
                    if quantity > 0:
                        amount = quantity * execution_price
                        commission = self._commission(amount, config)
                        total_cost = amount + commission
                        cash -= total_cost
                        slippage = (execution_price - base_price) * quantity
                        total_commission += commission
                        total_slippage += slippage
                        stop_price = (
                            execution_price - float(atr_value) * float(initial_multiple)
                            if initial_enabled and atr_value is not None
                            else None
                        )
                        position = _OpenTrade(
                            trade_id=next_trade_id,
                            buy_signal_date=str(pending_buy["signal_date"]),
                            buy_date=date_text,
                            buy_index=index,
                            base_buy_price=base_price,
                            buy_price=execution_price,
                            quantity=quantity,
                            buy_commission=commission,
                            buy_slippage_cost=slippage,
                            total_cost=total_cost,
                            highest_price=float(row["high"]),
                            stop_price=stop_price,
                        )
                        next_trade_id += 1
                        events.append(self._event(date_text, "BUY", f"买入 {quantity} 份"))
                        pending_buy = None
                    elif pending_buy is not None:
                        events.append(self._event(date_text, "CANCEL_BUY", "可买数量不足一个交易单位"))
                        pending_buy = None
                else:
                    events.append(self._event(date_text, "WAIT_BUY", "无法买入，等待条件复核"))

            # Intraday stop is checked after an opening buy and after pending orders.
            if position is not None and not sold_today and position.stop_price is not None:
                if float(row["low"]) <= position.stop_price:
                    if self._can_sell(row, config):
                        cash, record, commission, slippage = self._close_position(
                            position,
                            row,
                            index,
                            cash,
                            base_price=float(position.stop_price),
                            signal_date=date_text,
                            reason="ATR止损-盘中",
                            config=config,
                        )
                        completed.append(record)
                        total_commission += commission
                        total_slippage += slippage
                        events.append(self._event(date_text, "SELL", "ATR盘中止损成交"))
                        position = None
                        pending_sell = None
                        sold_today = True
                    else:
                        pending_sell = pending_sell or {
                            "signal_date": date_text,
                            "reason": "ATR止损顺延",
                        }
                        events.append(self._event(date_text, "WAIT_SELL", "ATR止损无法成交，转待卖"))

            # Close-time state updates and new signals. Last-day signals are ignored.
            if position is not None:
                position.highest_price = max(position.highest_price, float(row["high"]))
                if trailing_enabled:
                    atr_value = self._atr_at_row(frame, index, trailing_period)
                    if atr_value is not None:
                        candidate = position.highest_price - atr_value * float(trailing_multiple)
                        position.stop_price = (
                            candidate
                            if position.stop_price is None
                            else max(position.stop_price, candidate)
                        )

            is_last = index == len(frame) - 1
            if not is_last:
                if position is not None and pending_sell is None and bool(row["exit_signal"]):
                    pending_sell = {"signal_date": date_text, "reason": "策略退出"}
                    events.append(self._event(date_text, "SIGNAL_SELL", "生成退出信号"))
                elif position is None and not sold_today:
                    if pending_buy is not None:
                        if not bool(row["entry_signal"]):
                            pending_buy = None
                            events.append(
                                self._event(date_text, "CANCEL_BUY", "待买订单因入场条件失效而取消")
                            )
                    elif bool(row["entry_signal"]):
                        pending_buy = {"signal_date": date_text, "signal_index": index}
                        events.append(self._event(date_text, "SIGNAL_BUY", "生成入场信号"))

            equity = cash + (position.quantity * float(row["close"]) if position else 0.0)
            equity_rows.append(
                {
                    "trade_date": row["trade_date"],
                    "cash": cash,
                    "position_value": position.quantity * float(row["close"]) if position else 0.0,
                    "equity": equity,
                    "quantity": position.quantity if position else 0,
                }
            )
            stop_rows.append(position.stop_price if position else np.nan)

        frame = frame.copy()
        frame["active_stop"] = stop_rows
        equity_curve = pd.DataFrame(equity_rows)
        trade_columns = list(TradeRecord.__dataclass_fields__)
        trades = pd.DataFrame(
            [trade.to_dict() for trade in completed],
            columns=trade_columns,
        )
        events_frame = pd.DataFrame(events, columns=["trade_date", "event", "message"])
        metrics = self._metrics(
            equity_curve,
            trades,
            config,
            total_commission=total_commission,
            total_slippage=total_slippage,
        )
        open_position = self._open_position(position, frame.iloc[-1], cash) if position else {}
        if open_position:
            metrics["unrealized_profit"] = open_position["unrealized_profit"]
        else:
            metrics["unrealized_profit"] = 0.0

        return BacktestResult(
            symbol=symbol,
            strategy_name=strategy.name,
            source_path=Path(source_path) if source_path else Path(),
            config=config,
            data=frame,
            equity_curve=equity_curve,
            benchmark_curve=pd.DataFrame(),
            drawdown_curve=self._drawdown(equity_curve),
            trades=trades,
            events=events_frame,
            metrics=metrics,
            open_position=open_position,
        )

    @staticmethod
    def _validate_data(data: pd.DataFrame) -> pd.DataFrame:
        required = {
            "trade_date", "open", "high", "low", "close", "volume",
            "entry_signal", "exit_signal",
        }
        missing = required.difference(data.columns)
        if missing:
            raise BacktestValidationError("回测数据缺少字段：" + ", ".join(sorted(missing)))
        frame = data.copy().reset_index(drop=True)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
        for column in ("open", "high", "low", "close", "volume", "pre_close"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["entry_signal"] = frame["entry_signal"].map(
            lambda value: False if pd.isna(value) else bool(value)
        ).astype(bool)
        frame["exit_signal"] = frame["exit_signal"].map(
            lambda value: False if pd.isna(value) else bool(value)
        ).astype(bool)
        if frame["trade_date"].isna().any() or frame[["open", "high", "low", "close"]].isna().any().any():
            raise BacktestValidationError("回测行情包含无效日期或价格。")
        if frame.empty:
            raise BacktestValidationError("没有可用于回测的行情。")
        return frame

    @staticmethod
    def _initial_stop(strategy: TradingStrategy, config: BacktestConfig) -> tuple[int, float, bool]:
        rule = strategy.risk_rules.get("initial_atr_stop") or {}
        enabled = bool(rule.get("enabled", False))
        period = int(config.atr_period_override or rule.get("period", 14))
        multiple = float(config.initial_atr_multiple_override or rule.get("multiple", 2.0))
        return period, multiple, enabled

    @staticmethod
    def _trailing_stop(strategy: TradingStrategy, config: BacktestConfig) -> tuple[int, float, bool]:
        rule = strategy.risk_rules.get("trailing_atr_stop") or {}
        enabled = bool(rule.get("enabled", False))
        period = int(config.atr_period_override or rule.get("period", 14))
        multiple = float(config.trailing_atr_multiple_override or rule.get("multiple", 3.0))
        return period, multiple, enabled

    @staticmethod
    def _atr_at_signal(frame: pd.DataFrame, index: int, period: int) -> float | None:
        return BacktestEngine._atr_at_row(frame, index, period)

    @staticmethod
    def _atr_at_row(frame: pd.DataFrame, index: int, period: int) -> float | None:
        column = StrategyIndicatorEngine.atr_column(period)
        if column not in frame.columns:
            raise BacktestValidationError(f"回测数据缺少 ATR({period})。")
        value = frame.at[index, column]
        if pd.isna(value) or not math.isfinite(float(value)) or float(value) <= 0:
            return None
        return float(value)

    @staticmethod
    def _commission(amount: float, config: BacktestConfig) -> float:
        if amount <= 0:
            return 0.0
        return max(amount * config.commission_rate, config.minimum_commission)

    def _close_position(
        self,
        position: _OpenTrade,
        row: pd.Series,
        index: int,
        cash: float,
        *,
        base_price: float,
        signal_date: str,
        reason: str,
        config: BacktestConfig,
    ) -> tuple[float, TradeRecord, float, float]:
        sell_price = base_price * (1.0 - config.sell_slippage)
        amount = position.quantity * sell_price
        commission = self._commission(amount, config)
        stamp_duty = amount * config.stamp_duty
        proceeds = amount - commission - stamp_duty
        cash += proceeds
        sell_slippage_cost = (base_price - sell_price) * position.quantity
        total_slippage = position.buy_slippage_cost + sell_slippage_cost
        net_profit = proceeds - position.total_cost
        return_rate = net_profit / position.total_cost if position.total_cost else 0.0
        record = TradeRecord(
            trade_id=position.trade_id,
            buy_signal_date=position.buy_signal_date,
            buy_date=position.buy_date,
            buy_price=position.buy_price,
            sell_signal_date=signal_date,
            sell_date=self._date_text(row["trade_date"]),
            sell_price=sell_price,
            quantity=position.quantity,
            holding_days=index - position.buy_index + 1,
            buy_commission=position.buy_commission,
            sell_commission=commission,
            stamp_duty=stamp_duty,
            slippage_cost=total_slippage,
            net_profit=net_profit,
            return_rate=return_rate,
            exit_reason=reason,
        )
        return cash, record, commission, sell_slippage_cost

    @staticmethod
    def can_buy(row: pd.Series, config: BacktestConfig) -> bool:
        return BacktestEngine._can_buy(row, config)

    @staticmethod
    def can_sell(row: pd.Series, config: BacktestConfig) -> bool:
        return BacktestEngine._can_sell(row, config)

    @staticmethod
    def _can_buy(row: pd.Series, config: BacktestConfig) -> bool:
        if not BacktestEngine._base_tradeable(row):
            return False
        return not BacktestEngine._is_one_price_limit(row, config, upper=True)

    @staticmethod
    def _can_sell(row: pd.Series, config: BacktestConfig) -> bool:
        if not BacktestEngine._base_tradeable(row):
            return False
        return not BacktestEngine._is_one_price_limit(row, config, upper=False)

    @staticmethod
    def _base_tradeable(row: pd.Series) -> bool:
        return (
            pd.notna(row.get("open"))
            and float(row["open"]) > 0
            and pd.notna(row.get("volume"))
            and float(row["volume"]) > 0
        )

    @staticmethod
    def _is_one_price_limit(row: pd.Series, config: BacktestConfig, *, upper: bool) -> bool:
        pre_close = row.get("pre_close")
        if pre_close is None or pd.isna(pre_close) or float(pre_close) <= 0:
            return False
        prices = [float(row[name]) for name in ("open", "high", "low", "close")]
        if max(prices) - min(prices) > max(1e-8, abs(prices[0]) * 1e-6):
            return False
        ratio = 1.0 + config.limit_ratio if upper else 1.0 - config.limit_ratio
        limit_price = float(pre_close) * ratio
        tolerance = max(0.01, abs(limit_price) * 0.002)
        return abs(prices[0] - limit_price) <= tolerance

    @staticmethod
    def _event(date_text: str, event: str, message: str) -> dict[str, str]:
        return {"trade_date": date_text, "event": event, "message": message}

    @staticmethod
    def _date_text(value: Any) -> str:
        return pd.Timestamp(value).strftime("%Y-%m-%d")

    @staticmethod
    def _drawdown(equity_curve: pd.DataFrame) -> pd.DataFrame:
        result = equity_curve[["trade_date", "equity"]].copy()
        running_max = result["equity"].cummax()
        result["drawdown"] = result["equity"] / running_max.replace(0, np.nan) - 1.0
        return result[["trade_date", "drawdown"]]

    @staticmethod
    def _metrics(
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        config: BacktestConfig,
        *,
        total_commission: float,
        total_slippage: float,
    ) -> dict[str, Any]:
        final_equity = float(equity_curve.iloc[-1]["equity"])
        cumulative = final_equity / config.initial_cash - 1.0
        start = pd.Timestamp(equity_curve.iloc[0]["trade_date"])
        end = pd.Timestamp(equity_curve.iloc[-1]["trade_date"])
        days = max((end - start).days, 1)
        annualized = (final_equity / config.initial_cash) ** (365.25 / days) - 1.0
        drawdown = BacktestEngine._drawdown(equity_curve)
        completed_count = len(trades)
        if completed_count:
            wins = trades.loc[trades["net_profit"] > 0, "net_profit"]
            losses = trades.loc[trades["net_profit"] < 0, "net_profit"]
            win_rate = len(wins) / completed_count
            avg_win = float(wins.mean()) if not wins.empty else 0.0
            avg_loss = abs(float(losses.mean())) if not losses.empty else 0.0
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else (float("inf") if avg_win > 0 else 0.0)
            average_holding_days = float(trades["holding_days"].mean())
        else:
            win_rate = 0.0
            profit_loss_ratio = 0.0
            average_holding_days = 0.0
        return {
            "initial_cash": config.initial_cash,
            "final_equity": final_equity,
            "cumulative_return": cumulative,
            "annualized_return": annualized,
            "maximum_drawdown": float(drawdown["drawdown"].min()),
            "completed_trades": completed_count,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "average_holding_days": average_holding_days,
            "commission_total": total_commission,
            "slippage_cost": total_slippage,
            "calendar_days": days,
        }

    @staticmethod
    def _open_position(
        position: _OpenTrade,
        last_row: pd.Series,
        cash: float,
    ) -> dict[str, Any]:
        market_value = position.quantity * float(last_row["close"])
        unrealized = market_value - position.total_cost
        return {
            "trade_id": position.trade_id,
            "buy_signal_date": position.buy_signal_date,
            "buy_date": position.buy_date,
            "buy_price": position.buy_price,
            "quantity": position.quantity,
            "cost": position.total_cost,
            "market_value": market_value,
            "unrealized_profit": unrealized,
            "stop_price": position.stop_price,
            "cash": cash,
        }
