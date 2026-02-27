import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Box, Typography, Button, Stack, Switch, FormControlLabel,
  LinearProgress, Tooltip, IconButton, Chip,
} from '@mui/material';
import CloudSyncIcon    from '@mui/icons-material/CloudSync';
import CancelIcon       from '@mui/icons-material/Cancel';
import RefreshIcon      from '@mui/icons-material/Refresh';
import FolderIcon       from '@mui/icons-material/Folder';
import AutorenewIcon    from '@mui/icons-material/Autorenew';

// ── Per-category config ───────────────────────────────────────────────────────

const CATEGORIES = [
  {
    id:      'input',
    label:   'INPUT',
    sub:     'raw SVG sources',
    color:   '#00bcd4',
    dimColor:'rgba(0,188,212,0.15)',
  },
  {
    id:      'processed',
    label:   'PROCESSED',
    sub:     'classified symbols + JSON',
    color:   '#818cf8',
    dimColor:'rgba(129,140,248,0.15)',
  },
  {
    id:      'augmented',
    label:   'AUGMENTED',
    sub:     'generated PNG images',
    color:   '#f59e0b',
    dimColor:'rgba(245,158,11,0.15)',
  },
];

// ── Utility ───────────────────────────────────────────────────────────────────

function relativeTime(iso) {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)       return `${diff}s ago`;
  if (diff < 3600)     return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)    return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString();
}

// ── SSE reader ────────────────────────────────────────────────────────────────

async function* readSSE(response) {
  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith('data: ')) {
          yield JSON.parse(line.slice(6));
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Connection status dot ──────────────────────────────────────────────────────

function StatusDot({ connected, loading }) {
  const color = loading ? '#64748b' : connected ? '#22c55e' : '#ef4444';
  return (
    <Box sx={{ position: 'relative', width: 8, height: 8, flexShrink: 0 }}>
      <Box sx={{
        width: 8, height: 8, borderRadius: '50%', bgcolor: color,
        position: 'absolute', top: 0, left: 0,
      }} />
      {connected && !loading && (
        <Box sx={{
          width: 8, height: 8, borderRadius: '50%', bgcolor: color,
          position: 'absolute', top: 0, left: 0,
          opacity: 0,
          animation: 'gcs-pulse 2.4s ease-out infinite',
          '@keyframes gcs-pulse': {
            '0%':   { transform: 'scale(1)',   opacity: 0.9 },
            '100%': { transform: 'scale(2.8)', opacity: 0 },
          },
        }} />
      )}
    </Box>
  );
}

// ── Stat chip ──────────────────────────────────────────────────────────────────

function StatChip({ icon, value, color, title }) {
  return (
    <Tooltip title={title} placement="top" disableInteractive>
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: '3px',
        bgcolor: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '5px', px: '5px', py: '2px',
        cursor: 'default',
      }}>
        <Typography sx={{
          fontSize: 9, color, fontFamily: '"JetBrains Mono", monospace',
          lineHeight: 1,
        }}>
          {icon}
        </Typography>
        <Typography sx={{
          fontSize: 10, color: 'text.primary',
          fontFamily: '"JetBrains Mono", monospace',
          lineHeight: 1,
        }}>
          {fmt(value)}
        </Typography>
      </Box>
    </Tooltip>
  );
}

// ── Category card ──────────────────────────────────────────────────────────────

function CategoryCard({ cat, syncing, progress, result, lastSync, deleteOrphans, onToggleOrphans, onSync, onCancel }) {
  const isSyncing = syncing === cat.id;
  const pct = progress && progress.total > 0
    ? Math.round((progress.done / progress.total) * 100)
    : 0;

  return (
    <Box sx={{
      borderLeft: `2px solid ${cat.color}`,
      bgcolor: isSyncing ? cat.dimColor : 'rgba(255,255,255,0.02)',
      borderRadius: '0 6px 6px 0',
      p: '8px 10px 8px 10px',
      transition: 'background 0.2s ease',
    }}>
      {/* Header row */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" alignItems="center" gap={0.75}>
          <FolderIcon sx={{ fontSize: 11, color: cat.color, opacity: 0.85 }} />
          <Typography sx={{
            fontSize: 10, fontWeight: 800, letterSpacing: '0.1em',
            color: cat.color, fontFamily: '"JetBrains Mono", monospace',
          }}>
            {cat.label}
          </Typography>
          <Typography sx={{ fontSize: 9, color: 'text.disabled' }}>
            {cat.sub}
          </Typography>
        </Stack>

        {isSyncing ? (
          <Button
            size="small"
            startIcon={<CancelIcon sx={{ fontSize: 11 }} />}
            onClick={onCancel}
            sx={{
              fontSize: 9, py: '2px', px: '7px', minWidth: 0,
              color: '#ef4444', borderColor: 'rgba(239,68,68,0.4)',
              '&:hover': { borderColor: '#ef4444', bgcolor: 'rgba(239,68,68,0.06)' },
            }}
            variant="outlined"
          >
            Cancel
          </Button>
        ) : (
          <Button
            size="small"
            startIcon={<CloudSyncIcon sx={{ fontSize: 11 }} />}
            onClick={onSync}
            disabled={!!syncing}
            sx={{
              fontSize: 9, py: '2px', px: '7px', minWidth: 0,
              color: cat.color,
              borderColor: `${cat.color}55`,
              '&:hover': { borderColor: cat.color, bgcolor: `${cat.color}0d` },
              '&.Mui-disabled': { opacity: 0.35 },
            }}
            variant="outlined"
          >
            Sync
          </Button>
        )}
      </Stack>

      {/* Progress bar when syncing */}
      {isSyncing && (
        <Box sx={{ mb: 0.75 }}>
          <LinearProgress
            variant={progress ? 'determinate' : 'indeterminate'}
            value={pct}
            sx={{
              height: 3, borderRadius: 2,
              bgcolor: 'rgba(255,255,255,0.06)',
              '& .MuiLinearProgress-bar': { bgcolor: cat.color, borderRadius: 2 },
            }}
          />
          {progress && (
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: '3px' }}>
              <Typography sx={{
                fontSize: 9, color: 'text.disabled',
                fontFamily: '"JetBrains Mono", monospace',
                flex: 1, minWidth: 0,
              }} noWrap>
                {progress.file?.split('/').slice(-1)[0]}
              </Typography>
              <Typography sx={{
                fontSize: 9, color: cat.color, flexShrink: 0, ml: 1,
                fontFamily: '"JetBrains Mono", monospace',
              }}>
                {fmt(progress.done)}/{fmt(progress.total)}
              </Typography>
            </Stack>
          )}
        </Box>
      )}

      {/* Last sync result chips */}
      {result && !isSyncing && (
        <Stack direction="row" alignItems="center" gap={0.5} sx={{ mb: 0.5, flexWrap: 'wrap' }}>
          {result.uploaded > 0 && (
            <StatChip icon="↑" value={result.uploaded} color="#22c55e" title="Uploaded" />
          )}
          {result.skipped > 0 && (
            <StatChip icon="─" value={result.skipped} color="text.disabled" title="Unchanged / skipped" />
          )}
          {result.deleted > 0 && (
            <StatChip icon="✕" value={result.deleted} color="#f87171" title="Deleted from GCS" />
          )}
          {result.errors > 0 && (
            <StatChip icon="!" value={result.errors} color="#fb923c" title="Errors" />
          )}
          {result.cancelled && (
            <Typography sx={{ fontSize: 9, color: '#fb923c', fontFamily: '"JetBrains Mono", monospace' }}>
              cancelled
            </Typography>
          )}
        </Stack>
      )}

      {/* Last sync timestamp + orphan toggle */}
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography sx={{ fontSize: 9, color: 'text.disabled', fontFamily: '"JetBrains Mono", monospace' }}>
          {lastSync ? relativeTime(lastSync) : 'never synced'}
        </Typography>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={deleteOrphans}
              onChange={e => onToggleOrphans(e.target.checked)}
              sx={{
                '& .MuiSwitch-switchBase.Mui-checked': { color: '#ef4444' },
                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { bgcolor: '#ef4444' },
              }}
            />
          }
          label={
            <Typography sx={{ fontSize: 8.5, color: deleteOrphans ? '#f87171' : 'text.disabled', letterSpacing: '0.04em' }}>
              del orphans
            </Typography>
          }
          sx={{ m: 0, gap: 0 }}
          labelPlacement="start"
        />
      </Stack>
    </Box>
  );
}

// ── Error display ──────────────────────────────────────────────────────────────

function SyncError({ category, message, onDismiss }) {
  return (
    <Box sx={{
      bgcolor: 'rgba(239,68,68,0.06)',
      border: '1px solid rgba(239,68,68,0.2)',
      borderRadius: '6px',
      px: 1.25, py: 0.75,
    }}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" gap={0.5}>
        <Box>
          <Typography sx={{ fontSize: 9, color: '#ef4444', fontWeight: 700, fontFamily: '"JetBrains Mono", monospace', textTransform: 'uppercase', mb: '2px' }}>
            {category} sync error
          </Typography>
          <Typography sx={{ fontSize: 10, color: '#fca5a5', fontFamily: '"JetBrains Mono", monospace', wordBreak: 'break-all' }}>
            {message}
          </Typography>
        </Box>
        <IconButton size="small" onClick={onDismiss} sx={{ color: 'text.disabled', flexShrink: 0, p: '2px' }}>
          <CancelIcon sx={{ fontSize: 12 }} />
        </IconButton>
      </Stack>
    </Box>
  );
}

// ── Main CloudTab ──────────────────────────────────────────────────────────────

export default function CloudTab() {
  const [gcsStatus,     setGcsStatus]     = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [syncing,       setSyncing]       = useState(null);  // category id | null
  const [errors,        setErrors]        = useState({});    // {categoryId: message}

  const [progress, setProgress] = useState({
    input: null, processed: null, augmented: null,
  });
  const [results, setResults] = useState({
    input: null, processed: null, augmented: null,
  });
  const [lastSync, setLastSync] = useState({
    input: null, processed: null, augmented: null,
  });
  const [deleteOrphans, setDeleteOrphans] = useState({
    input: false, processed: false, augmented: false,
  });

  const readerRef = useRef(null);

  // Fetch connection status on mount
  useEffect(() => { fetchStatus(); }, []);

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const res  = await fetch('/api/gcs/status');
      const data = await res.json();
      setGcsStatus(data);
    } catch (e) {
      setGcsStatus({ connected: false, error: e.message });
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const handleSync = useCallback(async (categoryId) => {
    setSyncing(categoryId);
    setErrors(prev => ({ ...prev, [categoryId]: null }));
    setProgress(prev => ({ ...prev, [categoryId]: null }));
    setResults(prev => ({ ...prev, [categoryId]: null }));

    try {
      const res = await fetch('/api/gcs/sync', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          category:       categoryId,
          delete_orphans: deleteOrphans[categoryId],
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        setErrors(prev => ({ ...prev, [categoryId]: text }));
        return;
      }

      for await (const event of readSSE(res)) {
        if (event.type === 'start') {
          setProgress(prev => ({ ...prev, [categoryId]: { done: 0, total: event.total, file: '' } }));
        } else if (event.type === 'progress') {
          setProgress(prev => ({ ...prev, [categoryId]: { done: event.done, total: event.total, file: event.file } }));
        } else if (event.type === 'done' || event.type === 'cancelled') {
          setResults(prev => ({ ...prev, [categoryId]: { ...event, cancelled: event.type === 'cancelled' } }));
          setLastSync(prev => ({ ...prev, [categoryId]: new Date().toISOString() }));
          setProgress(prev => ({ ...prev, [categoryId]: null }));
        } else if (event.type === 'error') {
          setErrors(prev => ({ ...prev, [categoryId]: event.message }));
          setProgress(prev => ({ ...prev, [categoryId]: null }));
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        setErrors(prev => ({ ...prev, [categoryId]: e.message }));
        setProgress(prev => ({ ...prev, [categoryId]: null }));
      }
    } finally {
      setSyncing(null);
    }
  }, [deleteOrphans]);

  const handleCancel = useCallback(async () => {
    try { await fetch('/api/gcs/sync-cancel', { method: 'POST' }); } catch (_) {}
  }, []);

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>

        {/* ── Connection status bar ─────────────────────────────────────── */}
        <Box sx={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          bgcolor: 'rgba(255,255,255,0.025)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '7px',
          px: 1.25, py: 0.75,
          mb: 1.25,
        }}>
          <Stack direction="row" alignItems="center" gap={1}>
            <StatusDot connected={gcsStatus?.connected} loading={statusLoading} />
            <Box>
              {gcsStatus?.connected ? (
                <>
                  <Typography sx={{ fontSize: 10, fontWeight: 700, color: '#22c55e', fontFamily: '"JetBrains Mono", monospace', lineHeight: 1 }}>
                    CONNECTED
                  </Typography>
                  <Typography sx={{ fontSize: 9, color: 'text.disabled', fontFamily: '"JetBrains Mono", monospace', mt: '2px' }}>
                    {gcsStatus.bucket}
                    {gcsStatus.location && ` · ${gcsStatus.location}`}
                  </Typography>
                </>
              ) : gcsStatus ? (
                <>
                  <Typography sx={{ fontSize: 10, fontWeight: 700, color: '#ef4444', fontFamily: '"JetBrains Mono", monospace', lineHeight: 1 }}>
                    DISCONNECTED
                  </Typography>
                  <Typography sx={{ fontSize: 9, color: '#fca5a5', fontFamily: '"JetBrains Mono", monospace', mt: '2px' }} noWrap>
                    {gcsStatus.error}
                  </Typography>
                </>
              ) : (
                <Typography sx={{ fontSize: 10, color: 'text.disabled', fontFamily: '"JetBrains Mono", monospace' }}>
                  {statusLoading ? 'Checking…' : 'Not checked'}
                </Typography>
              )}
            </Box>
          </Stack>

          <Tooltip title="Refresh connection" placement="left">
            <IconButton
              size="small"
              onClick={fetchStatus}
              disabled={statusLoading}
              sx={{ color: 'text.disabled', '&:hover': { color: 'text.primary' }, p: '4px' }}
            >
              <RefreshIcon sx={{
                fontSize: 14,
                animation: statusLoading ? 'spin 1s linear infinite' : 'none',
                '@keyframes spin': { '100%': { transform: 'rotate(360deg)' } },
              }} />
            </IconButton>
          </Tooltip>
        </Box>

        {/* ── Section label ────────────────────────────────────────────── */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
          <Box sx={{ width: 2, height: 10, borderRadius: 1, bgcolor: 'primary.main', flexShrink: 0 }} />
          <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'text.disabled' }}>
            Sync Buckets
          </Typography>
          {syncing && (
            <AutorenewIcon sx={{
              fontSize: 11, color: 'primary.main', ml: 0.25,
              animation: 'spin 1s linear infinite',
              '@keyframes spin': { '100%': { transform: 'rotate(360deg)' } },
            }} />
          )}
        </Box>

        {/* ── Category cards ───────────────────────────────────────────── */}
        <Stack gap={0.75}>
          {CATEGORIES.map(cat => (
            <Box key={cat.id}>
              <CategoryCard
                cat={cat}
                syncing={syncing}
                progress={progress[cat.id]}
                result={results[cat.id]}
                lastSync={lastSync[cat.id]}
                deleteOrphans={deleteOrphans[cat.id]}
                onToggleOrphans={v => setDeleteOrphans(prev => ({ ...prev, [cat.id]: v }))}
                onSync={() => handleSync(cat.id)}
                onCancel={handleCancel}
              />
              {errors[cat.id] && (
                <Box sx={{ mt: 0.5 }}>
                  <SyncError
                    category={cat.id}
                    message={errors[cat.id]}
                    onDismiss={() => setErrors(prev => ({ ...prev, [cat.id]: null }))}
                  />
                </Box>
              )}
            </Box>
          ))}
        </Stack>

        {/* ── ADC hint ─────────────────────────────────────────────────── */}
        <Box sx={{
          mt: 1.5,
          p: '8px 10px',
          bgcolor: 'rgba(255,255,255,0.015)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '6px',
        }}>
          <Typography sx={{ fontSize: 9, color: 'text.disabled', fontFamily: '"JetBrains Mono", monospace', lineHeight: 1.7 }}>
            Auth: Application Default Credentials (ADC)<br />
            Bucket: <Box component="span" sx={{ color: 'text.secondary' }}>GCS_BUCKET_NAME</Box> env var<br />
            Default: pid_automation_labs
          </Typography>
        </Box>

      </Box>
    </Box>
  );
}
