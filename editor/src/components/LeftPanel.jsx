import { useMemo, useState, useEffect } from 'react';
import {
  Box, Typography, TextField, Select, MenuItem, FormControl,
  LinearProgress, List, ListItemButton, ListItemText, Tooltip,
  InputLabel, InputAdornment,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import SearchIcon from '@mui/icons-material/Search';
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

  return (
    <Box sx={{
      width: 248,
      borderRight: '1px solid rgba(255,255,255,0.07)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      overflow: 'hidden',
      bgcolor: 'background.paper',
    }}>
      {/* Header */}
      <Box sx={{
        px: 1.5, pt: 1.25, pb: 1,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        flexShrink: 0,
      }}>
        {/* Title row */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Typography sx={{ fontSize: '0.8rem', fontWeight: 700, color: 'text.primary', lineHeight: 1 }}>
            Symbol Studio
          </Typography>
          <Box sx={{
            px: 0.75, py: 0.2,
            bgcolor: 'rgba(129,140,248,0.15)',
            borderRadius: '999px',
            border: '1px solid rgba(129,140,248,0.25)',
          }}>
            <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: 'primary.main', lineHeight: 1 }}>
              {visible.length}
            </Typography>
          </Box>
        </Box>

        {/* Search field */}
        <TextField
          fullWidth
          size="small"
          placeholder="Search symbols…"
          value={filterText}
          onChange={e => setFilter('filterText', e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon sx={{ fontSize: 15, color: 'text.disabled' }} />
              </InputAdornment>
            ),
            style: { fontSize: 12 },
          }}
        />
      </Box>

      {/* Stats */}
      <Box sx={{ px: 1.5, py: 0.75, borderBottom: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
          <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'text.disabled' }}>
            Progress
          </Typography>
          <Typography sx={{ fontSize: '0.65rem', color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
            <Box component="span" sx={{ color: 'success.main', fontWeight: 600 }}>{done}</Box>
            <Box component="span" sx={{ color: 'text.disabled' }}> / {visible.length}</Box>
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={pct}
          sx={{
            '& .MuiLinearProgress-bar': { bgcolor: 'success.main' },
          }}
        />
      </Box>

      {/* Filters — side by side */}
      <Box sx={{
        px: 1.5, py: 0.75,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        flexShrink: 0,
        display: 'flex',
        gap: 0.75,
      }}>
        <FormControl size="small" sx={{ flex: 1, minWidth: 0 }}>
          <Select
            displayEmpty
            value={filterSource}
            onChange={e => setFilter('filterSource', e.target.value)}
            sx={{ fontSize: 11 }}
          >
            <MenuItem value=""><em style={{ fontSize: 11 }}>All origins</em></MenuItem>
            {sources.map(s => (
              <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ flex: 1, minWidth: 0 }}>
          <Select
            displayEmpty
            value={filterStandard}
            onChange={e => setFilter('filterStandard', e.target.value)}
            sx={{ fontSize: 11 }}
          >
            <MenuItem value=""><em style={{ fontSize: 11 }}>All standards</em></MenuItem>
            {standards.map(s => (
              <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* Symbol list */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 0.5, py: 0.5 }}>
        {[...grouped.entries()].map(([std, syms]) => (
          <Box key={std}>
            {/* Group header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, px: 1, pt: 1.25, pb: 0.4 }}>
              <Box sx={{ width: 2, height: 8, borderRadius: 1, bgcolor: 'primary.main', flexShrink: 0, opacity: 0.6 }} />
              <Typography sx={{
                fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em',
                textTransform: 'uppercase', color: 'text.disabled',
              }}>
                {std}
              </Typography>
              <Typography sx={{ fontSize: '0.6rem', color: 'text.disabled', ml: 'auto', flexShrink: 0 }}>
                ({syms.length})
              </Typography>
            </Box>

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
                    sx={{
                      py: 0.3,
                      pl: 1.25,
                      pr: 0.5,
                      transition: 'background 0.12s ease',
                    }}
                  >
                    {sym.completed && (
                      <CheckCircleIcon sx={{ fontSize: 10, color: 'success.main', mr: 0.6, flexShrink: 0 }} />
                    )}
                    <ListItemText
                      primary={sym.name}
                      secondary={sym.category || undefined}
                      primaryTypographyProps={{
                        fontSize: 12,
                        fontWeight: sym.path === currentPath ? 600 : 400,
                        color: sym.completed ? 'success.light' : 'text.primary',
                        noWrap: true,
                      }}
                      secondaryTypographyProps={{
                        fontSize: 9.5,
                        color: 'text.disabled',
                        noWrap: true,
                        sx: { lineHeight: 1.3 },
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
        flexShrink: 0,
        borderTop: '1px solid rgba(129,140,248,0.3)',
        bgcolor: 'rgba(255,255,255,0.015)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 120,
        p: 0.75,
        gap: 0.5,
      }}>
        {hover ? (
          <SymbolPreview path={hover} />
        ) : (
          <Typography sx={{ fontSize: 10, color: 'text.disabled' }}>Hover to preview</Typography>
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

  if (!src) return <Typography sx={{ fontSize: 10, color: 'text.disabled' }}>Loading…</Typography>;
  return (
    <>
      <Box
        component="img"
        src={src}
        alt={name}
        sx={{
          maxWidth: 210,
          maxHeight: 94,
          objectFit: 'contain',
          bgcolor: 'white',
          borderRadius: '6px',
          p: 0.25,
          boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
        }}
      />
      <Typography sx={{ fontSize: 9, color: 'text.disabled', textAlign: 'center', maxWidth: 210 }} noWrap>
        {name}
      </Typography>
    </>
  );
}
