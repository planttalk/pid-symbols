#!/usr/bin/env python3
"""symbol_studio.py — browser-based symbol editor for P&ID SVG symbols.

Covers snap-point editing, paper/scanning degradation preview, and
augmented image generation. Starts a local HTTP server and opens the
editor in the default browser.
Static files are served from the editor/ directory next to this script.

Usage
-----
    python symbol_studio.py                           # ./processed root, port 7421
    python symbol_studio.py --symbols /path/to/syms
    python symbol_studio.py --port 8080
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import re
import threading
import urllib.parse
import webbrowser

# globals set in main()
SYMBOLS_ROOT: pathlib.Path
SERVER_PORT: int

# Single flag shared across all threads — set by /api/augment-cancel to stop the running batch
_batch_cancel = threading.Event()
_EDITOR_ROOT = pathlib.Path(__file__).parent / "editor"
# Serve from editor/dist/ (React build) when available, otherwise editor/ (legacy)
EDITOR_DIR = _EDITOR_ROOT / "dist" if (_EDITOR_ROOT / "dist").is_dir() else _EDITOR_ROOT

_UNREALISTIC_REPORTS_FILE = pathlib.Path(__file__).parent / "unrealistic_reports.json"
_reports_lock = threading.RLock()

# port colour map (shared by _generate_debug)
_PORT_COLORS: dict[str, str] = {
    "in":        "#2196F3",
    "out":       "#F44336",
    "in_out":    "#009688",
    "signal":    "#9C27B0",
    "process":   "#FF9800",
    "north":     "#4CAF50",
    "south":     "#4CAF50",
    "east":      "#4CAF50",
    "west":      "#4CAF50",
    "reference": "#9E9E9E",  # spatial-only — no connection meaning
}
_DEFAULT_COLOR = "#607D8B"

# Cache for symbol list — avoids re-reading every JSON on each /api/symbols request.
# Invalidated whenever _save_symbol() writes to disk.
_symbols_cache: list | None = None


def _port_color(pid: str) -> str:
    return _PORT_COLORS.get(pid.lower(), _DEFAULT_COLOR)


# HTTP handler

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, *_):
        pass  # silence request logging

    # low-level send helpers

    def _sse_stream(self, gen) -> None:
        """Send an SSE response, pushing each dict yielded by *gen* as an event."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            for event in gen:
                self.wfile.write(
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send(self, body: str | bytes,
              ctype: str = "text/html; charset=utf-8",
              status: int = 200) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8", status)

    def _error(self, msg: str, status: int = 400) -> None:
        self._send(msg, "text/plain; charset=utf-8", status)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _serve_file(self, path: pathlib.Path, ctype: str) -> None:
        try:
            self._send(path.read_bytes(), ctype)
        except OSError:
            self._error(f"File not found: {path.name}", 404)

    # GET

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs     = urllib.parse.parse_qs(parsed.query)
        p      = parsed.path

        _STATIC_MIME = {
            ".html": "text/html; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".png":  "image/png",
            ".ico":  "image/x-icon",
        }

        if p in ("/", "/index.html"):
            self._serve_file(EDITOR_DIR / "index.html",
                             "text/html; charset=utf-8")

        elif not p.startswith("/api/") and "." in p.split("/")[-1]:
            # Generic static-file handler for all editor assets (JS modules,
            # CSS, etc.).  Rejects any path that escapes EDITOR_DIR.
            rel_clean = p.lstrip("/").replace("/", os.sep)
            try:
                target = (EDITOR_DIR / rel_clean).resolve()
                target.relative_to(EDITOR_DIR.resolve())  # path-traversal guard
            except ValueError:
                self._error("Forbidden", 403)
                return
            ext  = pathlib.Path(rel_clean).suffix.lower()
            mime = _STATIC_MIME.get(ext, "application/octet-stream")
            self._serve_file(target, mime)

        elif p == "/api/symbols":
            self._json(_list_symbols())

        elif p == "/api/symbol":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._error("missing ?path="); return
            result = _load_symbol(rel)
            if result is None:
                self._error(f"Symbol not found: {rel}", 404); return
            self._json(result)

        elif p == "/api/stats":
            self._json(_compute_stats())

        elif p == "/api/flag-reports":
            self._json(_load_reports())

        else:
            self._error("Not found", 404)

    # POST

    def do_POST(self) -> None:
        body = self._read_body()
        p    = urllib.parse.urlparse(self.path).path

        if p == "/api/save":
            ok, msg = _save_symbol(body.get("path"), body.get("meta"))
            if ok: self._send("ok")
            else:  self._error(msg, 500)

        elif p == "/api/debug":
            ok, msg = _generate_debug(body.get("path"), body.get("ports", []))
            if ok: self._send("ok")
            else:  self._error(msg, 500)

        elif p == "/api/export-completed":
            out = body.get("output_dir", "").strip()
            result = _export_completed(out)
            self._json(result)

        elif p == "/api/augment-preview":
            result, err = _augment_preview(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)

        elif p == "/api/augment-generate":
            result, err = _augment_generate(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)

        elif p == "/api/augment-batch":
            self._sse_stream(_augment_batch(body))

        elif p == "/api/augment-cancel":
            _batch_cancel.set()
            self._json({"ok": True})

        elif p == "/api/flag":
            ok, msg = _patch_meta(body.get("path"), {"flag": body.get("flag")})
            if ok: self._send("ok")
            else:  self._error(msg, 500)

        elif p == "/api/augment-combo":
            result, err = _augment_combo(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)

        elif p == "/api/flag-report":
            entry, err = _flag_report_add(body)
            if entry is not None:
                self._json({"ok": True, "entry": entry})
            else:
                self._error(err, 500)

        elif p == "/api/flag-report-delete":
            ok, err = _flag_report_delete(body.get("id", ""))
            if ok: self._json({"ok": True})
            else:  self._error(err, 500)

        elif p == "/api/flag-reports-clear":
            count, err = _flag_reports_clear()
            if err: self._error(err, 500)
            else:   self._json({"ok": True, "deleted": count})

        else:
            self._error("Not found", 404)


# business logic

def _safe_path(rel: str) -> pathlib.Path | None:
    """Resolve a relative symbol path safely (prevent path traversal)."""
    rel_clean = rel.replace("/", os.sep).replace("\\", os.sep)
    try:
        abs_path = (SYMBOLS_ROOT / rel_clean).resolve()
        abs_path.relative_to(SYMBOLS_ROOT.resolve())
    except (ValueError, OSError):
        return None
    return abs_path


def _compute_stats() -> dict:
    """Compute completion stats across all symbols."""
    symbols = _list_symbols()
    total = len(symbols)
    completed = sum(1 for s in symbols if s.get("completed", False))

    by_standard: dict[str, dict] = {}
    by_category: dict[str, dict] = {}

    for s in symbols:
        std    = s.get("standard", "unknown") or "unknown"
        cat    = s.get("category", "unknown") or "unknown"
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
        "total":       total,
        "completed":   completed,
        "percentage":  round(completed / total * 100, 1) if total else 0.0,
        "by_standard": by_standard,
        "by_category": by_category,
    }


def _list_symbols() -> list[dict]:
    """Return symbol descriptors, using registry.json when available.

    Results are cached in _symbols_cache for the lifetime of the server process
    and invalidated whenever _save_symbol() writes to disk.
    """
    global _symbols_cache
    if _symbols_cache is not None:
        return _symbols_cache
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
    results = []
    for sym in registry.get("symbols", []):
        sym_id = sym.get("id", "")
        if not sym_id:
            continue
        # Verify the JSON file actually exists on disk
        json_path = SYMBOLS_ROOT / (sym_id.replace("/", os.sep) + ".json")
        if not json_path.exists():
            continue
        parts = sym_id.split("/")
        # Support both 3-part (standard/category/stem) and 4-part (source/standard/category/stem) IDs
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
        flag      = None
        try:
            sym_data  = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
            flag      = sym_data.get("flag", None)  # 'unrelated' | 'similar' | None
        except (json.JSONDecodeError, OSError):
            pass
        source = parts[0] if len(parts) == 4 else ""
        results.append({
            "path":      sym_id,
            "name":      sym.get("display_name") or (parts[-1] if parts else sym_id),
            "standard":  sym.get("standard", std_from_id).lower(),
            "category":  sym.get("category", cat_from_id),
            "source":    source,
            "completed": completed,
            "flag":      flag,
        })
    return results


def _symbols_from_scan() -> list[dict]:
    """Fallback: discover JSON files by walking the symbols root."""
    results = []
    for json_path in sorted(SYMBOLS_ROOT.rglob("*.json")):
        stem = json_path.stem
        if stem == "registry" or "_debug" in stem:
            continue
        rel   = json_path.relative_to(SYMBOLS_ROOT)
        parts = rel.parts
        completed = False
        flag      = None
        try:
            sym_data  = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
            flag      = sym_data.get("flag", None)
        except (json.JSONDecodeError, OSError):
            pass
        id_parts = rel.with_suffix("").parts
        source   = id_parts[0] if len(id_parts) == 4 else ""
        results.append({
            "path":      "/".join(id_parts),
            "name":      stem,
            "standard":  parts[0] if len(parts) >= 1 else "",
            "category":  parts[1] if len(parts) >= 2 else "",
            "source":    source,
            "completed": completed,
            "flag":      flag,
        })
    return results


def _load_symbol(rel: str) -> dict | None:
    """Load and return {meta, svg} for a symbol, or None if not found."""
    base = _safe_path(rel)
    if base is None:
        return None
    json_path = base.with_suffix(".json")
    svg_path  = base.with_suffix(".svg")
    if not json_path.exists() or not svg_path.exists():
        return None
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    svg  = svg_path.read_text(encoding="utf-8")
    return {"meta": meta, "svg": svg}


def _save_symbol(rel: str | None, meta: dict | None) -> tuple[bool, str]:
    """Write updated metadata JSON back to disk."""
    global _symbols_cache
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
    # Invalidate symbol list cache so 'completed' status is refreshed next time
    _symbols_cache = None
    return True, ""


def _generate_debug(rel: str | None, ports: list[dict]) -> tuple[bool, str]:
    """Overlay labelled port markers on the symbol SVG and save as *_debug.svg."""
    if not rel:
        return False, "missing path"
    base = _safe_path(rel)
    if base is None:
        return False, "invalid path"
    svg_path   = base.with_suffix(".svg")
    debug_path = base.parent / (base.stem + "_debug.svg")
    if not svg_path.exists():
        return False, f"SVG not found: {svg_path}"

    original = svg_path.read_text(encoding="utf-8")

    # Detect viewBox to size port radius proportionally
    m  = re.search(r'viewBox=["\'][\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)',
                   original)
    vw, vh = (float(m.group(1)), float(m.group(2))) if m else (80.0, 80.0)
    r    = max(2.0, min(vw, vh) * 0.04)
    fsz  = round(r * 1.1, 2)
    sw   = round(r * 0.15, 2)
    tsw  = round(fsz * 0.12, 2)

    parts: list[str] = ['<g id="port-debug" style="pointer-events:none;">']
    for p in ports:
        pid   = str(p.get("id", "?"))
        ptype = str(p.get("type", pid))  # fall back to id for old single-field format
        col   = _port_color(ptype)
        disp  = pid                       # label shows the name, not the type

        zone = p.get("zone")
        if zone:
            zx, zy = zone.get("x", 0), zone.get("y", 0)
            zw, zh = zone.get("width", 10), zone.get("height", 10)
            parts.append(
                f'  <rect x="{zx}" y="{zy}" width="{zw}" height="{zh}"'
                f' fill="{col}" fill-opacity="0.2" stroke="{col}"'
                f' stroke-width="{sw}" stroke-dasharray="{r*0.7} {r*0.35}"/>'
            )
            lx = zx + zw / 2
            ly = zy + zh / 2 + fsz * 0.4
            parts.append(
                f'  <text x="{lx}" y="{ly}" font-size="{fsz}" fill="{col}"'
                f' font-family="monospace" text-anchor="middle"'
                f' stroke="white" stroke-width="{tsw}" paint-order="stroke"'
                f'>{disp}</text>'
            )
        else:
            x, y = p.get("x", 0), p.get("y", 0)
            parts.append(
                f'  <circle cx="{x}" cy="{y}" r="{r}" fill="{col}"'
                f' stroke="white" stroke-width="{sw}" opacity="0.9"/>'
            )
            parts.append(
                f'  <text x="{x + r + fsz * 0.25}" y="{y + fsz * 0.38}"'
                f' font-size="{fsz}" fill="{col}" font-family="monospace"'
                f' stroke="white" stroke-width="{tsw}" paint-order="stroke"'
                f'>{disp}</text>'
            )
    parts.append("</g>")

    overlay   = "\n".join(parts)
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


def _export_completed(output_dir_str: str) -> dict:
    """Copy every completed symbol (SVG + JSON) from SYMBOLS_ROOT to output_dir.

    Only 4-part id symbols are exported (origin/standard/category/stem) so the
    output always has a clean origin/standard/category/ folder structure.
    svg_path and metadata_path inside each JSON are rewritten to be relative to
    output_dir so the package is self-contained.

    Returns a dict with keys: output_dir, copied, skipped, errors, message.
    """
    import shutil

    output_dir = (pathlib.Path(output_dir_str) if output_dir_str
                  else SYMBOLS_ROOT.parent / "completed")

    copied  = 0
    skipped = 0
    errors  = 0

    for json_path in sorted(SYMBOLS_ROOT.rglob("*.json")):
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        if not meta.get("completed", False):
            skipped += 1
            continue

        # Only export 4-part structure (origin/standard/category/stem)
        if meta.get("id", "").count("/") < 3:
            skipped += 1
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            errors += 1
            continue

        rel       = json_path.relative_to(SYMBOLS_ROOT)
        dest_json = output_dir / rel
        dest_svg  = dest_json.with_suffix(".svg")

        # Rewrite path fields relative to output_dir (self-contained package)
        exported_meta = dict(meta)
        exported_meta["svg_path"]      = rel.with_suffix(".svg").as_posix()
        exported_meta["metadata_path"] = rel.as_posix()

        try:
            dest_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg_path, dest_svg)
            dest_json.write_text(
                json.dumps(exported_meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            copied += 1
        except OSError:
            errors += 1

    return {
        "output_dir": str(output_dir),
        "copied":     copied,
        "skipped":    skipped,
        "errors":     errors,
        "message":    f"Exported {copied} symbol{'s' if copied != 1 else ''} to {output_dir}",
    }


def _patch_meta(rel: str | None, updates: dict) -> tuple[bool, str]:
    """Patch specific fields in a symbol's metadata JSON.

    Pass ``None`` as a value to remove the key from the JSON.
    """
    global _symbols_cache
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
        _symbols_cache = None
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _load_reports() -> dict:
    """Return the unrealistic-reports store, creating an empty one if absent."""
    try:
        if _UNREALISTIC_REPORTS_FILE.exists():
            return json.loads(_UNREALISTIC_REPORTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {"reports": []}


def _save_reports(data: dict) -> tuple[bool, str]:
    """Atomically write *data* to the reports file under the reports lock."""
    try:
        with _reports_lock:
            tmp = _UNREALISTIC_REPORTS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(_UNREALISTIC_REPORTS_FILE)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _flag_report_add(body: dict) -> tuple[dict | None, str]:
    """Append a new unrealistic-flag report entry; return the entry on success."""
    import time as _time
    effects = body.get("effects")
    if effects is None:
        return None, "missing effects"
    symbol  = body.get("symbol", "")
    label   = body.get("label", "")
    source  = body.get("source", "preview")
    ts_ms   = int(_time.time() * 1000)
    import datetime as _dt
    timestamp = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _reports_lock:
        data = _load_reports()
        existing_ids = {e["id"] for e in data["reports"]}
        seq = 0
        while f"{ts_ms}-{seq}" in existing_ids:
            seq += 1
        entry = {
            "id":        f"{ts_ms}-{seq}",
            "timestamp": timestamp,
            "symbol":    symbol,
            "label":     label,
            "effects":   effects,
            "source":    source,
        }
        data["reports"].append(entry)
        ok, err = _save_reports(data)
    if not ok:
        return None, err
    return entry, ""


def _flag_report_delete(report_id: str) -> tuple[bool, str]:
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


def _flag_reports_clear() -> tuple[int, str]:
    """Delete all reports; return (count_deleted, error_str)."""
    with _reports_lock:
        data = _load_reports()
        count = len(data["reports"])
        data["reports"] = []
        ok, err = _save_reports(data)
    if not ok:
        return 0, err
    return count, ""


def _random_geom(arr, rng=None):
    """Apply random mirror / rotation using PIL. Returns (new_arr, geom_dict).

    Geometry applied:
      - horizontal mirror  (p=0.5)
      - vertical flip      (p=0.5)
      - discrete rotation  (0 / 90 / 180 / 270°, equal weight)

    Returns a dict entry for each transform that was applied so it shows up
    in the effects display (value = 1.0 so it renders as 100%).
    """
    import random as _r
    from PIL import Image as _Img

    geom = {}
    img  = _Img.fromarray(arr)

    if _r.random() < 0.5:
        img = img.transpose(_Img.FLIP_LEFT_RIGHT)
        geom["mirror_h"] = 1.0

    if _r.random() < 0.5:
        img = img.transpose(_Img.FLIP_TOP_BOTTOM)
        geom["mirror_v"] = 1.0

    rot = _r.choice([0, 90, 180, 270])
    if rot == 90:
        img = img.transpose(_Img.ROTATE_90)
        geom["rot_90"] = 1.0
    elif rot == 180:
        img = img.transpose(_Img.ROTATE_180)
        geom["rot_180"] = 1.0
    elif rot == 270:
        img = img.transpose(_Img.ROTATE_270)
        geom["rot_270"] = 1.0

    import numpy as _np
    return _np.array(img, dtype=arr.dtype), geom


def _augment_preview(body: dict) -> tuple[dict | None, str]:
    """Render SVG → N augmented PNGs in memory, return base64 list.

    Parameters
    ----------
    count               : int  – variations to generate (1–200, default 1)
    randomize_per_image : bool – if True each image gets an independent random
                          effect subset; otherwise the supplied effects are
                          varied ±30 % per image.
    """
    import base64
    import io as _io
    import random as _random

    rel           = body.get("path", "")
    effects       = {k: float(v) for k, v in body.get("effects", {}).items()}
    size          = max(64, min(2048, int(body.get("size", 512))))
    count         = max(1, min(200, int(body.get("count", 1))))
    randomize_per = bool(body.get("randomize_per_image", False))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"

    try:
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER
        from src.svg_utils import _render_svg_to_png

        # Render at intrinsic SVG dimensions then resize to target size.
        png_bytes = _render_svg_to_png(svg_path)
        img = Image.open(_io.BytesIO(png_bytes)).convert("RGB")
        if img.width != size or img.height != size:
            img = img.resize((size, size), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)

        images_out: list[dict] = []
        for _ in range(count):
            if randomize_per:
                n      = _random.randint(3, 7)
                picked = _random.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                varied = {name: round(_random.uniform(0.15, 0.65), 2) for name in picked}
            elif effects:
                varied = {
                    name: round(float(np.clip(intensity * _random.uniform(0.7, 1.3), 0.0, 1.0)), 3)
                    for name, intensity in effects.items() if intensity > 0.0
                }
            else:
                varied = {}
            frame, geom = _random_geom(arr)
            varied = {**geom, **varied}
            out = apply_effects(frame, varied)
            buf = _io.BytesIO()
            Image.fromarray(out).save(buf, format="PNG")
            images_out.append({
                "src":     "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
                "effects": varied,
            })

        return {"images": images_out}, ""
    except Exception as exc:
        return None, str(exc)


def _augment_generate(body: dict) -> tuple[dict | None, str]:
    """Generate count augmented PNG variants.

    Parameters (from JSON body)
    ---------------------------
    randomize_per_image : bool  — if True each image gets independent random effects
                                  from the full catalogue; if False the supplied
                                  effects are varied ±30 % per image.
    return_images       : bool  — if True include base64 PNGs in the response.
    """
    import base64
    import io as _io
    import random as _random

    rel              = body.get("path", "")
    effects          = {k: float(v) for k, v in body.get("effects", {}).items()}
    count            = max(1, min(100, int(body.get("count", 5))))
    size             = max(64, min(2048, int(body.get("size", 512))))
    output_dir       = (body.get("output_dir") or "").strip() or "./augmented"
    randomize_per    = bool(body.get("randomize_per_image", False))
    return_images    = bool(body.get("return_images", False))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"

    try:
        import cairosvg
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER

        out_dir = pathlib.Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        svg_text  = svg_path.read_text(encoding="utf-8")
        png_bytes = cairosvg.svg2png(
            bytestring=svg_text.encode("utf-8"),
            output_width=size,
            output_height=size,
        )
        base_arr = np.array(
            Image.open(_io.BytesIO(png_bytes)).convert("RGB"), dtype=np.uint8
        )
        stem       = base.stem
        images_b64 = []

        for i in range(count):
            if randomize_per:
                n      = _random.randint(3, 7)
                picked = _random.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                varied = {name: round(_random.uniform(0.15, 0.65), 2) for name in picked}
            else:
                varied = {
                    name: float(np.clip(intensity * _random.uniform(0.7, 1.3), 0.0, 1.0))
                    for name, intensity in effects.items()
                    if intensity > 0.0
                }

            frame, geom = _random_geom(base_arr)
            varied = {**geom, **varied}
            arr   = apply_effects(frame, varied)
            fname = out_dir / f"{stem}_aug_{i + 1:04d}.png"
            Image.fromarray(arr).save(fname)

            if return_images:
                buf = _io.BytesIO()
                Image.fromarray(arr).save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                images_b64.append({
                    "src":     f"data:image/png;base64,{b64}",
                    "effects": varied,
                })

        result: dict = {"saved": count, "output_dir": str(out_dir.resolve())}
        if return_images:
            result["images"] = images_b64
        return result, ""
    except Exception as exc:
        return None, str(exc)


def _tight_bbox_yolo(arr) -> tuple | None:
    """Return YOLO-normalised (cx, cy, w, h) bounding box for non-white pixels.

    Scans *arr* (uint8 HxWx3) for pixels whose mean channel value is below 240
    and returns the normalised centre + size of their tight bounding box.
    Returns ``None`` if the image is blank (all white).
    """
    import numpy as _np
    gray = arr.mean(axis=2)
    mask = gray < 240
    rows = _np.where(mask.any(axis=1))[0]
    cols = _np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None
    H, W = arr.shape[:2]
    r0, r1 = int(rows[0]), int(rows[-1])
    c0, c1 = int(cols[0]), int(cols[-1])
    cx = ((c0 + c1) / 2.0) / W
    cy = ((r0 + r1) / 2.0) / H
    bw = (c1 - c0 + 1.0) / W
    bh = (r1 - r0 + 1.0) / H
    return (cx, cy, bw, bh)


def _augment_batch(body: dict):
    """Generator: yields SSE progress events while augmenting a filtered symbol set.

    Emitted event shapes
    --------------------
    {"type": "start",    "total": N}
    {"type": "progress", "current": i, "total": N, "name": str,
                         "status": "ok"|"skipped"|"error", "saved": cumulative}
    {"type": "done",     "processed": N, "saved": N, "skipped": N,
                         "errors": N, "output_dir": str,
                         "format": "png"|"yolo", ["class_count": N]}
    """
    import io as _io
    import base64
    import random as _random

    source    = body.get("source",   "").strip()
    standard  = body.get("standard", "").strip()
    effects   = {k: float(v) for k, v in body.get("effects", {}).items()}
    size      = max(64, min(2048, int(body.get("size",  512))))
    count     = max(1,  min(200,  int(body.get("count", 1))))
    out_str   = (body.get("output_dir") or "").strip() or "./augmented"
    rand_per  = bool(body.get("randomize_per_image", False))
    fmt       = body.get("format", "png")   # "png" | "yolo"

    symbols = _list_symbols()
    if source:   symbols = [s for s in symbols if s["source"]   == source]
    if standard: symbols = [s for s in symbols if s["standard"] == standard]
    total = len(symbols)

    if total == 0:
        yield {"type": "done", "processed": 0, "saved": 0,
               "skipped": 0, "errors": 0, "output_dir": out_str, "format": fmt}
        return

    _batch_cancel.clear()
    yield {"type": "start", "total": total}

    try:
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER
        from src.svg_utils import _render_svg_to_png
    except Exception as exc:
        yield {"type": "done", "processed": 0, "saved": 0, "skipped": total,
               "errors": 1, "output_dir": out_str, "format": fmt, "error": str(exc)}
        return

    out_dir = pathlib.Path(out_str)
    out_dir.mkdir(parents=True, exist_ok=True)

    # YOLO setup
    def _sym_cls_name(sym_id: str) -> str:
        parts = sym_id.split("/")
        return f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else parts[-1]

    if fmt == "yolo":
        # Per-symbol class names (category/stem) for fine-grained specificity
        all_cats = sorted({_sym_cls_name(sym["path"]) for sym in symbols})
        class_map  = {cls: i for i, cls in enumerate(all_cats)}
        n_classes  = len(all_cats)
        img_dir    = out_dir / "images" / "train"
        lbl_dir    = out_dir / "labels" / "train"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        # Write data.yaml (no PyYAML dependency — plain string)
        names_block = "\n".join(f"  {i}: {c}" for i, c in enumerate(all_cats))
        (out_dir / "data.yaml").write_text(
            f"path: {out_dir.resolve()}\n"
            f"train: images/train\n"
            f"nc: {n_classes}\n"
            f"names:\n{names_block}\n",
            encoding="utf-8",
        )
    else:
        img_dir   = out_dir
        class_map = {}
        n_classes = 0

    processed = saved = skipped = errors = 0

    for i, sym in enumerate(symbols):
        if _batch_cancel.is_set():
            yield {"type": "cancelled", "processed": processed, "saved": saved,
                   "skipped": skipped + (total - i), "errors": errors}
            return

        sym_id = sym["path"]
        base   = _safe_path(sym_id)
        name   = sym.get("name", sym_id)

        if base is None:
            errors += 1
            yield {"type": "progress", "current": i + 1, "total": total,
                   "name": name, "status": "error", "saved": saved}
            continue

        svg_path = base.with_suffix(".svg")
        if not svg_path.exists():
            skipped += 1
            yield {"type": "progress", "current": i + 1, "total": total,
                   "name": name, "status": "skipped", "saved": saved}
            continue

        try:
            png_bytes = _render_svg_to_png(svg_path)
            img = Image.open(_io.BytesIO(png_bytes)).convert("RGB")
            if img.width != size or img.height != size:
                img = img.resize((size, size), Image.LANCZOS)
            arr = np.array(img, dtype=np.uint8)

            stem = sym_id.replace("/", "_")

            # YOLO: class index for this symbol
            if fmt == "yolo":
                cls_idx = class_map.get(_sym_cls_name(sym_id), 0)

            for j in range(count):
                if rand_per:
                    n      = _random.randint(3, 7)
                    picked = _random.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                    varied = {nm: round(_random.uniform(0.15, 0.65), 2) for nm in picked}
                elif effects:
                    varied = {
                        nm: float(np.clip(intensity * _random.uniform(0.7, 1.3), 0.0, 1.0))
                        for nm, intensity in effects.items() if intensity > 0.0
                    }
                else:
                    varied = {}

                out_arr = apply_effects(arr.copy(), varied)
                fname   = f"{stem}_aug_{j + 1:04d}"
                Image.fromarray(out_arr).save(img_dir / f"{fname}.png")

                if fmt == "yolo":
                    bbox = _tight_bbox_yolo(out_arr)
                    if bbox:
                        cx, cy, bw, bh = bbox
                        (lbl_dir / f"{fname}.txt").write_text(
                            f"{cls_idx} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n",
                            encoding="utf-8",
                        )

                saved += 1

            processed += 1
            yield {"type": "progress", "current": i + 1, "total": total,
                   "name": name, "status": "ok", "saved": saved}

        except Exception as exc:
            errors += 1
            yield {"type": "progress", "current": i + 1, "total": total,
                   "name": name, "status": "error", "saved": saved,
                   "error": str(exc)}

    done = {"type": "done", "processed": processed, "saved": saved,
            "skipped": skipped, "errors": errors,
            "output_dir": str(out_dir.resolve()), "format": fmt}
    if fmt == "yolo":
        done["class_count"] = n_classes
    yield done


def _augment_combo(body: dict) -> tuple[dict | None, str]:
    """Generate all 1-, 2-, and 3-effect combinations of the selected effects.

    Returns a list of ``{src, label}`` objects — one per combination — so the
    frontend can display every combination in a grid.  Limits to C(n,1..3) so
    the count stays manageable even with many effects enabled.
    """
    import base64
    import io as _io
    import itertools

    rel       = body.get("path", "")
    effects   = {k: float(v) for k, v in body.get("effects", {}).items() if float(v) > 0}
    size      = max(64, min(2048, int(body.get("size", 512))))
    max_combo = max(1, min(3, int(body.get("max_combo", 3))))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"
    if not effects:
        return None, "no effects selected"

    try:
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects
        from src.svg_utils import _render_svg_to_png

        png_bytes = _render_svg_to_png(svg_path)
        img = Image.open(_io.BytesIO(png_bytes)).convert("RGB")
        if img.width != size or img.height != size:
            img = img.resize((size, size), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)

        effect_names = list(effects.keys())
        combos: list[dict] = []

        for n in range(1, min(max_combo, len(effect_names)) + 1):
            for combo in itertools.combinations(effect_names, n):
                combo_effects = {name: effects[name] for name in combo}
                out = apply_effects(arr.copy(), combo_effects)
                buf = _io.BytesIO()
                Image.fromarray(out).save(buf, format="PNG")
                b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
                combos.append({"src": b64, "label": " + ".join(combo), "effects": combo_effects})

        return {"combos": combos, "total": len(combos)}, ""
    except Exception as exc:
        return None, str(exc)


# entry point

def main(argv: list[str] | None = None) -> None:
    global SYMBOLS_ROOT, SERVER_PORT

    parser = argparse.ArgumentParser(
        description="Browser-based snap-point editor for P&ID SVG symbols."
    )
    parser.add_argument(
        "--symbols",
        default=str(pathlib.Path(__file__).parent / "processed"),
        help="Path to the symbols root directory (default: ./processed).",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", 7421)),
        help="Local HTTP port (default: 7421, or $PORT env var).",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HOST", "127.0.0.1"),
        help="Bind address (default: 127.0.0.1, or $HOST env var). Use 0.0.0.0 for Docker.",
    )
    args = parser.parse_args(argv)

    SYMBOLS_ROOT = pathlib.Path(args.symbols).resolve()
    SERVER_PORT  = args.port
    SERVER_HOST  = args.host

    if not SYMBOLS_ROOT.is_dir():
        print(f"Error: symbols directory not found: {SYMBOLS_ROOT}")
        return

    if not EDITOR_DIR.is_dir():
        print(f"Error: editor/ directory not found: {EDITOR_DIR}")
        return

    display_host = "127.0.0.1" if SERVER_HOST == "0.0.0.0" else SERVER_HOST
    url    = f"http://{display_host}:{SERVER_PORT}"
    server = http.server.ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), Handler)

    print(f"Symbol Studio  →  {url}")
    print(f"Symbols root →  {SYMBOLS_ROOT}")
    print(f"Editor dir   →  {EDITOR_DIR}")
    print("Press Ctrl+C to stop.")

    if not os.environ.get("NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
