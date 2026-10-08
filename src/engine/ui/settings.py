"""UI settings from the environment (M00_UI rule U5): moving the app is configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class UiSettings:
    host: str = "127.0.0.1"  # this PC only (D29); change only together with a login (U1)
    port: int = 8765
    data_dir: Path = ROOT / "data"
    watchlist: Path = ROOT / "config" / "watchlist.toml"


def from_env() -> UiSettings:
    return UiSettings(
        host=os.getenv("ENGINE_UI_HOST", "127.0.0.1"),
        port=int(os.getenv("ENGINE_UI_PORT", "8765")),
        data_dir=Path(os.getenv("ENGINE_DATA_DIR", str(ROOT / "data"))),
        watchlist=Path(os.getenv("ENGINE_WATCHLIST", str(ROOT / "config" / "watchlist.toml"))),
    )
