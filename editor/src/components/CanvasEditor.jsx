import { useRef, useEffect, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { useEditorStore } from '../store';
import { portColor } from '../constants';

// ── Coordinate helper ────────────────────────────────────────────────────────
function toSvgCoords(svg, clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

// ── Port marker components ────────────────────────────────────────────────────
function CrosshairMarker({ x, y, r, col, sw }) {
  return (
    <>
      <line x1={x-r} y1={y} x2={x+r} y2={y} stroke={col} strokeWidth={sw} />
      <line x1={x} y1={y-r} x2={x} y2={y+r} stroke={col} strokeWidth={sw} />
      <circle cx={x} cy={y} r={r*0.28} fill={col} opacity={0.85} />
    </>
  );
}

function PortLabel({ x, y, r, col, tsw, label }) {
  return (
    <text x={x + r*1.15} y={y + r*0.5} fontSize={r*1.1} fill={col}
      fontFamily="monospace" stroke="white" strokeWidth={tsw} paintOrder="stroke">
      {label}
    </text>
  );
}

function PortMarker({ port, idx, selected, markerMode, r, onMouseDown, onContextMenu }) {
  const col = portColor(port.type);
  const sw  = Math.max(0.15, r * 0.12);
  const tsw = Math.max(0.1,  r * 1.1 * 0.12);

  if (port.zone) {
    const { x, y, width: zw, height: zh } = port.zone;
    return (
      <g onMouseDown={onMouseDown} onContextMenu={onContextMenu} style={{ cursor: 'move' }}>
        <rect x={x} y={y} width={zw} height={zh}
          fill={col} fillOpacity={0.12} stroke={col} strokeWidth={sw}
          strokeDasharray={selected ? undefined : `${r*0.5} ${r*0.25}`} />
        {selected && [[x,y],[x+zw,y],[x,y+zh],[x+zw,y+zh]].map(([hx,hy],hi) => (
          <rect key={hi}
            x={hx - r*0.6} y={hy - r*0.6} width={r*1.2} height={r*1.2}
            fill={col} stroke="white" strokeWidth={sw*0.5}
            style={{ cursor: 'nwse-resize' }}
            data-corner={['nw','ne','sw','se'][hi]}
            onMouseDown={e => { e.stopPropagation(); onMouseDown(e, hi); }}
          />
        ))}
        <text x={x+zw/2} y={y+zh/2} fontSize={r} fill={col}
          textAnchor="middle" dominantBaseline="middle"
          fontFamily="monospace" stroke="white" strokeWidth={tsw} paintOrder="stroke">
          {port.id}
        </text>
      </g>
    );
  }

  return (
    <g onMouseDown={onMouseDown} onContextMenu={onContextMenu}
       style={{ cursor: port.locked ? 'default' : 'grab' }}>
      {selected && (
        <circle cx={port.x} cy={port.y} r={r*1.45}
          fill="none" stroke="white" strokeWidth={sw*0.8} opacity={0.5} />
      )}
      {markerMode === 'crosshair' && (
        <CrosshairMarker x={port.x} y={port.y} r={r} col={col} sw={sw} />
      )}
      {markerMode === 'dot' && (
        <circle cx={port.x} cy={port.y} r={r}
          fill={col} stroke="white" strokeWidth={sw} opacity={0.9} />
      )}
      {markerMode !== 'none' && (
        <PortLabel x={port.x} y={port.y} r={r} col={col} tsw={tsw} label={port.id} />
      )}
      {/* invisible hit area */}
      <circle cx={port.x} cy={port.y} r={r*2} fill="transparent" />
    </g>
  );
}

// ── Main canvas component ─────────────────────────────────────────────────────
export default function CanvasEditor() {
  const svgRef  = useRef(null);
  const wrapRef = useRef(null);
  const dragRef = useRef({
    active: false,
    type: 'port',       // 'port' | 'zone-corner'
    idx: -1,
    corner: -1,         // 0=nw 1=ne 2=sw 3=se
    startX: 0, startY: 0,
    origX: 0, origY: 0,
    origZone: null,
  });

  const {
    currentPath, symbolSvgDataUri, viewBox, ports, selIdx, selection,
    markerMode, axisLock, showGrid, gridSize, zoom, midState, matchMode,
    portType, snapVal,
    setZoom, selectPort, deselectAll, updatePort, addPort,
    setMidState, setMatchMode, setStatusMsg,
  } = useEditorStore();

  const r    = Math.max(1.2, Math.min(viewBox.w, viewBox.h) * 0.025);
  const svgW = viewBox.w * zoom;
  const svgH = viewBox.h * zoom;

  // ── Zoom via wheel ─────────────────────────────────────────────────────────
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      setZoom(zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoom, setZoom]);

  // ── Global mousemove / mouseup (for drag) ──────────────────────────────────
  useEffect(() => {
    const onMove = (e) => {
      const d = dragRef.current;
      if (!d.active || !svgRef.current) return;
      const pt = toSvgCoords(svgRef.current, e.clientX, e.clientY);

      if (d.type === 'port') {
        const p = useEditorStore.getState().ports[d.idx];
        if (!p || p.locked) return;

        let nx = d.origX + (pt.x - d.startX);
        let ny = d.origY + (pt.y - d.startY);

        const al = useEditorStore.getState().axisLock;
        if (al === 'LOCK_X') nx = p.x;   // lock x → only y moves
        if (al === 'LOCK_Y') ny = p.y;   // lock y → only x moves

        nx = +snapVal(nx).toFixed(2);
        ny = +snapVal(ny).toFixed(2);

        updatePort(d.idx, { x: nx, y: ny });
        setStatusMsg(`"${p.id}"  x=${nx}  y=${ny}`);

      } else if (d.type === 'zone-corner') {
        const p    = useEditorStore.getState().ports[d.idx];
        const oz   = d.origZone;
        const dx   = pt.x - d.startX;
        const dy   = pt.y - d.startY;
        const [cx, cy] = [d.corner % 2, Math.floor(d.corner / 2)]; // 0/1=left/right, 0/1=top/bottom
        let { x, y, width, height } = { ...oz };

        if (cx === 0) { x     = snapVal(oz.x + dx);     width  = Math.max(1, oz.width  - dx); }
        else          { width  = Math.max(1, snapVal(oz.width  + dx)); }
        if (cy === 0) { y     = snapVal(oz.y + dy);     height = Math.max(1, oz.height - dy); }
        else          { height = Math.max(1, snapVal(oz.height + dy)); }

        updatePort(d.idx, { zone: { x: +x.toFixed(2), y: +y.toFixed(2), width: +width.toFixed(2), height: +height.toFixed(2) } });
      }
    };

    const onUp = () => { dragRef.current.active = false; };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };
  }, [updatePort, setStatusMsg, snapVal]);

  // ── Port mousedown ─────────────────────────────────────────────────────────
  const handlePortMouseDown = useCallback((e, idx, zoneCorner = -1) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    const p   = ports[idx];
    const pt  = toSvgCoords(svgRef.current, e.clientX, e.clientY);

    // Midpoint mode
    if (midState) {
      if (midState.step === 1) {
        setMidState({ step: 2, first: { idx, x: p.x, y: p.y } });
        return;
      }
      if (midState.step === 2) {
        const { first } = midState;
        const midX = (first.x + p.x) / 2;
        const midY = (first.y + p.y) / 2;
        setMidState({ step: 3, first, second: { idx, x: p.x, y: p.y }, midX, midY });
        return;
      }
      return;
    }

    // Match mode
    if (matchMode) {
      if (matchMode.firstIdx === null) {
        setMatchMode({ ...matchMode, firstIdx: idx });
      } else {
        const ref = ports[matchMode.firstIdx];
        updatePort(idx, matchMode.axis === 'Y' ? { y: ref.y } : { x: ref.x });
        setMatchMode(null);
      }
      return;
    }

    // Selection
    selectPort(idx, e.ctrlKey || e.metaKey);

    // Start drag
    dragRef.current = {
      active: true,
      type: zoneCorner >= 0 ? 'zone-corner' : 'port',
      idx,
      corner: zoneCorner,
      startX: pt.x, startY: pt.y,
      origX: p.x, origY: p.y,
      origZone: p.zone ? { ...p.zone } : null,
    };
  }, [ports, midState, matchMode, selectPort, updatePort, setMidState, setMatchMode]);

  // ── Port right-click (delete) ──────────────────────────────────────────────
  const handlePortContextMenu = useCallback((e, idx) => {
    e.preventDefault();
    e.stopPropagation();
    useEditorStore.setState(s => ({
      ports:    s.ports.filter((_, i) => i !== idx),
      selIdx:   s.selIdx === idx ? null : s.selIdx !== null && s.selIdx > idx ? s.selIdx - 1 : s.selIdx,
      selection: new Set(),
    }));
  }, []);

  // ── SVG background double-click (add port) ─────────────────────────────────
  const handleSvgDblClick = useCallback((e) => {
    if (!currentPath) return;
    if (midState) return;
    const pt = toSvgCoords(svgRef.current, e.clientX, e.clientY);
    const x  = +snapVal(pt.x).toFixed(2);
    const y  = +snapVal(pt.y).toFixed(2);
    const pt2 = { id: `port-${Date.now()}`, type: portType, x, y, zone: null, locked: false };
    addPort(pt2);
    selectPort(useEditorStore.getState().ports.length, false);
  }, [currentPath, midState, portType, snapVal, addPort, selectPort]);

  // ── SVG background click (deselect / confirm midpoint) ────────────────────
  const handleSvgClick = useCallback((e) => {
    if (e.detail > 1) return; // handled by dblclick
    if (midState?.step === 3) {
      const { midX, midY } = midState;
      addPort({ id: `port-${Date.now()}`, type: portType, x: +snapVal(midX).toFixed(2), y: +snapVal(midY).toFixed(2), zone: null, locked: false });
      setMidState(null);
      return;
    }
    // Click on background: deselect
    if (e.target === svgRef.current || e.target.id === 'canvas-bg' || e.target.id === 'grid-bg' || e.target.id === 'sym-img') {
      deselectAll();
    }
  }, [midState, portType, snapVal, addPort, deselectAll, setMidState]);

  // ── Guide lines (axis lock) ────────────────────────────────────────────────
  const selPort = selIdx !== null ? ports[selIdx] : null;
  const guideX  = selPort && axisLock === 'LOCK_X' ? selPort.x : null;
  const guideY  = selPort && axisLock === 'LOCK_Y' ? selPort.y : null;

  // ── Midpoint preview line ──────────────────────────────────────────────────
  const midPreview = midState?.step === 3 ? midState : null;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden', bgcolor: '#2a2a2a', p: 1, gap: 0.75 }}>
      {/* Status bar */}
      <Typography sx={{ fontSize: 11, color: 'text.secondary', textAlign: 'center', flexShrink: 0 }}>
        {useEditorStore(s => s.statusMsg)}
      </Typography>

      {/* Canvas */}
      <Box ref={wrapRef} sx={{ flex: 1, minHeight: 0, overflow: 'auto', boxShadow: 'inset 0 0 12px rgba(0,0,0,0.4)', bgcolor: '#3a3a3a',
        '&::-webkit-scrollbar': { width: 8, height: 8 },
        '&::-webkit-scrollbar-track': { bgcolor: '#2a2a2a' },
        '&::-webkit-scrollbar-thumb': { bgcolor: '#555', borderRadius: 1 },
      }}>
        <svg
          ref={svgRef}
          width={svgW}
          height={svgH}
          viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
          style={{ display: 'block', cursor: 'crosshair' }}
          onDblClick={handleSvgDblClick}
          onClick={handleSvgClick}
        >
          {/* White background */}
          <rect id="canvas-bg" x={viewBox.x} y={viewBox.y} width={viewBox.w} height={viewBox.h} fill="white" />

          {/* Grid */}
          {showGrid && (
            <>
              <defs>
                <pattern id="grid-pat" patternUnits="userSpaceOnUse" width={gridSize} height={gridSize}>
                  <path d={`M ${gridSize} 0 L 0 0 0 ${gridSize}`} fill="none" stroke="#bbb" strokeWidth={0.3 * viewBox.w / Math.max(svgW, 1)} />
                </pattern>
              </defs>
              <rect id="grid-bg" x={viewBox.x - 5000} y={viewBox.y - 5000} width={10000} height={10000} fill="url(#grid-pat)" />
            </>
          )}

          {/* Symbol image */}
          {symbolSvgDataUri && (
            <image id="sym-img"
              x={viewBox.x} y={viewBox.y}
              width={viewBox.w} height={viewBox.h}
              href={symbolSvgDataUri}
              preserveAspectRatio="none"
            />
          )}

          {/* Axis guide lines */}
          {guideX !== null && (
            <line x1={guideX} y1={viewBox.y - 5000} x2={guideX} y2={viewBox.y + 5000}
              stroke="#FF8800" strokeWidth={0.4} strokeDasharray="2,2" pointerEvents="none" />
          )}
          {guideY !== null && (
            <line x1={viewBox.x - 5000} y1={guideY} x2={viewBox.x + 5000} y2={guideY}
              stroke="#FF8800" strokeWidth={0.4} strokeDasharray="2,2" pointerEvents="none" />
          )}

          {/* Midpoint preview */}
          {midPreview && (
            <g pointerEvents="none">
              <line x1={midPreview.first.x} y1={midPreview.first.y}
                    x2={midPreview.second.x} y2={midPreview.second.y}
                stroke="#9C27B0" strokeWidth={r*0.3} strokeDasharray={`${r*0.5},${r*0.25}`} />
              <circle cx={midPreview.midX} cy={midPreview.midY} r={r*0.8}
                fill="none" stroke="#9C27B0" strokeWidth={r*0.2} />
            </g>
          )}

          {/* Port markers */}
          <g id="port-layer">
            {ports.map((port, i) => (
              <PortMarker
                key={i}
                port={port}
                idx={i}
                selected={i === selIdx || selection.has(i)}
                markerMode={markerMode}
                r={r}
                onMouseDown={(e, corner) => handlePortMouseDown(e, i, corner)}
                onContextMenu={(e) => handlePortContextMenu(e, i)}
              />
            ))}
          </g>
        </svg>
      </Box>

      {/* Hint bar */}
      <Typography sx={{ fontSize: 10, color: '#555', textAlign: 'center', flexShrink: 0 }}>
        Double-click to add&nbsp;|&nbsp;Drag to move&nbsp;|&nbsp;Right-click to delete&nbsp;|&nbsp;Scroll to zoom&nbsp;|&nbsp;Ctrl+click multi-select&nbsp;|&nbsp;Arrow keys nudge
        {midState?.step === 1 && <>&nbsp;|&nbsp;<span style={{color:'#9C27B0'}}>Click first port…</span></>}
        {midState?.step === 2 && <>&nbsp;|&nbsp;<span style={{color:'#9C27B0'}}>Click second port…</span></>}
        {midState?.step === 3 && <>&nbsp;|&nbsp;<span style={{color:'#9C27B0'}}>Click canvas or Enter to place midpoint</span></>}
        {matchMode && <>&nbsp;|&nbsp;<span style={{color:'#ffcc00'}}>{matchMode.firstIdx === null ? `Click source port to match ${matchMode.axis}…` : `Click target port…`}</span></>}
      </Typography>
    </Box>
  );
}
