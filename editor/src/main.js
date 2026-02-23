'use strict';

// Entry point: wire up all event listeners and boot the editor.
// All heavy logic lives in the imported modules.

import { svg } from './dom.js';
import { toggleGrid, updateGridPattern } from './canvas.js';
import { buildTypeGrid } from './ui.js';
import { renderPorts, renderPortList } from './render.js';
import { populateFields, clearFields, applyId, applyXY, applyZoneFields, convertToZone } from './fields.js';
import { addPortCenter, deleteSelected } from './ports.js';
import { snap } from './canvas.js';
import { addPort } from './ports.js';
import { startMidpointMode, confirmMidpoint, cancelMidMode, refreshMidPreview } from './midpoint.js';
import { toggleMatch, cancelMatch } from './match.js';
import { loadSymbolList, filterSymbols, nextSymbol } from './symbols.js';
import { saveJSON, toggleComplete, exportCompleted, generateDebug } from './api.js';
import { initAugment, previewAugment } from './augment.js';
import { state } from './state.js';
import { setStatus } from './ui.js';
import { toSvgCoords } from './canvas.js';

// ── Canvas: double-click to add port ────────────────────────────────────────
svg.addEventListener('dblclick', e => {
  if (!state.currentPath) return;
  if (state.midState) return;
  if (e.target.tagName.toLowerCase() === 'circle') return;
  const pt = toSvgCoords(e.clientX, e.clientY);
  addPort(+snap(pt.x).toFixed(2), +snap(pt.y).toFixed(2));
});

// ── Canvas: single click → confirm midpoint (step 3 only) ────────────────────
svg.addEventListener('click', e => {
  if (!state.midState || state.midState.step !== 3) return;
  if (e.detail > 1) return;
  if (e.target.tagName.toLowerCase() === 'circle') return;
  confirmMidpoint();
});

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  const inInput = ['input', 'textarea'].includes(
    document.activeElement.tagName.toLowerCase()
  );

  if (e.key === 'Escape') {
    if (state.midState)  { cancelMidMode(); return; }
    if (state.matchMode) { cancelMatch();   return; }
    return;
  }

  if (e.key === 'Enter' && state.midState && state.midState.step === 3) {
    e.preventDefault();
    confirmMidpoint();
    return;
  }

  if (inInput) return;

  if (e.key === 'Delete' && state.selection.size > 0 && !state.midState && !state.matchMode) {
    deleteSelected();
    return;
  }

  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)
      && state.selIdx !== null && !state.midState && !state.ports[state.selIdx].locked) {
    e.preventDefault();
    const step = document.getElementById('snap-grid').checked
      ? (parseFloat(document.getElementById('grid-size').value) || 10)
      : 1;
    const p = state.ports[state.selIdx];
    if (e.key === 'ArrowLeft')  p.x = +(p.x - step).toFixed(2);
    if (e.key === 'ArrowRight') p.x = +(p.x + step).toFixed(2);
    if (e.key === 'ArrowUp')    p.y = +(p.y - step).toFixed(2);
    if (e.key === 'ArrowDown')  p.y = +(p.y + step).toFixed(2);
    renderPorts();
    renderPortList();
    populateFields(state.selIdx);
    setStatus(`"${p.id}"  x=${p.x}  y=${p.y}`);
  }
});

// ── Static event listeners ───────────────────────────────────────────────────
document.getElementById('sym-search').addEventListener('input',    filterSymbols);
document.getElementById('filter-source').addEventListener('change',   filterSymbols);
document.getElementById('filter-standard').addEventListener('change',  filterSymbols);
document.getElementById('show-grid').addEventListener('change',  toggleGrid);
document.querySelectorAll('input[name=marker]').forEach(r =>
  r.addEventListener('change', () => {
    renderPorts();
    if (state.midState?.step === 3) refreshMidPreview();
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
document.getElementById('f-zone-x').addEventListener('input', applyZoneFields);
document.getElementById('f-zone-y').addEventListener('input', applyZoneFields);
document.getElementById('f-zone-w').addEventListener('input', applyZoneFields);
document.getElementById('f-zone-h').addEventListener('input', applyZoneFields);
document.getElementById('btn-to-zone').addEventListener('click', convertToZone);

document.getElementById('btn-save').addEventListener('click',     () => saveJSON());
document.getElementById('btn-next').addEventListener('click',     nextSymbol);
document.getElementById('btn-complete').addEventListener('click', toggleComplete);
document.getElementById('btn-debug').addEventListener('click',    generateDebug);
document.getElementById('btn-export').addEventListener('click',   exportCompleted);

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b =>
      b.classList.toggle('active', b === btn)
    );
    document.getElementById('tab-ports').style.display  = tab === 'ports'   ? '' : 'none';
    document.getElementById('tab-augment').style.display = tab === 'augment' ? '' : 'none';
    if (tab === 'augment' && state.currentPath) previewAugment();
  });
});

// ── Boot ─────────────────────────────────────────────────────────────────────
buildTypeGrid();
initAugment();
loadSymbolList();
