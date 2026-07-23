from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    output_dir: Path = Path("outputs")
    strategy_dir: Path = Path("strategies")
    server_name: str = "0.0.0.0"
    server_port: int = 7860
    gradio_share: bool = False
    lot_size: int = 100
    output_retention_hours: int = 24
    fetch_attempts: int = 3
    retry_base_delay_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")),
            strategy_dir=Path(os.getenv("STRATEGY_DIR", "strategies")),
            server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
            server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
            gradio_share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
            lot_size=int(os.getenv("A_SHARE_LOT_SIZE", "100")),
            output_retention_hours=int(os.getenv("OUTPUT_RETENTION_HOURS", "24")),
            fetch_attempts=int(os.getenv("FETCH_ATTEMPTS", "3")),
            retry_base_delay_seconds=float(os.getenv("RETRY_BASE_DELAY_SECONDS", "1.0")),
        )
