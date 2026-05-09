"""Bootstrap loader for the medal catalog.

The repository keeps the startup medal set in data/eremek.bootstrap.json so the
catalog can be seeded into the database without inlining it in the rule engine.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from felvi_games.models import Erem

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_BOOTSTRAP_FILE = _DATA_DIR / "eremek.bootstrap.json"


def _parse_datetime(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _load_payload() -> dict[str, dict[str, Any]]:
    if not _BOOTSTRAP_FILE.exists():
        return {}
    raw = json.loads(_BOOTSTRAP_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid medal bootstrap payload in {_BOOTSTRAP_FILE}")
    return raw


@lru_cache(maxsize=1)
def _load_bootstrap_policies() -> dict[str, dict[str, Any]]:
    payload = _load_payload()
    policies: dict[str, dict[str, Any]] = {}
    for erem_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        policy = raw.get("policy")
        if isinstance(policy, dict):
            policies[erem_id] = dict(policy)
    return policies


def get_bootstrap_repeatable_cooldown_hours(erem_id: str) -> int | None:
    policy = _load_bootstrap_policies().get(erem_id)
    if not policy:
        return None
    raw = policy.get("repeatable_cooldown_hours")
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return None
    return hours if hours > 0 else None


@lru_cache(maxsize=1)
def load_bootstrap_erem_catalog() -> dict[str, Erem]:
    payload = _load_payload()
    catalog: dict[str, Erem] = {}
    for erem_id, raw in payload.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid medal entry for {erem_id!r} in {_BOOTSTRAP_FILE}")
        data = dict(raw)
        data.pop("policy", None)
        data["condition_valid_from"] = _parse_datetime(data.get("condition_valid_from"))
        catalog[erem_id] = Erem(**data)
    return catalog


EREM_KATALOGUS = load_bootstrap_erem_catalog()