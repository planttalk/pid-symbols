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

# ── globals set in main() ─────────────────────────────────────────────────────
SYMBOLS_ROOT: pathlib.Path
SERVER_PORT: int
_EDITOR_ROOT = pathlib.Path(__file__).parent / "editor"
# Serve from editor/dist/ (React build) when available, otherwise editor/ (legacy)
EDITOR_DIR = _EDITOR_ROOT / "dist" if (_EDITOR_ROOT / "dist").is_dir() else _EDITOR_ROOT

# ── port colour map (shared by _generate_debug) ───────────────────────────────
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


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, *_):
        pass  # silence request logging

    # ── low-level send helpers ─────────────────────────────────────────────────

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

    # ── GET ────────────────────────────────────────────────────────────────────

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

        else:
            self._error("Not found", 404)

    # ── POST ───────────────────────────────────────────────────────────────────

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

        else:
            self._error("Not found", 404)


# ── business logic ─────────────────────────────────────────────────────────────

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
        try:
            sym_data  = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
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
        try:
            sym_data  = json.loads(json_path.read_text(encoding="utf-8"))
            completed = bool(sym_data.get("completed", False))
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


def _augment_preview(body: dict) -> tuple[dict | None, str]:
    """Render SVG → PNG, apply degradation effects, return base64 PNG."""
    import base64
    import io as _io

    rel     = body.get("path", "")
    effects = {k: float(v) for k, v in body.get("effects", {}).items()}
    size    = max(64, min(2048, int(body.get("size", 512))))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"

    try:
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects
        from src.svg_utils import _render_svg_to_png

        # Render at intrinsic SVG dimensions (same as the YOLO pipeline) so
        # that the symbol geometry is correct, then resize to the target size.
        png_bytes = _render_svg_to_png(svg_path)
        img = Image.open(_io.BytesIO(png_bytes)).convert("RGB")
        if img.width != size or img.height != size:
            img = img.resize((size, size), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)
        arr = apply_effects(arr, effects)
        buf = _io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {"image": f"data:image/png;base64,{b64}"}, ""
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
                # Each image: independent random subset of ALL effects
                n      = _random.randint(3, 7)
                picked = _random.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                varied = {name: round(_random.uniform(0.2, 0.9), 2) for name in picked}
            else:
                # Vary the supplied effects ±30 %
                varied = {
                    name: float(np.clip(intensity * _random.uniform(0.7, 1.3), 0.0, 1.0))
                    for name, intensity in effects.items()
                    if intensity > 0.0
                }

            arr   = apply_effects(base_arr.copy(), varied)
            fname = out_dir / f"{stem}_aug_{i + 1:04d}.png"
            Image.fromarray(arr).save(fname)

            if return_images:
                buf = _io.BytesIO()
                Image.fromarray(arr).save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                images_b64.append(f"data:image/png;base64,{b64}")

        result: dict = {"saved": count, "output_dir": str(out_dir.resolve())}
        if return_images:
            result["images"] = images_b64
        return result, ""
    except Exception as exc:
        return None, str(exc)


# ── entry point ────────────────────────────────────────────────────────────────

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
        "--port", type=int, default=7421,
        help="Local HTTP port (default: 7421).",
    )
    args = parser.parse_args(argv)

    SYMBOLS_ROOT = pathlib.Path(args.symbols).resolve()
    SERVER_PORT  = args.port

    if not SYMBOLS_ROOT.is_dir():
        print(f"Error: symbols directory not found: {SYMBOLS_ROOT}")
        return

    if not EDITOR_DIR.is_dir():
        print(f"Error: editor/ directory not found: {EDITOR_DIR}")
        return

    url    = f"http://127.0.0.1:{SERVER_PORT}"
    server = http.server.HTTPServer(("127.0.0.1", SERVER_PORT), Handler)

    print(f"Symbol Studio  →  {url}")
    print(f"Symbols root →  {SYMBOLS_ROOT}")
    print(f"Editor dir   →  {EDITOR_DIR}")
    print("Press Ctrl+C to stop.")

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
