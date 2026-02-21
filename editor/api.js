'use strict';

import { state } from './state.js';
import { setStatus, showMsg } from './ui.js';
import { renderSymbolList, loadStats } from './symbols.js';

// ── Save JSON ────────────────────────────────────────────────────────────────
export async function saveJSON(silent = false) {
  if (!state.currentPath || !state.symbolMeta) return false;
  state.symbolMeta.snap_points = state.ports.map(p => {
    let sp;
    if (p.zone) {
      sp = {
        id:   p.id,
        type: p.type,
        zone: {
          x:      +p.zone.x.toFixed(2),
          y:      +p.zone.y.toFixed(2),
          width:  +p.zone.width.toFixed(2),
          height: +p.zone.height.toFixed(2),
        },
      };
    } else {
      sp = { id: p.id, type: p.type, x: +p.x.toFixed(2), y: +p.y.toFixed(2) };
    }
    if (p.locked) sp.locked = true;
    return sp;
  });
  try {
    const res = await fetch('/api/save', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: state.currentPath, meta: state.symbolMeta }),
    });
    if (!silent) showMsg(res.ok ? { ok: '✓ Saved' } : { err: '✗ ' + await res.text() });
    return res.ok;
  } catch (err) {
    if (!silent) showMsg({ err: '✗ ' + err.message });
    return false;
  }
}

// ── Toggle completion status ─────────────────────────────────────────────────
export async function toggleComplete() {
  if (!state.currentPath || !state.symbolMeta) return;
  const newState = !state.symbolMeta.completed;
  state.symbolMeta.completed = newState;

  const btn = document.getElementById('btn-complete');
  btn.classList.toggle('is-complete', newState);
  btn.textContent = newState ? '✓ Completed' : '✓ Mark Complete';

  const sym = state.allSymbols.find(s => s.path === state.currentPath);
  if (sym) sym.completed = newState;
  renderSymbolList(state.visibleSymbols.map(s =>
    s.path === state.currentPath ? { ...s, completed: newState } : s
  ));

  const saved = await saveJSON(/*silent=*/true);
  if (!saved) {
    state.symbolMeta.completed = !newState;
    btn.classList.toggle('is-complete', !newState);
    btn.textContent = !newState ? '✓ Completed' : '✓ Mark Complete';
    if (sym) sym.completed = !newState;
    renderSymbolList(state.visibleSymbols.map(s =>
      s.path === state.currentPath ? { ...s, completed: !newState } : s
    ));
    showMsg({ err: '✗ Save failed' });
  } else {
    showMsg({ ok: newState ? '✓ Marked complete' : '✓ Marked incomplete' });
    loadStats();
  }
}

// ── Export completed symbols ─────────────────────────────────────────────────
export async function exportCompleted() {
  const btn    = document.getElementById('btn-export');
  const msgEl  = document.getElementById('export-msg');
  const dirVal = document.getElementById('export-dir').value.trim();

  btn.disabled      = true;
  msgEl.className   = '';
  msgEl.textContent = 'Exporting…';

  try {
    const res  = await fetch('/api/export-completed', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ output_dir: dirVal }),
    });
    const data = await res.json();
    if (data.errors > 0) {
      msgEl.className   = 'err';
      msgEl.textContent = `✗ ${data.copied} copied, ${data.errors} error(s) → ${data.output_dir}`;
    } else {
      msgEl.className   = 'ok';
      msgEl.textContent = `✓ ${data.message}`;
    }
  } catch (err) {
    msgEl.className   = 'err';
    msgEl.textContent = '✗ ' + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Generate _debug.svg ──────────────────────────────────────────────────────
export async function generateDebug() {
  if (!state.currentPath) return;
  try {
    const res = await fetch('/api/debug', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        path:  state.currentPath,
        ports: state.ports.map(p => p.zone
          ? { id: p.id, type: p.type, zone: p.zone }
          : { id: p.id, type: p.type, x: +p.x.toFixed(2), y: +p.y.toFixed(2) }
        ),
      }),
    });
    showMsg(res.ok
      ? { ok: '✓ _debug.svg written' }
      : { err: '✗ ' + await res.text() });
  } catch (err) {
    showMsg({ err: '✗ ' + err.message });
  }
}
