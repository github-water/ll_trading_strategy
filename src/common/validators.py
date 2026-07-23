from __future__ import annotations

import re
from datetime import date, datetime

from common.constants import ADJUST_MAP, ASSET_TYPE_MAP
from common.exceptions import InputValidationError
from common.models import AdjustType, AssetType


def normalize_symbol(value: str) -> str:
    if value is None:
        raise InputValidationError("请输入证券代码。")
    symbol = str(value).strip().upper()
    symbol = re.sub(r"^(SH|SZ|BJ)", "", symbol)
    symbol = re.sub(r"\.(SH|SZ|BJ|SSE|SZSE|BSE)$", "", symbol)
    if not re.fullmatch(r"\d{6}", symbol):
        raise InputValidationError(
            "证券代码必须为6位数字，例如 510300、600519 或 000001。"
        )
    return symbol


def infer_exchange(symbol: str) -> str:
    if symbol.startswith(("4", "8")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def infer_asset_type(symbol: str) -> AssetType:
    if symbol.startswith("5") or symbol.startswith(("15", "16", "18")):
        return AssetType.ETF
    return AssetType.STOCK


def resolve_asset_type(value: str, symbol: str) -> AssetType:
    try:
        requested = ASSET_TYPE_MAP[str(value)]
    except KeyError as exc:
        raise InputValidationError(f"不支持的资产类型：{value}") from exc
    return infer_asset_type(symbol) if requested == "auto" else AssetType(requested)


def resolve_adjust(value: str) -> tuple[AdjustType, int]:
    try:
        adjust, fqt = ADJUST_MAP[str(value)]
    except KeyError as exc:
        raise InputValidationError(f"不支持的复权方式：{value}") from exc
    return AdjustType(adjust), fqt


def parse_date(value: str | date | datetime, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise InputValidationError(
        f"{field_name}格式错误，请使用 YYYY-MM-DD，例如 2016-07-23。"
    )


def validate_date_range(start: date, end: date) -> None:
    if start > end:
        raise InputValidationError("开始日期不能晚于结束日期。")
    if end > date.today():
        raise InputValidationError("结束日期不能晚于今天。")
    if (end - start).days > 365 * 35 + 10:
        raise InputValidationError("单次查询区间不能超过35年。")
