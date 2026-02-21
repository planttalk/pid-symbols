'use strict';

import { state } from './state.js';
import { guideH, guideV } from './dom.js';
import { toSvgCoords, snap } from './canvas.js';
import { setStatus } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { populateFields } from './fields.js';
import { selectPort } from './ports.js';

// ── Axis guides ──────────────────────────────────────────────────────────────
export function updateGuides(nx, ny, lock) {
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

export function hideGuides() {
  guideH.setAttribute('display', 'none');
  guideV.setAttribute('display', 'none');
}

// ── Point port drag ──────────────────────────────────────────────────────────
export function onPortDown(e, idx) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();

  if (state.midState !== null) {
    import('./midpoint.js').then(({ handleMidPortClick }) => handleMidPortClick(idx));
    return;
  }
  if (state.matchMode && state.selIdx !== null && idx !== state.selIdx) {
    import('./match.js').then(({ applyMatch }) => applyMatch(idx));
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    selectPort(idx, true);
    return;
  }
  selectPort(idx);
  if (!state.ports[idx].locked) state.drag = { idx };
}

// ── Zone drag ────────────────────────────────────────────────────────────────
export function onZoneDown(ev, i) {
  if (ev.button !== 0) return;
  ev.preventDefault();
  ev.stopPropagation();
  if (state.midState !== null) {
    import('./midpoint.js').then(({ handleMidPortClick }) => handleMidPortClick(i));
    return;
  }
  selectPort(i);
  if (!state.ports[i].locked) {
    const pt = toSvgCoords(ev.clientX, ev.clientY);
    state.zoneDrag = { idx: i, mode: 'move', startPt: pt, startZone: { ...state.ports[i].zone } };
  }
}

export function onZoneHandleDown(ev, i, corner) {
  if (ev.button !== 0) return;
  ev.preventDefault();
  const pt = toSvgCoords(ev.clientX, ev.clientY);
  state.zoneDrag = { idx: i, mode: corner, startPt: pt, startZone: { ...state.ports[i].zone } };
}

// ── Global mouse move / up ───────────────────────────────────────────────────
document.addEventListener('mousemove', e => {
  if (state.zoneDrag) {
    const pt  = toSvgCoords(e.clientX, e.clientY);
    const dx  = pt.x - state.zoneDrag.startPt.x;
    const dy  = pt.y - state.zoneDrag.startPt.y;
    const sz  = state.zoneDrag.startZone;
    const p   = state.ports[state.zoneDrag.idx];
    const MIN = 2;

    if (state.zoneDrag.mode === 'move') {
      p.zone = { x: +(sz.x + dx).toFixed(2), y: +(sz.y + dy).toFixed(2), width: sz.width, height: sz.height };
    } else if (state.zoneDrag.mode === 'nw') {
      const newX = +(sz.x + dx).toFixed(2), newY = +(sz.y + dy).toFixed(2);
      const newW = +(sz.width - dx).toFixed(2), newH = +(sz.height - dy).toFixed(2);
      if (newW >= MIN && newH >= MIN) p.zone = { x: newX, y: newY, width: newW, height: newH };
    } else if (state.zoneDrag.mode === 'ne') {
      const newY = +(sz.y + dy).toFixed(2);
      const newW = +(sz.width + dx).toFixed(2), newH = +(sz.height - dy).toFixed(2);
      if (newW >= MIN && newH >= MIN) p.zone = { x: sz.x, y: newY, width: newW, height: newH };
    } else if (state.zoneDrag.mode === 'sw') {
      const newX = +(sz.x + dx).toFixed(2);
      const newW = +(sz.width - dx).toFixed(2), newH = +(sz.height + dy).toFixed(2);
      if (newW >= MIN && newH >= MIN) p.zone = { x: newX, y: sz.y, width: newW, height: newH };
    } else if (state.zoneDrag.mode === 'se') {
      const newW = +(sz.width + dx).toFixed(2), newH = +(sz.height + dy).toFixed(2);
      if (newW >= MIN && newH >= MIN) p.zone = { x: sz.x, y: sz.y, width: newW, height: newH };
    }
    renderPorts();
    renderPortList();
    populateFields(state.zoneDrag.idx);
    return;
  }

  if (!state.drag) return;
  const pt   = toSvgCoords(e.clientX, e.clientY);
  const lock = document.querySelector('input[name=axis]:checked').value;
  const p    = state.ports[state.drag.idx];

  const nx = lock === 'LOCK_X' ? p.x : +snap(pt.x).toFixed(2);
  const ny = lock === 'LOCK_Y' ? p.y : +snap(pt.y).toFixed(2);

  p.x = nx;
  p.y = ny;

  renderPorts();
  renderPortList();
  populateFields(state.drag.idx);
  updateGuides(nx, ny, lock);
  setStatus(`"${p.id}"  x=${nx}  y=${ny}`);
});

document.addEventListener('mouseup', e => {
  if (e.button === 0) {
    if (state.drag)     { state.drag = null;     hideGuides(); }
    if (state.zoneDrag) { state.zoneDrag = null; }
  }
});
