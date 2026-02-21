'use strict';

import { NS, portColor } from './constants.js';
import { state } from './state.js';
import { midLayer } from './dom.js';
import { setStatus, updateActionButtons } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { addPort } from './ports.js';
import { cancelMatch } from './match.js';

// ── Midpoint state machine ───────────────────────────────────────────────────

export function startMidpointMode() {
  if (!state.currentPath) return;
  if (state.midState) { cancelMidMode(); return; }
  cancelMatch();
  state.selection = new Set();
  state.selIdx    = null;
  state.midState  = { step: 1 };
  document.getElementById('btn-mid').classList.add('armed');
  setStatus('Midpoint: click first reference port  (Escape to cancel)');
  renderPorts();
  renderPortList();
  updateActionButtons();
}

export function handleMidPortClick(idx) {
  if (!state.midState) return;

  if (state.midState.step === 1) {
    state.midState = { step: 2, a: idx };
    setStatus(`Midpoint: "${state.ports[idx].id}" selected — click second reference port`);
    renderPorts();

  } else if (state.midState.step === 2) {
    if (idx === state.midState.a) return;
    const a  = state.midState.a;
    const px = +((state.ports[a].x + state.ports[idx].x) / 2).toFixed(2);
    const py = +((state.ports[a].y + state.ports[idx].y) / 2).toFixed(2);
    state.midState = { step: 3, a, b: idx, px, py };
    showMidPreview(px, py, a, idx);
    setStatus(`Midpoint preview at (${px}, ${py}) — click to place  |  Escape to cancel`);
    renderPorts();

  } else if (state.midState.step === 3) {
    confirmMidpoint();
  }
}

export function confirmMidpoint() {
  if (!state.midState || state.midState.step !== 3) return;
  const { px, py } = state.midState;
  state.midState = null;
  hideMidPreview();
  document.getElementById('btn-mid').classList.remove('armed');
  updateActionButtons();
  addPort(px, py);
}

export function cancelMidMode() {
  if (!state.midState) return;
  state.midState = null;
  hideMidPreview();
  document.getElementById('btn-mid').classList.remove('armed');
  renderPorts();
  renderPortList();
  updateActionButtons();
  setStatus('Midpoint cancelled.');
}

// ── Midpoint preview overlay ─────────────────────────────────────────────────

export function showMidPreview(px, py, ai, bi) {
  midLayer.innerHTML = '';

  const pa   = state.ports[ai];
  const pb   = state.ports[bi];
  const sw   = state.portR * 0.2;
  const dash = `${state.portR * 0.9} ${state.portR * 0.45}`;

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

  const c = document.createElementNS(NS, 'circle');
  c.setAttribute('cx',             px);
  c.setAttribute('cy',             py);
  c.setAttribute('r',              state.portR);
  c.setAttribute('fill',           portColor(state.activeType));
  c.setAttribute('fill-opacity',   '0.45');
  c.setAttribute('stroke',         '#FFD700');
  c.setAttribute('stroke-width',   sw);
  c.setAttribute('stroke-dasharray', dash);
  midLayer.appendChild(c);

  const markerStyle = document.querySelector('input[name=marker]:checked')?.value ?? 'crosshair';
  if (markerStyle === 'crosshair') {
    const chSw = state.portR * 0.12;
    for (const attrs of [
      { x1: px - state.portR, y1: py,               x2: px + state.portR, y2: py               },
      { x1: px,               y1: py - state.portR, x2: px,               y2: py + state.portR },
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
    dot.setAttribute('r',    state.portR * 0.22);
    dot.setAttribute('fill', '#FFD700');
    midLayer.appendChild(dot);
  }

  const t = document.createElementNS(NS, 'text');
  t.setAttribute('x',           px + state.portR + state.labelSz * 0.3);
  t.setAttribute('y',           py + state.labelSz * 0.4);
  t.setAttribute('font-size',   state.labelSz);
  t.setAttribute('fill',        '#FFD700');
  t.setAttribute('font-family', 'monospace');
  t.setAttribute('stroke',      'white');
  t.setAttribute('stroke-width', state.labelSz * 0.12);
  t.setAttribute('paint-order', 'stroke');
  t.textContent = `${state.activeType} (${px}, ${py})`;
  midLayer.appendChild(t);

  midLayer.removeAttribute('display');
}

export function hideMidPreview() {
  midLayer.innerHTML = '';
  midLayer.setAttribute('display', 'none');
}

export function refreshMidPreview() {
  if (!state.midState || state.midState.step !== 3) return;
  const { a, b } = state.midState;
  const px = +((state.ports[a].x + state.ports[b].x) / 2).toFixed(2);
  const py = +((state.ports[a].y + state.ports[b].y) / 2).toFixed(2);
  state.midState.px = px;
  state.midState.py = py;
  showMidPreview(px, py, a, b);
}
