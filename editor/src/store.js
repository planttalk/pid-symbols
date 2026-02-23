import { create } from 'zustand';

export const useEditorStore = create((set, get) => ({
  // ── Symbol browser ────────────────────────────────────────────────────────
  allSymbols:    [],
  filterSource:  '',
  filterStandard:'',
  filterText:    '',

  // ── Loaded symbol ─────────────────────────────────────────────────────────
  currentPath:      null,
  symbolMeta:       null,
  symbolSvgDataUri: null,
  viewBox:          { x: 0, y: 0, w: 80, h: 80 },

  // ── Port editing ──────────────────────────────────────────────────────────
  ports:      [],
  selIdx:     null,
  selection:  new Set(),
  portType:   'in',
  markerMode: 'crosshair',
  axisLock:   'FREE',

  // ── Canvas ────────────────────────────────────────────────────────────────
  zoom:     6,
  showGrid: false,
  snapGrid: false,
  gridSize: 10,

  // ── Interaction modes ─────────────────────────────────────────────────────
  // midState: null | {step:1} | {step:2,first:{idx,x,y}} | {step:3,first,second,midX,midY}
  midState:  null,
  // matchMode: null | {axis:'Y'|'X', firstIdx:null|number}
  matchMode: null,

  // ── UI ────────────────────────────────────────────────────────────────────
  activeTab:  0,
  statusMsg:  'No symbol loaded — select one on the left.',
  saveMsg:    null,
  exportMsg:  null,

  // ── Augmentation ──────────────────────────────────────────────────────────
  augEffects:         {},    // {name: 0-1}
  augSize:            512,
  augCount:           5,
  augOutputDir:       '',
  augRandomizePerImg: true,
  augImages:          [],    // [{src, label}]
  augGenerating:      false,
  augPreviewLoading:  false,
  augPreviewSrc:      null,

  // ── Simple setters ────────────────────────────────────────────────────────
  setFilter:     (k, v) => set({ [k]: v }),
  setStatusMsg:  (m)    => set({ statusMsg: m }),
  setSaveMsg:    (m)    => set({ saveMsg: m }),
  setExportMsg:  (m)    => set({ exportMsg: m }),
  setActiveTab:  (t)    => set({ activeTab: t }),
  setZoom:       (z)    => set({ zoom: Math.max(1, Math.min(60, z)) }),
  setPortType:   (t)    => set({ portType: t }),
  setMarkerMode: (m)    => set({ markerMode: m }),
  setAxisLock:   (a)    => set({ axisLock: a }),
  setShowGrid:   (v)    => set({ showGrid: v }),
  setSnapGrid:   (v)    => set({ snapGrid: v }),
  setGridSize:   (v)    => set({ gridSize: v }),
  setMidState:   (s)    => set({ midState: s }),
  setMatchMode:  (m)    => set({ matchMode: m }),
  setAugImages:  (imgs) => set({ augImages: imgs }),
  setAugPreviewSrc: (s) => set({ augPreviewSrc: s }),
  setAugEffect: (name, intensity) =>
    set(s => ({ augEffects: { ...s.augEffects, [name]: intensity } })),
  removeAugEffect: (name) =>
    set(s => { const e = { ...s.augEffects }; delete e[name]; return { augEffects: e }; }),

  // ── Snap helper ───────────────────────────────────────────────────────────
  snapVal: (v) => {
    const { snapGrid, gridSize } = get();
    return snapGrid ? Math.round(v / gridSize) * gridSize : v;
  },

  // ── Port mutations ────────────────────────────────────────────────────────
  addPort: (port) => set(s => ({ ports: [...s.ports, port] })),

  updatePort: (idx, updates) => set(s => {
    const ports = [...s.ports];
    ports[idx] = { ...ports[idx], ...updates };
    return { ports };
  }),

  deleteSelected: () => set(s => {
    const toDelete = new Set(s.selection);
    if (s.selIdx !== null) toDelete.add(s.selIdx);
    const ports = s.ports.filter((_, i) => !toDelete.has(i));
    return { ports, selIdx: null, selection: new Set() };
  }),

  selectPort: (idx, multi = false) => set(s => {
    if (!multi) return { selIdx: idx, selection: new Set([idx]) };
    const sel = new Set(s.selection);
    sel.has(idx) ? sel.delete(idx) : sel.add(idx);
    return { selIdx: idx, selection: sel };
  }),

  deselectAll: () => set({ selIdx: null, selection: new Set() }),

  // ── API actions ───────────────────────────────────────────────────────────
  loadSymbols: async () => {
    try {
      const data = await (await fetch('/api/symbols')).json();
      set({ allSymbols: data });
    } catch (e) { console.error('loadSymbols:', e); }
  },

  loadSymbol: async (path) => {
    try {
      const res = await fetch(`/api/symbol?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error(await res.text());
      const { meta, svg } = await res.json();

      const vbM = svg.match(/viewBox=["']([^"']+)["']/);
      let viewBox = { x: 0, y: 0, w: 80, h: 80 };
      if (vbM) {
        const [x, y, w, h] = vbM[1].trim().split(/[\s,]+/).map(Number);
        viewBox = { x, y, w, h };
      }

      const fitZoom = Math.max(3, Math.round(480 / Math.max(viewBox.w, viewBox.h)));
      const dataUri = 'data:image/svg+xml;base64,' +
        btoa(unescape(encodeURIComponent(svg)));

      const ports = (meta.snap_points || []).map((sp, i) => ({
        id:     sp.id   || `port-${i}`,
        type:   sp.type || 'in',
        x:      sp.x   ?? 0,
        y:      sp.y   ?? 0,
        zone:   sp.zone || null,
        locked: !!sp.locked,
      }));

      set({
        currentPath: path, symbolMeta: meta, symbolSvgDataUri: dataUri,
        viewBox, ports, selIdx: null, selection: new Set(), zoom: fitZoom,
        statusMsg: meta.display_name || path, saveMsg: null,
        augImages: [], augPreviewSrc: null, midState: null, matchMode: null,
      });
    } catch (e) { set({ statusMsg: 'Error: ' + e.message }); }
  },

  saveSymbol: async (silent = false) => {
    const { currentPath, symbolMeta, ports } = get();
    if (!currentPath || !symbolMeta) return false;
    const snap_points = ports.map(p => {
      const sp = { id: p.id, type: p.type };
      if (p.zone) {
        sp.zone = {
          x: +p.zone.x.toFixed(2), y: +p.zone.y.toFixed(2),
          width: +p.zone.width.toFixed(2), height: +p.zone.height.toFixed(2),
        };
      } else { sp.x = +p.x.toFixed(2); sp.y = +p.y.toFixed(2); }
      if (p.locked) sp.locked = true;
      return sp;
    });
    const updatedMeta = { ...symbolMeta, snap_points };
    try {
      const res = await fetch('/api/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentPath, meta: updatedMeta }),
      });
      if (res.ok) {
        set({ symbolMeta: updatedMeta });
        if (!silent) set({ saveMsg: { ok: '✓ Saved' } });
        return true;
      }
      if (!silent) set({ saveMsg: { err: '✗ ' + await res.text() } });
      return false;
    } catch (e) {
      if (!silent) set({ saveMsg: { err: '✗ ' + e.message } });
      return false;
    }
  },

  toggleComplete: async () => {
    const { currentPath, symbolMeta, saveSymbol } = get();
    if (!currentPath || !symbolMeta) return;
    const newVal = !symbolMeta.completed;
    set(s => ({
      symbolMeta: { ...s.symbolMeta, completed: newVal },
      allSymbols: s.allSymbols.map(sym =>
        sym.path === currentPath ? { ...sym, completed: newVal } : sym
      ),
    }));
    const ok = await saveSymbol(true);
    if (!ok) {
      set(s => ({ symbolMeta: { ...s.symbolMeta, completed: !newVal } }));
      set({ saveMsg: { err: '✗ Save failed' } });
    } else {
      set({ saveMsg: { ok: newVal ? '✓ Marked complete' : '✓ Marked incomplete' } });
    }
  },

  nextSymbol: async () => {
    const { currentPath, allSymbols, filterSource, filterStandard, filterText, saveSymbol } = get();
    await saveSymbol(true);
    const q = filterText.toLowerCase();
    const visible = allSymbols.filter(s => {
      if (filterSource   && s.source   !== filterSource)   return false;
      if (filterStandard && s.standard !== filterStandard) return false;
      if (q && !s.name.toLowerCase().includes(q) && !s.path.toLowerCase().includes(q)) return false;
      return true;
    });
    const idx  = visible.findIndex(s => s.path === currentPath);
    const rest = [...visible.slice(idx + 1), ...visible.slice(0, idx)];
    const next = rest.find(s => !s.completed);
    if (next) get().loadSymbol(next.path);
  },

  generateDebug: async () => {
    const { currentPath, ports } = get();
    if (!currentPath) return;
    try {
      const res = await fetch('/api/debug', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: currentPath,
          ports: ports.map(p => p.zone
            ? { id: p.id, type: p.type, zone: p.zone }
            : { id: p.id, type: p.type, x: +p.x.toFixed(2), y: +p.y.toFixed(2) }
          ),
        }),
      });
      set({ saveMsg: res.ok ? { ok: '✓ _debug.svg written' } : { err: '✗ ' + await res.text() } });
    } catch (e) { set({ saveMsg: { err: '✗ ' + e.message } }); }
  },

  exportCompleted: async (dir) => {
    try {
      const res = await fetch('/api/export-completed', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: dir }),
      });
      const data = await res.json();
      set({ exportMsg: data.errors > 0
        ? { err: `✗ ${data.copied} copied, ${data.errors} error(s)` }
        : { ok: `✓ ${data.message}` }
      });
    } catch (e) { set({ exportMsg: { err: '✗ ' + e.message } }); }
  },
}));
