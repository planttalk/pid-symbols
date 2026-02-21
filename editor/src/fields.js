'use strict';

import { state } from './state.js';
import { setActiveType } from './ui.js';
import { renderPorts, renderPortList } from './render.js';

// ── Field editor ─────────────────────────────────────────────────────────────

export function populateFields(idx) {
  const p        = state.ports[idx];
  const isZone   = !!p.zone;
  const pointDiv = document.getElementById('point-fields');
  const zoneDiv  = document.getElementById('zone-fields');
  const toZoneBtn = document.getElementById('btn-to-zone');

  document.getElementById('f-id').value = p.id;
  setActiveType(p.type, false);

  if (isZone) {
    pointDiv.style.display = 'none';
    zoneDiv.style.display  = '';
    if (toZoneBtn) toZoneBtn.textContent = 'Convert to Point';
    document.getElementById('f-zone-x').value = p.zone.x;
    document.getElementById('f-zone-y').value = p.zone.y;
    document.getElementById('f-zone-w').value = p.zone.width;
    document.getElementById('f-zone-h').value = p.zone.height;
    ['f-zone-x','f-zone-y','f-zone-w','f-zone-h'].forEach(id =>
      document.getElementById(id).disabled = p.locked
    );
  } else {
    pointDiv.style.display = '';
    zoneDiv.style.display  = 'none';
    if (toZoneBtn) toZoneBtn.textContent = 'Convert to Zone';
    document.getElementById('f-x').value    = p.x;
    document.getElementById('f-y').value    = p.y;
    document.getElementById('f-x').disabled = p.locked;
    document.getElementById('f-y').disabled = p.locked;
  }
}

export function clearFields() {
  ['f-id', 'f-x', 'f-y'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.value = ''; el.disabled = false; }
  });
  ['f-zone-x','f-zone-y','f-zone-w','f-zone-h'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.value = ''; el.disabled = false; }
  });
  const pointDiv  = document.getElementById('point-fields');
  const zoneDiv   = document.getElementById('zone-fields');
  const toZoneBtn = document.getElementById('btn-to-zone');
  if (pointDiv)  pointDiv.style.display = '';
  if (zoneDiv)   zoneDiv.style.display  = 'none';
  if (toZoneBtn) toZoneBtn.textContent  = 'Convert to Zone';
}

export function convertToZone() {
  if (state.selIdx === null) return;
  const p = state.ports[state.selIdx];
  if (p.zone) {
    const cx = +(p.zone.x + p.zone.width  / 2).toFixed(2);
    const cy = +(p.zone.y + p.zone.height / 2).toFixed(2);
    delete p.zone;
    p.x = cx;
    p.y = cy;
  } else {
    const zw = +(state.vw * 0.2).toFixed(2);
    const zh = +(state.vh * 0.2).toFixed(2);
    p.zone = {
      x:      +(p.x - zw / 2).toFixed(2),
      y:      +(p.y - zh / 2).toFixed(2),
      width:  zw,
      height: zh,
    };
    delete p.x;
    delete p.y;
  }
  renderPorts();
  renderPortList();
  populateFields(state.selIdx);
}

export function applyZoneFields() {
  if (state.selIdx === null || !state.ports[state.selIdx].zone || state.ports[state.selIdx].locked) return;
  const x = parseFloat(document.getElementById('f-zone-x').value);
  const y = parseFloat(document.getElementById('f-zone-y').value);
  const w = parseFloat(document.getElementById('f-zone-w').value);
  const h = parseFloat(document.getElementById('f-zone-h').value);
  if (!isNaN(x)) state.ports[state.selIdx].zone.x      = +x.toFixed(2);
  if (!isNaN(y)) state.ports[state.selIdx].zone.y      = +y.toFixed(2);
  if (!isNaN(w) && w > 0) state.ports[state.selIdx].zone.width  = +w.toFixed(2);
  if (!isNaN(h) && h > 0) state.ports[state.selIdx].zone.height = +h.toFixed(2);
  renderPorts();
  renderPortList();
}

export function applyId() {
  if (state.selIdx === null) return;
  const v = document.getElementById('f-id').value.trim();
  if (!v) return;
  state.ports[state.selIdx].id = v;
  renderPorts();
  renderPortList();
}

export function applyXY() {
  if (state.selIdx === null || state.ports[state.selIdx].locked) return;
  const x = parseFloat(document.getElementById('f-x').value);
  const y = parseFloat(document.getElementById('f-y').value);
  if (!isNaN(x)) state.ports[state.selIdx].x = +x.toFixed(2);
  if (!isNaN(y)) state.ports[state.selIdx].y = +y.toFixed(2);
  renderPorts();
  renderPortList();
  if (state.midState && state.midState.step === 3) {
    import('./midpoint.js').then(({ refreshMidPreview }) => refreshMidPreview());
  }
}
