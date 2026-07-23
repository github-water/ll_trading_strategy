import pandas as pd
import pytest

from common.exceptions import InputValidationError
from service.technical_indicator_service import TechnicalIndicatorService


def price_frame(rows: int = 80) -> pd.DataFrame:
    close = pd.Series([100 + i * 0.5 + (i % 5) * 0.2 for i in range(rows)])
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=rows),
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.9,
            "close": close,
            "volume": 1000 + pd.Series(range(rows)) * 10,
        }
    )


def test_calculate_adds_macd_boll_and_rsi_columns():
    service = TechnicalIndicatorService()

    result = service.calculate(
        price_frame(),
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        boll_period=20,
        boll_std=2.0,
        rsi_period=14,
    )

    expected = {
        "macd",
        "macd_signal",
        "macd_hist",
        "boll_mid",
        "boll_upper",
        "boll_lower",
        "rsi",
    }
    assert expected.issubset(result.columns)
    assert len(result) == 80
    assert result["boll_mid"].iloc[:19].isna().all()
    assert result["boll_mid"].iloc[19] == pytest.approx(
        result["close"].iloc[:20].mean()
    )
    assert result["macd_hist"].iloc[-1] == pytest.approx(
        result["macd"].iloc[-1] - result["macd_signal"].iloc[-1]
    )
    assert 0 <= result["rsi"].dropna().iloc[-1] <= 100


def test_calculate_adds_standard_moving_averages():
    source = price_frame(rows=400)

    result = TechnicalIndicatorService().calculate(source)

    for period in (5, 10, 20, 60, 250, 360):
        column = f"ma{period}"
        assert column in result.columns
        assert result[column].iloc[: period - 1].isna().all()
        assert result[column].iloc[period - 1] == pytest.approx(
            result["close"].iloc[:period].mean()
        )


def test_calculate_does_not_mutate_input_frame():
    source = price_frame()
    original_columns = source.columns.tolist()

    TechnicalIndicatorService().calculate(source)

    assert source.columns.tolist() == original_columns


@pytest.mark.parametrize(
    "kwargs",
    [
        {"macd_fast": 0},
        {"macd_fast": 26, "macd_slow": 12},
        {"macd_signal": 0},
        {"boll_period": 1},
        {"boll_std": 0},
        {"rsi_period": 1},
    ],
)
def test_calculate_rejects_invalid_indicator_parameters(kwargs):
    with pytest.raises(InputValidationError):
        TechnicalIndicatorService().calculate(price_frame(), **kwargs)
