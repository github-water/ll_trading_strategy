from __future__ import annotations

import math

from common.backtest_models import BacktestConfig, PositionSizingMode
from common.exceptions import BacktestValidationError


class PositionSizingService:
    def calculate_quantity(
        self,
        *,
        cash: float,
        equity: float,
        execution_price: float,
        atr: float | None,
        config: BacktestConfig,
        initial_atr_multiple: float | None,
    ) -> int:
        if cash <= 0 or equity <= 0 or execution_price <= 0:
            return 0

        cash_limit = self._cash_quantity(cash, execution_price, config)
        if config.position_mode == PositionSizingMode.FULL:
            return cash_limit

        if atr is None or not math.isfinite(float(atr)) or atr <= 0:
            raise BacktestValidationError("ATR风险仓位需要有效的ATR值。")
        if initial_atr_multiple is None or initial_atr_multiple <= 0:
            raise BacktestValidationError("ATR风险仓位需要有效的初始止损倍数。")

        risk_amount = equity * config.risk_per_trade
        stop_distance = float(atr) * float(initial_atr_multiple)
        risk_quantity = self._round_lot(risk_amount / stop_distance, config.lot_size)
        position_quantity = self._round_lot(
            equity * config.maximum_position / execution_price,
            config.lot_size,
        )
        return max(0, min(risk_quantity, position_quantity, cash_limit))

    @staticmethod
    def _round_lot(raw_quantity: float, lot_size: int) -> int:
        if raw_quantity <= 0:
            return 0
        return int(raw_quantity // lot_size) * lot_size

    def _cash_quantity(
        self,
        cash: float,
        execution_price: float,
        config: BacktestConfig,
    ) -> int:
        quantity = self._round_lot(cash / execution_price, config.lot_size)
        while quantity > 0:
            amount = quantity * execution_price
            commission = max(amount * config.commission_rate, config.minimum_commission)
            if amount + commission <= cash + 1e-9:
                return quantity
            quantity -= config.lot_size
        return 0
