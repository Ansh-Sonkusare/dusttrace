"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = REPO_ROOT / "data" / "seed" / "k-east.json"


@dataclass(frozen=True)
class Settings:
    database_url: str
    openaq_api_key: str | None
    ward_id: str
    horizon_hours: int = 48
    # PM10 threshold that counts as an exceedance (India 24-h NAAQS for PM10 is 100 ug/m3).
    exceed_threshold: float = 100.0
    # Plume footprint threshold: modelled increment above which an area is "in the plume".
    plume_threshold: float = 25.0
    # Receptor thresholds for Safe-Work Windows (modelled increment, ug/m3).
    avoid_threshold: float = 40.0
    caution_threshold: float = 15.0


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://postgres@localhost:5432/dusttrace"
        ),
        openaq_api_key=os.environ.get("OPENAQ_API_KEY") or None,
        ward_id=os.environ.get("DUSTTRACE_WARD", "K-East"),
        horizon_hours=int(os.environ.get("DUSTTRACE_HORIZON_H", "48")),
    )


def load_seed(path: Path = SEED_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
