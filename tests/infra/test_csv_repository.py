from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from common.config import Settings
from common.models import AdjustType, AssetType, DataFetchCommand
from infra.storage.csv_repository import LocalCsvRepository


def command():
    return DataFetchCommand(
        symbol="510300",
        asset_type=AssetType.ETF,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        adjust=AdjustType.RAW,
        fqt=0,
    )


def test_repository_writes_utf8_bom_csv_and_cleans_stale_files(tmp_path):
    stale = tmp_path / "stale.csv"
    stale.write_text("old", encoding="utf-8")
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    timestamp = old.timestamp()
    stale.touch()
    import os
    os.utime(stale, (timestamp, timestamp))

    repo = LocalCsvRepository(
        Settings(output_dir=tmp_path, output_retention_hours=24)
    )
    path = repo.save(pd.DataFrame({"trade_date": ["2024-01-02"]}), command(), "SSE")

    assert path.exists()
    assert path.name.startswith("510300_SSE_ETF_20240102_20240103_raw_")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not stale.exists()


def test_repository_finds_latest_csv_for_symbol(tmp_path):
    older = tmp_path / "510300_SSE_ETF_20200101_20201231_raw_old.csv"
    newer = tmp_path / "510300_SSE_ETF_20210101_20211231_raw_new.csv"
    other = tmp_path / "600519_SSE_STOCK_20210101_20211231_raw_new.csv"
    for path in (older, newer, other):
        path.write_text("trade_date,close\n2024-01-01,1\n", encoding="utf-8")

    import os
    now = datetime.now(timezone.utc).timestamp()
    os.utime(older, (now - 100, now - 100))
    os.utime(newer, (now, now))

    repo = LocalCsvRepository(Settings(output_dir=tmp_path))

    assert repo.find_latest("510300") == newer


def test_repository_find_latest_raises_when_symbol_has_no_csv(tmp_path):
    from common.exceptions import StorageError

    repo = LocalCsvRepository(Settings(output_dir=tmp_path))

    import pytest
    with pytest.raises(StorageError, match="未找到代码 510300"):
        repo.find_latest("510300")


def test_repository_reads_utf8_bom_csv(tmp_path):
    path = tmp_path / "510300.csv"
    pd.DataFrame(
        {"trade_date": ["2024-01-02"], "close": [3.5]}
    ).to_csv(path, index=False, encoding="utf-8-sig")
    repo = LocalCsvRepository(Settings(output_dir=tmp_path))

    result = repo.read(path)

    assert result.to_dict("records") == [
        {"trade_date": "2024-01-02", "close": 3.5}
    ]


def test_repository_preserves_leading_zero_symbols(tmp_path):
    path = tmp_path / "000001.csv"
    path.write_text(
        "instrument_id,symbol,trade_date,close\n000001.SZSE,000001,2024-01-02,10.5\n",
        encoding="utf-8-sig",
    )
    repo = LocalCsvRepository(Settings(output_dir=tmp_path))

    result = repo.read(path)

    assert result.loc[0, "symbol"] == "000001"
    assert result.loc[0, "instrument_id"] == "000001.SZSE"
