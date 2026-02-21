'use strict';

import { state } from './state.js';
import { setStatus } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { populateFields, clearFields } from './fields.js';

// ── Port add / delete ────────────────────────────────────────────────────────
export function addPort(x, y, id = null, type = null) {
  const t = type ?? state.activeType;
  state.ports.push({ id: id ?? t, type: t, x, y, locked: false });
  const idx = state.ports.length - 1;
  state.selection = new Set([idx]);
  state.selIdx    = idx;
  renderPorts();
  renderPortList();
  populateFields(idx);
  setStatus(`Added "${state.ports[idx].id}" at (${x}, ${y})`);
}

export function addPortCenter() {
  if (!state.currentPath) return;
  addPort(+(state.vw / 2).toFixed(2), +(state.vh / 2).toFixed(2));
}

export function deleteSelected() {
  if (state.selection.size === 0) return;
  const sorted = [...state.selection].sort((a, b) => b - a);
  for (const idx of sorted) state.ports.splice(idx, 1);

  state.selection = new Set();
  state.selIdx    = state.ports.length > 0
    ? Math.min(state.selIdx ?? 0, state.ports.length - 1)
    : null;
  if (state.selIdx !== null) state.selection.add(state.selIdx);

  renderPorts();
  renderPortList();
  if (state.selIdx !== null) populateFields(state.selIdx); else clearFields();
}

// ── Selection ────────────────────────────────────────────────────────────────
export function selectPort(idx, additive = false) {
  if (additive) {
    state.selection.has(idx) ? state.selection.delete(idx) : state.selection.add(idx);
    state.selIdx = idx;
  } else {
    state.selection = new Set([idx]);
    state.selIdx    = idx;
  }
  renderPorts();
  renderPortList();
  if (state.selection.size === 1) populateFields(idx); else clearFields();
}

export function ctxDelete(idx) {
  state.selection = new Set([idx]);
  state.selIdx    = idx;
  deleteSelected();
}

// ── Port row click ───────────────────────────────────────────────────────────
export function onPortRowClick(ev, i) {
  if (state.midState) {
    import('./midpoint.js').then(({ handleMidPortClick }) => handleMidPortClick(i));
    return;
  }

  if (state.matchMode && state.selIdx !== null && i !== state.selIdx) {
    import('./match.js').then(({ applyMatch }) => applyMatch(i));
    return;
  }

  if (ev.ctrlKey || ev.metaKey) {
    state.selection.has(i) ? state.selection.delete(i) : state.selection.add(i);
    state.selIdx = i;
  } else {
    state.selection = new Set([i]);
    state.selIdx    = i;
  }
  renderPorts();
  renderPortList();
  if (state.selection.size === 1) populateFields(state.selIdx); else clearFields();
}
