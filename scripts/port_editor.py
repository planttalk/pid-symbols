#!/usr/bin/env python3
"""
port_editor.py
--------------
Browser-based GUI for manually editing connection snap-points on P&ID SVG
symbols.  No external Python dependencies — stdlib only.

Controls:
  Click canvas      → place a new port (using the active type)
  Click a marker    → select it  (change type via the type buttons)
  Drag a marker     → reposition it
  Right-click/Del   → delete selected port
  Save              → persist snap_points in JSON + regenerate _debug.svg

Port types: in · out · in_out (bidirectional) · signal · process
            north · south · east · west · custom (free text)

Usage:
    python scripts/port_editor.py
    python scripts/port_editor.py --processed path/to/processed --port 8765
"""

import argparse
import json
import re
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "processed"

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


def _overlay_svg(svg_text: str, snap_points: list[dict]) -> str:
    """Inject snap-point markers into an SVG string."""
    if not snap_points:
        return svg_text
    vb_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_text)
    radius = 4.0
    label_size = 5.0
    if vb_match:
        try:
            parts = [float(v) for v in vb_match.group(1).split()]
            if len(parts) >= 4:
                shorter    = min(parts[2], parts[3])
                radius     = max(2.0, round(shorter * 0.025, 2))
                label_size = max(3.0, round(shorter * 0.04,  2))
        except ValueError:
            pass
    stroke_w = round(radius * 0.3,      2)
    text_sw  = round(label_size * 0.15, 2)
    label_dx = round(radius * 1.3,      2)
    label_dy = round(label_size * 0.35, 2)
    lines = ['<g id="snap-points" style="pointer-events:none;font-family:sans-serif;">']
    for pt in snap_points:
        pid   = str(pt.get("id", "?"))
        x, y  = pt["x"], pt["y"]
        color = _PORT_COLORS.get(pid, _DEFAULT_COLOR)
        disp  = "in/out" if pid == "in_out" else pid
        lines.append(
            f'  <circle cx="{x}" cy="{y}" r="{radius}"'
            f' fill="{color}" fill-opacity="0.8"'
            f' stroke="white" stroke-width="{stroke_w}"/>'
        )
        lines.append(
            f'  <text x="{x + label_dx}" y="{y + label_dy}"'
            f' font-size="{label_size}" fill="{color}"'
            f' stroke="white" stroke-width="{text_sw}" paint-order="stroke"'
            f'>{disp}</text>'
        )
    lines.append("</g>")
    overlay   = "\n".join(lines)
    close_idx = svg_text.rfind("</svg>")
    if close_idx == -1:
        return svg_text + "\n" + overlay
    return svg_text[:close_idx] + "\n" + overlay + "\n" + svg_text[close_idx:]


# HTTP handler

class EditorHandler(BaseHTTPRequestHandler):
    processed_dir: Path  # set on the class before starting

    def log_message(self, fmt, *args):  # silence access log
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data) -> None:
        self._send(200, "application/json; charset=utf-8",
                   json.dumps(data, ensure_ascii=False).encode())

    def _error(self, code: int, msg: str) -> None:
        self._send(code, "application/json",
                   json.dumps({"error": msg}).encode())

    def do_GET(self):
        p  = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)
        if p.path == "/":
            self._send(200, "text/html; charset=utf-8", _HTML.encode())
        elif p.path == "/api/symbols":
            self._api_symbols()
        elif p.path == "/api/symbol":
            self._api_get(qs.get("path", [""])[0])
        else:
            self._error(404, "not found")

    def do_POST(self):
        p  = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)
        if p.path == "/api/symbol":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            self._api_save(qs.get("path", [""])[0], body)
        else:
            self._error(404, "not found")

    # API methods

    def _api_symbols(self):
        reg_path = self.processed_dir / "registry.json"
        if not reg_path.exists():
            self._error(404, "registry.json missing — run main.py first")
            return
        with open(reg_path, encoding="utf-8") as fh:
            registry = json.load(fh)
        out = []
        for sym in registry.get("symbols", []):
            meta_rel = sym.get("metadata_path", "")
            # metadata_path is relative to repo root
            abs_path = REPO_ROOT / meta_rel if meta_rel else None
            if abs_path and abs_path.exists():
                rel = str(abs_path.relative_to(self.processed_dir)).replace("\\", "/")
            else:
                rel = ""
            out.append({
                "path":         rel,
                "filename":     sym.get("filename", ""),
                "display_name": sym.get("display_name", ""),
                "standard":     sym.get("standard", ""),
                "category":     sym.get("category", ""),
                "pointCount":   len(sym.get("snap_points", [])),
            })
        self._json(out)

    def _api_get(self, rel: str):
        if not rel:
            self._error(400, "path required")
            return
        json_path = (self.processed_dir / rel).resolve()
        if not json_path.is_relative_to(self.processed_dir) or not json_path.exists():
            self._error(404, f"not found: {rel}")
            return
        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            self._error(404, "SVG not found")
            return
        with open(json_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        self._json({
            "snapPoints": meta.get("snap_points", []),
            "svgContent": svg_path.read_text(encoding="utf-8", errors="replace"),
        })

    def _api_save(self, rel: str, body: bytes):
        if not rel:
            self._error(400, "path required")
            return
        json_path = (self.processed_dir / rel).resolve()
        if not json_path.is_relative_to(self.processed_dir) or not json_path.exists():
            self._error(404, f"not found: {rel}")
            return
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            self._error(400, str(exc))
            return
        pts = data.get("snapPoints", [])
        for pt in pts:
            if not isinstance(pt.get("id"), str) or \
               not isinstance(pt.get("x"), (int, float)) or \
               not isinstance(pt.get("y"), (int, float)):
                self._error(400, "invalid point structure")
                return
        pts = [{"id": pt["id"],
                "x": round(float(pt["x"]), 2),
                "y": round(float(pt["y"]), 2)} for pt in pts]
        with open(json_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["snap_points"] = pts
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
        # Regenerate debug SVG
        svg_path   = json_path.with_suffix(".svg")
        debug_path = json_path.with_name(json_path.stem + "_debug.svg")
        if svg_path.exists():
            debug_path.write_text(
                _overlay_svg(svg_path.read_text(encoding="utf-8", errors="replace"), pts),
                encoding="utf-8",
            )
        self._json({"ok": True, "saved": len(pts)})


# Embedded UI

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Port Editor — P&amp;ID Symbols</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  display: flex; height: 100vh; overflow: hidden;
  font: 13px/1.4 system-ui, sans-serif;
  background: #12121f; color: #dde;
}

/* ── Left panel ── */
#panel-left {
  width: 240px; display: flex; flex-direction: column;
  background: #16213e; border-right: 1px solid #243560;
}
#panel-left h2 {
  padding: 10px 12px 6px; font-size: 11px;
  text-transform: uppercase; letter-spacing: .1em; color: #6a8aaa;
}
#search {
  margin: 0 10px 8px; padding: 6px 10px;
  background: #0f2040; border: 1px solid #243560;
  border-radius: 4px; color: #dde; font-size: 12px; outline: none;
  width: calc(100% - 20px);
}
#search:focus { border-color: #4fc3f7; }
#sym-list { flex: 1; overflow-y: auto; }
.sym-item {
  padding: 7px 12px; cursor: pointer;
  border-bottom: 1px solid #1a2a3e;
  display: flex; flex-direction: column; gap: 2px;
}
.sym-item:hover  { background: #1e3458; }
.sym-item.active { background: #0f3060; border-left: 3px solid #4fc3f7; padding-left: 9px; }
.sym-name { font-size: 12px; color: #cce; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sym-meta { font-size: 10px; color: #4a6a8a; display: flex; gap: 8px; }
.sym-pts  { color: #4fc3f7; }
.sym-none { color: #e57373; }

/* ── Center panel ── */
#panel-center {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
#toolbar {
  height: 36px; background: #16213e; border-bottom: 1px solid #243560;
  display: flex; align-items: center; padding: 0 12px; gap: 12px;
  font-size: 11px; color: #5a8aaa;
}
#tb-name { color: #aac; font-weight: 600; font-size: 12px; }
#svg-area {
  flex: 1; overflow: auto; display: flex;
  align-items: center; justify-content: center;
  background: #0e0e1c; padding: 24px;
}
#svg-container {
  position: relative; display: inline-block; cursor: crosshair;
  background: white; border-radius: 2px;
  box-shadow: 0 4px 24px rgba(0,0,0,.6);
}
#svg-container svg {
  display: block; max-width: 70vw; max-height: calc(100vh - 140px);
}
#empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px;
  color: #2a4a6a; min-width: 400px; min-height: 300px;
}
#empty svg { opacity: .3; }
#statusbar {
  height: 26px; background: #16213e; border-top: 1px solid #243560;
  display: flex; align-items: center; padding: 0 12px;
  font-size: 11px; color: #4a6a8a; gap: 20px;
}
#st-coords { font-variant-numeric: tabular-nums; min-width: 140px; }
#st-msg    { color: #81c784; }

/* ── Right panel ── */
#panel-right {
  width: 272px; display: flex; flex-direction: column;
  background: #16213e; border-left: 1px solid #243560; overflow-y: auto;
}
.section {
  padding: 10px 12px;
  border-bottom: 1px solid #1a2a3e;
}
.section h3 {
  font-size: 10px; text-transform: uppercase; letter-spacing: .1em;
  color: #6a8aaa; margin-bottom: 8px;
}

/* Symbol info */
#sym-info { font-size: 11px; color: #8a9aaa; line-height: 1.8; }
#sym-info b { color: #cce; }

/* Type grid */
#type-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px;
}
.type-btn {
  padding: 5px 2px; border-radius: 4px; border: 2px solid transparent;
  background: #0f2030; font-size: 10px; font-weight: 700;
  cursor: pointer; text-align: center; transition: filter .12s, border-color .12s;
}
.type-btn:hover  { filter: brightness(1.4); }
.type-btn.active { border-color: currentColor; filter: brightness(1.3); }
#custom-row {
  display: none; margin-top: 7px; gap: 6px; align-items: center;
}
#custom-row.visible { display: flex; }
#custom-id {
  flex: 1; padding: 5px 8px; background: #0f2030;
  border: 1px solid #2a4060; border-radius: 4px;
  color: #dde; font-size: 11px; outline: none;
}
#custom-id:focus { border-color: #4fc3f7; }

/* Port list */
#port-list { flex: 1; overflow-y: auto; }
.port-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-bottom: 1px solid #1a2a3e; cursor: pointer;
}
.port-row:hover    { background: #1a2a3e; }
.port-row.selected { background: #0f3060; }
.port-badge {
  width: 36px; height: 18px; border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; color: white; flex-shrink: 0;
}
.port-label  { flex: 1; font-size: 11px; color: #bbc; }
.port-coords { font-size: 10px; color: #4a6a8a; }
.port-del {
  background: none; border: none; color: #c57373;
  cursor: pointer; font-size: 16px; padding: 0 3px; line-height: 1;
  border-radius: 3px;
}
.port-del:hover { background: #3a1a1a; }

/* Actions */
#actions {
  padding: 10px 12px; display: flex; gap: 8px; background: #13192e;
  border-top: 1px solid #243560;
}
.btn {
  flex: 1; padding: 8px; border-radius: 4px; border: none;
  font-size: 12px; font-weight: 700; cursor: pointer; transition: filter .12s;
}
.btn:hover    { filter: brightness(1.2); }
.btn:disabled { opacity: .35; cursor: default; filter: none; }
#btn-save  { background: #1565C0; color: #fff; }
#btn-reset { background: #2a3040; color: #8a9aaa; }
</style>
</head>
<body>

<!-- ── Left: symbol browser ── -->
<div id="panel-left">
  <h2>Symbols</h2>
  <input id="search" placeholder="Search…" autocomplete="off" oninput="filterList()">
  <div id="sym-list"></div>
</div>

<!-- ── Center: SVG canvas ── -->
<div id="panel-center">
  <div id="toolbar">
    <span id="tb-name">No symbol selected</span>
    <span id="tb-hint">Select a symbol to begin</span>
  </div>
  <div id="svg-area">
    <div id="svg-container">
      <div id="empty">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="1.2">
          <rect x="2" y="2" width="20" height="20" rx="3"/>
          <circle cx="7"  cy="12" r="1.8"/>
          <circle cx="17" cy="12" r="1.8"/>
          <line x1="8.8" y1="12" x2="15.2" y2="12"/>
        </svg>
        <span>Select a symbol from the left panel</span>
      </div>
    </div>
  </div>
  <div id="statusbar">
    <span id="st-coords">—</span>
    <span id="st-msg"></span>
  </div>
</div>

<!-- ── Right: port editor ── -->
<div id="panel-right">
  <div class="section">
    <h3>Symbol</h3>
    <div id="sym-info"><span style="color:#2a4a6a">Nothing loaded</span></div>
  </div>

  <div class="section">
    <h3>Port type <small style="font-size:9px;text-transform:none;color:#4a6a8a">
      — click canvas to place</small></h3>
    <div id="type-grid"></div>
    <div id="custom-row">
      <input id="custom-id" placeholder="type an ID…" maxlength="32"
             oninput="onCustomInput()">
    </div>
  </div>

  <div class="section" style="flex:1;padding-bottom:0">
    <h3>Ports <span id="pt-count" style="color:#4fc3f7"></span></h3>
    <div id="port-list"></div>
  </div>

  <div id="actions">
    <button class="btn" id="btn-save"  onclick="saveSymbol()" disabled>Save</button>
    <button class="btn" id="btn-reset" onclick="resetSymbol()" disabled>Reset</button>
  </div>
</div>

<script>
// ── Constants ─────────────────────────────────────────────────────────────────
const TYPES = [
  { id:'in',      label:'in',      color:'#2196F3' },
  { id:'out',     label:'out',     color:'#F44336' },
  { id:'in_out',  label:'in/out',  color:'#009688' },
  { id:'signal',  label:'signal',  color:'#9C27B0' },
  { id:'process', label:'process', color:'#FF9800' },
  { id:'north',   label:'north',   color:'#4CAF50' },
  { id:'south',   label:'south',   color:'#4CAF50' },
  { id:'east',    label:'east',    color:'#4CAF50' },
  { id:'west',    label:'west',    color:'#4CAF50' },
  { id:'_custom', label:'custom…', color:'#607D8B' },
];
const DEFAULT_COLOR = '#607D8B';
function portColor(id) {
  const t = TYPES.find(t => t.id === id);
  return t ? t.color : DEFAULT_COLOR;
}
function portDisplay(id) { return id === 'in_out' ? 'in/out' : id; }

// ── State ─────────────────────────────────────────────────────────────────────
let allSymbols  = [];
let curPath     = null;
let origPts     = [];
let pts         = [];   // working copy
let selIdx      = -1;
let activeType  = 'in';
let dirty       = false;

// Drag state
let drag = { active: false, idx: -1, ox: 0, oy: 0 };

// ── Boot ──────────────────────────────────────────────────────────────────────
buildTypeGrid();
(async () => {
  try {
    allSymbols = await (await fetch('/api/symbols')).json();
    renderList(allSymbols);
  } catch(e) {
    document.getElementById('sym-list').innerHTML =
      '<p style="padding:12px;color:#e57373">Failed to load symbols.<br>Run main.py first.</p>';
  }
})();

// ── Symbol list ───────────────────────────────────────────────────────────────
function renderList(list) {
  document.getElementById('sym-list').innerHTML = list.map(s => {
    const cls  = s.pointCount > 0 ? 'sym-pts' : 'sym-none';
    const lbl  = s.pointCount > 0 ? s.pointCount + ' pt' : 'no pts';
    const name = s.display_name || s.filename;
    return `<div class="sym-item" data-path="${xe(s.path)}"
              onclick="loadSymbol('${xe(s.path)}',this)">
      <div class="sym-name" title="${xe(name)}">${xe(name)}</div>
      <div class="sym-meta">
        <span>${xe(s.standard)}</span><span>${xe(s.category)}</span>
        <span class="${cls}">${lbl}</span>
      </div></div>`;
  }).join('');
}
function filterList() {
  const q = document.getElementById('search').value.toLowerCase();
  renderList(q ? allSymbols.filter(s =>
    (s.display_name||'').toLowerCase().includes(q) ||
    (s.filename||'').toLowerCase().includes(q) ||
    (s.category||'').toLowerCase().includes(q)
  ) : allSymbols);
}

// ── Load symbol ───────────────────────────────────────────────────────────────
async function loadSymbol(path, el) {
  if (dirty && !confirm('Unsaved changes — discard?')) return;
  document.querySelectorAll('.sym-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  curPath = path; dirty = false; selIdx = -1;

  const data = await (await fetch('/api/symbol?path=' + encodeURIComponent(path))).json();
  origPts = JSON.parse(JSON.stringify(data.snapPoints));
  pts     = JSON.parse(JSON.stringify(data.snapPoints));

  // Inject SVG inline
  const container = document.getElementById('svg-container');
  container.innerHTML = data.svgContent;
  document.getElementById('empty')?.remove();

  const svg = container.querySelector('svg');
  if (!svg) {
    container.innerHTML = '<p style="color:#e57373;padding:16px">Could not parse SVG</p>';
    return;
  }
  // Let CSS control size
  svg.removeAttribute('width'); svg.removeAttribute('height');
  svg.style.cssText = 'display:block;max-width:70vw;max-height:calc(100vh - 140px)';

  // Attach events
  svg.addEventListener('click',      onCanvasClick);
  svg.addEventListener('mousemove',  onMouseMove);
  svg.addEventListener('mouseleave', () => { document.getElementById('st-coords').textContent = '—'; });
  window.addEventListener('mouseup', stopDrag);

  // Add overlay layer
  const g = document.createElementNS('http://www.w3.org/2000/svg','g');
  g.id = 'port-overlay';
  svg.appendChild(g);

  const sym = allSymbols.find(s => s.path === path);
  document.getElementById('tb-name').textContent = sym ? (sym.display_name || sym.filename) : path;
  document.getElementById('tb-hint').textContent = 'Click to add · Drag to move · Right-click to delete';
  document.getElementById('sym-info').innerHTML = sym
    ? `<b>${xe(sym.display_name||sym.filename)}</b><br>Standard: ${xe(sym.standard)}<br>Category: ${xe(sym.category)}`
    : '';

  renderOverlay(); renderPortList(); setDirty(false);
}

// ── Coordinate helpers ────────────────────────────────────────────────────────
function getSvg() { return document.getElementById('svg-container')?.querySelector('svg'); }

function toSvgCoords(svg, cx, cy) {
  const rect = svg.getBoundingClientRect();
  const vb   = svg.viewBox.baseVal;
  if (!vb || vb.width === 0) {
    const w = parseFloat(svg.getAttribute('width'))  || rect.width;
    const h = parseFloat(svg.getAttribute('height')) || rect.height;
    return { x: (cx - rect.left) * (w / rect.width),
             y: (cy - rect.top)  * (h / rect.height) };
  }
  return { x: vb.x + (cx - rect.left) * vb.width  / rect.width,
           y: vb.y + (cy - rect.top)  * vb.height / rect.height };
}

function markerRadius(svg) {
  const vb = svg.viewBox?.baseVal;
  return Math.max(2, Math.min((vb?.width||100), (vb?.height||100)) * 0.028);
}

// ── Canvas interaction ────────────────────────────────────────────────────────
function onCanvasClick(e) {
  if (drag.active) return;
  if (e.target.closest('#port-overlay')) return;  // handled by marker
  if (!curPath) return;

  const svg    = getSvg();
  const {x, y} = toSvgCoords(svg, e.clientX, e.clientY);
  const id     = activeType === '_custom'
    ? (document.getElementById('custom-id').value.trim() || 'port')
    : activeType;

  pts.push({ id, x: Math.round(x * 100)/100, y: Math.round(y * 100)/100 });
  selIdx = pts.length - 1;
  setDirty(true); renderOverlay(); renderPortList();
}

function onMouseMove(e) {
  const svg = getSvg(); if (!svg) return;
  const {x, y} = toSvgCoords(svg, e.clientX, e.clientY);
  document.getElementById('st-coords').textContent = `x: ${x.toFixed(1)}  y: ${y.toFixed(1)}`;
  if (drag.active && drag.idx >= 0) {
    pts[drag.idx].x = Math.round((x + drag.ox) * 100) / 100;
    pts[drag.idx].y = Math.round((y + drag.oy) * 100) / 100;
    setDirty(true); renderOverlay(); renderPortList();
  }
}

function startDrag(e, idx) {
  e.stopPropagation();
  const {x, y} = toSvgCoords(getSvg(), e.clientX, e.clientY);
  drag = { active: true, idx, ox: pts[idx].x - x, oy: pts[idx].y - y };
  selIdx = idx; renderOverlay(); renderPortList();
}
function stopDrag() { drag.active = false; drag.idx = -1; }

// ── Overlay ───────────────────────────────────────────────────────────────────
function renderOverlay() {
  const svg = getSvg(); if (!svg) return;
  let g = document.getElementById('port-overlay');
  if (!g) { g = document.createElementNS('http://www.w3.org/2000/svg','g'); g.id='port-overlay'; svg.appendChild(g); }
  g.innerHTML = '';

  const r  = markerRadius(svg);
  const fs = r * 1.7;
  const sw = r * 0.28;

  pts.forEach((pt, i) => {
    const color = portColor(pt.id);
    const sel   = i === selIdx;
    const cr    = sel ? r * 1.6 : r;

    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx', pt.x); c.setAttribute('cy', pt.y); c.setAttribute('r', cr);
    c.setAttribute('fill', color); c.setAttribute('fill-opacity', sel ? '1' : '0.82');
    c.setAttribute('stroke', sel ? 'white' : 'rgba(255,255,255,0.4)');
    c.setAttribute('stroke-width', sel ? sw * 1.8 : sw);
    c.style.cursor = 'grab';
    c.addEventListener('mousedown',   e => startDrag(e, i));
    c.addEventListener('contextmenu', e => { e.preventDefault(); deletePort(i); });
    c.addEventListener('click',       e => { e.stopPropagation(); selectPort(i); });
    g.appendChild(c);

    const t = document.createElementNS('http://www.w3.org/2000/svg','text');
    t.setAttribute('x', pt.x + r * 1.35); t.setAttribute('y', pt.y + fs * 0.38);
    t.setAttribute('font-size', fs); t.setAttribute('font-family','sans-serif');
    t.setAttribute('fill', color);
    t.setAttribute('stroke', 'rgba(0,0,0,0.55)'); t.setAttribute('stroke-width', fs * 0.14);
    t.setAttribute('paint-order','stroke'); t.style.pointerEvents = 'none';
    t.textContent = portDisplay(pt.id);
    g.appendChild(t);
  });
}

// ── Port list ──────────────────────────────────────────────────────────────────
function renderPortList() {
  document.getElementById('pt-count').textContent = `(${pts.length})`;
  const el = document.getElementById('port-list');
  if (!pts.length) {
    el.innerHTML = '<p style="padding:10px 8px;color:#2a4a6a;font-size:11px">No ports — click the SVG to add one.</p>';
    return;
  }
  el.innerHTML = pts.map((pt, i) => {
    const color = portColor(pt.id);
    const disp  = portDisplay(pt.id);
    const sel   = i === selIdx ? ' selected' : '';
    const badge = disp.length > 4 ? disp.slice(0,4) : disp;
    return `<div class="port-row${sel}" onclick="selectPort(${i})">
      <div class="port-badge" style="background:${color}">${xe(badge)}</div>
      <div style="flex:1">
        <div class="port-label">${xe(disp)}</div>
        <div class="port-coords">${pt.x.toFixed(1)}, ${pt.y.toFixed(1)}</div>
      </div>
      <button class="port-del" onclick="event.stopPropagation();deletePort(${i})" title="Delete">×</button>
    </div>`;
  }).join('');
}

function selectPort(i) {
  selIdx = (selIdx === i) ? -1 : i;
  // Sync active type to the selected port's type
  if (selIdx >= 0) {
    const pid = pts[selIdx].id;
    const known = TYPES.find(t => t.id === pid);
    setType(known ? pid : '_custom', known ? null : pid);
  }
  renderOverlay(); renderPortList();
}

function deletePort(i) {
  pts.splice(i, 1);
  if (selIdx >= pts.length) selIdx = pts.length - 1;
  setDirty(true); renderOverlay(); renderPortList();
}

// ── Type selector ──────────────────────────────────────────────────────────────
function buildTypeGrid() {
  document.getElementById('type-grid').innerHTML = TYPES.map(t =>
    `<button class="type-btn${t.id === activeType ? ' active':''}"
      data-type="${t.id}" style="color:${t.color}"
      onclick="setType('${t.id}')">${t.label}</button>`
  ).join('');
}

function setType(id, customValue) {
  activeType = id;
  document.querySelectorAll('.type-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.type === id));
  const customRow = document.getElementById('custom-row');
  customRow.classList.toggle('visible', id === '_custom');
  if (customValue !== undefined && customValue !== null)
    document.getElementById('custom-id').value = customValue;

  // If a port is selected, retype it
  if (selIdx >= 0) {
    const newId = id === '_custom'
      ? (document.getElementById('custom-id').value.trim() || 'port')
      : id;
    pts[selIdx].id = newId;
    setDirty(true); renderOverlay(); renderPortList();
  }
}

function onCustomInput() {
  if (activeType !== '_custom' || selIdx < 0) return;
  pts[selIdx].id = document.getElementById('custom-id').value.trim() || 'port';
  setDirty(true); renderOverlay(); renderPortList();
}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if ((e.key === 'Delete' || e.key === 'Backspace') && selIdx >= 0) {
    deletePort(selIdx);
  } else if (e.key === 'Escape') {
    selIdx = -1; renderOverlay(); renderPortList();
  }
});

// ── Save / Reset ───────────────────────────────────────────────────────────────
async function saveSymbol() {
  if (!curPath) return;
  const r = await fetch('/api/symbol?path=' + encodeURIComponent(curPath), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapPoints: pts }),
  });
  const d = await r.json();
  if (d.ok) {
    origPts = JSON.parse(JSON.stringify(pts));
    setDirty(false);
    // Update sidebar count
    const sym = allSymbols.find(s => s.path === curPath);
    if (sym) {
      sym.pointCount = pts.length;
      const active = document.querySelector('.sym-item.active');
      if (active) {
        const sp = active.querySelector('.sym-pts,.sym-none');
        if (sp) { sp.className = pts.length ? 'sym-pts' : 'sym-none'; sp.textContent = pts.length ? pts.length + ' pt' : 'no pts'; }
      }
    }
    flash('✓ Saved ' + d.saved + ' port' + (d.saved !== 1 ? 's' : ''));
  } else {
    alert('Save failed: ' + (d.error || '?'));
  }
}

function resetSymbol() {
  if (!confirm('Discard all unsaved changes?')) return;
  pts = JSON.parse(JSON.stringify(origPts));
  selIdx = -1; setDirty(false); renderOverlay(); renderPortList();
}

function setDirty(v) {
  dirty = v;
  document.getElementById('btn-save').disabled  = !v || !curPath;
  document.getElementById('btn-reset').disabled = !v || !curPath;
}

function flash(msg) {
  const el = document.getElementById('st-msg');
  el.textContent = msg;
  setTimeout(() => { if (el.textContent === msg) el.textContent = ''; }, 3000);
}

// ── Util ───────────────────────────────────────────────────────────────────────
function xe(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""


# Entry point

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browser-based snap-point editor for P&ID SVG symbols."
    )
    parser.add_argument("--processed", default=None, metavar="DIR",
                        help="Processed directory (default: <repo>/processed).")
    parser.add_argument("--port", type=int, default=8765, metavar="N",
                        help="HTTP port to listen on (default: 8765).")
    args = parser.parse_args()

    processed = Path(args.processed).resolve() if args.processed else PROCESSED_DIR
    EditorHandler.processed_dir = processed

    server = HTTPServer(("127.0.0.1", args.port), EditorHandler)
    url    = f"http://127.0.0.1:{args.port}/"
    print(f"Port editor running at  {url}")
    print(f"Serving processed dir:  {processed}")
    print("Press Ctrl+C to stop.\n")

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
