'use strict';

import { state } from './state.js';
import { setStatus } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { populateFields } from './fields.js';

// ── Match Y / Match X ────────────────────────────────────────────────────────

export function toggleMatch(axis) {
  if (state.selIdx === null) return;
  if (state.matchMode === axis) { cancelMatch(); return; }
  state.matchMode = axis;
  document.getElementById('btn-match-y').classList.toggle('armed', axis === 'Y');
  document.getElementById('btn-match-x').classList.toggle('armed', axis === 'X');
  setStatus(`Match ${axis}: click another port to copy its ${axis} coordinate…`);
}

export function applyMatch(targetIdx) {
  if (state.selIdx === null || !state.matchMode || state.ports[state.selIdx].locked) return;
  if (state.matchMode === 'Y') state.ports[state.selIdx].y = state.ports[targetIdx].y;
  else                         state.ports[state.selIdx].x = state.ports[targetIdx].x;
  cancelMatch();
  renderPorts();
  renderPortList();
  populateFields(state.selIdx);
}

export function cancelMatch() {
  state.matchMode = null;
  document.getElementById('btn-match-y').classList.remove('armed');
  document.getElementById('btn-match-x').classList.remove('armed');
}
