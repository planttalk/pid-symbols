'use strict';

import { state } from './state.js';
import { svg, wrap, gridPat, gridBg } from './dom.js';

// ── SVG coordinate transform ─────────────────────────────────────────────────
// viewBox is always "0 0 vw vh" — only the SVG element's pixel size changes on
// zoom, so getBoundingClientRect() correctly reflects any zoom level.
export function toSvgCoords(clientX, clientY) {
  const rect = svg.getBoundingClientRect();
  const vb   = svg.viewBox.baseVal;
  return {
    x: vb.x + (clientX - rect.left) * vb.width  / rect.width,
    y: vb.y + (clientY - rect.top)  * vb.height / rect.height,
  };
}

// ── Grid helpers ─────────────────────────────────────────────────────────────
export function gridSz() {
  return parseFloat(document.getElementById('grid-size').value) || 10;
}

export function snap(v) {
  if (!document.getElementById('snap-grid').checked) return v;
  const g = gridSz();
  return Math.round(v / g) * g;
}

export function toggleGrid() {
  gridBg.setAttribute('display', document.getElementById('show-grid').checked ? '' : 'none');
}

export function updateGridPattern() {
  const g = gridSz();
  gridPat.setAttribute('width',  g);
  gridPat.setAttribute('height', g);
  gridPat.innerHTML =
    `<path d="M ${g} 0 L 0 0 0 ${g}" fill="none" stroke="#bbb"` +
    ` stroke-width="${(g * 0.035).toFixed(2)}"/>`;
}

// ── Zoom ─────────────────────────────────────────────────────────────────────
// Grows/shrinks the SVG element; canvas-wrap provides scrollbars.
// The viewBox is never changed; only width/height attributes are updated.
// Zoom is anchored to the cursor position.
svg.addEventListener('wheel', e => {
  if (!state.currentPath) return;
  e.preventDefault();

  const factor = e.deltaY > 0 ? 1.0 / 1.15 : 1.15;
  const oldW   = parseFloat(svg.getAttribute('width'));
  const oldH   = parseFloat(svg.getAttribute('height'));

  const maxW = Math.min(Math.max(state.vw, state.vh) * 20, 3000);
  const newW = Math.max(state.initSvgW, Math.min(maxW, oldW * factor));
  const newH = newW * (state.vh / state.vw);

  if (Math.abs(newW - oldW) < 0.5) return;

  const svgRect = svg.getBoundingClientRect();
  const fx = (e.clientX - svgRect.left) / svgRect.width;
  const fy = (e.clientY - svgRect.top)  / svgRect.height;

  svg.setAttribute('width',  Math.round(newW));
  svg.setAttribute('height', Math.round(newH));

  const wrapRect = wrap.getBoundingClientRect();
  wrap.scrollLeft = fx * newW - (e.clientX - wrapRect.left);
  wrap.scrollTop  = fy * newH - (e.clientY - wrapRect.top);
}, { passive: false });
