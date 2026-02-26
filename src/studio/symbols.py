"""Symbol management for the studio editor."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Module-level globals set by the server
SYMBOLS_ROOT: Path | None = None


def set_symbols_root(path: Path) -> None:
    """Set the symbols root directory."""
    global SYMBOLS_ROOT
    SYMBOLS_ROOT = path


# Cache for symbol list
_symbols_cache: list[dict] | None = None


# Port colour map
PORT_COLORS: dict[str, str] = {
    "in": "#2196F3",
    "out": "#F44336",
    "in_out": "#009688",
    "signal": "#9C27B0",
    "process": "#FF9800",
    "north": "#4CAF50",
    "south": "#4CAF50",
    "east": "#4CAF50",
    "west": "#4CAF50",
    "reference": "#9E9E9E",
}
DEFAULT_COLOR = "#607D8B"


def _port_color(port_id: str) -> str:
    return PORT_COLORS.get(port_id.lower(), DEFAULT_COLOR)


def _safe_path(rel: str) -> Path | None:
    """Resolve a relative symbol path safely (prevent path traversal)."""
    if SYMBOLS_ROOT is None:
        return None
    rel_clean = rel.replace("/", os.sep).replace("\\", os.sep)
    try:
        abs_path = (SYMBOLS_ROOT / rel_clean).resolve()
        abs_path.relative_to(SYMBOLS_ROOT.resolve())
    except (ValueError, OSError):
        return None
    return abs_path


def _invalidate_cache() -> None:
    """Invalidate the symbol list cache."""
    global _symbols_cache
    _symbols_cache = None


def compute_stats() -> dict:
    """Compute completion stats across all symbols."""
    symbols = list_symbols()
    total = len(symbols)
    completed = sum(1 for s in symbols if s.get("completed", False))

    by_standard: dict[str, dict] = {}
    by_category: dict[str, dict] = {}

    for s in symbols:
        std = s.get("standard", "unknown") or "unknown"
        cat = s.get("category", "unknown") or "unknown"
        is_done = bool(s.get("completed", False))

        if std not in by_standard:
            by_standard[std] = {"total": 0, "completed": 0}
        by_standard[std]["total"] += 1
        if is_done:
            by_standard[std]["completed"] += 1

        if cat not in by_category:
            by_category[cat] = {"total": 0, "completed": 0}
        by_category[cat]["total"] += 1
        if is_done:
            by_category[cat]["completed"] += 1

    return {
        "total": total,
        "completed": completed,
        "percentage": round(completed / total * 100, 1) if total else 0.0,
        "by_standard": by_standard,
        "by_category": by_category,
    }


def list_symbols() -> list[dict]:
    """Return symbol descriptors, using registry.json when available."""
    global _symbols_cache
    if _symbols_cache is not None:
        return _symbols_cache
    if SYMBOLS_ROOT is None:
        return []

    reg_path = SYMBOLS_ROOT / "registry.json"
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
            _symbols_cache = _symbols_from_registry(registry)
            return _symbols_cache
        except (json.JSONDecodeError, OSError):
            pass
    _symbols_cache = _symbols_from_scan()
    return _symbols_cache


def _symbols_from_registry(registry: dict) -> list[dict]:
    if SYMBOLS_ROOT is None:
        return []
    results = []
    for sym in registry.get("symbols", []):
        sym_id = sym.get("id", "")
        if not sym_id:
            continue
        json_path = SYMBOLS_ROOT / (sym_id.replace("/", os.sep) + ".json")
        if not json_path.exists():
            continue
        parts = sym_id.split("/")
        if len(parts) == 4:
            std_from_id = parts[1]
            cat_from_id = parts[2]
        elif len(parts) == 3:
            std_from_id = parts[0]
            cat_from_id = parts[1]
        else:
            std_from_id = parts[0] if parts else ""
            cat_from_id = parts[1] if len(parts) > 1 else ""

        completed = False
        flag = None
        try:
            sym_data = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
            flag = sym_data.get("flag", None)
        except (json.JSONDecodeError, OSError):
            pass
        source = parts[0] if len(parts) == 4 else ""
        results.append(
            {
                "path": sym_id,
                "name": sym.get("display_name") or (parts[-1] if parts else sym_id),
                "standard": sym.get("standard", std_from_id).lower(),
                "category": sym.get("category", cat_from_id),
                "source": source,
                "completed": completed,
                "flag": flag,
            }
        )
    return results


def _symbols_from_scan() -> list[dict]:
    if SYMBOLS_ROOT is None:
        return []
    results = []
    for json_path in sorted(SYMBOLS_ROOT.rglob("*.json")):
        stem = json_path.stem
        if stem == "registry" or "_debug" in stem:
            continue
        rel = json_path.relative_to(SYMBOLS_ROOT)
        parts = rel.parts
        completed = False
        flag = None
        try:
            sym_data = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
            flag = sym_data.get("flag", None)
        except (json.JSONDecodeError, OSError):
            pass
        id_parts = rel.with_suffix("").parts
        source = id_parts[0] if len(id_parts) == 4 else ""
        results.append(
            {
                "path": "/".join(id_parts),
                "name": stem,
                "standard": parts[0] if len(parts) >= 1 else "",
                "category": parts[1] if len(parts) >= 2 else "",
                "source": source,
                "completed": completed,
                "flag": flag,
            }
        )
    return results


def load_symbol(rel: str) -> dict | None:
    """Load and return {meta, svg} for a symbol, or None if not found."""
    base = _safe_path(rel)
    if base is None:
        return None
    json_path = base.with_suffix(".json")
    svg_path = base.with_suffix(".svg")
    if not json_path.exists() or not svg_path.exists():
        return None
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    svg = svg_path.read_text(encoding="utf-8")
    return {"meta": meta, "svg": svg}


def save_symbol(rel: str | None, meta: dict | None) -> tuple[bool, str]:
    """Write updated metadata JSON back to disk."""
    if not rel or meta is None:
        return False, "missing path or meta"
    base = _safe_path(rel)
    if base is None:
        return False, "invalid path"
    json_path = base.with_suffix(".json")
    if not json_path.exists():
        return False, f"JSON not found: {json_path}"
    try:
        json_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)
    _invalidate_cache()
    return True, ""


def patch_meta(rel: str | None, updates: dict) -> tuple[bool, str]:
    """Patch specific fields in a symbol's metadata JSON."""
    if not rel:
        return False, "missing path"
    base = _safe_path(rel)
    if base is None:
        return False, "invalid path"
    json_path = base.with_suffix(".json")
    if not json_path.exists():
        return False, f"JSON not found: {json_path}"
    try:
        meta = json.loads(json_path.read_text(encoding="utf-8"))
        for k, v in updates.items():
            if v is None:
                meta.pop(k, None)
            else:
                meta[k] = v
        json_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _invalidate_cache()
        return True, ""
    except OSError as exc:
        return False, str(exc)


def generate_debug(rel: str | None, ports: list[dict]) -> tuple[bool, str]:
    """Overlay labelled port markers on the symbol SVG and save as *_debug.svg."""
    import re

    if not rel:
        return False, "missing path"
    base = _safe_path(rel)
    if base is None:
        return False, "invalid path"
    svg_path = base.with_suffix(".svg")
    debug_path = base.parent / (base.stem + "_debug.svg")
    if not svg_path.exists():
        return False, f"SVG not found: {svg_path}"

    original = svg_path.read_text(encoding="utf-8")

    m = re.search(
        r'viewBox=["\'][\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)',
        original,
    )
    vw, vh = (float(m.group(1)), float(m.group(2))) if m else (80.0, 80.0)
    r = max(2.0, min(vw, vh) * 0.04)
    fsz = round(r * 1.1, 2)
    sw = round(r * 0.15, 2)
    tsw = round(fsz * 0.12, 2)

    parts: list[str] = ['<g id="port-debug" style="pointer-events:none;">']
    for p in ports:
        pid = str(p.get("id", "?"))
        ptype = str(p.get("type", pid))
        col = _port_color(ptype)
        disp = pid

        zone = p.get("zone")
        if zone:
            zx, zy = zone.get("x", 0), zone.get("y", 0)
            zw, zh = zone.get("width", 10), zone.get("height", 10)
            parts.append(
                f'  <rect x="{zx}" y="{zy}" width="{zw}" height="{zh}"'
                f' fill="{col}" fill-opacity="0.2" stroke="{col}"'
                f' stroke-width="{sw}" stroke-dasharray="{r * 0.7} {r * 0.35}"/>'
            )
            lx = zx + zw / 2
            ly = zy + zh / 2 + fsz * 0.4
            parts.append(
                f'  <text x="{lx}" y="{ly}" font-size="{fsz}" fill="{col}"'
                f' font-family="monospace" text-anchor="middle"'
                f' stroke="white" stroke-width="{tsw}" paint-order="stroke"'
                f">{disp}</text>"
            )
        else:
            x, y = p.get("x", 0), p.get("y", 0)
            parts.append(
                f'  <circle cx="{x}"cy="{y}" r="{r}" fill="{col}"'
                f' stroke="white" stroke-width="{sw}" opacity="0.9"/>'
            )
            parts.append(
                f'  <text x="{x + r + fsz * 0.25}" y="{y + fsz * 0.38}"'
                f' font-size="{fsz}" fill="{col}" font-family="monospace"'
                f' stroke="white" stroke-width="{tsw}" paint-order="stroke"'
                f">{disp}</text>"
            )
    parts.append("</g>")

    overlay = "\n".join(parts)
    close_idx = original.rfind("</svg>")
    if close_idx == -1:
        debug_svg = original + "\n" + overlay
    else:
        debug_svg = original[:close_idx] + "\n" + overlay + "\n" + original[close_idx:]

    try:
        debug_path.write_text(debug_svg, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, ""
