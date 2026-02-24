import { Box, IconButton, Tooltip, Divider, Typography, Slider } from '@mui/material';
import AddCircleOutlineIcon    from '@mui/icons-material/AddCircleOutline';
import DeleteOutlineIcon       from '@mui/icons-material/DeleteOutline';
import GridOnIcon              from '@mui/icons-material/GridOn';
import CenterFocusStrongIcon   from '@mui/icons-material/CenterFocusStrong';
import ZoomInIcon              from '@mui/icons-material/ZoomIn';
import ZoomOutIcon             from '@mui/icons-material/ZoomOut';
import LinearScaleIcon         from '@mui/icons-material/LinearScale';
import SwapHorizIcon           from '@mui/icons-material/SwapHoriz';
import SwapVertIcon            from '@mui/icons-material/SwapVert';
import SaveIcon                from '@mui/icons-material/Save';
import CheckCircleOutlineIcon  from '@mui/icons-material/CheckCircleOutline';
import SkipNextIcon            from '@mui/icons-material/SkipNext';
import BlockIcon               from '@mui/icons-material/Block';
import ContentCopyIcon         from '@mui/icons-material/ContentCopy';
import GpsFixedIcon            from '@mui/icons-material/GpsFixed';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import VisibilityOffIcon       from '@mui/icons-material/VisibilityOff';
import LockIcon                from '@mui/icons-material/Lock';
import LockOpenIcon            from '@mui/icons-material/LockOpen';
import { useEditorStore }      from '../store';

// Helpers

function Sep() {
  return (
    <Divider
      orientation="vertical"
      flexItem
      sx={{ mx: 0.75, bgcolor: 'rgba(255,255,255,0.07)', alignSelf: 'center', height: 20 }}
    />
  );
}

function Btn({ title, onClick, disabled, active, color = 'primary.main', children }) {
  return (
    <Tooltip title={title} enterDelay={500} disableInteractive>
      <span>
        <IconButton
          size="small"
          onClick={onClick}
          disabled={disabled}
          sx={{
            p: '6px',
            borderRadius: '8px',
            color: active ? color : 'text.secondary',
            bgcolor: active ? 'rgba(129,140,248,0.14)' : 'transparent',
            '&:hover:not(:disabled)': {
              bgcolor: active ? 'rgba(129,140,248,0.22)' : 'rgba(255,255,255,0.07)',
            },
            '&.Mui-disabled': { opacity: 0.3 },
          }}
        >
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}

const S  = { fontSize: 18 };  // standard icon size
const SM = { fontSize: 15 };  // smaller icon

// Dock

export default function CanvasDock() {
  const {
    currentPath, symbolMeta,
    ports, selIdx, selection,
    markerMode, axisLock, showGrid, snapGrid, zoom,
    midState, matchMode,
    setMarkerMode, setAxisLock, setShowGrid, setSnapGrid, setZoom,
    addPort, deleteSelected, setMidState, setMatchMode,
    saveSymbol, nextSymbol, toggleComplete, flagSymbol, selectPort,
  } = useEditorStore();

  const canDelete = selection.size > 0 || selIdx !== null;
  const canMid    = !midState && !matchMode;
  const flag      = symbolMeta?.flag;

  const handleAddCenter = () => {
    if (!currentPath) return;
    const { viewBox: vb, portType: pt } = useEditorStore.getState();
    addPort({
      id: `port-${Date.now()}`, type: pt,
      x: +(vb.x + vb.w / 2).toFixed(2),
      y: +(vb.y + vb.h / 2).toFixed(2),
      zone: null, locked: false,
    });
    selectPort(useEditorStore.getState().ports.length - 1, false);
  };

  const fitZoom = () => {
    const { viewBox } = useEditorStore.getState();
    setZoom(Math.max(3, Math.round(480 / Math.max(viewBox.w, viewBox.h))));
  };

  const zoomStep = (dir) =>
    setZoom(useEditorStore.getState().zoom * (dir > 0 ? 1.2 : 1 / 1.2));

  return (
    <Box sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 0,
      px: 1.25,
      py: 0.5,
      bgcolor: 'rgba(12,12,18,0.95)',
      backdropFilter: 'blur(8px)',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.07)',
      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
      flexWrap: 'nowrap',
      overflowX: 'auto',
    }}>

      {/* Marker mode */}
      <Btn title="Crosshair marker" onClick={() => setMarkerMode('crosshair')} active={markerMode === 'crosshair'}>
        <GpsFixedIcon sx={S} />
      </Btn>
      <Btn title="Dot marker" onClick={() => setMarkerMode('dot')} active={markerMode === 'dot'}>
        <RadioButtonUncheckedIcon sx={S} />
      </Btn>
      <Btn title="Hide markers" onClick={() => setMarkerMode('none')} active={markerMode === 'none'}>
        <VisibilityOffIcon sx={S} />
      </Btn>

      <Sep />

      {/* Grid / Snap */}
      <Btn title={showGrid ? 'Hide grid' : 'Show grid'} onClick={() => setShowGrid(!showGrid)} active={showGrid}>
        <GridOnIcon sx={S} />
      </Btn>
      <Btn title={snapGrid ? 'Disable snap' : 'Snap to grid'} onClick={() => setSnapGrid(!snapGrid)} active={snapGrid}>
        {snapGrid ? <LockIcon sx={SM} /> : <LockOpenIcon sx={SM} />}
      </Btn>

      <Sep />

      {/* Axis lock */}
      <Btn title="Free movement" onClick={() => setAxisLock('FREE')} active={axisLock === 'FREE'}>
        <Typography sx={{ fontSize: 10, fontWeight: 800, lineHeight: 1, fontFamily: 'monospace' }}>XY</Typography>
      </Btn>
      <Btn title="Lock X — vertical movement only" onClick={() => setAxisLock('LOCK_X')} active={axisLock === 'LOCK_X'}>
        <SwapVertIcon sx={SM} />
      </Btn>
      <Btn title="Lock Y — horizontal movement only" onClick={() => setAxisLock('LOCK_Y')} active={axisLock === 'LOCK_Y'}>
        <SwapHorizIcon sx={SM} />
      </Btn>

      <Sep />

      {/* Zoom */}
      <Btn title="Zoom out" onClick={() => zoomStep(-1)}>
        <ZoomOutIcon sx={S} />
      </Btn>
      <Btn title="Fit to canvas" onClick={fitZoom}>
        <CenterFocusStrongIcon sx={SM} />
      </Btn>
      <Btn title="Zoom in" onClick={() => zoomStep(1)}>
        <ZoomInIcon sx={S} />
      </Btn>

      {/* Slider in its own flex container so it never overlaps adjacent buttons */}
      <Box sx={{ display: 'flex', alignItems: 'center', mx: 1, gap: 0.75, flexShrink: 0 }}>
        <Tooltip title={`Zoom: ${Math.round(zoom)}×`} placement="top" disableInteractive>
          <Slider
            size="small"
            min={1} max={60} step={1}
            value={Math.round(zoom)}
            onChange={(_, v) => setZoom(v)}
            sx={{
              width: 80, color: 'primary.main',
              '& .MuiSlider-thumb': { width: 12, height: 12 },
              '& .MuiSlider-track': { height: 2 },
              '& .MuiSlider-rail':  { height: 2, opacity: 0.3 },
            }}
          />
        </Tooltip>
        <Typography sx={{
          fontSize: 10, color: 'text.disabled', minWidth: 26,
          textAlign: 'right', fontFamily: '"JetBrains Mono", monospace',
        }}>
          {Math.round(zoom)}×
        </Typography>
      </Box>

      <Sep />

      {/* Port actions */}
      <Btn title="Add port at center" onClick={handleAddCenter} disabled={!currentPath}>
        <AddCircleOutlineIcon sx={S} />
      </Btn>
      <Btn
        title={midState ? 'Cancel midpoint mode' : 'Midpoint mode — click two ports'}
        onClick={() => setMidState(midState ? null : { step: 1 })}
        disabled={!canMid && !midState}
        active={!!midState}
        color="#9C27B0"
      >
        <LinearScaleIcon sx={SM} />
      </Btn>
      <Btn title="Delete selected ports" onClick={deleteSelected} disabled={!canDelete} color="#ef4444">
        <DeleteOutlineIcon sx={S} />
      </Btn>
      <Btn
        title="Match Y — align ports to same Y (horizontal)"
        onClick={() => setMatchMode(matchMode?.axis === 'Y' ? null : { axis: 'Y', firstIdx: null })}
        active={matchMode?.axis === 'Y'}
        color="#facc15"
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <SwapHorizIcon sx={SM} />
          <Typography sx={{ fontSize: 8, lineHeight: 1, fontWeight: 700 }}>Y</Typography>
        </Box>
      </Btn>
      <Btn
        title="Match X — align ports to same X (vertical)"
        onClick={() => setMatchMode(matchMode?.axis === 'X' ? null : { axis: 'X', firstIdx: null })}
        active={matchMode?.axis === 'X'}
        color="#facc15"
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <SwapVertIcon sx={SM} />
          <Typography sx={{ fontSize: 8, lineHeight: 1, fontWeight: 700 }}>X</Typography>
        </Box>
      </Btn>

      <Sep />

      {/* Save / workflow */}
      <Btn title="Save JSON" onClick={() => saveSymbol()} disabled={!currentPath}>
        <SaveIcon sx={S} />
      </Btn>
      <Btn title="Save & load next incomplete symbol" onClick={nextSymbol} disabled={!currentPath}>
        <SkipNextIcon sx={S} />
      </Btn>
      <Btn
        title={symbolMeta?.completed ? 'Mark as incomplete' : 'Mark as complete'}
        onClick={toggleComplete}
        disabled={!currentPath}
        active={!!symbolMeta?.completed}
        color="#4ade80"
      >
        <CheckCircleOutlineIcon sx={S} />
      </Btn>

      <Sep />

      {/* Flags */}
      <Btn
        title={flag === 'unrelated' ? 'Remove "unrelated" flag' : 'Flag as Unrelated (not a P&ID symbol)'}
        onClick={() => flagSymbol('unrelated')}
        disabled={!currentPath}
        active={flag === 'unrelated'}
        color="#ef4444"
      >
        <BlockIcon sx={S} />
      </Btn>
      <Btn
        title={flag === 'similar' ? 'Remove "similar" flag' : 'Flag as Similar / Duplicate'}
        onClick={() => flagSymbol('similar')}
        disabled={!currentPath}
        active={flag === 'similar'}
        color="#f59e0b"
      >
        <ContentCopyIcon sx={SM} />
      </Btn>
    </Box>
  );
}
