import { useState } from 'react';
import {
  Box, Typography, Button, Divider, TextField, Stack, Alert,
} from '@mui/material';
import { useEditorStore } from '../store';

function SectionLabel({ children }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mt: 1.5, mb: 0.5 }}>
      <Box sx={{ width: 2, height: 10, borderRadius: 1, bgcolor: 'primary.main', flexShrink: 0 }} />
      <Typography sx={{
        fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em',
        textTransform: 'uppercase', color: 'text.disabled',
      }}>
        {children}
      </Typography>
    </Box>
  );
}

export default function ExportTab() {
  const [exportDir, setExportDir] = useState('');
  const {
    currentPath, symbolMeta,
    saveSymbol, nextSymbol, toggleComplete, generateDebug, exportCompleted,
    saveMsg, exportMsg,
  } = useEditorStore();

  return (
    <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>

      {/* ── Save / Next / Complete / Debug ───────────────────────────────── */}
      <SectionLabel>Symbol</SectionLabel>
      <Stack gap={0.5} sx={{ mt: 0.5 }}>
        <Button
          fullWidth variant="contained"
          onClick={() => saveSymbol()}
          disabled={!currentPath}
          sx={{ fontSize: 11, bgcolor: 'primary.main', '&:hover': { bgcolor: 'primary.dark' } }}
        >
          Save JSON
        </Button>
        <Button
          fullWidth variant="outlined" color="success"
          disabled={!currentPath}
          onClick={nextSymbol}
          sx={{ fontSize: 11 }}
        >
          Save &amp; Next →
        </Button>
        <Button
          fullWidth variant="outlined"
          color={symbolMeta?.completed ? 'success' : 'inherit'}
          disabled={!currentPath}
          onClick={toggleComplete}
          sx={{ fontSize: 11 }}
        >
          {symbolMeta?.completed ? '✓ Completed' : '✓ Mark Complete'}
        </Button>
        <Button
          fullWidth variant="outlined"
          disabled={!currentPath}
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

      <Divider sx={{ my: 1 }} />

      {/* ── Export Completed ─────────────────────────────────────────────── */}
      <SectionLabel>Export Completed</SectionLabel>
      <TextField
        fullWidth size="small"
        placeholder="output folder (default: ./completed)"
        value={exportDir}
        onChange={e => setExportDir(e.target.value)}
        sx={{ mt: 0.5, mb: 0.5 }}
        inputProps={{ style: { fontSize: 11 } }}
      />
      <Button
        fullWidth variant="outlined"
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
