import { useState } from 'react';
import {
  Box, Typography, Button, Divider, RadioGroup, FormControlLabel, Radio,
  Checkbox, TextField, List, ListItemButton, ListItemText, IconButton,
  Stack, Chip, Alert,
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import { useEditorStore } from '../store';
import { PORT_TYPES, portColor } from '../constants';

// ── Section label helper ──────────────────────────────────────────────────────
function SectionLabel({ children }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mt: 1.5, mb: 0.5 }}>
      <Box sx={{
        width: 2, height: 10, borderRadius: 1,
        bgcolor: 'primary.main', flexShrink: 0,
      }} />
      <Typography sx={{
        fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em',
        textTransform: 'uppercase', color: 'text.disabled',
      }}>
        {children}
      </Typography>
    </Box>
  );
}

// ── Port type grid ────────────────────────────────────────────────────────────
function TypeGrid() {
  const { portType, selIdx, ports, setPortType, updatePort } = useEditorStore();

  const handleTypeClick = (id) => {
    setPortType(id);
    if (selIdx !== null) updatePort(selIdx, { type: id });
  };

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.5, my: 0.5 }}>
      {PORT_TYPES.map(t => {
        const active = selIdx !== null
          ? ports[selIdx]?.type === t.id
          : portType === t.id;
        return (
          <Button
            key={t.id}
            onClick={() => handleTypeClick(t.id)}
            variant={active ? 'contained' : 'outlined'}
            sx={{
              justifyContent: 'flex-start', gap: 0.75, p: '3px 8px',
              fontSize: 11,
              borderColor: active ? t.color : 'rgba(255,255,255,0.12)',
              bgcolor: active ? t.color + '33' : 'transparent',
              color: active ? t.color : 'text.secondary',
              borderRadius: '999px',
              '&:hover': { bgcolor: t.color + '22', borderColor: t.color },
            }}
          >
            <Box sx={{ width: 9, height: 9, borderRadius: '50%', bgcolor: t.color, flexShrink: 0 }} />
            {t.label}
          </Button>
        );
      })}
    </Box>
  );
}

// ── Port list item ────────────────────────────────────────────────────────────
function PortRow({ port, idx }) {
  const { selIdx, selection, selectPort, updatePort } = useEditorStore();
  const selected = idx === selIdx || selection.has(idx);
  const col = portColor(port.type);

  return (
    <ListItemButton
      selected={selected}
      onClick={e => selectPort(idx, e.ctrlKey || e.metaKey)}
      sx={{ py: 0.25, px: 0.75, borderRadius: '6px', gap: 0.5 }}
    >
      <Box sx={{
        width: 11, height: 11, borderRadius: '50%', bgcolor: col,
        border: '1.5px solid rgba(255,255,255,0.3)', flexShrink: 0,
      }} />
      <ListItemText
        primary={port.id}
        secondary={port.zone
          ? `${port.zone.x.toFixed(1)},${port.zone.y.toFixed(1)} ${port.zone.width.toFixed(1)}×${port.zone.height.toFixed(1)}`
          : `${(port.x||0).toFixed(1)}, ${(port.y||0).toFixed(1)}`
        }
        primaryTypographyProps={{ fontSize: 12 }}
        secondaryTypographyProps={{ fontSize: 10, fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace' }}
      />
      {port.zone && (
        <Chip
          label="zone"
          size="small"
          sx={{ fontSize: 8, height: 14, ml: 0.5, color: 'secondary.main', borderColor: 'secondary.main' }}
          variant="outlined"
        />
      )}
      <IconButton
        size="small"
        onClick={e => { e.stopPropagation(); updatePort(idx, { locked: !port.locked }); }}
        sx={{ p: 0.25, ml: 'auto', opacity: port.locked ? 0.9 : 0.4, '&:hover': { opacity: 1 } }}
      >
        {port.locked ? <LockIcon sx={{ fontSize: 11 }} /> : <LockOpenIcon sx={{ fontSize: 11 }} />}
      </IconButton>
    </ListItemButton>
  );
}

// ── Field editor ──────────────────────────────────────────────────────────────
function FieldEditor() {
  const { ports, selIdx, updatePort } = useEditorStore();
  if (selIdx === null || !ports[selIdx]) return null;
  const p = ports[selIdx];

  const setField = (key, raw) => {
    const v = parseFloat(raw);
    if (!isNaN(v)) updatePort(selIdx, { [key]: v });
  };

  const convertToZone = () => {
    const vb = useEditorStore.getState().viewBox;
    updatePort(selIdx, {
      zone: { x: p.x - vb.w*0.1, y: p.y - vb.h*0.1, width: vb.w*0.2, height: vb.h*0.2 },
      x: undefined, y: undefined,
    });
  };

  const convertToPoint = () => {
    if (!p.zone) return;
    updatePort(selIdx, {
      x: +(p.zone.x + p.zone.width/2).toFixed(2),
      y: +(p.zone.y + p.zone.height/2).toFixed(2),
      zone: null,
    });
  };

  return (
    <Box sx={{
      bgcolor: 'rgba(255,255,255,0.025)',
      borderRadius: 1,
      p: 1,
      mt: 0.5,
    }}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <TextField
          label="Name" fullWidth size="small"
          value={p.id}
          onChange={e => updatePort(selIdx, { id: e.target.value })}
          inputProps={{ style: { fontSize: 11 } }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={p.zone ? convertToPoint : convertToZone}
          sx={{ fontSize: 10, py: 0.25, borderColor: 'secondary.main', color: 'secondary.main' }}
        >
          {p.zone ? 'Convert to Point' : 'Convert to Zone'}
        </Button>
        {!p.zone ? (
          <Stack direction="row" gap={1}>
            <TextField label="X" size="small" type="number" inputProps={{ step: 0.5, style: { fontSize: 11 } }}
              value={(p.x||0).toFixed(2)} onChange={e => setField('x', e.target.value)} sx={{ flex: 1 }} />
            <TextField label="Y" size="small" type="number" inputProps={{ step: 0.5, style: { fontSize: 11 } }}
              value={(p.y||0).toFixed(2)} onChange={e => setField('y', e.target.value)} sx={{ flex: 1 }} />
          </Stack>
        ) : (
          <>
            <Stack direction="row" gap={1}>
              <TextField label="ZX" size="small" type="number" inputProps={{ step: 0.5, style: { fontSize: 11 } }}
                value={(p.zone.x||0).toFixed(2)} onChange={e => updatePort(selIdx, { zone: { ...p.zone, x: +e.target.value } })} sx={{ flex: 1 }} />
              <TextField label="ZY" size="small" type="number" inputProps={{ step: 0.5, style: { fontSize: 11 } }}
                value={(p.zone.y||0).toFixed(2)} onChange={e => updatePort(selIdx, { zone: { ...p.zone, y: +e.target.value } })} sx={{ flex: 1 }} />
            </Stack>
            <Stack direction="row" gap={1}>
              <TextField label="W" size="small" type="number" inputProps={{ step: 0.5, min: 0.1, style: { fontSize: 11 } }}
                value={(p.zone.width||1).toFixed(2)} onChange={e => updatePort(selIdx, { zone: { ...p.zone, width: +e.target.value } })} sx={{ flex: 1 }} />
              <TextField label="H" size="small" type="number" inputProps={{ step: 0.5, min: 0.1, style: { fontSize: 11 } }}
                value={(p.zone.height||1).toFixed(2)} onChange={e => updatePort(selIdx, { zone: { ...p.zone, height: +e.target.value } })} sx={{ flex: 1 }} />
            </Stack>
          </>
        )}
      </Box>
    </Box>
  );
}

// ── Main Ports tab ────────────────────────────────────────────────────────────
export default function PortsTab() {
  const [exportDir, setExportDir] = useState('');
  const {
    currentPath, symbolMeta, ports, selIdx, selection, markerMode, axisLock,
    showGrid, snapGrid, gridSize, midState, matchMode,
    setMarkerMode, setAxisLock, setShowGrid, setSnapGrid, setGridSize,
    saveSymbol, nextSymbol, toggleComplete, generateDebug, exportCompleted,
    addPort, deleteSelected, setMidState, setMatchMode,
    saveMsg, exportMsg, portType, snapVal, selectPort, updatePort,
  } = useEditorStore();

  const canDelete = selection.size > 0 || selIdx !== null;
  const canMid    = !midState && !matchMode;
  const canMatch  = !midState && !matchMode;

  const handleAddCenter = () => {
    if (!currentPath) return;
    const { viewBox: vb, portType: pt, ports: ps } = useEditorStore.getState();
    addPort({ id: `port-${Date.now()}`, type: pt, x: +(vb.x + vb.w/2).toFixed(2), y: +(vb.y + vb.h/2).toFixed(2), zone: null, locked: false });
    selectPort(ps.length, false);
  };

  return (
    <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>

      {/* Symbol info */}
      <SectionLabel>Symbol</SectionLabel>
      <Box sx={{
        bgcolor: 'rgba(255,255,255,0.03)',
        borderRadius: 1,
        p: 0.75,
        mt: 0.5,
        mb: 0.5,
      }}>
        <Typography sx={{ fontSize: 10, color: 'text.secondary', wordBreak: 'break-all', lineHeight: 1.5 }}>
          {symbolMeta ? symbolMeta.display_name || currentPath : '—'}
          {symbolMeta?.standard && (
            <><br /><Box component="span" sx={{ color: 'text.disabled' }}>{symbolMeta.standard} / {symbolMeta.category}</Box></>
          )}
        </Typography>
      </Box>

      <Divider />
      <SectionLabel>Port Type</SectionLabel>
      <TypeGrid />

      <Divider />
      <SectionLabel>Marker</SectionLabel>
      <RadioGroup row value={markerMode} onChange={e => setMarkerMode(e.target.value)} sx={{ gap: 1 }}>
        {['crosshair','dot','none'].map(m => (
          <FormControlLabel key={m} value={m} control={<Radio size="small" />}
            label={<Typography sx={{ fontSize: 11 }}>{m}</Typography>} />
        ))}
      </RadioGroup>

      <Divider />
      <SectionLabel>Grid</SectionLabel>
      <FormControlLabel
        control={<Checkbox size="small" checked={showGrid} onChange={e => setShowGrid(e.target.checked)} />}
        label={<Typography sx={{ fontSize: 11 }}>Show Grid</Typography>}
      />
      <FormControlLabel
        control={<Checkbox size="small" checked={snapGrid} onChange={e => setSnapGrid(e.target.checked)} />}
        label={<Typography sx={{ fontSize: 11 }}>Snap to Grid</Typography>}
      />
      <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.5 }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>Size</Typography>
        <TextField
          type="number"
          size="small"
          value={gridSize}
          onChange={e => setGridSize(+e.target.value || 10)}
          inputProps={{ min: 1, max: 200, style: { width: 56, fontSize: 11 } }}
        />
      </Stack>

      <Divider />
      <SectionLabel>Axis Lock</SectionLabel>
      <RadioGroup value={axisLock} onChange={e => setAxisLock(e.target.value)}>
        {[['FREE','Free'],['LOCK_X','Lock X — vertical only'],['LOCK_Y','Lock Y — horizontal only']].map(([v,l]) => (
          <FormControlLabel key={v} value={v} control={<Radio size="small" />}
            label={<Typography sx={{ fontSize: 11 }}>{l}</Typography>} sx={{ m: 0 }} />
        ))}
      </RadioGroup>

      <Divider />
      <SectionLabel>Ports</SectionLabel>
      <List dense disablePadding sx={{ maxHeight: 130, overflowY: 'auto', mb: 0.5 }}>
        {ports.map((p, i) => <PortRow key={i} port={p} idx={i} />)}
      </List>

      {/* Port actions */}
      <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mb: 0.5 }}>
        <Button size="small" onClick={handleAddCenter} sx={{ fontSize: 11 }}>+ Add</Button>
        <Button
          size="small"
          disabled={!canMid}
          onClick={() => setMidState(midState ? null : { step: 1 })}
          sx={{
            fontSize: 11,
            ...(midState ? { borderColor: '#9944ee', color: '#cc88ff' } : {}),
          }}
        >
          ⊕ Midpoint
        </Button>
        <Button size="small" color="error" disabled={!canDelete} onClick={deleteSelected} sx={{ fontSize: 11 }}>
          ✕ Delete
        </Button>
      </Stack>
      <Stack direction="row" gap={0.5} sx={{ mb: 0.5 }}>
        {['Y','X'].map(axis => (
          <Button
            key={axis}
            size="small"
            fullWidth
            onClick={() => setMatchMode(matchMode?.axis === axis ? null : { axis, firstIdx: null })}
            sx={{
              fontSize: 11,
              ...(matchMode?.axis === axis ? { borderColor: '#ffcc00', color: '#ffcc00' } : {}),
            }}
          >
            Match {axis}
          </Button>
        ))}
      </Stack>

      <FieldEditor />

      <Divider />

      {/* Save / Next / Complete / Debug */}
      <SectionLabel>Export</SectionLabel>
      <Stack gap={0.5} sx={{ mt: 0.5 }}>
        <Button
          fullWidth
          variant="contained"
          onClick={() => saveSymbol()}
          sx={{
            fontSize: 11,
            bgcolor: 'primary.main',
            '&:hover': { bgcolor: 'primary.dark' },
          }}
        >
          Save JSON
        </Button>
        <Button
          fullWidth
          variant="outlined"
          color="success"
          disabled={!currentPath}
          onClick={nextSymbol}
          sx={{ fontSize: 11 }}
        >
          Save &amp; Next →
        </Button>
        <Button
          fullWidth
          variant="outlined"
          color={symbolMeta?.completed ? 'success' : 'inherit'}
          disabled={!currentPath}
          onClick={toggleComplete}
          sx={{ fontSize: 11 }}
        >
          {symbolMeta?.completed ? '✓ Completed' : '✓ Mark Complete'}
        </Button>
        <Button
          fullWidth
          variant="outlined"
          onClick={generateDebug}
          sx={{ fontSize: 11 }}
        >
          Generate _debug.svg
        </Button>
        {saveMsg && (
          <Alert severity={saveMsg.ok ? 'success' : 'error'} sx={{ py: 0, fontSize: 11 }}>
            {saveMsg.ok || saveMsg.err}
          </Alert>
        )}
      </Stack>

      <Divider />

      {/* Export completed */}
      <SectionLabel>Export Completed</SectionLabel>
      <TextField
        fullWidth
        size="small"
        placeholder="output folder (default: ./completed)"
        value={exportDir}
        onChange={e => setExportDir(e.target.value)}
        sx={{ mt: 0.5, mb: 0.5 }}
        inputProps={{ style: { fontSize: 11 } }}
      />
      <Button
        fullWidth
        variant="outlined"
        onClick={() => exportCompleted(exportDir)}
        sx={{ fontSize: 11, borderColor: '#9944ee', color: '#cc88ff' }}
      >
        Export Completed
      </Button>
      {exportMsg && (
        <Alert severity={exportMsg.ok ? 'success' : 'error'} sx={{ mt: 0.5, py: 0, fontSize: 11 }}>
          {exportMsg.ok || exportMsg.err}
        </Alert>
      )}
    </Box>
  );
}
