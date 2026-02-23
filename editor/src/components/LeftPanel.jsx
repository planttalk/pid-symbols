import { useMemo, useState, useEffect } from 'react';
import {
  Box, Typography, TextField, Select, MenuItem, FormControl,
  LinearProgress, List, ListItemButton, ListItemText, Tooltip,
  InputLabel,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useEditorStore } from '../store';

export default function LeftPanel() {
  const {
    allSymbols, filterSource, filterStandard, filterText, currentPath,
    loadSymbol, setFilter,
  } = useEditorStore();

  const [hover, setHover] = useState(null);

  // Derive unique sources + standards for filter dropdowns
  const sources   = useMemo(() => [...new Set(allSymbols.map(s => s.source).filter(Boolean))].sort(), [allSymbols]);
  const standards = useMemo(() => [...new Set(allSymbols.map(s => s.standard).filter(Boolean))].sort(), [allSymbols]);

  // Filter
  const visible = useMemo(() => {
    const q = filterText.toLowerCase();
    return allSymbols.filter(s => {
      if (filterSource   && s.source   !== filterSource)   return false;
      if (filterStandard && s.standard !== filterStandard) return false;
      if (q && !s.name.toLowerCase().includes(q) && !s.path.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allSymbols, filterSource, filterStandard, filterText]);

  // Stats for filtered list
  const done = visible.filter(s => s.completed).length;
  const pct  = visible.length ? Math.round(done / visible.length * 100) : 0;

  // Group by standard
  const grouped = useMemo(() => {
    const map = new Map();
    for (const s of visible) {
      const key = s.standard || 'unknown';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    }
    return map;
  }, [visible]);

  // Preview symbol (hovered)
  const previewSym = hover ? allSymbols.find(s => s.path === hover) : null;
  const previewSrc = previewSym
    ? `/api/symbol?path=${encodeURIComponent(previewSym.path)}`
    : null;

  return (
    <Box sx={{
      width: 240,
      borderRight: '1px solid #444',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <Box sx={{ p: '8px', borderBottom: '1px solid #444', flexShrink: 0 }}>
        <Typography variant="h6" sx={{ mb: 0.5 }}>Symbols</Typography>
        <TextField
          fullWidth size="small" placeholder="Filter…"
          value={filterText}
          onChange={e => setFilter('filterText', e.target.value)}
          inputProps={{ style: { fontSize: 11 } }}
        />
      </Box>

      {/* Stats */}
      <Box sx={{ px: 1, py: 0.5, borderBottom: '1px solid #333', flexShrink: 0 }}>
        <Typography sx={{ fontSize: 10, color: 'text.secondary', mb: 0.3 }}>
          {done} / {visible.length} complete ({pct}%)
        </Typography>
        <LinearProgress
          variant="determinate" value={pct}
          sx={{ height: 3, borderRadius: 1, bgcolor: '#3c3c3c',
                '& .MuiLinearProgress-bar': { bgcolor: 'success.main' } }}
        />
      </Box>

      {/* Filters */}
      <Box sx={{ px: 1, py: 0.5, borderBottom: '1px solid #333', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <FormControl fullWidth size="small">
          <Select
            displayEmpty value={filterSource}
            onChange={e => setFilter('filterSource', e.target.value)}
            sx={{ fontSize: 11 }}
          >
            <MenuItem value=""><em>All origins</em></MenuItem>
            {sources.map(s => <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl fullWidth size="small">
          <Select
            displayEmpty value={filterStandard}
            onChange={e => setFilter('filterStandard', e.target.value)}
            sx={{ fontSize: 11 }}
          >
            <MenuItem value=""><em>All standards</em></MenuItem>
            {standards.map(s => <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>)}
          </Select>
        </FormControl>
      </Box>

      {/* Symbol list */}
      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {[...grouped.entries()].map(([std, syms]) => (
          <Box key={std}>
            <Typography sx={{
              fontSize: 9, color: 'text.disabled', px: 1, pt: 1, pb: 0.25,
              textTransform: 'uppercase', letterSpacing: '0.8px',
            }}>
              {std}
            </Typography>
            <List dense disablePadding>
              {syms.map(sym => (
                <Tooltip
                  key={sym.path}
                  title={sym.path}
                  placement="right"
                  arrow
                  enterDelay={600}
                >
                  <ListItemButton
                    selected={sym.path === currentPath}
                    onClick={() => loadSymbol(sym.path)}
                    onMouseEnter={() => setHover(sym.path)}
                    onMouseLeave={() => setHover(null)}
                    sx={{ py: 0.25, pl: 1.5, pr: 0.5 }}
                  >
                    {sym.completed && (
                      <CheckCircleIcon sx={{ fontSize: 10, color: 'success.main', mr: 0.5, flexShrink: 0 }} />
                    )}
                    <ListItemText
                      primary={sym.name}
                      primaryTypographyProps={{
                        fontSize: 12,
                        color: sym.completed ? 'success.light' : 'text.primary',
                        noWrap: true,
                      }}
                    />
                  </ListItemButton>
                </Tooltip>
              ))}
            </List>
          </Box>
        ))}
      </Box>

      {/* SVG preview on hover */}
      <Box sx={{
        flexShrink: 0, borderTop: '1px solid #444', bgcolor: '#252525',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', minHeight: 110, p: 0.5, gap: 0.5,
      }}>
        {hover ? (
          <SymbolPreview path={hover} />
        ) : (
          <Typography sx={{ fontSize: 10, color: '#555' }}>Hover to preview</Typography>
        )}
      </Box>
    </Box>
  );
}

function SymbolPreview({ path }) {
  const [src, setSrc] = useState(null);
  const [name, setName] = useState('');

  useEffect(() => {
    let cancelled = false;
    setSrc(null);
    fetch(`/api/symbol?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const uri = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(data.svg)));
        setSrc(uri);
        setName(data.meta?.display_name || path.split('/').pop());
      })
      .catch(() => { if (!cancelled) setSrc(null); });
    return () => { cancelled = true; };
  }, [path]);

  if (!src) return <Typography sx={{ fontSize: 10, color: '#555' }}>Loading…</Typography>;
  return (
    <>
      <Box component="img" src={src} alt={name}
        sx={{ maxWidth: 200, maxHeight: 90, objectFit: 'contain', bgcolor: 'white', borderRadius: 0.5, p: 0.25 }} />
      <Typography sx={{ fontSize: 9, color: 'text.disabled', textAlign: 'center', maxWidth: 200 }} noWrap>
        {name}
      </Typography>
    </>
  );
}
