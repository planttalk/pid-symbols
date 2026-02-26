"""Unrealistic reports handling for the studio editor."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

REPORTS_FILE: Path | None = None
_reports_lock = threading.RLock()

GEOMETRY_EFFECTS = frozenset({"mirror_h", "mirror_v", "rot_90", "rot_180", "rot_270"})


def set_reports_file(path: Path) -> None:
    """Set the reports file path."""
    global REPORTS_FILE
    REPORTS_FILE = path


def _load_reports() -> dict:
    """Return the unrealistic-reports store, creating an empty one if absent."""
    if REPORTS_FILE is None:
        return {"reports": []}
    try:
        if REPORTS_FILE.exists():
            return json.loads(REPORTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {"reports": []}


def _save_reports(data: dict) -> tuple[bool, str]:
    """Atomically write *data* to the reports file under the reports lock."""
    if REPORTS_FILE is None:
        return False, "reports file not configured"
    try:
        with _reports_lock:
            tmp = REPORTS_FILE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            tmp.replace(REPORTS_FILE)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def load_reports() -> dict:
    """Return the reports for API."""
    return _load_reports()


def flag_report_add(body: dict) -> tuple[dict | None, str]:
    """Append a new unrealistic-flag report entry; return the entry on success."""
    effects = body.get("effects")
    if effects is None:
        return None, "missing effects"
    symbol = body.get("symbol", "")
    label = body.get("label", "")
    source = body.get("source", "preview")
    ts_ms = int(time.time() * 1000)
    import datetime as dt

    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _reports_lock:
        data = _load_reports()
        existing_ids = {e["id"] for e in data["reports"]}
        seq = 0
        while f"{ts_ms}-{seq}" in existing_ids:
            seq += 1
        entry = {
            "id": f"{ts_ms}-{seq}",
            "timestamp": timestamp,
            "symbol": symbol,
            "label": label,
            "effects": effects,
            "source": source,
        }
        data["reports"].append(entry)
        ok, err = _save_reports(data)
    if not ok:
        return None, err
    return entry, ""


def flag_report_delete(report_id: str) -> tuple[bool, str]:
    """Remove a single report by id."""
    if not report_id:
        return False, "missing id"
    with _reports_lock:
        data = _load_reports()
        before = len(data["reports"])
        data["reports"] = [e for e in data["reports"] if e.get("id") != report_id]
        if len(data["reports"]) == before:
            return False, f"report not found: {report_id}"
        return _save_reports(data)


def flag_reports_clear() -> tuple[int, str]:
    """Delete all reports; return (count_deleted, error_str)."""
    with _reports_lock:
        data = _load_reports()
        count = len(data["reports"])
        data["reports"] = []
        ok, err = _save_reports(data)
    if not ok:
        return 0, err
    return count, ""


def compute_effect_caps() -> dict[str, float]:
    """Derive per-effect intensity caps from flagged unrealistic reports."""
    data = _load_reports()
    reports = data.get("reports", [])
    if not reports:
        return {}

    mins: dict[str, float] = {}
    for entry in reports:
        for name, intensity in (entry.get("effects") or {}).items():
            if name in GEOMETRY_EFFECTS:
                continue
            try:
                v = float(intensity)
            except (TypeError, ValueError):
                continue
            if v <= 0.0:
                continue
            if name not in mins or v < mins[name]:
                mins[name] = v

    caps = {name: max(0.05, round(v * 0.85, 3)) for name, v in mins.items()}
    return caps


def compute_flagged_combos() -> list[frozenset]:
    """Return each flagged report as a frozenset of non-geom effect names."""
    data = _load_reports()
    combos: list[frozenset] = []
    for entry in data.get("reports", []):
        names = frozenset(
            k
            for k, v in (entry.get("effects") or {}).items()
            if k not in GEOMETRY_EFFECTS and float(v) > 0.0
        )
        if names:
            combos.append(names)
    return combos


def combo_overlaps_flagged(
    picked: set | frozenset,
    flagged_combos: list[frozenset],
    threshold: float = 0.70,
) -> bool:
    """Return True if *picked* shares >= threshold fraction of any flagged combo."""
    ps = frozenset(picked)
    for fc in flagged_combos:
        if fc and len(fc & ps) / len(fc) >= threshold:
            return True
    return False
