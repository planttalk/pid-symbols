'use strict';

import { PORT_TYPES } from './constants.js';
import { state } from './state.js';

// ── Status bar ───────────────────────────────────────────────────────────────
export function setStatus(msg) {
  document.getElementById('status-bar').textContent = msg;
}

// ── Save / error message (auto-clears after 3.5 s) ──────────────────────────
let _msgTimer = null;
export function showMsg(obj) {
  const el = document.getElementById('save-msg');
  el.className   = obj.ok ? 'ok' : 'err';
  el.textContent = obj.ok ?? obj.err;
  clearTimeout(_msgTimer);
  _msgTimer = setTimeout(() => { el.textContent = ''; }, 3500);
}

// ── Port type selector grid ──────────────────────────────────────────────────
export function buildTypeGrid() {
  const el = document.getElementById('type-grid');
  for (const t of PORT_TYPES) {
    const btn = document.createElement('button');
    btn.className      = 'type-btn' + (t.id === state.activeType ? ' active' : '');
    btn.dataset.typeId = t.id;
    btn.innerHTML =
      `<span class="type-dot" style="background:${t.color}"></span>${t.label}`;
    btn.addEventListener('click', () => setActiveType(t.id));
    el.appendChild(btn);
  }
}

/**
 * Switch the active port type and optionally apply it to the selected port.
 * Pass updatePort=false when calling from populateFields() to sync the UI
 * without side effects.
 */
export function setActiveType(id, updatePort = true) {
  state.activeType = id;
  document.querySelectorAll('.type-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.typeId === id)
  );
  if (updatePort && state.selIdx !== null && state.selection.size === 1
      && !state.ports[state.selIdx].locked) {
    state.ports[state.selIdx].type = id;
    // renderPorts / renderPortList imported lazily to avoid circular deps at init
    import('./render.js').then(({ renderPorts, renderPortList }) => {
      renderPorts();
      renderPortList();
    });
  }
}

// ── Action button enable/disable ─────────────────────────────────────────────
export function updateActionButtons() {
  const n      = state.selection.size;
  const hasSym = state.currentPath !== null;
  document.getElementById('btn-del').disabled     = n === 0;
  document.getElementById('btn-mid').disabled     = !hasSym;
  document.getElementById('btn-match-y').disabled = n !== 1 || !!state.midState;
  document.getElementById('btn-match-x').disabled = n !== 1 || !!state.midState;
}
