"""HTTP server for the studio editor."""

from __future__ import annotations

import http.server
import json
import os
import threading
import urllib.parse
from pathlib import Path

from . import augmentation as aug_module
from . import reports as reports_module
from . import symbols as symbols_module


EDITOR_DIR: Path | None = None
SERVER_PORT: int = 7421
SERVER_HOST: str = "127.0.0.1"
_batch_cancel = threading.Event()


def set_editor_dir(path: Path) -> None:
    """Set the editor directory."""
    global EDITOR_DIR
    EDITOR_DIR = path


def set_server_config(port: int, host: str) -> None:
    """Set server port and host."""
    global SERVER_PORT, SERVER_HOST
    SERVER_PORT = port
    SERVER_HOST = host


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _sse_stream(self, gen) -> None:
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

    def _send(
        self,
        body: str | bytes,
        ctype: str = "text/html; charset=utf-8",
        status: int = 200,
    ) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status: int = 200) -> None:
        self._send(
            json.dumps(obj, ensure_ascii=False),
            "application/json; charset=utf-8",
            status,
        )

    def _error(self, msg: str, status: int = 400) -> None:
        self._send(msg, "text/plain; charset=utf-8", status)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _serve_file(self, path: Path, ctype: str) -> None:
        try:
            self._send(path.read_bytes(), ctype)
        except OSError:
            self._error(f"File not found: {path.name}", 404)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        p = parsed.path

        STATIC_MIME = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }

        if p in ("/", "/index.html"):
            if EDITOR_DIR:
                self._serve_file(EDITOR_DIR / "index.html", "text/html; charset=utf-8")
            else:
                self._error("Editor directory not configured", 500)
            return

        if not p.startswith("/api/") and "." in p.split("/")[-1]:
            if EDITOR_DIR is None:
                self._error("Editor directory not configured", 500)
                return
            rel_clean = p.lstrip("/").replace("/", os.sep)
            try:
                target = (EDITOR_DIR / rel_clean).resolve()
                target.relative_to(EDITOR_DIR.resolve())
            except ValueError:
                self._error("Forbidden", 403)
                return
            ext = Path(rel_clean).suffix.lower()
            mime = STATIC_MIME.get(ext, "application/octet-stream")
            self._serve_file(target, mime)
            return

        if p == "/api/symbols":
            self._json(symbols_module.list_symbols())
            return

        if p == "/api/symbol":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._error("missing ?path=")
                return
            result = symbols_module.load_symbol(rel)
            if result is None:
                self._error(f"Symbol not found: {rel}", 404)
                return
            self._json(result)
            return

        if p == "/api/stats":
            self._json(symbols_module.compute_stats())
            return

        if p == "/api/flag-reports":
            self._json(reports_module.load_reports())
            return

        self._error("Not found", 404)

    def do_POST(self) -> None:
        body = self._read_body()
        p = urllib.parse.urlparse(self.path).path

        if p == "/api/save":
            ok, msg = symbols_module.save_symbol(body.get("path"), body.get("meta"))
            if ok:
                self._send("ok")
            else:
                self._error(msg, 500)
            return

        if p == "/api/debug":
            ok, msg = symbols_module.generate_debug(
                body.get("path"), body.get("ports", [])
            )
            if ok:
                self._send("ok")
            else:
                self._error(msg, 500)
            return

        if p == "/api/export-completed":
            from . import export_completed as ec_module

            out = body.get("output_dir", "").strip()
            result = ec_module.export_completed(out)
            self._json(result)
            return

        if p == "/api/augment-preview":
            result, err = aug_module.augment_preview(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)
            return

        if p == "/api/augment-generate":
            result, err = aug_module.augment_generate(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)
            return

        if p == "/api/augment-batch":
            self._sse_stream(aug_module.augment_batch(body, _batch_cancel))
            return

        if p == "/api/augment-cancel":
            _batch_cancel.set()
            self._json({"ok": True})
            return

        if p == "/api/flag":
            ok, msg = symbols_module.patch_meta(
                body.get("path"), {"flag": body.get("flag")}
            )
            if ok:
                self._send("ok")
            else:
                self._error(msg, 500)
            return

        if p == "/api/augment-combo":
            result, err = aug_module.augment_combo(body)
            if result is not None:
                self._json(result)
            else:
                self._error(err, 500)
            return

        if p == "/api/flag-report":
            entry, err = reports_module.flag_report_add(body)
            if entry is not None:
                self._json({"ok": True, "entry": entry})
            else:
                self._error(err, 500)
            return

        if p == "/api/flag-report-delete":
            ok, err = reports_module.flag_report_delete(body.get("id", ""))
            if ok:
                self._json({"ok": True})
            else:
                self._error(err, 500)
            return

        if p == "/api/flag-reports-clear":
            count, err = reports_module.flag_reports_clear()
            if err:
                self._error(err, 500)
            else:
                self._json({"ok": True, "deleted": count})
            return

        self._error("Not found", 404)


def run_server() -> None:
    """Run the HTTP server."""
    import webbrowser

    if EDITOR_DIR is None:
        print("Error: editor directory not configured")
        return

    if not EDITOR_DIR.is_dir():
        print(f"Error: editor directory not found: {EDITOR_DIR}")
        return

    display_host = "127.0.0.1" if SERVER_HOST == "0.0.0.0" else SERVER_HOST
    url = f"http://{display_host}:{SERVER_PORT}"
    server = http.server.ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), Handler)

    print(f"Symbol Studio  →  {url}")
    print(f"Editor dir   →  {EDITOR_DIR}")
    print("Press Ctrl+C to stop.")

    if not os.environ.get("NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
