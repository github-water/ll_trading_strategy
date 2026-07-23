from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from common.exceptions import BacktestValidationError


class PositionSizingMode(str, Enum):
    FULL = "full"
    ATR_RISK = "atr_risk"


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    position_mode: PositionSizingMode = PositionSizingMode.FULL
    risk_per_trade: float = 0.01
    maximum_position: float = 0.30
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    buy_slippage: float = 0.0005
    sell_slippage: float = 0.0005
    stamp_duty: float = 0.0
    lot_size: int = 100
    limit_ratio: float = 0.10
    atr_period_override: int | None = None
    initial_atr_multiple_override: float | None = None
    trailing_atr_multiple_override: float | None = None

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise BacktestValidationError("初始资金必须大于0。")
        if not isinstance(self.position_mode, PositionSizingMode):
            try:
                object.__setattr__(self, "position_mode", PositionSizingMode(self.position_mode))
            except ValueError as exc:
                raise BacktestValidationError("仓位方式不受支持。") from exc
        if not 0 < self.risk_per_trade <= 1:
            raise BacktestValidationError("单笔风险比例必须位于0到1之间。")
        if not 0 < self.maximum_position <= 1:
            raise BacktestValidationError("最大仓位比例必须位于0到1之间。")
        for label, value in (
            ("佣金率", self.commission_rate),
            ("最低佣金", self.minimum_commission),
            ("买入滑点", self.buy_slippage),
            ("卖出滑点", self.sell_slippage),
            ("印花税", self.stamp_duty),
        ):
            if value < 0:
                raise BacktestValidationError(f"{label}不能小于0。")
        if self.lot_size <= 0:
            raise BacktestValidationError("交易单位必须是正整数。")
        if not 0 < self.limit_ratio < 1:
            raise BacktestValidationError("涨跌停比例必须位于0到1之间。")
        if self.atr_period_override is not None and self.atr_period_override <= 0:
            raise BacktestValidationError("ATR周期覆盖值必须大于0。")
        for label, value in (
            ("初始止损倍数", self.initial_atr_multiple_override),
            ("移动止损倍数", self.trailing_atr_multiple_override),
        ):
            if value is not None and value <= 0:
                raise BacktestValidationError(f"{label}必须大于0。")


@dataclass
class TradeRecord:
    trade_id: int
    buy_signal_date: str
    buy_date: str
    buy_price: float
    sell_signal_date: str | None
    sell_date: str | None
    sell_price: float | None
    quantity: int
    holding_days: int | None
    buy_commission: float
    sell_commission: float
    stamp_duty: float
    slippage_cost: float
    net_profit: float | None
    return_rate: float | None
    exit_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "buy_signal_date": self.buy_signal_date,
            "buy_date": self.buy_date,
            "buy_price": self.buy_price,
            "sell_signal_date": self.sell_signal_date,
            "sell_date": self.sell_date,
            "sell_price": self.sell_price,
            "quantity": self.quantity,
            "holding_days": self.holding_days,
            "buy_commission": self.buy_commission,
            "sell_commission": self.sell_commission,
            "stamp_duty": self.stamp_duty,
            "slippage_cost": self.slippage_cost,
            "net_profit": self.net_profit,
            "return_rate": self.return_rate,
            "exit_reason": self.exit_reason,
        }


@dataclass(frozen=True)
class BacktestRequest:
    symbol: str = ""
    csv_path: str | Path | None = None
    strategy_id: str = ""
    start_date: str | None = None
    end_date: str | None = None
    config: BacktestConfig = field(default_factory=BacktestConfig)


@dataclass
class BacktestResult:
    symbol: str
    strategy_name: str
    source_path: Path
    config: BacktestConfig
    data: pd.DataFrame
    equity_curve: pd.DataFrame
    benchmark_curve: pd.DataFrame
    drawdown_curve: pd.DataFrame
    trades: pd.DataFrame
    events: pd.DataFrame
    metrics: dict[str, Any]
    open_position: dict[str, Any]
    price_figure: Any | None = None
    equity_figure: Any | None = None
    drawdown_figure: Any | None = None
