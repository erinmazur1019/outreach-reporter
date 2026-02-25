"""
Persistent store for manual channel counts (Telegram, Signal, LinkedIn add-on).

Data is kept in a simple JSON file so it survives process restarts and works
with both local runs and GitHub Actions (where the file can be committed or
stored as an artifact).

Schema:
  {
    "2026-02-25": {"telegram": 3, "signal": 1, "linkedin": 0},
    ...
  }
"""

import json
import logging
import os
from datetime import date

from src.config import cfg

logger = logging.getLogger(__name__)


def _load() -> dict:
    if not os.path.exists(cfg.MANUAL_COUNTS_FILE):
        return {}
    with open(cfg.MANUAL_COUNTS_FILE, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(cfg.MANUAL_COUNTS_FILE) or ".", exist_ok=True)
    with open(cfg.MANUAL_COUNTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def set_count(channel: str, count: int, for_date: date | None = None) -> None:
    """
    Persist a manual count for a given channel and date.
    channel: "telegram" | "signal" | "linkedin"
    """
    key = str(for_date or date.today())
    data = _load()
    if key not in data:
        data[key] = {}
    data[key][channel] = count
    _save(data)
    logger.info("Saved manual count: %s/%s = %d", key, channel, count)


def get_counts(for_date: date | None = None) -> dict[str, int]:
    """Return the manual counts for a given date (defaults to today)."""
    key = str(for_date or date.today())
    data = _load()
    return data.get(key, {"telegram": 0, "signal": 0, "linkedin": 0})
