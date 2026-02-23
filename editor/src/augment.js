'use strict';

// Augmentation viewer — effect panel, live preview and batch generation.

import { state } from './state.js';

// ── Effect catalogue ─────────────────────────────────────────────────────────

const EFFECT_GROUPS = [
  {
    label: 'Physical',
    effects: [
      { name: 'yellowing',      label: 'Yellowing' },
      { name: 'foxing',         label: 'Foxing' },
      { name: 'crease',         label: 'Crease' },
      { name: 'water_stain',    label: 'Water Stain' },
      { name: 'edge_wear',      label: 'Edge Wear' },
      { name: 'fingerprint',    label: 'Fingerprint' },
      { name: 'binding_shadow', label: 'Binding Shadow' },
      { name: 'bleed_through',  label: 'Bleed Through' },
      { name: 'hole_punch',     label: 'Hole Punch' },
      { name: 'tape_residue',   label: 'Tape Residue' },
    ],
  },
  {
    label: 'Chemical',
    effects: [
      { name: 'ink_fading',    label: 'Ink Fading' },
      { name: 'ink_bleed',     label: 'Ink Bleed' },
      { name: 'coffee_stain',  label: 'Coffee Stain' },
      { name: 'oil_stain',     label: 'Oil Stain' },
      { name: 'acid_spots',    label: 'Acid Spots' },
      { name: 'bleaching',     label: 'Bleaching' },
      { name: 'toner_flaking', label: 'Toner Flaking' },
    ],
  },
  {
    label: 'Biological',
    effects: [
      { name: 'mold',          label: 'Mold' },
      { name: 'mildew',        label: 'Mildew' },
      { name: 'bio_foxing',    label: 'Bio Foxing' },
      { name: 'insect_damage', label: 'Insect Damage' },
    ],
  },
  {
    label: 'Scanning',
    effects: [
      { name: 'noise',             label: 'Noise' },
      { name: 'salt_pepper',       label: 'Salt & Pepper' },
      { name: 'vignette',          label: 'Vignette' },
      { name: 'jpeg_artifacts',    label: 'JPEG Artifacts' },
      { name: 'skew',              label: 'Skew' },
      { name: 'barrel_distortion', label: 'Barrel Distortion' },
      { name: 'moire',             label: 'Moiré' },
      { name: 'halftone',          label: 'Halftone' },
      { name: 'color_cast',        label: 'Color Cast' },
      { name: 'blur',              label: 'Blur' },
      { name: 'dust',              label: 'Dust' },
      { name: 'overexpose',        label: 'Overexpose' },
      { name: 'underexpose',       label: 'Underexpose' },
      { name: 'motion_streak',     label: 'Motion Streak' },
      { name: 'binarization',      label: 'Binarization' },
      { name: 'pixelation',        label: 'Pixelation' },
    ],
  },
];

// ── Build panel ──────────────────────────────────────────────────────────────

export function buildAugmentPanel() {
  const container = document.getElementById('augment-effects');
  if (!container) return;
  container.innerHTML = '';

  for (const group of EFFECT_GROUPS) {
    const details = document.createElement('details');
    details.className = 'aug-group';

    const summary = document.createElement('summary');
    summary.className = 'aug-group-label';
    summary.textContent = group.label;
    details.appendChild(summary);

    for (const eff of group.effects) {
      const row = document.createElement('div');
      row.className = 'aug-effect-row';
      row.innerHTML =
        `<label class="aug-effect-label">` +
        `<input type="checkbox" class="aug-cb" data-effect="${eff.name}"> ${eff.label}` +
        `</label>` +
        `<input type="range" class="aug-slider" data-effect="${eff.name}"` +
        ` min="0" max="100" value="50" disabled>` +
        `<span class="aug-value" data-effect="${eff.name}">—</span>`;

      const cb     = row.querySelector('.aug-cb');
      const slider = row.querySelector('.aug-slider');
      const valEl  = row.querySelector('.aug-value');

      cb.addEventListener('change', () => {
        slider.disabled = !cb.checked;
        valEl.textContent = cb.checked ? (slider.value / 100).toFixed(2) : '—';
        _schedulePreview();
      });
      slider.addEventListener('input', () => {
        valEl.textContent = (slider.value / 100).toFixed(2);
        _schedulePreview();
      });

      details.appendChild(row);
    }
    container.appendChild(details);
  }
}

// ── Collect current effects dict ─────────────────────────────────────────────

function collectEffects() {
  const effects = {};
  document.querySelectorAll('.aug-cb:checked').forEach(cb => {
    const name   = cb.dataset.effect;
    const slider = document.querySelector(`.aug-slider[data-effect="${name}"]`);
    effects[name] = slider ? slider.value / 100 : 0.5;
  });
  return effects;
}

// ── Debounced auto-preview ───────────────────────────────────────────────────

let _previewTimer = null;

function _schedulePreview() {
  if (_previewTimer) clearTimeout(_previewTimer);
  _previewTimer = setTimeout(previewAugment, 700);
}

// ── Preview ──────────────────────────────────────────────────────────────────

export async function previewAugment() {
  if (!state.currentPath) return;

  const imgEl  = document.getElementById('augment-preview-img');
  const hintEl = document.getElementById('augment-preview-hint');
  const sizeEl = document.getElementById('augment-size');
  const size   = parseInt(sizeEl?.value || '512', 10);
  const effects = collectEffects();

  if (imgEl) imgEl.style.opacity = '0.4';
  if (hintEl) hintEl.style.display = 'none';

  try {
    const res = await fetch('/api/augment-preview', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: state.currentPath, effects, size }),
    });
    if (!res.ok) {
      const txt = await res.text();
      if (hintEl) { hintEl.style.display = ''; hintEl.textContent = '\u2717 ' + txt; }
      if (imgEl)  { imgEl.style.display = 'none'; }
      return;
    }
    const data = await res.json();
    if (imgEl) {
      imgEl.src          = data.image;
      imgEl.style.display   = '';
      imgEl.style.opacity   = '1';
    }
  } catch (err) {
    if (hintEl) { hintEl.style.display = ''; hintEl.textContent = '\u2717 ' + err.message; }
    if (imgEl)  { imgEl.style.display = 'none'; }
  }
}

// ── Randomize ────────────────────────────────────────────────────────────────

export function randomizeEffects() {
  const allEffects = EFFECT_GROUPS.flatMap(g => g.effects);
  const n      = Math.floor(Math.random() * 4) + 3;   // 3–6 effects
  const picked = new Set(
    [...allEffects].sort(() => Math.random() - 0.5).slice(0, n).map(e => e.name)
  );

  document.querySelectorAll('.aug-cb').forEach(cb => {
    const name    = cb.dataset.effect;
    const isPicked = picked.has(name);
    cb.checked    = isPicked;
    const slider  = document.querySelector(`.aug-slider[data-effect="${name}"]`);
    const valEl   = document.querySelector(`.aug-value[data-effect="${name}"]`);
    if (slider) {
      const v = isPicked ? Math.floor(Math.random() * 70) + 20 : 50;
      slider.value    = v;
      slider.disabled = !isPicked;
      if (valEl) valEl.textContent = isPicked ? (v / 100).toFixed(2) : '—';
    }
  });
  _schedulePreview();
}

// ── Generate batch ───────────────────────────────────────────────────────────

export async function generateAugmented() {
  if (!state.currentPath) return;

  const btn     = document.getElementById('btn-augment-generate');
  const msgEl   = document.getElementById('augment-msg');
  const countEl = document.getElementById('augment-count');
  const dirEl   = document.getElementById('augment-output-dir');
  const sizeEl  = document.getElementById('augment-size');
  const effects = collectEffects();
  const count   = parseInt(countEl?.value || '5', 10);
  const outDir  = dirEl?.value.trim() || '';
  const size    = parseInt(sizeEl?.value || '512', 10);

  if (btn)   btn.disabled      = true;
  if (msgEl) { msgEl.className = ''; msgEl.textContent = 'Generating\u2026'; }

  try {
    const res  = await fetch('/api/augment-generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        path: state.currentPath, effects, count, output_dir: outDir, size,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      if (msgEl) {
        msgEl.className   = 'ok';
        msgEl.textContent = `\u2713 ${data.saved} image(s) saved to ${data.output_dir}`;
      }
    } else {
      if (msgEl) {
        msgEl.className   = 'err';
        msgEl.textContent = '\u2717 ' + (data.error || 'Unknown error');
      }
    }
  } catch (err) {
    if (msgEl) { msgEl.className = 'err'; msgEl.textContent = '\u2717 ' + err.message; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Boot ─────────────────────────────────────────────────────────────────────

export function initAugment() {
  buildAugmentPanel();
  document.getElementById('btn-augment-preview')?.addEventListener('click', previewAugment);
  document.getElementById('btn-augment-random')?.addEventListener('click',  randomizeEffects);
  document.getElementById('btn-augment-generate')?.addEventListener('click', generateAugmented);
  document.getElementById('augment-size')?.addEventListener('change', _schedulePreview);
}
