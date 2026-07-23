from datetime import date

import pytest

from common.exceptions import InputValidationError
from common.models import AdjustType, AssetType
from common.validators import (
    infer_asset_type,
    infer_exchange,
    normalize_symbol,
    parse_date,
    resolve_adjust,
    resolve_asset_type,
    validate_date_range,
)


def test_normalize_symbol_accepts_common_formats():
    assert normalize_symbol("510300") == "510300"
    assert normalize_symbol("510300.SH") == "510300"
    assert normalize_symbol("sh510300") == "510300"
    assert normalize_symbol("000001.SZ") == "000001"


def test_normalize_symbol_rejects_invalid_input():
    with pytest.raises(InputValidationError):
        normalize_symbol("ABC")
    with pytest.raises(InputValidationError):
        normalize_symbol("51030")


def test_infers_exchange_and_asset_type():
    assert infer_exchange("510300") == "SSE"
    assert infer_exchange("000001") == "SZSE"
    assert infer_exchange("830001") == "BSE"
    assert infer_asset_type("510300") is AssetType.ETF
    assert infer_asset_type("159915") is AssetType.ETF
    assert infer_asset_type("600519") is AssetType.STOCK


def test_resolves_ui_values_to_domain_enums():
    assert resolve_asset_type("自动识别", "510300") is AssetType.ETF
    assert resolve_asset_type("股票", "510300") is AssetType.STOCK
    assert resolve_adjust("不复权") == (AdjustType.RAW, 0)
    assert resolve_adjust("前复权") == (AdjustType.QFQ, 1)
    assert resolve_adjust("后复权") == (AdjustType.HFQ, 2)


def test_parses_dates_and_rejects_invalid_ranges():
    assert parse_date("2024-01-02", "开始日期") == date(2024, 1, 2)
    assert parse_date("20240102", "开始日期") == date(2024, 1, 2)
    with pytest.raises(InputValidationError):
        parse_date("2024/01/02", "开始日期")
    with pytest.raises(InputValidationError):
        validate_date_range(date(2024, 2, 1), date(2024, 1, 1))
