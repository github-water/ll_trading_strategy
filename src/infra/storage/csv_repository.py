from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common.config import Settings
from common.exceptions import StorageError
from common.models import DataFetchCommand


class LocalCsvRepository:
    def __init__(self, settings: Settings) -> None:
        self._output_dir = settings.output_dir
        self._retention_hours = settings.output_retention_hours

    def save(
        self,
        data: pd.DataFrame,
        command: DataFetchCommand,
        exchange: str,
    ) -> Path:
        try:
            self._cleanup_stale_files()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = (
                f"{command.symbol}_{exchange}_{command.asset_type.value.upper()}_"
                f"{command.start_date:%Y%m%d}_{command.end_date:%Y%m%d}_"
                f"{command.adjust.value}_{timestamp}.csv"
            )
            path = self._output_dir / filename
            data.to_csv(path, index=False, encoding="utf-8-sig")
            return path
        except OSError as exc:
            raise StorageError(f"CSV 保存失败：{exc}") from exc

    def find_latest(self, symbol: str) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        candidates = [
            path
            for path in self._output_dir.glob(f"{symbol}_*.csv")
            if path.is_file()
        ]
        if not candidates:
            raise StorageError(
                f"未找到代码 {symbol} 的已下载 CSV，请先获取数据，"
                "或在技术图表中上传 CSV。"
            )
        try:
            return max(candidates, key=lambda path: path.stat().st_mtime)
        except OSError as exc:
            raise StorageError(f"读取 CSV 文件信息失败：{exc}") from exc

    def replace(self, path: str | Path, data: pd.DataFrame) -> Path:
        csv_path = Path(path)
        if not csv_path.exists() or not csv_path.is_file():
            raise StorageError(f"CSV 文件不存在：{csv_path}")
        temp_path = csv_path.with_name(f".{csv_path.name}.tmp")
        try:
            data.to_csv(temp_path, index=False, encoding="utf-8-sig")
            temp_path.replace(csv_path)
            return csv_path
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StorageError(f"CSV 更新失败：{exc}") from exc

    def read(self, path: str | Path) -> pd.DataFrame:
        csv_path = Path(path)
        if not csv_path.exists() or not csv_path.is_file():
            raise StorageError(f"CSV 文件不存在：{csv_path}")
        try:
            return pd.read_csv(
                csv_path,
                encoding="utf-8-sig",
                converters={
                    "symbol": lambda value: str(value).strip().zfill(6),
                    "instrument_id": lambda value: str(value).strip(),
                },
            )
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            raise StorageError(f"CSV 读取失败：{exc}") from exc

    def _cleanup_stale_files(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - self._retention_hours * 3600
        for path in self._output_dir.glob("*.csv"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                continue
