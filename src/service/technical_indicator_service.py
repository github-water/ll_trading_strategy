from __future__ import annotations

import pandas as pd

from common.exceptions import InputValidationError


class TechnicalIndicatorService:
    """Calculate deterministic technical indicators on daily OHLCV data."""

    def calculate(
        self,
        data: pd.DataFrame,
        *,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        boll_period: int = 20,
        boll_std: float = 2.0,
        rsi_period: int = 14,
    ) -> pd.DataFrame:
        self._validate_parameters(
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            boll_period=boll_period,
            boll_std=boll_std,
            rsi_period=rsi_period,
        )

        result = data.copy()
        close = pd.to_numeric(result["close"], errors="coerce")

        for period in (5, 10, 20, 60, 250, 360):
            result[f"ma{period}"] = close.rolling(
                window=period,
                min_periods=period,
            ).mean()

        fast_ema = close.ewm(span=macd_fast, adjust=False).mean()
        slow_ema = close.ewm(span=macd_slow, adjust=False).mean()
        result["macd"] = fast_ema - slow_ema
        result["macd_signal"] = result["macd"].ewm(
            span=macd_signal,
            adjust=False,
        ).mean()
        result["macd_hist"] = result["macd"] - result["macd_signal"]

        result["boll_mid"] = close.rolling(
            window=boll_period,
            min_periods=boll_period,
        ).mean()
        rolling_std = close.rolling(
            window=boll_period,
            min_periods=boll_period,
        ).std(ddof=0)
        result["boll_upper"] = result["boll_mid"] + boll_std * rolling_std
        result["boll_lower"] = result["boll_mid"] - boll_std * rolling_std

        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        average_gain = gain.ewm(
            alpha=1 / rsi_period,
            adjust=False,
            min_periods=rsi_period,
        ).mean()
        average_loss = loss.ewm(
            alpha=1 / rsi_period,
            adjust=False,
            min_periods=rsi_period,
        ).mean()
        relative_strength = average_gain / average_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + relative_strength))
        rsi = rsi.where(average_loss != 0, 100.0)
        rsi = rsi.where(~((average_gain == 0) & (average_loss == 0)), 50.0)
        result["rsi"] = rsi.clip(lower=0, upper=100)

        return result

    @staticmethod
    def _validate_parameters(
        *,
        macd_fast: int,
        macd_slow: int,
        macd_signal: int,
        boll_period: int,
        boll_std: float,
        rsi_period: int,
    ) -> None:
        if macd_fast < 1:
            raise InputValidationError("MACD 快线周期必须大于等于1。")
        if macd_slow <= macd_fast:
            raise InputValidationError("MACD 慢线周期必须大于快线周期。")
        if macd_signal < 1:
            raise InputValidationError("MACD 信号周期必须大于等于1。")
        if boll_period < 2:
            raise InputValidationError("BOLL 周期必须大于等于2。")
        if boll_std <= 0:
            raise InputValidationError("BOLL 标准差倍数必须大于0。")
        if rsi_period < 2:
            raise InputValidationError("RSI 周期必须大于等于2。")
