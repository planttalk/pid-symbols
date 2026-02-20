'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// Port type definitions (id → label + color)
// ─────────────────────────────────────────────────────────────────────────────
const PORT_TYPES = [
  { id: 'in',      label: 'In',      color: '#2196F3' },
  { id: 'out',     label: 'Out',     color: '#F44336' },
  { id: 'in_out',  label: 'In/Out',  color: '#009688' },
  { id: 'signal',  label: 'Signal',  color: '#9C27B0' },
  { id: 'process', label: 'Process', color: '#FF9800' },
  { id: 'north',   label: 'North',   color: '#4CAF50' },
  { id: 'south',   label: 'South',   color: '#4CAF50' },
  { id: 'east',    label: 'East',    color: '#4CAF50' },
  { id: 'west',    label: 'West',    color: '#4CAF50' },
  { id: 'custom',  label: 'Custom',  color: '#607D8B' },
];

const TYPE_COLOR = Object.fromEntries(PORT_TYPES.map(t => [t.id, t.color]));

function portColor(id) {
  return TYPE_COLOR[(id || '').toLowerCase()] ?? '#607D8B';
}

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let allSymbols  = [];       // [{path, name, standard, category}]
let currentPath = null;     // currently loaded symbol path (no extension)
let symbolMeta  = null;     // parsed JSON metadata object
let ports       = [];       // [{id, x, y}] — working copy

let selection   = new Set(); // indices of selected ports
let selIdx      = null;      // primary selected port (drives field editor)

let drag        = null;      // {idx} — set while dragging a port
let panState    = null;      // {clientX, clientY, vbX, vbY} — set while panning

let matchMode   = null;      // null | 'Y' | 'X' — armed match axis
let activeType  = 'in';     // port type applied to newly created ports

let vw = 80, vh = 80;       // current symbol viewBox width/height
let portR   = 3;             // port circle radius in viewBox units
let labelSz = 3.3;           // port label font-size in viewBox units

// ─────────────────────────────────────────────────────────────────────────────
// Element shortcuts
// ─────────────────────────────────────────────────────────────────────────────
const svg       = document.getElementById('editor-svg');
const portLayer = document.getElementById('port-layer');
const symImg    = document.getElementById('sym-img');
const guideH    = document.getElementById('guide-h');
const guideV    = document.getElementById('guide-v');
const gridPat   = document.getElementById('grid-pat');
const gridBg    = document.getElementById('grid-bg');
const NS        = 'http://www.w3.org/2000/svg';

// ─────────────────────────────────────────────────────────────────────────────
// Port type grid
// ─────────────────────────────────────────────────────────────────────────────
function buildTypeGrid() {
  const el = document.getElementById('type-grid');
  for (const t of PORT_TYPES) {
    const btn = document.createElement('button');
    btn.className      = 'type-btn' + (t.id === activeType ? ' active' : '');
    btn.dataset.typeId = t.id;
    btn.innerHTML =
      `<span class="type-dot" style="background:${t.color}"></span>${t.label}`;
    btn.addEventListener('click', () => setActiveType(t.id));
    el.appendChild(btn);
  }
}

function setActiveType(id) {
  activeType = id;
  document.querySelectorAll('.type-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.typeId === id)
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Grid helpers
// ─────────────────────────────────────────────────────────────────────────────
function gridSz() {
  return parseFloat(document.getElementById('grid-size').value) || 10;
}

function snap(v) {
  if (!document.getElementById('snap-grid').checked) return v;
  const g = gridSz();
  return Math.round(v / g) * g;
}

function toggleGrid() {
  const on = document.getElementById('show-grid').checked;
  gridBg.setAttribute('display', on ? '' : 'none');
}

function updateGridPattern() {
  const g = gridSz();
  gridPat.setAttribute('width',  g);
  gridPat.setAttribute('height', g);
  gridPat.innerHTML =
    `<path d="M ${g} 0 L 0 0 0 ${g}" fill="none" stroke="#bbb"` +
    ` stroke-width="${(g * 0.035).toFixed(2)}"/>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// SVG coordinate transform
// Uses viewBox.baseVal so zoom and pan are automatically accounted for.
// ─────────────────────────────────────────────────────────────────────────────
function toSvgCoords(clientX, clientY) {
  const rect = svg.getBoundingClientRect();
  const vb   = svg.viewBox.baseVal;
  return {
    x: vb.x + (clientX - rect.left) * vb.width  / rect.width,
    y: vb.y + (clientY - rect.top)  * vb.height / rect.height,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Zoom (scroll wheel — zoom around the cursor position)
// ─────────────────────────────────────────────────────────────────────────────
svg.addEventListener('wheel', e => {
  if (!currentPath) return;
  e.preventDefault();
  const pt     = toSvgCoords(e.clientX, e.clientY);
  const factor = e.deltaY > 0 ? 1.12 : 1 / 1.12;
  const vb     = svg.viewBox.baseVal;
  const nx     = pt.x - (pt.x - vb.x) * factor;
  const ny     = pt.y - (pt.y - vb.y) * factor;
  svg.setAttribute('viewBox', `${nx} ${ny} ${vb.width * factor} ${vb.height * factor}`);
}, { passive: false });

// ─────────────────────────────────────────────────────────────────────────────
// Middle-drag pan
// ─────────────────────────────────────────────────────────────────────────────
svg.addEventListener('mousedown', e => {
  if (e.button !== 1) return;
  e.preventDefault();
  const vb = svg.viewBox.baseVal;
  panState = { clientX: e.clientX, clientY: e.clientY, vbX: vb.x, vbY: vb.y };
  svg.style.cursor = 'move';
});

// Suppress context menu that some browsers show on middle-click release
svg.addEventListener('contextmenu', e => {
  if (panState !== null) e.preventDefault();
});

// ─────────────────────────────────────────────────────────────────────────────
// Symbol list
// ─────────────────────────────────────────────────────────────────────────────
async function loadSymbolList() {
  try {
    const res  = await fetch('/api/symbols');
    allSymbols = await res.json();
  } catch {
    allSymbols = [];
    setStatus('Failed to load symbol list.');
  }
  renderSymbolList(allSymbols);
}

function filterSymbols() {
  const q = document.getElementById('sym-search').value.toLowerCase();
  renderSymbolList(
    allSymbols.filter(s =>
      s.name.toLowerCase().includes(q) || s.path.toLowerCase().includes(q))
  );
}

function renderSymbolList(list) {
  const el = document.getElementById('sym-list');
  el.innerHTML = '';
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
    d.className   = 'sym-item' + (s.path === currentPath ? ' active' : '');
    d.textContent = s.name;
    d.title       = s.path;
    d.addEventListener('click', () => loadSymbol(s.path));
    el.appendChild(d);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Symbol loading
// ─────────────────────────────────────────────────────────────────────────────
async function loadSymbol(relPath) {
  if (drag || panState) return;  // don't interrupt an interaction
  currentPath = relPath;
  selection   = new Set();
  selIdx      = null;
  cancelMatch();

  const res = await fetch('/api/symbol?path=' + encodeURIComponent(relPath));
  if (!res.ok) { setStatus('Error loading ' + relPath); return; }
  const data = await res.json();

  symbolMeta = data.meta;
  ports      = JSON.parse(JSON.stringify(data.meta.snap_points || []));

  // Parse viewBox (take width/height from parts[2] and parts[3])
  const vbMatch = data.svg.match(/viewBox=["']([^"']+)["']/);
  if (vbMatch) {
    const parts = vbMatch[1].trim().split(/[\s,]+/).map(Number);
    vw = parts[2] || 80;
    vh = parts[3] || 80;
  } else {
    vw = 80; vh = 80;
  }

  portR   = Math.max(2, Math.min(vw, vh) * 0.04);
  labelSz = portR * 1.1;

  // Reset SVG element size (fit within 480×480, preserve aspect ratio)
  const MAX   = 480;
  const scale = Math.min(MAX / vw, MAX / vh);
  svg.setAttribute('viewBox', `0 0 ${vw} ${vh}`);
  svg.setAttribute('width',   Math.round(vw * scale));
  svg.setAttribute('height',  Math.round(vh * scale));

  updateGridPattern();

  // Embed symbol as data-URI so its internal IDs don't collide with ours
  symImg.setAttribute('href',   'data:image/svg+xml,' + encodeURIComponent(data.svg));
  symImg.setAttribute('width',  vw);
  symImg.setAttribute('height', vh);

  document.getElementById('sym-info').textContent =
    (symbolMeta.display_name || symbolMeta.id || relPath) + '\n' + relPath;

  setStatus('Loaded: ' + relPath + '  (' + ports.length + ' port' +
            (ports.length === 1 ? '' : 's') + ')');
  renderPorts();
  renderPortList();
  clearFields();
  renderSymbolList(allSymbols);  // refresh active highlight
}

// ─────────────────────────────────────────────────────────────────────────────
// Port rendering (SVG canvas)
// ─────────────────────────────────────────────────────────────────────────────
function renderPorts() {
  portLayer.innerHTML = '';

  ports.forEach((p, i) => {
    const col   = portColor(p.id);
    const isSel = selection.has(i);

    if (isSel) {
      const halo = document.createElementNS(NS, 'circle');
      halo.setAttribute('cx',           p.x);
      halo.setAttribute('cy',           p.y);
      halo.setAttribute('r',            portR * 1.7);
      halo.setAttribute('fill',         'none');
      halo.setAttribute('stroke',       i === selIdx ? '#FFD700' : '#8888FF');
      halo.setAttribute('stroke-width', portR * 0.2);
      portLayer.appendChild(halo);
    }

    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx',           p.x);
    c.setAttribute('cy',           p.y);
    c.setAttribute('r',            portR);
    c.setAttribute('fill',         col);
    c.setAttribute('stroke',       'white');
    c.setAttribute('stroke-width', portR * 0.15);
    c.style.cursor = 'grab';
    c.addEventListener('mousedown',   ev => onPortDown(ev, i));
    c.addEventListener('contextmenu', ev => { ev.preventDefault(); ctxDelete(i); });

    const title = document.createElementNS(NS, 'title');
    title.textContent = `${p.id}  (${p.x.toFixed(2)}, ${p.y.toFixed(2)})`;
    c.appendChild(title);
    portLayer.appendChild(c);

    const label = p.id === 'in_out' ? 'in/out' : p.id;
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x',              p.x + portR + labelSz * 0.25);
    t.setAttribute('y',              p.y + labelSz * 0.38);
    t.setAttribute('font-size',      labelSz);
    t.setAttribute('fill',           col);
    t.setAttribute('font-family',    'monospace');
    t.setAttribute('pointer-events', 'none');
    t.setAttribute('stroke',         'white');
    t.setAttribute('stroke-width',   labelSz * 0.12);
    t.setAttribute('paint-order',    'stroke');
    t.textContent = label;
    portLayer.appendChild(t);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Port list (right panel)
// ─────────────────────────────────────────────────────────────────────────────
function renderPortList() {
  const el = document.getElementById('port-list');
  el.innerHTML = '';
  ports.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'port-row' + (selection.has(i) ? ' sel' : '');
    const label = p.id === 'in_out' ? 'in/out' : p.id;
    row.innerHTML =
      `<span class="port-dot" style="background:${portColor(p.id)}"></span>` +
      `<span class="port-name">${label}</span>` +
      `<span class="port-xy">${p.x.toFixed(1)}, ${p.y.toFixed(1)}</span>`;
    row.addEventListener('click', ev => onPortRowClick(ev, i));
    el.appendChild(row);
  });
  updateActionButtons();
}

function onPortRowClick(ev, i) {
  // Match mode: clicking a row sets the target
  if (matchMode && selIdx !== null && i !== selIdx) {
    applyMatch(i);
    return;
  }
  // Multi-select with Ctrl/Cmd
  if (ev.ctrlKey || ev.metaKey) {
    selection.has(i) ? selection.delete(i) : selection.add(i);
    selIdx = i;
  } else {
    selection = new Set([i]);
    selIdx    = i;
  }
  renderPorts();
  renderPortList();
  if (selection.size === 1) populateFields(selIdx); else clearFields();
}

// ─────────────────────────────────────────────────────────────────────────────
// Action buttons state
// ─────────────────────────────────────────────────────────────────────────────
function updateActionButtons() {
  const n = selection.size;
  document.getElementById('btn-del').disabled     = n === 0;
  document.getElementById('btn-mid').disabled     = n !== 2;
  document.getElementById('btn-match-y').disabled = n !== 1;
  document.getElementById('btn-match-x').disabled = n !== 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// Selection helpers
// ─────────────────────────────────────────────────────────────────────────────
function selectPort(idx, additive = false) {
  if (additive) {
    selection.has(idx) ? selection.delete(idx) : selection.add(idx);
    selIdx = idx;
  } else {
    selection = new Set([idx]);
    selIdx    = idx;
  }
  renderPorts();
  renderPortList();
  if (selection.size === 1) populateFields(idx); else clearFields();
}

function ctxDelete(idx) {
  // Right-click: make it the only selection, then delete
  selection = new Set([idx]);
  selIdx    = idx;
  deleteSelected();
}

// ─────────────────────────────────────────────────────────────────────────────
// Field editor sync
// ─────────────────────────────────────────────────────────────────────────────
function populateFields(idx) {
  const p = ports[idx];
  document.getElementById('f-id').value = p.id;
  document.getElementById('f-x').value  = p.x;
  document.getElementById('f-y').value  = p.y;
  // Sync active type button when loading a port with a known type
  if (TYPE_COLOR[p.id]) setActiveType(p.id);
}

function clearFields() {
  ['f-id', 'f-x', 'f-y'].forEach(id => { document.getElementById(id).value = ''; });
}

function applyId() {
  if (selIdx === null) return;
  const v = document.getElementById('f-id').value.trim();
  if (!v) return;
  ports[selIdx].id = v;
  renderPorts();
  renderPortList();
}

function applyXY() {
  if (selIdx === null) return;
  const x = parseFloat(document.getElementById('f-x').value);
  const y = parseFloat(document.getElementById('f-y').value);
  if (!isNaN(x)) ports[selIdx].x = +x.toFixed(2);
  if (!isNaN(y)) ports[selIdx].y = +y.toFixed(2);
  renderPorts();
  renderPortList();
}

// ─────────────────────────────────────────────────────────────────────────────
// Drag (left-button only; Ctrl+click adds to selection instead)
// ─────────────────────────────────────────────────────────────────────────────
function onPortDown(e, idx) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();

  // In match mode, clicking a canvas port applies the match
  if (matchMode && selIdx !== null && idx !== selIdx) {
    applyMatch(idx);
    return;
  }

  // Ctrl+click toggles selection without starting a drag
  if (e.ctrlKey || e.metaKey) {
    selectPort(idx, true);
    return;
  }

  selectPort(idx);
  drag = { idx };
}

document.addEventListener('mousemove', e => {
  // ── port drag ────────────────────────────────────────────────────────
  if (drag) {
    const pt   = toSvgCoords(e.clientX, e.clientY);
    const lock = document.querySelector('input[name=axis]:checked').value;
    const p    = ports[drag.idx];

    let nx = lock === 'LOCK_X' ? p.x : +snap(pt.x).toFixed(2);
    let ny = lock === 'LOCK_Y' ? p.y : +snap(pt.y).toFixed(2);

    p.x = nx;
    p.y = ny;

    renderPorts();
    renderPortList();
    populateFields(drag.idx);
    updateGuides(nx, ny, lock);
    setStatus(`"${p.id}"  x=${nx}  y=${ny}`);
  }

  // ── middle-drag pan ──────────────────────────────────────────────────
  if (panState) {
    const vb   = svg.viewBox.baseVal;
    const rect = svg.getBoundingClientRect();
    const dx   = (e.clientX - panState.clientX) * vb.width  / rect.width;
    const dy   = (e.clientY - panState.clientY) * vb.height / rect.height;
    svg.setAttribute('viewBox',
      `${panState.vbX - dx} ${panState.vbY - dy} ${vb.width} ${vb.height}`);
  }
});

document.addEventListener('mouseup', e => {
  if (drag     && e.button === 0) { drag     = null; hideGuides(); }
  if (panState && e.button === 1) { panState = null; svg.style.cursor = 'crosshair'; }
});

// ─────────────────────────────────────────────────────────────────────────────
// Axis guide lines
// ─────────────────────────────────────────────────────────────────────────────
function updateGuides(nx, ny, lock) {
  if (lock === 'LOCK_Y') {
    // Port is constrained to a fixed Y — show horizontal guide at that Y
    guideH.setAttribute('y1', ny);
    guideH.setAttribute('y2', ny);
    guideH.removeAttribute('display');
    guideV.setAttribute('display', 'none');
  } else if (lock === 'LOCK_X') {
    // Port is constrained to a fixed X — show vertical guide at that X
    guideV.setAttribute('x1', nx);
    guideV.setAttribute('x2', nx);
    guideV.removeAttribute('display');
    guideH.setAttribute('display', 'none');
  } else {
    hideGuides();
  }
}

function hideGuides() {
  guideH.setAttribute('display', 'none');
  guideV.setAttribute('display', 'none');
}

// ─────────────────────────────────────────────────────────────────────────────
// Double-click canvas → add port at that SVG position
// ─────────────────────────────────────────────────────────────────────────────
svg.addEventListener('dblclick', e => {
  if (!currentPath) return;
  if (e.target.tagName.toLowerCase() === 'circle') return; // ignore port hits
  const pt = toSvgCoords(e.clientX, e.clientY);
  addPort(+snap(pt.x).toFixed(2), +snap(pt.y).toFixed(2));
});

// ─────────────────────────────────────────────────────────────────────────────
// Add / Delete / Midpoint
// ─────────────────────────────────────────────────────────────────────────────
function addPort(x, y, id = null) {
  ports.push({ id: id ?? activeType, x, y });
  const idx = ports.length - 1;
  selection = new Set([idx]);
  selIdx    = idx;
  renderPorts();
  renderPortList();
  populateFields(idx);
  setStatus(`Added "${ports[idx].id}" at (${x}, ${y})`);
}

function addPortCenter() {
  if (!currentPath) return;
  addPort(+(vw / 2).toFixed(2), +(vh / 2).toFixed(2));
}

function deleteSelected() {
  if (selection.size === 0) return;
  // Remove in reverse index order so earlier indices stay valid
  const sorted = [...selection].sort((a, b) => b - a);
  for (const idx of sorted) ports.splice(idx, 1);

  selection = new Set();
  selIdx    = ports.length > 0 ? Math.min(selIdx ?? 0, ports.length - 1) : null;
  if (selIdx !== null) selection.add(selIdx);

  renderPorts();
  renderPortList();
  if (selIdx !== null) populateFields(selIdx); else clearFields();
}

function placeMidpoint() {
  if (selection.size !== 2) return;
  const [a, b] = [...selection];
  const x = +((ports[a].x + ports[b].x) / 2).toFixed(2);
  const y = +((ports[a].y + ports[b].y) / 2).toFixed(2);
  addPort(x, y);
  setStatus(`Midpoint placed at (${x}, ${y})`);
}

// ─────────────────────────────────────────────────────────────────────────────
// Match Y / Match X
// ─────────────────────────────────────────────────────────────────────────────
function toggleMatch(axis) {
  if (selIdx === null) return;
  if (matchMode === axis) { cancelMatch(); return; }
  matchMode = axis;
  document.getElementById('btn-match-y').classList.toggle('armed', axis === 'Y');
  document.getElementById('btn-match-x').classList.toggle('armed', axis === 'X');
  setStatus(`Match ${axis}: click another port to copy its ${axis} coordinate…`);
}

function applyMatch(targetIdx) {
  if (selIdx === null || matchMode === null) return;
  if (matchMode === 'Y') ports[selIdx].y = ports[targetIdx].y;
  else                   ports[selIdx].x = ports[targetIdx].x;
  cancelMatch();
  renderPorts();
  renderPortList();
  populateFields(selIdx);
}

function cancelMatch() {
  matchMode = null;
  document.getElementById('btn-match-y').classList.remove('armed');
  document.getElementById('btn-match-x').classList.remove('armed');
}

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard shortcuts
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  const tag = document.activeElement.tagName.toLowerCase();
  const inInput = (tag === 'input' || tag === 'textarea');

  if (e.key === 'Escape') {
    cancelMatch();
    return;
  }

  if (inInput) return;  // don't intercept typing in fields

  if (e.key === 'Delete' && selection.size > 0 && !matchMode) {
    deleteSelected();
    return;
  }

  // Arrow-key nudge for the primary selected port
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)
      && selIdx !== null) {
    e.preventDefault();
    const step = document.getElementById('snap-grid').checked ? gridSz() : 1;
    const p    = ports[selIdx];
    if (e.key === 'ArrowLeft')  p.x = +(p.x - step).toFixed(2);
    if (e.key === 'ArrowRight') p.x = +(p.x + step).toFixed(2);
    if (e.key === 'ArrowUp')    p.y = +(p.y - step).toFixed(2);
    if (e.key === 'ArrowDown')  p.y = +(p.y + step).toFixed(2);
    renderPorts();
    renderPortList();
    populateFields(selIdx);
    setStatus(`"${ports[selIdx].id}"  x=${p.x}  y=${p.y}`);
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Save JSON
// ─────────────────────────────────────────────────────────────────────────────
async function saveJSON() {
  if (!currentPath || !symbolMeta) return;
  symbolMeta.snap_points = ports.map(p => ({
    id: p.id,
    x:  +p.x.toFixed(2),
    y:  +p.y.toFixed(2),
  }));
  try {
    const res = await fetch('/api/save', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: currentPath, meta: symbolMeta }),
    });
    showMsg(res.ok ? { ok: '✓ Saved' } : { err: '✗ ' + await res.text() });
  } catch (err) {
    showMsg({ err: '✗ ' + err.message });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Generate _debug.svg
// ─────────────────────────────────────────────────────────────────────────────
async function generateDebug() {
  if (!currentPath) return;
  try {
    const res = await fetch('/api/debug', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        path:  currentPath,
        ports: ports.map(p => ({ id: p.id, x: +p.x.toFixed(2), y: +p.y.toFixed(2) })),
      }),
    });
    showMsg(res.ok
      ? { ok: '✓ _debug.svg written' }
      : { err: '✗ ' + await res.text() });
  } catch (err) {
    showMsg({ err: '✗ ' + err.message });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI helpers
// ─────────────────────────────────────────────────────────────────────────────
function setStatus(msg) {
  document.getElementById('status-bar').textContent = msg;
}

let _msgTimer = null;
function showMsg(obj) {
  const el = document.getElementById('save-msg');
  el.className   = obj.ok ? 'ok' : 'err';
  el.textContent = obj.ok ?? obj.err;
  clearTimeout(_msgTimer);
  _msgTimer = setTimeout(() => { el.textContent = ''; }, 3500);
}

// ─────────────────────────────────────────────────────────────────────────────
// Wire up DOM event listeners (no inline handlers in HTML)
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById('sym-search').addEventListener('input',  filterSymbols);
document.getElementById('show-grid').addEventListener('change',  toggleGrid);
document.getElementById('grid-size').addEventListener('change',  updateGridPattern);

document.getElementById('btn-add').addEventListener('click',     addPortCenter);
document.getElementById('btn-mid').addEventListener('click',     placeMidpoint);
document.getElementById('btn-del').addEventListener('click',     deleteSelected);
document.getElementById('btn-match-y').addEventListener('click', () => toggleMatch('Y'));
document.getElementById('btn-match-x').addEventListener('click', () => toggleMatch('X'));

document.getElementById('f-id').addEventListener('input', applyId);
document.getElementById('f-x').addEventListener('input',  applyXY);
document.getElementById('f-y').addEventListener('input',  applyXY);

document.getElementById('btn-save').addEventListener('click',  saveJSON);
document.getElementById('btn-debug').addEventListener('click', generateDebug);

// ─────────────────────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────────────────────
buildTypeGrid();
loadSymbolList();
