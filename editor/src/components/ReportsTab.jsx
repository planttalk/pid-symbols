import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Box, Typography, Stack, IconButton, Tooltip, Alert, Collapse,
} from '@mui/material';
import FlagIcon          from '@mui/icons-material/Flag';
import RefreshIcon       from '@mui/icons-material/Refresh';
import CloseIcon         from '@mui/icons-material/Close';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DownloadIcon      from '@mui/icons-material/Download';
import ExpandMoreIcon    from '@mui/icons-material/ExpandMore';
import BarChartIcon      from '@mui/icons-material/BarChart';
import ListIcon          from '@mui/icons-material/List';

// Geometry-only transforms — excluded from effect frequency analysis
const GEOM_KEYS = new Set(['mirror_h', 'mirror_v', 'rot_90', 'rot_180', 'rot_270']);

// ── Effect pill ───────────────────────────────────────────────────────────────
function EffectPill({ name, val }) {
  const isGeom = GEOM_KEYS.has(name);
  return (
    <Box sx={{
      bgcolor: isGeom ? 'rgba(100,100,120,0.12)' : 'rgba(239,68,68,0.10)',
      border: `1px solid ${isGeom ? 'rgba(255,255,255,0.1)' : 'rgba(239,68,68,0.22)'}`,
      borderRadius: 0.5, px: 0.75, py: '2px',
      fontSize: 9, color: isGeom ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.65)',
      fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
      whiteSpace: 'nowrap',
    }}>
      {name}{!isGeom && <>&nbsp;<span style={{ color: '#f87171' }}>{Math.round(val * 100)}%</span></>}
    </Box>
  );
}

// ── Single report card ────────────────────────────────────────────────────────
function ReportCard({ r, onDelete }) {
  const effectEntries = Object.entries(r.effects || {}).sort(([a], [b]) => {
    const ag = GEOM_KEYS.has(a), bg = GEOM_KEYS.has(b);
    if (ag !== bg) return ag ? 1 : -1;       // geom last
    return (r.effects[b] - r.effects[a]);    // highest intensity first
  });

  return (
    <Box sx={{
      border: '1px solid rgba(239,68,68,0.18)',
      borderRadius: 1.5, px: 1.25, py: 1,
      bgcolor: 'rgba(239,68,68,0.03)',
    }}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" gap={0.5}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" gap={0.5} sx={{ mb: 0.25 }}>
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
            <Typography sx={{ fontSize: 9, color: 'text.disabled', fontFamily: 'monospace', ml: 'auto' }}>
              {r.timestamp.replace('T', ' ').replace('Z', '')}
            </Typography>
          </Stack>
          {effectEntries.length > 0 ? (
            <Stack direction="row" flexWrap="wrap" gap={0.4} sx={{ mt: 0.5 }}>
              {effectEntries.map(([name, val]) => (
                <EffectPill key={name} name={name} val={val} />
              ))}
            </Stack>
          ) : (
            <Typography sx={{ fontSize: 9, color: 'text.disabled', fontStyle: 'italic' }}>no effect data</Typography>
          )}
        </Box>
        <IconButton
          size="small" onClick={() => onDelete(r.id)}
          sx={{ color: 'text.disabled', '&:hover': { color: '#ef4444' }, p: '3px', flexShrink: 0, mt: '-2px' }}
        >
          <CloseIcon sx={{ fontSize: 13 }} />
        </IconButton>
      </Stack>
    </Box>
  );
}

// ── Symbol group (collapsible) ────────────────────────────────────────────────
function SymbolGroup({ symbol, reports, onDelete }) {
  const [open, setOpen] = useState(true);
  const stem = symbol ? symbol.split('/').pop() : '—';
  const path = symbol ? symbol.split('/').slice(0, -1).join(' / ') : '';

  return (
    <Box sx={{ border: '1px solid rgba(255,255,255,0.07)', borderRadius: 1.5, overflow: 'hidden', mb: 0.75 }}>
      {/* Group header */}
      <Stack
        direction="row" alignItems="center" gap={0.75}
        onClick={() => setOpen(o => !o)}
        sx={{
          px: 1.25, py: 0.75, cursor: 'pointer', userSelect: 'none',
          bgcolor: 'rgba(255,255,255,0.03)',
          '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
        }}
      >
        <ExpandMoreIcon sx={{
          fontSize: 14, color: 'text.disabled',
          transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
          transition: 'transform 0.15s ease',
        }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: 11, color: 'text.primary', fontFamily: 'monospace', fontWeight: 600 }}>
            {stem}
          </Typography>
          {path && (
            <Typography sx={{ fontSize: 9, color: 'text.disabled', fontFamily: 'monospace' }}>
              {path}
            </Typography>
          )}
        </Box>
        <Box sx={{
          fontSize: 9, color: '#ef4444', fontWeight: 600,
          bgcolor: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)',
          borderRadius: 0.75, px: '6px', py: '2px', flexShrink: 0,
        }}>
          {reports.length}
        </Box>
      </Stack>

      {/* Report cards */}
      <Collapse in={open}>
        <Stack gap={0.5} sx={{ px: 1, pb: 1, pt: 0.5 }}>
          {reports.map(r => <ReportCard key={r.id} r={r} onDelete={onDelete} />)}
        </Stack>
      </Collapse>
    </Box>
  );
}

// ── Summary view ──────────────────────────────────────────────────────────────
function SummaryView({ reports }) {
  const stats = useMemo(() => {
    const map = {};
    for (const r of reports) {
      for (const [name, val] of Object.entries(r.effects || {})) {
        if (GEOM_KEYS.has(name)) continue;
        if (!map[name]) map[name] = { count: 0, totalVal: 0 };
        map[name].count++;
        map[name].totalVal += val;
      }
    }
    return Object.entries(map)
      .map(([name, { count, totalVal }]) => ({ name, count, avg: totalVal / count }))
      .sort((a, b) => b.count - a.count || b.avg - a.avg);
  }, [reports]);

  const symbolCount = useMemo(() =>
    new Set(reports.map(r => r.symbol).filter(Boolean)).size
  , [reports]);

  const maxCount = stats[0]?.count || 1;

  if (stats.length === 0) {
    return (
      <Typography sx={{ fontSize: 10, color: 'text.disabled', textAlign: 'center', mt: 3 }}>
        No effect data to summarise yet.
      </Typography>
    );
  }

  return (
    <Box>
      {/* Overview chips */}
      <Stack direction="row" gap={0.75} sx={{ mb: 1.5 }} flexWrap="wrap">
        {[
          { label: 'Reports', val: reports.length },
          { label: 'Symbols', val: symbolCount },
          { label: 'Unique effects', val: stats.length },
        ].map(({ label, val }) => (
          <Box key={label} sx={{
            border: '1px solid rgba(239,68,68,0.2)', borderRadius: 1,
            px: 1, py: 0.5, bgcolor: 'rgba(239,68,68,0.05)',
          }}>
            <Typography sx={{ fontSize: 16, color: '#f87171', fontWeight: 700, lineHeight: 1.1, textAlign: 'center' }}>
              {val}
            </Typography>
            <Typography sx={{ fontSize: 9, color: 'text.disabled', textAlign: 'center' }}>{label}</Typography>
          </Box>
        ))}
      </Stack>

      {/* Per-effect rows */}
      <Typography sx={{ fontSize: 9, color: 'text.disabled', mb: 0.75, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Effect frequency · avg intensity
      </Typography>
      <Stack gap={0.5}>
        {stats.map(({ name, count, avg }, i) => (
          <Box key={name}>
            <Stack direction="row" alignItems="center" gap={0.75} sx={{ mb: '3px' }}>
              <Typography sx={{
                fontSize: 9, color: 'rgba(255,255,255,0.55)',
                fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
                width: 22, textAlign: 'right', flexShrink: 0,
              }}>
                #{i + 1}
              </Typography>
              <Typography sx={{
                fontSize: 10, color: 'text.primary', flex: 1, minWidth: 0,
                fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {name}
              </Typography>
              <Typography sx={{ fontSize: 9, color: '#f87171', flexShrink: 0, fontFamily: 'monospace' }}>
                {Math.round(avg * 100)}%
              </Typography>
              <Typography sx={{ fontSize: 9, color: 'rgba(239,68,68,0.7)', flexShrink: 0, fontFamily: 'monospace', width: 28, textAlign: 'right' }}>
                ×{count}
              </Typography>
            </Stack>
            {/* Frequency bar */}
            <Box sx={{ ml: '30px', height: 4, bgcolor: 'rgba(255,255,255,0.06)', borderRadius: 1, overflow: 'hidden' }}>
              <Box sx={{
                height: '100%', borderRadius: 1,
                width: `${(count / maxCount) * 100}%`,
                bgcolor: `rgba(248,113,113,${0.3 + (count / maxCount) * 0.7})`,
              }} />
            </Box>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

// ── Main ReportsTab ───────────────────────────────────────────────────────────
export default function ReportsTab() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [view,    setView]    = useState('list'); // 'list' | 'summary'

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

  const handleClearAll = useCallback(async () => {
    try {
      const res = await fetch('/api/flag-reports-clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) setReports([]);
    } catch (_) {}
  }, []);

  const handleDownload = useCallback(() => {
    const blob = new Blob([JSON.stringify({ reports }, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'unrealistic_reports.json'; a.click();
    URL.revokeObjectURL(url);
  }, [reports]);

  // Group reports by symbol for list view
  const bySymbol = useMemo(() => {
    const map = new Map();
    for (const r of reports) {
      const key = r.symbol || '';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(r);
    }
    return [...map.entries()];
  }, [reports]);

  const iconBtnSx = { color: 'text.disabled', '&:hover': { color: 'text.secondary' }, p: '3px' };
  const viewBtnSx = (active) => ({
    p: '3px', borderRadius: '5px',
    color: active ? '#f87171' : 'text.disabled',
    bgcolor: active ? 'rgba(239,68,68,0.12)' : 'transparent',
    '&:hover': { color: active ? '#f87171' : 'text.secondary' },
  });

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Stack
        direction="row" alignItems="center" gap={0.5}
        sx={{ px: 1.25, py: 0.75, borderBottom: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}
      >
        <FlagIcon sx={{ fontSize: 13, color: '#ef4444' }} />
        <Typography sx={{ fontSize: 11, color: '#ef4444', fontWeight: 600, flex: 1 }}>
          Flagged Effects
          {reports.length > 0 && (
            <span style={{ color: 'rgba(239,68,68,0.55)', marginLeft: 5, fontWeight: 400 }}>
              {reports.length}
            </span>
          )}
        </Typography>

        {/* View toggle */}
        <Tooltip title="List view" disableInteractive>
          <IconButton size="small" onClick={() => setView('list')} sx={viewBtnSx(view === 'list')}>
            <ListIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Summary" disableInteractive>
          <IconButton size="small" onClick={() => setView('summary')} sx={viewBtnSx(view === 'summary')}>
            <BarChartIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>

        <Box sx={{ width: 1, height: 16, bgcolor: 'rgba(255,255,255,0.08)', mx: 0.25 }} />

        {reports.length > 0 && (
          <Tooltip title="Clear all" disableInteractive>
            <IconButton size="small" onClick={handleClearAll}
              sx={{ ...iconBtnSx, color: 'rgba(239,68,68,0.5)', '&:hover': { color: '#ef4444' } }}>
              <DeleteOutlineIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Download JSON" disableInteractive>
          <span>
            <IconButton size="small" onClick={handleDownload} disabled={reports.length === 0} sx={iconBtnSx}>
              <DownloadIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh" disableInteractive>
          <IconButton size="small" onClick={fetchReports} sx={iconBtnSx}>
            <RefreshIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>
        {error && <Alert severity="error" sx={{ py: 0, fontSize: 11, mb: 1 }}>{error}</Alert>}

        {!loading && reports.length === 0 && !error && (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 1 }}>
            <FlagIcon sx={{ fontSize: 32, color: 'rgba(239,68,68,0.18)' }} />
            <Typography sx={{ fontSize: 11, color: 'text.disabled', textAlign: 'center' }}>
              No flagged effects yet.<br />
              Use "Flag as unrealistic" in the image preview.
            </Typography>
          </Box>
        )}

        {view === 'summary' && reports.length > 0 && (
          <SummaryView reports={reports} />
        )}

        {view === 'list' && bySymbol.map(([symbol, reps]) => (
          <SymbolGroup
            key={symbol}
            symbol={symbol}
            reports={reps}
            onDelete={handleDelete}
          />
        ))}
      </Box>
    </Box>
  );
}
