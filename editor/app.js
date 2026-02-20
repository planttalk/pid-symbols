'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// Port type definitions
// ─────────────────────────────────────────────────────────────────────────────
const PORT_TYPES = [
  { id: 'in',        label: 'In',        color: '#2196F3' },
  { id: 'out',       label: 'Out',       color: '#F44336' },
  { id: 'in_out',    label: 'In/Out',    color: '#009688' },
  { id: 'signal',    label: 'Signal',    color: '#9C27B0' },
  { id: 'process',   label: 'Process',   color: '#FF9800' },
  { id: 'north',     label: 'North',     color: '#4CAF50' },
  { id: 'south',     label: 'South',     color: '#4CAF50' },
  { id: 'east',      label: 'East',      color: '#4CAF50' },
  { id: 'west',      label: 'West',      color: '#4CAF50' },
  { id: 'reference', label: 'Ref.',      color: '#9E9E9E' },  // spatial only — no connection
  { id: 'custom',    label: 'Custom',    color: '#607D8B' },
];

// Set of all known type ids (used for migration of old single-field snap_points)
const KNOWN_TYPES = new Set(PORT_TYPES.map(t => t.id));

const TYPE_COLOR = Object.fromEntries(PORT_TYPES.map(t => [t.id, t.color]));

function portColor(id) {
  return TYPE_COLOR[(id || '').toLowerCase()] ?? '#607D8B';
}

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let allSymbols    = [];       // [{path, name, standard, category}] — full list
let visibleSymbols = [];      // currently shown (filtered) symbols
let currentPath   = null;
let symbolMeta    = null;
let ports         = [];       // [{id, x, y}]

let selection     = new Set();
let selIdx        = null;     // primary selected port (drives field editor)

let drag          = null;     // {idx} while dragging
let matchMode     = null;     // null | 'Y' | 'X'

// Midpoint state machine:
//   null                          → idle
//   { step: 1 }                   → waiting for first reference port
//   { step: 2, a }                → first ref picked, waiting for second
//   { step: 3, a, b, px, py }    → both refs picked, preview shown
let midState      = null;

let activeType    = 'in';     // type applied to newly created ports

let vw = 80, vh = 80;        // current symbol viewBox dimensions (never changes after load)
let portR   = 3;
let labelSz = 3.3;
let initSvgW = 480, initSvgH = 480;  // pixel size at fit-to-window (min zoom bound)

// ─────────────────────────────────────────────────────────────────────────────
// Element shortcuts
// ─────────────────────────────────────────────────────────────────────────────
const svg       = document.getElementById('editor-svg');
const wrap      = document.getElementById('canvas-wrap');
const portLayer = document.getElementById('port-layer');
const midLayer  = document.getElementById('mid-layer');
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

// updatePort: when true and exactly 1 port is selected, also change that port's type.
// Pass false when calling from populateFields() to just sync the UI without side effects.
function setActiveType(id, updatePort = true) {
  activeType = id;
  document.querySelectorAll('.type-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.typeId === id)
  );
  if (updatePort && selIdx !== null && selection.size === 1 && !ports[selIdx].locked) {
    ports[selIdx].type = id;
    renderPorts();
    renderPortList();
  }
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
  gridBg.setAttribute('display', document.getElementById('show-grid').checked ? '' : 'none');
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
// viewBox is always "0 0 vw vh" — only the SVG element's pixel size changes on
// zoom, so getBoundingClientRect() correctly reflects any zoom level.
// ─────────────────────────────────────────────────────────────────────────────
function toSvgCoords(clientX, clientY) {
  const rect = svg.getBoundingClientRect();
  const vb   = svg.viewBox.baseVal;   // always 0 0 vw vh
  return {
    x: vb.x + (clientX - rect.left) * vb.width  / rect.width,
    y: vb.y + (clientY - rect.top)  * vb.height / rect.height,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Zoom — grows/shrinks the SVG element; canvas-wrap provides scrollbars.
// The viewBox is never changed; only width/height attributes are updated.
// Zoom is anchored to the cursor position.
// ─────────────────────────────────────────────────────────────────────────────
svg.addEventListener('wheel', e => {
  if (!currentPath) return;
  e.preventDefault();

  const factor   = e.deltaY > 0 ? 1.0 / 1.15 : 1.15;
  const oldW     = parseFloat(svg.getAttribute('width'));
  const oldH     = parseFloat(svg.getAttribute('height'));

  // Clamp: cannot zoom out past initial fit-to-window, max 3000 px in any dim
  const maxW = Math.min(Math.max(vw, vh) * 20, 3000);
  const newW = Math.max(initSvgW, Math.min(maxW, oldW * factor));
  const newH = newW * (vh / vw);  // maintain aspect ratio

  if (Math.abs(newW - oldW) < 0.5) return;  // at limit, nothing to do

  // Cursor as fraction [0..1] of current SVG pixel size
  const svgRect = svg.getBoundingClientRect();
  const fx = (e.clientX - svgRect.left) / svgRect.width;
  const fy = (e.clientY - svgRect.top)  / svgRect.height;

  svg.setAttribute('width',  Math.round(newW));
  svg.setAttribute('height', Math.round(newH));

  // Adjust scroll so the point under the cursor stays fixed on screen
  const wrapRect = wrap.getBoundingClientRect();
  wrap.scrollLeft = fx * newW - (e.clientX - wrapRect.left);
  wrap.scrollTop  = fy * newH - (e.clientY - wrapRect.top);
}, { passive: false });

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
  visibleSymbols = list;
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
    d.className = 'sym-item' +
      (s.path === currentPath ? ' active' : '') +
      (s.completed ? ' completed' : '');
    if (s.completed) {
      const check = document.createElement('span');
      check.className   = 'sym-check';
      check.textContent = '✓';
      d.appendChild(check);
    }
    const nameSpan = document.createTextNode(s.name);
    d.appendChild(nameSpan);
    d.title = s.path;
    d.addEventListener('click', () => loadSymbol(s.path));
    el.appendChild(d);
  }
}

function scrollSymListToActive() {
  const active = document.querySelector('#sym-list .sym-item.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

// ─────────────────────────────────────────────────────────────────────────────
// Symbol loading
// ─────────────────────────────────────────────────────────────────────────────
async function loadSymbol(relPath) {
  if (drag) return;
  currentPath = relPath;
  selection   = new Set();
  selIdx      = null;
  cancelMatch();
  cancelMidMode();

  const res = await fetch('/api/symbol?path=' + encodeURIComponent(relPath));
  if (!res.ok) { setStatus('Error loading ' + relPath); return; }
  const data = await res.json();

  symbolMeta = data.meta;
  ports = JSON.parse(JSON.stringify(data.meta.snap_points || []));
  ports.forEach(p => {
    p.locked = !!p.locked;
    // Migrate old single-field format: {id:"in"} → {id:"in", type:"in"}
    // Descriptive names that aren't known types become "reference".
    if (!p.type) {
      p.type = KNOWN_TYPES.has(p.id) ? p.id : 'reference';
    }
  });

  // Parse viewBox dimensions
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

  // Size SVG to fit inside canvas-wrap, preserving aspect ratio
  const wrapW = wrap.clientWidth  || 600;
  const wrapH = wrap.clientHeight || 500;
  const scale = Math.min(wrapW / vw, wrapH / vh) * 0.96;
  initSvgW = Math.round(vw * scale);
  initSvgH = Math.round(vh * scale);

  svg.setAttribute('viewBox', `0 0 ${vw} ${vh}`);
  svg.setAttribute('width',   initSvgW);
  svg.setAttribute('height',  initSvgH);

  // Reset scroll to origin
  wrap.scrollLeft = 0;
  wrap.scrollTop  = 0;

  updateGridPattern();

  // Embed symbol as data-URI so its internal IDs don't collide
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
  renderSymbolList(visibleSymbols);  // refresh active highlight
  scrollSymListToActive();

  document.getElementById('btn-next').disabled = false;

  const btnComplete = document.getElementById('btn-complete');
  btnComplete.disabled = false;
  const isComplete = !!symbolMeta.completed;
  btnComplete.classList.toggle('is-complete', isComplete);
  btnComplete.textContent = isComplete ? '✓ Completed' : '✓ Mark Complete';
}

// ─────────────────────────────────────────────────────────────────────────────
// Next symbol (saves current JSON first)
// ─────────────────────────────────────────────────────────────────────────────
async function nextSymbol() {
  if (!currentPath) return;
  const saved = await saveJSON(/*silent=*/true);
  if (!saved) return;  // save failed, don't navigate

  const idx = visibleSymbols.findIndex(s => s.path === currentPath);
  if (idx < 0 || idx >= visibleSymbols.length - 1) {
    setStatus('No more symbols in the current list.');
    return;
  }
  await loadSymbol(visibleSymbols[idx + 1].path);
}

// ─────────────────────────────────────────────────────────────────────────────
// Port rendering (SVG canvas)
// ─────────────────────────────────────────────────────────────────────────────
function renderPorts() {
  portLayer.innerHTML = '';
  const markerStyle =
    document.querySelector('input[name=marker]:checked')?.value ?? 'crosshair';

  ports.forEach((p, i) => {
    const col   = portColor(p.type);
    const isSel = selection.has(i);

    // Selection halo
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

    // Midpoint reference ring (gold dashed) — step 2 highlights A, step 3 highlights A and B
    const isMidRef =
      (midState && midState.step >= 2 && midState.a === i) ||
      (midState && midState.step === 3 && midState.b === i);
    if (isMidRef) {
      const ring = document.createElementNS(NS, 'circle');
      ring.setAttribute('cx',             p.x);
      ring.setAttribute('cy',             p.y);
      ring.setAttribute('r',              portR * 2.3);
      ring.setAttribute('fill',           'none');
      ring.setAttribute('stroke',         '#FFD700');
      ring.setAttribute('stroke-width',   portR * 0.18);
      ring.setAttribute('stroke-dasharray', `${portR * 0.9} ${portR * 0.45}`);
      portLayer.appendChild(ring);
    }

    // Port circle
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx',           p.x);
    c.setAttribute('cy',           p.y);
    c.setAttribute('r',            portR);
    c.setAttribute('fill',         col);
    c.setAttribute('fill-opacity', p.locked ? '0.38' : '0.55');
    c.setAttribute('stroke',       'white');
    c.setAttribute('stroke-width', portR * 0.15);
    if (p.locked) c.setAttribute('stroke-dasharray', `${portR * 0.55} ${portR * 0.28}`);
    c.style.cursor = p.locked ? 'not-allowed' : (midState ? 'crosshair' : 'grab');
    c.addEventListener('mousedown',   ev => onPortDown(ev, i));
    c.addEventListener('contextmenu', ev => { ev.preventDefault(); ctxDelete(i); });

    const title = document.createElementNS(NS, 'title');
    title.textContent = `${p.id} [${p.type}]  (${p.x.toFixed(2)}, ${p.y.toFixed(2)})`;
    c.appendChild(title);
    portLayer.appendChild(c);

    // Centre marker — style controlled by the "Port Marker" radio group
    if (markerStyle === 'crosshair') {
      const chSw = portR * 0.12;
      for (const attrs of [
        { x1: p.x - portR, y1: p.y,        x2: p.x + portR, y2: p.y        },
        { x1: p.x,         y1: p.y - portR, x2: p.x,         y2: p.y + portR },
      ]) {
        const ln = document.createElementNS(NS, 'line');
        ln.setAttribute('x1', attrs.x1); ln.setAttribute('y1', attrs.y1);
        ln.setAttribute('x2', attrs.x2); ln.setAttribute('y2', attrs.y2);
        ln.setAttribute('stroke',         'white');
        ln.setAttribute('stroke-width',   chSw);
        ln.setAttribute('pointer-events', 'none');
        portLayer.appendChild(ln);
      }
    } else if (markerStyle === 'dot') {
      const dot = document.createElementNS(NS, 'circle');
      dot.setAttribute('cx',             p.x);
      dot.setAttribute('cy',             p.y);
      dot.setAttribute('r',              portR * 0.22);
      dot.setAttribute('fill',           'white');
      dot.setAttribute('pointer-events', 'none');
      portLayer.appendChild(dot);
    }
    // markerStyle === 'none' → no centre indicator added

    // Label — shows the port name (id), not the type
    const label = p.id;
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
    row.className = 'port-row' + (selection.has(i) ? ' sel' : '') + (p.locked ? ' locked' : '');
    row.innerHTML =
      `<span class="port-dot" style="background:${portColor(p.type)}"></span>` +
      `<span class="port-name">${p.id}</span>` +
      `<span class="port-xy">${p.x.toFixed(1)}, ${p.y.toFixed(1)}</span>`;
    // Lock toggle — stopPropagation so it doesn't also trigger row selection
    const lockBtn = document.createElement('button');
    lockBtn.className = 'port-lock-btn' + (p.locked ? ' is-locked' : '');
    lockBtn.title     = p.locked ? 'Unlock port' : 'Lock port';
    lockBtn.textContent = p.locked ? '🔒' : '🔓';
    lockBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      ports[i].locked = !ports[i].locked;
      renderPorts();
      renderPortList();
      if (selIdx === i) populateFields(i);
    });
    row.appendChild(lockBtn);
    row.addEventListener('click', ev => onPortRowClick(ev, i));
    el.appendChild(row);
  });
  updateActionButtons();
}

function onPortRowClick(ev, i) {
  if (midState) { handleMidPortClick(i); return; }

  if (matchMode && selIdx !== null && i !== selIdx) {
    applyMatch(i);
    return;
  }

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
// Action button enable/disable
// ─────────────────────────────────────────────────────────────────────────────
function updateActionButtons() {
  const n      = selection.size;
  const hasSym = currentPath !== null;
  document.getElementById('btn-del').disabled     = n === 0;
  document.getElementById('btn-mid').disabled     = !hasSym;
  document.getElementById('btn-match-y').disabled = n !== 1 || !!midState;
  document.getElementById('btn-match-x').disabled = n !== 1 || !!midState;
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
  selection = new Set([idx]);
  selIdx    = idx;
  deleteSelected();
}

// ─────────────────────────────────────────────────────────────────────────────
// Field editor
// ─────────────────────────────────────────────────────────────────────────────
function populateFields(idx) {
  const p = ports[idx];
  document.getElementById('f-id').value    = p.id;
  document.getElementById('f-x').value     = p.x;
  document.getElementById('f-y').value     = p.y;
  // Disable position fields for locked ports (ID rename is still allowed)
  document.getElementById('f-x').disabled  = p.locked;
  document.getElementById('f-y').disabled  = p.locked;
  // Sync type grid to this port's type — don't trigger a port update (updatePort=false)
  setActiveType(p.type, false);
}

function clearFields() {
  ['f-id', 'f-x', 'f-y'].forEach(id => {
    const el = document.getElementById(id);
    el.value    = '';
    el.disabled = false;
  });
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
  if (selIdx === null || ports[selIdx].locked) return;
  const x = parseFloat(document.getElementById('f-x').value);
  const y = parseFloat(document.getElementById('f-y').value);
  if (!isNaN(x)) ports[selIdx].x = +x.toFixed(2);
  if (!isNaN(y)) ports[selIdx].y = +y.toFixed(2);
  renderPorts();
  renderPortList();
  // If in midState step 3, the preview references might be stale; refresh it
  if (midState && midState.step === 3) refreshMidPreview();
}

// ─────────────────────────────────────────────────────────────────────────────
// Drag (left-button, blocked in midpoint mode)
// ─────────────────────────────────────────────────────────────────────────────
function onPortDown(e, idx) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();

  // Midpoint pick: delegate to state machine
  if (midState !== null) {
    handleMidPortClick(idx);
    return;
  }

  // Match mode: apply match to clicked port
  if (matchMode && selIdx !== null && idx !== selIdx) {
    applyMatch(idx);
    return;
  }

  // Ctrl+click → multi-select (no drag)
  if (e.ctrlKey || e.metaKey) {
    selectPort(idx, true);
    return;
  }

  selectPort(idx);
  if (!ports[idx].locked) drag = { idx };  // locked ports: select only, no drag
}

document.addEventListener('mousemove', e => {
  if (!drag) return;
  const pt   = toSvgCoords(e.clientX, e.clientY);
  const lock = document.querySelector('input[name=axis]:checked').value;
  const p    = ports[drag.idx];

  const nx = lock === 'LOCK_X' ? p.x : +snap(pt.x).toFixed(2);
  const ny = lock === 'LOCK_Y' ? p.y : +snap(pt.y).toFixed(2);

  p.x = nx;
  p.y = ny;

  renderPorts();
  renderPortList();
  populateFields(drag.idx);
  updateGuides(nx, ny, lock);
  setStatus(`"${p.id}"  x=${nx}  y=${ny}`);
});

document.addEventListener('mouseup', e => {
  if (drag && e.button === 0) { drag = null; hideGuides(); }
});

// ─────────────────────────────────────────────────────────────────────────────
// Axis guide lines
// ─────────────────────────────────────────────────────────────────────────────
function updateGuides(nx, ny, lock) {
  if (lock === 'LOCK_Y') {
    guideH.setAttribute('y1', ny);
    guideH.setAttribute('y2', ny);
    guideH.removeAttribute('display');
    guideV.setAttribute('display', 'none');
  } else if (lock === 'LOCK_X') {
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
// Double-click canvas → add port
// ─────────────────────────────────────────────────────────────────────────────
svg.addEventListener('dblclick', e => {
  if (!currentPath) return;
  if (midState) return;   // don't accidentally add ports during midpoint mode
  if (e.target.tagName.toLowerCase() === 'circle') return;
  const pt = toSvgCoords(e.clientX, e.clientY);
  addPort(+snap(pt.x).toFixed(2), +snap(pt.y).toFixed(2));
});

// Single click on canvas → confirm midpoint placement (step 3 only)
svg.addEventListener('click', e => {
  if (!midState || midState.step !== 3) return;
  if (e.detail > 1) return;  // ignore clicks that are part of a dblclick
  // Port clicks are handled by onPortDown; this catches empty-canvas clicks
  if (e.target.tagName.toLowerCase() === 'circle') return;
  confirmMidpoint();
});

// ─────────────────────────────────────────────────────────────────────────────
// Add / Delete ports
// ─────────────────────────────────────────────────────────────────────────────
function addPort(x, y, id = null, type = null) {
  const t = type ?? activeType;
  ports.push({ id: id ?? t, type: t, x, y, locked: false });
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
  const sorted = [...selection].sort((a, b) => b - a);
  for (const idx of sorted) ports.splice(idx, 1);

  selection = new Set();
  selIdx    = ports.length > 0 ? Math.min(selIdx ?? 0, ports.length - 1) : null;
  if (selIdx !== null) selection.add(selIdx);

  renderPorts();
  renderPortList();
  if (selIdx !== null) populateFields(selIdx); else clearFields();
}

// ─────────────────────────────────────────────────────────────────────────────
// Midpoint state machine
// ─────────────────────────────────────────────────────────────────────────────

function startMidpointMode() {
  if (!currentPath) return;
  if (midState) { cancelMidMode(); return; }  // toggle off if already active
  cancelMatch();
  selection = new Set();
  selIdx    = null;
  midState  = { step: 1 };
  document.getElementById('btn-mid').classList.add('armed');
  setStatus('Midpoint: click first reference port  (Escape to cancel)');
  renderPorts();
  renderPortList();
  updateActionButtons();
}

function handleMidPortClick(idx) {
  if (!midState) return;

  if (midState.step === 1) {
    // First reference picked
    midState = { step: 2, a: idx };
    setStatus(`Midpoint: "${ports[idx].id}" selected — click second reference port`);
    renderPorts();

  } else if (midState.step === 2) {
    if (idx === midState.a) return;  // same port, ignore
    // Both references known — compute preview
    const a = midState.a;
    const px = +((ports[a].x + ports[idx].x) / 2).toFixed(2);
    const py = +((ports[a].y + ports[idx].y) / 2).toFixed(2);
    midState = { step: 3, a, b: idx, px, py };
    showMidPreview(px, py, a, idx);
    setStatus(`Midpoint preview at (${px}, ${py}) — click to place  |  Escape to cancel`);
    renderPorts();

  } else if (midState.step === 3) {
    // Clicking any port in step 3 confirms placement
    confirmMidpoint();
  }
}

function confirmMidpoint() {
  if (!midState || midState.step !== 3) return;
  const { px, py } = midState;
  midState = null;
  hideMidPreview();
  document.getElementById('btn-mid').classList.remove('armed');
  updateActionButtons();
  addPort(px, py);
}

function cancelMidMode() {
  if (!midState) return;
  midState = null;
  hideMidPreview();
  document.getElementById('btn-mid').classList.remove('armed');
  renderPorts();
  renderPortList();
  updateActionButtons();
  setStatus('Midpoint cancelled.');
}

// ── midpoint preview overlay ──────────────────────────────────────────────────

function showMidPreview(px, py, ai, bi) {
  midLayer.innerHTML = '';

  const pa   = ports[ai];
  const pb   = ports[bi];
  const sw   = portR * 0.2;
  const dash = `${portR * 0.9} ${portR * 0.45}`;

  // Dotted lines from each reference to the midpoint
  const makeLine = (x1, y1, x2, y2) => {
    const l = document.createElementNS(NS, 'line');
    l.setAttribute('x1', x1); l.setAttribute('y1', y1);
    l.setAttribute('x2', x2); l.setAttribute('y2', y2);
    l.setAttribute('stroke', '#FFD700');
    l.setAttribute('stroke-width', sw);
    l.setAttribute('stroke-dasharray', dash);
    return l;
  };
  midLayer.appendChild(makeLine(pa.x, pa.y, px, py));
  midLayer.appendChild(makeLine(pb.x, pb.y, px, py));

  // Ghost circle at midpoint
  const c = document.createElementNS(NS, 'circle');
  c.setAttribute('cx',             px);
  c.setAttribute('cy',             py);
  c.setAttribute('r',              portR);
  c.setAttribute('fill',           portColor(activeType));
  c.setAttribute('fill-opacity',   '0.45');
  c.setAttribute('stroke',         '#FFD700');
  c.setAttribute('stroke-width',   sw);
  c.setAttribute('stroke-dasharray', dash);
  midLayer.appendChild(c);

  // Centre marker on the ghost — follows the same marker style setting
  const markerStyle = document.querySelector('input[name=marker]:checked')?.value ?? 'crosshair';
  if (markerStyle === 'crosshair') {
    const chSw = portR * 0.12;
    for (const attrs of [
      { x1: px - portR, y1: py,         x2: px + portR, y2: py         },
      { x1: px,         y1: py - portR, x2: px,         y2: py + portR },
    ]) {
      const ln = document.createElementNS(NS, 'line');
      ln.setAttribute('x1', attrs.x1); ln.setAttribute('y1', attrs.y1);
      ln.setAttribute('x2', attrs.x2); ln.setAttribute('y2', attrs.y2);
      ln.setAttribute('stroke',           '#FFD700');
      ln.setAttribute('stroke-width',     chSw);
      ln.setAttribute('stroke-dasharray', dash);
      midLayer.appendChild(ln);
    }
  } else if (markerStyle === 'dot') {
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx',   px);
    dot.setAttribute('cy',   py);
    dot.setAttribute('r',    portR * 0.22);
    dot.setAttribute('fill', '#FFD700');
    midLayer.appendChild(dot);
  }

  // Coordinate label
  const t = document.createElementNS(NS, 'text');
  t.setAttribute('x',           px + portR + labelSz * 0.3);
  t.setAttribute('y',           py + labelSz * 0.4);
  t.setAttribute('font-size',   labelSz);
  t.setAttribute('fill',        '#FFD700');
  t.setAttribute('font-family', 'monospace');
  t.setAttribute('stroke',      'white');
  t.setAttribute('stroke-width', labelSz * 0.12);
  t.setAttribute('paint-order', 'stroke');
  t.textContent = `${activeType} (${px}, ${py})`;
  midLayer.appendChild(t);

  midLayer.removeAttribute('display');
}

function hideMidPreview() {
  midLayer.innerHTML = '';
  midLayer.setAttribute('display', 'none');
}

// Recompute preview when a reference port is moved via field editor
function refreshMidPreview() {
  if (!midState || midState.step !== 3) return;
  const { a, b } = midState;
  const px = +((ports[a].x + ports[b].x) / 2).toFixed(2);
  const py = +((ports[a].y + ports[b].y) / 2).toFixed(2);
  midState.px = px;
  midState.py = py;
  showMidPreview(px, py, a, b);
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
  if (selIdx === null || !matchMode || ports[selIdx].locked) return;
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
  const inInput = ['input', 'textarea'].includes(
    document.activeElement.tagName.toLowerCase()
  );

  if (e.key === 'Escape') {
    if (midState)   { cancelMidMode(); return; }
    if (matchMode)  { cancelMatch();   return; }
    return;
  }

  // Enter confirms midpoint when in step 3
  if (e.key === 'Enter' && midState && midState.step === 3) {
    e.preventDefault();
    confirmMidpoint();
    return;
  }

  if (inInput) return;

  if (e.key === 'Delete' && selection.size > 0 && !midState && !matchMode) {
    deleteSelected();
    return;
  }

  // Arrow-key nudge of primary selected port (skipped when locked)
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)
      && selIdx !== null && !midState && !ports[selIdx].locked) {
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
// Toggle completion status
// ─────────────────────────────────────────────────────────────────────────────
async function toggleComplete() {
  if (!currentPath || !symbolMeta) return;
  const newState = !symbolMeta.completed;
  symbolMeta.completed = newState;

  // Update button immediately
  const btn = document.getElementById('btn-complete');
  btn.classList.toggle('is-complete', newState);
  btn.textContent = newState ? '✓ Completed' : '✓ Mark Complete';

  // Update local cache so the list reflects the change without a reload
  const sym = allSymbols.find(s => s.path === currentPath);
  if (sym) sym.completed = newState;
  renderSymbolList(visibleSymbols.map(s =>
    s.path === currentPath ? { ...s, completed: newState } : s
  ));

  const saved = await saveJSON(/*silent=*/true);
  if (!saved) {
    // Revert on failure
    symbolMeta.completed = !newState;
    btn.classList.toggle('is-complete', !newState);
    btn.textContent = !newState ? '✓ Completed' : '✓ Mark Complete';
    if (sym) sym.completed = !newState;
    renderSymbolList(visibleSymbols.map(s =>
      s.path === currentPath ? { ...s, completed: !newState } : s
    ));
    showMsg({ err: '✗ Save failed' });
  } else {
    showMsg({ ok: newState ? '✓ Marked complete' : '✓ Marked incomplete' });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Save JSON  (returns true on success, false on failure)
// ─────────────────────────────────────────────────────────────────────────────
async function saveJSON(silent = false) {
  if (!currentPath || !symbolMeta) return false;
  symbolMeta.snap_points = ports.map(p => {
    const sp = { id: p.id, type: p.type, x: +p.x.toFixed(2), y: +p.y.toFixed(2) };
    if (p.locked) sp.locked = true;
    return sp;
  });
  try {
    const res = await fetch('/api/save', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: currentPath, meta: symbolMeta }),
    });
    if (!silent) showMsg(res.ok ? { ok: '✓ Saved' } : { err: '✗ ' + await res.text() });
    return res.ok;
  } catch (err) {
    if (!silent) showMsg({ err: '✗ ' + err.message });
    return false;
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
// Wire up event listeners
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById('sym-search').addEventListener('input',  filterSymbols);
document.getElementById('show-grid').addEventListener('change',  toggleGrid);
document.querySelectorAll('input[name=marker]').forEach(r =>
  r.addEventListener('change', () => {
    renderPorts();
    if (midState?.step === 3) refreshMidPreview();
  })
);
document.getElementById('grid-size').addEventListener('change',  updateGridPattern);

document.getElementById('btn-add').addEventListener('click',     addPortCenter);
document.getElementById('btn-mid').addEventListener('click',     startMidpointMode);
document.getElementById('btn-del').addEventListener('click',     deleteSelected);
document.getElementById('btn-match-y').addEventListener('click', () => toggleMatch('Y'));
document.getElementById('btn-match-x').addEventListener('click', () => toggleMatch('X'));

document.getElementById('f-id').addEventListener('input', applyId);
document.getElementById('f-x').addEventListener('input',  applyXY);
document.getElementById('f-y').addEventListener('input',  applyXY);

document.getElementById('btn-save').addEventListener('click',     () => saveJSON());
document.getElementById('btn-next').addEventListener('click',     nextSymbol);
document.getElementById('btn-complete').addEventListener('click', toggleComplete);
document.getElementById('btn-debug').addEventListener('click',    generateDebug);

// ─────────────────────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────────────────────
buildTypeGrid();
loadSymbolList();
