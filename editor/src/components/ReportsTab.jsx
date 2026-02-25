import { useState, useCallback, useEffect } from 'react';
import {
  Box, Typography, Stack, IconButton, Tooltip, Alert,
} from '@mui/material';
import FlagIcon          from '@mui/icons-material/Flag';
import RefreshIcon       from '@mui/icons-material/Refresh';
import CloseIcon         from '@mui/icons-material/Close';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DownloadIcon      from '@mui/icons-material/Download';

export default function ReportsTab() {
  const [reports,  setReports]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);

  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res  = await fetch('/api/flag-reports');
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      const sorted = [...(data.reports || [])].sort((a, b) => b.id.localeCompare(a.id));
      setReports(sorted);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleDelete = useCallback(async (id) => {
    try {
      const res = await fetch('/api/flag-report-delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
      if (res.ok) setReports(prev => prev.filter(r => r.id !== id));
    } catch (_) {}
  }, []);

  const handleDownload = useCallback(() => {
    const payload = { reports };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'unrealistic_reports.json';
    a.click();
    URL.revokeObjectURL(url);
  }, [reports]);

  const handleClearAll = useCallback(async () => {
    try {
      const res = await fetch('/api/flag-reports-clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) setReports([]);
    } catch (_) {}
  }, []);

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Stack
        direction="row" alignItems="center" gap={0.75}
        sx={{ px: 1.25, py: 0.75, borderBottom: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}
      >
        <FlagIcon sx={{ fontSize: 13, color: '#ef4444' }} />
        <Typography sx={{ fontSize: 11, color: '#ef4444', fontWeight: 600, flex: 1 }}>
          Flagged Effects
          {reports.length > 0 && (
            <span style={{ color: 'rgba(239,68,68,0.6)', marginLeft: 5, fontWeight: 400 }}>
              {reports.length} report{reports.length !== 1 ? 's' : ''}
            </span>
          )}
        </Typography>
        {reports.length > 0 && (
          <Tooltip title="Clear all" disableInteractive>
            <IconButton
              size="small"
              onClick={handleClearAll}
              sx={{ color: 'rgba(239,68,68,0.5)', '&:hover': { color: '#ef4444' }, p: '3px' }}
            >
              <DeleteOutlineIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Download JSON" disableInteractive>
          <span>
            <IconButton
              size="small"
              onClick={handleDownload}
              disabled={reports.length === 0}
              sx={{ color: 'text.disabled', '&:hover': { color: 'text.secondary' }, p: '3px' }}
            >
              <DownloadIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh" disableInteractive>
          <IconButton
            size="small"
            onClick={fetchReports}
            sx={{ color: 'text.disabled', '&:hover': { color: 'text.secondary' }, p: '3px' }}
          >
            <RefreshIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>
        {error && (
          <Alert severity="error" sx={{ py: 0, fontSize: 11, mb: 1 }}>{error}</Alert>
        )}

        {!loading && reports.length === 0 && !error && (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 1 }}>
            <FlagIcon sx={{ fontSize: 32, color: 'rgba(239,68,68,0.18)' }} />
            <Typography sx={{ fontSize: 11, color: 'text.disabled', textAlign: 'center' }}>
              No flagged effects yet.
              <br />
              Use "Flag as unrealistic" in the image preview.
            </Typography>
          </Box>
        )}

        <Stack gap={0.75}>
          {reports.map(r => {
            const stem = r.symbol ? r.symbol.split('/').pop() : '—';
            const effectEntries = Object.entries(r.effects || {}).sort(([, a], [, b]) => b - a);
            return (
              <Box
                key={r.id}
                sx={{
                  border: '1px solid rgba(239,68,68,0.18)',
                  borderRadius: 1.5, px: 1.25, py: 1,
                  bgcolor: 'rgba(239,68,68,0.03)',
                }}
              >
                <Stack direction="row" alignItems="flex-start" justifyContent="space-between" gap={0.5}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>

                    {/* Symbol + label + source badge */}
                    <Stack direction="row" alignItems="center" gap={0.5} sx={{ mb: 0.25 }}>
                      <Typography sx={{
                        fontSize: 11, color: 'text.primary', fontFamily: 'monospace',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                      }}>
                        {stem}
                      </Typography>
                      <Typography sx={{ fontSize: 9, color: 'text.disabled', flexShrink: 0 }}>
                        {r.label}
                      </Typography>
                      <Box sx={{
                        fontSize: 8, color: 'rgba(239,68,68,0.65)',
                        border: '1px solid rgba(239,68,68,0.25)', borderRadius: 0.5,
                        px: '4px', py: '1px', flexShrink: 0, lineHeight: 1.6,
                      }}>
                        {r.source || 'preview'}
                      </Box>
                    </Stack>

                    {/* Timestamp */}
                    <Typography sx={{ fontSize: 9, color: 'text.disabled', mb: 0.75, fontFamily: 'monospace' }}>
                      {r.timestamp}
                    </Typography>

                    {/* Effect pills */}
                    {effectEntries.length > 0 ? (
                      <Stack direction="row" flexWrap="wrap" gap={0.4}>
                        {effectEntries.map(([name, val]) => (
                          <Box key={name} sx={{
                            bgcolor: 'rgba(239,68,68,0.10)',
                            border: '1px solid rgba(239,68,68,0.22)',
                            borderRadius: 0.5, px: 0.75, py: '2px',
                            fontSize: 9, color: 'rgba(255,255,255,0.65)',
                            fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
                            whiteSpace: 'nowrap',
                          }}>
                            {name}&nbsp;
                            <span style={{ color: '#f87171' }}>{Math.round(val * 100)}%</span>
                          </Box>
                        ))}
                      </Stack>
                    ) : (
                      <Typography sx={{ fontSize: 9, color: 'text.disabled', fontStyle: 'italic' }}>
                        no effect data
                      </Typography>
                    )}
                  </Box>

                  {/* Delete button */}
                  <IconButton
                    size="small"
                    onClick={() => handleDelete(r.id)}
                    sx={{ color: 'text.disabled', '&:hover': { color: '#ef4444' }, p: '3px', flexShrink: 0, mt: '-2px' }}
                  >
                    <CloseIcon sx={{ fontSize: 13 }} />
                  </IconButton>
                </Stack>
              </Box>
            );
          })}
        </Stack>
      </Box>
    </Box>
  );
}
