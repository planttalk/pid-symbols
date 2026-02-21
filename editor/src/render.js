'use strict';

import { NS, portColor } from './constants.js';
import { state } from './state.js';
import { portLayer } from './dom.js';
import { updateActionButtons } from './ui.js';

// ── Port canvas rendering ────────────────────────────────────────────────────
export function renderPorts() {
  portLayer.innerHTML = '';
  const markerStyle =
    document.querySelector('input[name=marker]:checked')?.value ?? 'crosshair';

  state.ports.forEach((p, i) => {
    const col   = portColor(p.type);
    const isSel = state.selection.has(i);

    // ── Zone port rendering ────────────────────────────────────────────────
    if (p.zone) {
      const z  = p.zone;
      const zr = document.createElementNS(NS, 'rect');
      zr.setAttribute('x',            z.x);
      zr.setAttribute('y',            z.y);
      zr.setAttribute('width',        z.width);
      zr.setAttribute('height',       z.height);
      zr.setAttribute('fill',         col);
      zr.setAttribute('fill-opacity', isSel ? '0.25' : '0.12');
      zr.setAttribute('stroke',       col);
      zr.setAttribute('stroke-width', state.portR * 0.18);
      zr.setAttribute('stroke-dasharray', `${state.portR * 0.7} ${state.portR * 0.35}`);
      zr.style.cursor = p.locked ? 'not-allowed' : 'move';
      zr.addEventListener('mousedown',   ev => _onZoneDown(ev, i));
      zr.addEventListener('contextmenu', ev => { ev.preventDefault(); _ctxDelete(i); });
      portLayer.appendChild(zr);

      const zt = document.createElementNS(NS, 'text');
      zt.setAttribute('x',           z.x + z.width / 2);
      zt.setAttribute('y',           z.y + z.height / 2 + state.labelSz * 0.4);
      zt.setAttribute('font-size',   state.labelSz);
      zt.setAttribute('fill',        col);
      zt.setAttribute('font-family', 'monospace');
      zt.setAttribute('text-anchor', 'middle');
      zt.setAttribute('pointer-events', 'none');
      zt.setAttribute('stroke',      'white');
      zt.setAttribute('stroke-width', state.labelSz * 0.12);
      zt.setAttribute('paint-order', 'stroke');
      zt.textContent = p.id;
      portLayer.appendChild(zt);

      if (isSel && !p.locked) {
        const corners = [
          { corner: 'nw', cx: z.x,           cy: z.y            },
          { corner: 'ne', cx: z.x + z.width,  cy: z.y            },
          { corner: 'sw', cx: z.x,            cy: z.y + z.height },
          { corner: 'se', cx: z.x + z.width,  cy: z.y + z.height },
        ];
        for (const { corner, cx, cy } of corners) {
          const h  = document.createElementNS(NS, 'rect');
          const hs = state.portR * 0.9;
          h.setAttribute('x',      cx - hs / 2);
          h.setAttribute('y',      cy - hs / 2);
          h.setAttribute('width',  hs);
          h.setAttribute('height', hs);
          h.setAttribute('fill',   '#FFD700');
          h.setAttribute('stroke', 'white');
          h.setAttribute('stroke-width', state.portR * 0.1);
          h.style.cursor = corner + '-resize';
          h.addEventListener('mousedown', ev => { ev.stopPropagation(); _onZoneHandleDown(ev, i, corner); });
          portLayer.appendChild(h);
        }
      }
      return;
    }

    // ── Point port rendering ───────────────────────────────────────────────

    // Selection halo
    if (isSel) {
      const halo = document.createElementNS(NS, 'circle');
      halo.setAttribute('cx',           p.x);
      halo.setAttribute('cy',           p.y);
      halo.setAttribute('r',            state.portR * 1.7);
      halo.setAttribute('fill',         'none');
      halo.setAttribute('stroke',       i === state.selIdx ? '#FFD700' : '#8888FF');
      halo.setAttribute('stroke-width', state.portR * 0.2);
      portLayer.appendChild(halo);
    }

    // Midpoint reference ring
    const isMidRef =
      (state.midState && state.midState.step >= 2 && state.midState.a === i) ||
      (state.midState && state.midState.step === 3 && state.midState.b === i);
    if (isMidRef) {
      const ring = document.createElementNS(NS, 'circle');
      ring.setAttribute('cx',             p.x);
      ring.setAttribute('cy',             p.y);
      ring.setAttribute('r',              state.portR * 2.3);
      ring.setAttribute('fill',           'none');
      ring.setAttribute('stroke',         '#FFD700');
      ring.setAttribute('stroke-width',   state.portR * 0.18);
      ring.setAttribute('stroke-dasharray', `${state.portR * 0.9} ${state.portR * 0.45}`);
      portLayer.appendChild(ring);
    }

    // Port circle
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx',           p.x);
    c.setAttribute('cy',           p.y);
    c.setAttribute('r',            state.portR);
    c.setAttribute('fill',         col);
    c.setAttribute('fill-opacity', p.locked ? '0.38' : '0.55');
    c.setAttribute('stroke',       'white');
    c.setAttribute('stroke-width', state.portR * 0.15);
    if (p.locked) c.setAttribute('stroke-dasharray', `${state.portR * 0.55} ${state.portR * 0.28}`);
    c.style.cursor = p.locked ? 'not-allowed' : (state.midState ? 'crosshair' : 'grab');
    c.addEventListener('mousedown',   ev => _onPortDown(ev, i));
    c.addEventListener('contextmenu', ev => { ev.preventDefault(); _ctxDelete(i); });

    const title = document.createElementNS(NS, 'title');
    title.textContent = `${p.id} [${p.type}]  (${p.x.toFixed(2)}, ${p.y.toFixed(2)})`;
    c.appendChild(title);
    portLayer.appendChild(c);

    // Centre marker
    if (markerStyle === 'crosshair') {
      const chSw = state.portR * 0.12;
      for (const attrs of [
        { x1: p.x - state.portR, y1: p.y,             x2: p.x + state.portR, y2: p.y             },
        { x1: p.x,               y1: p.y - state.portR, x2: p.x,               y2: p.y + state.portR },
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
      dot.setAttribute('r',              state.portR * 0.22);
      dot.setAttribute('fill',           'white');
      dot.setAttribute('pointer-events', 'none');
      portLayer.appendChild(dot);
    }

    // Label
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x',              p.x + state.portR + state.labelSz * 0.25);
    t.setAttribute('y',              p.y + state.labelSz * 0.38);
    t.setAttribute('font-size',      state.labelSz);
    t.setAttribute('fill',           col);
    t.setAttribute('font-family',    'monospace');
    t.setAttribute('pointer-events', 'none');
    t.setAttribute('stroke',         'white');
    t.setAttribute('stroke-width',   state.labelSz * 0.12);
    t.setAttribute('paint-order',    'stroke');
    t.textContent = p.id;
    portLayer.appendChild(t);
  });
}

// ── Port list (right panel) ──────────────────────────────────────────────────
export function renderPortList() {
  const el = document.getElementById('port-list');
  el.innerHTML = '';
  state.ports.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'port-row' + (state.selection.has(i) ? ' sel' : '') + (p.locked ? ' locked' : '');
    const xyLabel = p.zone
      ? `${p.zone.x.toFixed(1)},${p.zone.y.toFixed(1)} ${p.zone.width.toFixed(1)}×${p.zone.height.toFixed(1)}`
      : `${p.x.toFixed(1)}, ${p.y.toFixed(1)}`;
    const badge = p.zone ? '<span class="zone-badge">zone</span>' : '';
    row.innerHTML =
      `<span class="port-dot" style="background:${portColor(p.type)}"></span>` +
      `<span class="port-name">${p.id}${badge}</span>` +
      `<span class="port-xy">${xyLabel}</span>`;

    const lockBtn = document.createElement('button');
    lockBtn.className   = 'port-lock-btn' + (p.locked ? ' is-locked' : '');
    lockBtn.title       = p.locked ? 'Unlock port' : 'Lock port';
    lockBtn.textContent = p.locked ? '🔒' : '🔓';
    lockBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      state.ports[i].locked = !state.ports[i].locked;
      renderPorts();
      renderPortList();
      if (state.selIdx === i) {
        import('./fields.js').then(({ populateFields }) => populateFields(i));
      }
    });
    row.appendChild(lockBtn);
    row.addEventListener('click', ev => _onPortRowClick(ev, i));
    el.appendChild(row);
  });
  updateActionButtons();
}

// ── Internal helpers (called from render.js event listeners) ─────────────────
// These delegate to the appropriate modules via dynamic import to avoid
// circular top-level imports while keeping render.js self-contained.

function _onPortDown(e, idx) {
  import('./drag.js').then(({ onPortDown }) => onPortDown(e, idx));
}

function _onZoneDown(ev, i) {
  import('./drag.js').then(({ onZoneDown }) => onZoneDown(ev, i));
}

function _onZoneHandleDown(ev, i, corner) {
  import('./drag.js').then(({ onZoneHandleDown }) => onZoneHandleDown(ev, i, corner));
}

function _ctxDelete(idx) {
  import('./ports.js').then(({ ctxDelete }) => ctxDelete(idx));
}

function _onPortRowClick(ev, i) {
  import('./ports.js').then(({ onPortRowClick }) => onPortRowClick(ev, i));
}
