'use strict';

import { KNOWN_TYPES } from './constants.js';
import { state } from './state.js';
import { svg, wrap, symImg } from './dom.js';
import { updateGridPattern } from './canvas.js';
import { setStatus } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { clearFields } from './fields.js';
import { cancelMatch } from './match.js';
import { cancelMidMode } from './midpoint.js';
import { saveJSON } from './api.js';

// ── Symbol preview (hover on list item) ─────────────────────────────────────
const _svgCache  = new Map();
let   _prevTimer = null;

function _showPreview(svgStr, name) {
  const hint = document.getElementById('sym-preview-hint');
  const img  = document.getElementById('sym-preview-img');
  const lbl  = document.getElementById('sym-preview-name');
  hint.style.display = 'none';
  img.src             = 'data:image/svg+xml,' + encodeURIComponent(svgStr);
  img.style.display   = 'block';
  lbl.textContent     = name;
}

export async function previewSymbol(path, name) {
  clearTimeout(_prevTimer);
  _prevTimer = setTimeout(async () => {
    if (_svgCache.has(path)) { _showPreview(_svgCache.get(path), name); return; }
    try {
      const res  = await fetch('/api/symbol?path=' + encodeURIComponent(path));
      if (!res.ok) return;
      const data = await res.json();
      if (_svgCache.size >= 200) _svgCache.delete(_svgCache.keys().next().value);
      _svgCache.set(path, data.svg);
      _showPreview(data.svg, name);
    } catch { /* silent */ }
  }, 100);
}

// ── Stats ────────────────────────────────────────────────────────────────────
export async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    renderStats(await res.json());
  } catch { /* silent */ }
}

function renderStats(data) {
  const pct  = data.percentage ?? 0;
  const done = data.completed  ?? 0;
  const tot  = data.total      ?? 0;
  document.getElementById('stats-text').textContent =
    `${done} / ${tot} completed (${pct}%)`;
  document.getElementById('stats-fill').style.width = pct + '%';
}

// ── Symbol list ──────────────────────────────────────────────────────────────
export async function loadSymbolList() {
  try {
    const res     = await fetch('/api/symbols');
    state.allSymbols = await res.json();
  } catch {
    state.allSymbols = [];
    setStatus('Failed to load symbol list.');
  }
  renderSymbolList(state.allSymbols);
}

export function filterSymbols() {
  const q = document.getElementById('sym-search').value.toLowerCase();
  renderSymbolList(
    state.allSymbols.filter(s =>
      s.name.toLowerCase().includes(q) || s.path.toLowerCase().includes(q))
  );
}

export function renderSymbolList(list) {
  state.visibleSymbols = list;
  const el = document.getElementById('sym-list');
  el.innerHTML = '';

  const grpNameCount = {};
  for (const s of list) {
    const key = (s.standard || '') + '/' + (s.category || '') + '\x00' + s.name;
    grpNameCount[key] = (grpNameCount[key] || 0) + 1;
  }

  let lastGrp = null;
  for (const s of list) {
    const grp = (s.standard || '') + ' / ' + (s.category || '');
    if (grp !== lastGrp) {
      const h = document.createElement('div');
      h.className   = 'grp-head';
      h.textContent = grp;
      el.appendChild(h);
      lastGrp = grp;
    }
    const d = document.createElement('div');
    d.className = 'sym-item' +
      (s.path === state.currentPath ? ' active' : '') +
      (s.completed ? ' completed' : '');
    if (s.completed) {
      const check = document.createElement('span');
      check.className   = 'sym-check';
      check.textContent = '✓';
      d.appendChild(check);
    }
    d.appendChild(document.createTextNode(s.name));

    const key = (s.standard || '') + '/' + (s.category || '') + '\x00' + s.name;
    if (grpNameCount[key] > 1) {
      const parts    = s.path.split('/');
      const hint     = parts.length > 1 ? parts.slice(0, -1).join('/') : s.path;
      const disambig = document.createElement('span');
      disambig.className   = 'sym-disambig';
      disambig.textContent = ' · ' + hint;
      d.appendChild(disambig);
    }

    d.title = s.path;
    d.addEventListener('mouseenter', () => previewSymbol(s.path, s.name));
    d.addEventListener('click',      () => loadSymbol(s.path));
    el.appendChild(d);
  }
}

export function scrollSymListToActive() {
  const active = document.querySelector('#sym-list .sym-item.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

// ── Symbol loading ───────────────────────────────────────────────────────────
export async function loadSymbol(relPath) {
  if (state.drag) return;
  state.currentPath = relPath;
  state.selection   = new Set();
  state.selIdx      = null;
  cancelMatch();
  cancelMidMode();

  const res = await fetch('/api/symbol?path=' + encodeURIComponent(relPath));
  if (!res.ok) { setStatus('Error loading ' + relPath); return; }
  const data = await res.json();

  state.symbolMeta = data.meta;

  if (!_svgCache.has(relPath)) {
    if (_svgCache.size >= 200) _svgCache.delete(_svgCache.keys().next().value);
    _svgCache.set(relPath, data.svg);
  }

  state.ports = JSON.parse(JSON.stringify(data.meta.snap_points || []));
  state.ports.forEach(p => {
    p.locked = !!p.locked;
    if (!p.type) {
      p.type = KNOWN_TYPES.has(p.id) ? p.id : 'reference';
    }
    if (p.zone) {
      delete p.x;
      delete p.y;
    } else if (p.x === undefined) {
      p.x = 0;
      p.y = 0;
    }
  });

  const vbMatch = data.svg.match(/viewBox=["']([^"']+)["']/);
  if (vbMatch) {
    const parts = vbMatch[1].trim().split(/[\s,]+/).map(Number);
    state.vw = parts[2] || 80;
    state.vh = parts[3] || 80;
  } else {
    state.vw = 80; state.vh = 80;
  }

  state.portR   = Math.max(2, Math.min(state.vw, state.vh) * 0.04);
  state.labelSz = state.portR * 1.1;

  const wrapW = wrap.clientWidth  || 600;
  const wrapH = wrap.clientHeight || 500;
  const scale = Math.min(wrapW / state.vw, wrapH / state.vh) * 0.96;
  state.initSvgW = Math.round(state.vw * scale);
  state.initSvgH = Math.round(state.vh * scale);

  svg.setAttribute('viewBox', `0 0 ${state.vw} ${state.vh}`);
  svg.setAttribute('width',   state.initSvgW);
  svg.setAttribute('height',  state.initSvgH);

  wrap.scrollLeft = 0;
  wrap.scrollTop  = 0;

  updateGridPattern();

  symImg.setAttribute('href',   'data:image/svg+xml,' + encodeURIComponent(data.svg));
  symImg.setAttribute('width',  state.vw);
  symImg.setAttribute('height', state.vh);

  const displayName = state.symbolMeta.display_name || state.symbolMeta.id || relPath.split('/').pop();
  document.getElementById('sym-info').textContent = displayName + '\n' + relPath;
  _showPreview(data.svg, displayName);

  setStatus('Loaded: ' + relPath + '  (' + state.ports.length + ' port' +
            (state.ports.length === 1 ? '' : 's') + ')');
  renderPorts();
  renderPortList();
  clearFields();
  renderSymbolList(state.visibleSymbols);
  scrollSymListToActive();

  document.getElementById('btn-next').disabled = false;

  const btnComplete = document.getElementById('btn-complete');
  btnComplete.disabled = false;
  const isComplete = !!state.symbolMeta.completed;
  btnComplete.classList.toggle('is-complete', isComplete);
  btnComplete.textContent = isComplete ? '✓ Completed' : '✓ Mark Complete';
}

// ── Next symbol (saves first) ────────────────────────────────────────────────
export async function nextSymbol() {
  if (!state.currentPath) return;
  const saved = await saveJSON(/*silent=*/true);
  if (!saved) return;

  const idx = state.visibleSymbols.findIndex(s => s.path === state.currentPath);
  if (idx < 0 || idx >= state.visibleSymbols.length - 1) {
    setStatus('No more symbols in the current list.');
    return;
  }
  await loadSymbol(state.visibleSymbols[idx + 1].path);
}
