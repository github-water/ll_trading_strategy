SOURCE_NAME = "EFINANCE_EASTMONEY"

ASSET_TYPE_MAP = {
    "自动识别": "auto",
    "ETF": "etf",
    "股票": "stock",
    "auto": "auto",
    "etf": "etf",
    "stock": "stock",
}

ADJUST_MAP = {
    "不复权": ("raw", 0),
    "前复权": ("qfq", 1),
    "后复权": ("hfq", 2),
    "raw": ("raw", 0),
    "qfq": ("qfq", 1),
    "hfq": ("hfq", 2),
}

OUTPUT_COLUMNS = [
    "instrument_id",
    "symbol",
    "exchange",
    "asset_type",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "source_volume_lots",
    "amount",
    "vwap",
    "amplitude",
    "pct_change",
    "change",
    "turnover_rate",
    "adjust",
    "source",
    "source_version",
    "fetched_at",
]


TECHNICAL_REQUIRED_COLUMNS = {
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
}

TECHNICAL_NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
]
