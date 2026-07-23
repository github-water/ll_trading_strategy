from datetime import date

import pandas as pd
import pytest

from common.config import Settings
from common.exceptions import DataFetchError, DataQualityError
from common.models import AdjustType, AssetType, DataFetchCommand
from infra.market_data.efinance_gateway import EfinanceMarketDataGateway


def command(adjust=AdjustType.RAW, fqt=0, asset_type=AssetType.ETF):
    return DataFetchCommand(
        symbol="510300",
        asset_type=asset_type,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        adjust=adjust,
        fqt=fqt,
    )


def source_frame(name_column="名称", code_column="代码"):
    return pd.DataFrame(
        {
            name_column: ["沪深300ETF", "沪深300ETF"],
            code_column: ["510300", "510300"],
            "日期": ["2024-01-02", "2024-01-03"],
            "开盘": [3.50, 3.55],
            "收盘": [3.54, 3.52],
            "最高": [3.56, 3.58],
            "最低": [3.48, 3.50],
            "成交量": [1000, 1200],
            "成交额": [352000.0, 424800.0],
            "振幅": [2.0, 2.26],
            "涨跌幅": [1.14, -0.56],
            "涨跌额": [0.04, -0.02],
            "换手率": [0.50, 0.60],
        }
    )


def test_gateway_maps_efinance_columns_and_units():
    calls = []

    def fetcher(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return source_frame()

    gateway = EfinanceMarketDataGateway(
        settings=Settings(), fetcher=fetcher, version_getter=lambda: "test"
    )
    result = gateway.fetch_daily(command())

    assert calls[0][0] == "510300"
    assert calls[0][1]["beg"] == "20240102"
    assert calls[0][1]["end"] == "20240103"
    assert calls[0][1]["klt"] == 101
    assert result.instrument_name == "沪深300ETF"
    assert result.data.loc[0, "instrument_id"] == "510300.SSE"
    assert result.data.loc[0, "asset_type"] == "ETF"
    assert result.data.loc[0, "volume"] == 100000
    assert result.data.loc[0, "source_volume_lots"] == 1000
    assert result.data.loc[0, "pre_close"] == pytest.approx(3.50)
    assert result.data.loc[0, "vwap"] == pytest.approx(3.52)
    assert result.data.loc[0, "pct_change"] == pytest.approx(0.0114)


def test_gateway_accepts_legacy_columns_and_warns_for_adjusted_prices():
    gateway = EfinanceMarketDataGateway(
        settings=Settings(),
        fetcher=lambda *_args, **_kwargs: source_frame("股票名称", "股票代码"),
        version_getter=lambda: "test",
    )
    result = gateway.fetch_daily(command(AdjustType.QFQ, 1))
    assert result.instrument_name == "沪深300ETF"
    assert any("复权价格" in warning for warning in result.warnings)


def test_gateway_retries_and_raises_provider_error():
    attempts = 0

    def failing_fetcher(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("blocked")

    gateway = EfinanceMarketDataGateway(
        settings=Settings(fetch_attempts=3, retry_base_delay_seconds=0),
        fetcher=failing_fetcher,
        version_getter=lambda: "test",
        sleep_fn=lambda _seconds: None,
    )
    with pytest.raises(DataFetchError, match="连续失败 3 次"):
        gateway.fetch_daily(command())
    assert attempts == 3


def test_gateway_rejects_invalid_ohlc():
    bad = source_frame()
    bad.loc[0, "最高"] = 3.0
    gateway = EfinanceMarketDataGateway(
        settings=Settings(), fetcher=lambda *_args, **_kwargs: bad,
        version_getter=lambda: "test",
    )
    with pytest.raises(DataQualityError, match="OHLC"):
        gateway.fetch_daily(command())
