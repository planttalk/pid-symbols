import { useEffect, useCallback } from 'react';
import { Box } from '@mui/material';
import { useEditorStore } from './store';
import LeftPanel from './components/LeftPanel';
import CanvasEditor from './components/CanvasEditor';
import RightPanel from './components/RightPanel';

export default function App() {
  const {
    currentPath, ports, selIdx, selection, axisLock, snapGrid, gridSize,
    midState, matchMode, activeTab,
    loadSymbols, loadSymbol, saveSymbol, nextSymbol, deleteSelected,
    updatePort, selectPort, deselectAll, setMidState, setMatchMode,
    setStatusMsg, addPort, snapVal, viewBox,
  } = useEditorStore();

  // Boot: load symbol list
  useEffect(() => { loadSymbols(); }, []);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e) => {
    const inInput = ['input', 'textarea'].includes(
      document.activeElement?.tagName?.toLowerCase()
    );

    if (e.key === 'Escape') {
      if (midState)  { setMidState(null);  return; }
      if (matchMode) { setMatchMode(null); return; }
      return;
    }

    if (e.key === 'Enter' && midState?.step === 3) {
      e.preventDefault();
      // Confirm midpoint — add port at mid position
      const { midX, midY } = midState;
      const { portType, snapVal: snap } = useEditorStore.getState();
      addPort({ id: `port-${Date.now()}`, type: portType, x: +snap(midX).toFixed(2), y: +snap(midY).toFixed(2), zone: null, locked: false });
      setMidState(null);
      return;
    }

    if (inInput) return;

    if (e.key === 'Delete' && (selection.size > 0 || selIdx !== null)) {
      deleteSelected();
      return;
    }

    if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key) && selIdx !== null) {
      const p = ports[selIdx];
      if (!p || p.locked) return;
      e.preventDefault();
      const step = snapGrid ? (gridSize || 10) : 1;
      const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
      const dy = e.key === 'ArrowUp'   ? -step : e.key === 'ArrowDown'  ? step : 0;
      updatePort(selIdx, { x: +(p.x + dx).toFixed(2), y: +(p.y + dy).toFixed(2) });
      setStatusMsg(`"${p.id}"  x=${+(p.x+dx).toFixed(2)}  y=${+(p.y+dy).toFixed(2)}`);
    }
  }, [midState, matchMode, selIdx, selection, ports, snapGrid, gridSize]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden', bgcolor: 'background.default' }}>
      <LeftPanel />
      <CanvasEditor />
      <RightPanel />
    </Box>
  );
}
