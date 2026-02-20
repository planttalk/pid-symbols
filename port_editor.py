#!/usr/bin/env python3
"""port_editor.py — browser-based snap-point editor for P&ID SVG symbols.

Starts a local HTTP server and opens the editor in the default browser.
Static files are served from the editor/ directory next to this script.

Usage
-----
    python port_editor.py                           # ./processed root, port 7421
    python port_editor.py --symbols /path/to/syms
    python port_editor.py --port 8080
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
EDITOR_DIR = pathlib.Path(__file__).parent / "editor"

# ── port colour map (shared by _generate_debug) ───────────────────────────────
_PORT_COLORS: dict[str, str] = {
    "in":      "#2196F3",
    "out":     "#F44336",
    "in_out":  "#009688",
    "signal":  "#9C27B0",
    "process": "#FF9800",
    "north":   "#4CAF50",
    "south":   "#4CAF50",
    "east":    "#4CAF50",
    "west":    "#4CAF50",
}
_DEFAULT_COLOR = "#607D8B"


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

        if p in ("/", "/index.html"):
            self._serve_file(EDITOR_DIR / "index.html",
                             "text/html; charset=utf-8")

        elif p == "/style.css":
            self._serve_file(EDITOR_DIR / "style.css",
                             "text/css; charset=utf-8")

        elif p == "/app.js":
            self._serve_file(EDITOR_DIR / "app.js",
                             "application/javascript; charset=utf-8")

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


def _list_symbols() -> list[dict]:
    """Return symbol descriptors, using registry.json when available."""
    reg_path = SYMBOLS_ROOT / "registry.json"
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
            return _symbols_from_registry(registry)
        except (json.JSONDecodeError, OSError):
            pass
    return _symbols_from_scan()


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
        results.append({
            "path":     sym_id,
            "name":     sym.get("display_name") or (parts[-1] if parts else sym_id),
            "standard": sym.get("standard", parts[0] if parts else "").lower(),
            "category": sym.get("category", parts[1] if len(parts) > 1 else ""),
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
        results.append({
            "path":     "/".join(rel.with_suffix("").parts),
            "name":     stem,
            "standard": parts[0] if len(parts) >= 1 else "",
            "category": parts[1] if len(parts) >= 2 else "",
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
        pid  = str(p.get("id", "?"))
        x, y = p.get("x", 0), p.get("y", 0)
        col  = _port_color(pid)
        disp = "in/out" if pid == "in_out" else pid
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

    print(f"Port Editor  →  {url}")
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
