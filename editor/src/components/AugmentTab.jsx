import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Box, Typography, Button, Slider, Checkbox, FormControlLabel,
  TextField, Stack, Accordion, AccordionSummary, AccordionDetails,
  Alert, CircularProgress, Switch, ImageList, ImageListItem,
  ImageListItemBar, Divider, IconButton, Modal,
  Select, MenuItem, FormControl, LinearProgress,
} from '@mui/material';
import ExpandMoreIcon       from '@mui/icons-material/ExpandMore';
import ShuffleIcon          from '@mui/icons-material/Shuffle';
import VisibilityIcon       from '@mui/icons-material/Visibility';
import SaveIcon             from '@mui/icons-material/Save';
import ChevronLeftIcon      from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon     from '@mui/icons-material/ChevronRight';
import CloseIcon            from '@mui/icons-material/Close';
import { useEditorStore } from '../store';
import { EFFECT_GROUPS, ALL_EFFECT_NAMES } from '../constants';

const PAGE_SIZE = 20;

// Adaptive column count based on total image count
function gridCols(n) {
  if (n === 1)  return 1;
  if (n <= 4)   return 2;
  if (n <= 9)   return 3;
  if (n <= 16)  return 4;
  return 5;
}

// ── Single effect row ─────────────────────────────────────────────────────────
function EffectRow({ name, label, value, onChange, onToggle, enabled }) {
  return (
    <Stack direction="row" alignItems="center" gap={0.5} sx={{ py: 0.25 }}>
      <Checkbox
        size="small" checked={enabled}
        onChange={e => onToggle(name, e.target.checked)}
        sx={{ p: 0.25 }}
      />
      <Typography sx={{ fontSize: 11, flex: '0 0 110px', cursor: 'pointer' }} onClick={() => onToggle(name, !enabled)}>
        {label}
      </Typography>
      <Slider
        size="small" min={0} max={1} step={0.01}
        value={enabled ? value : 0}
        disabled={!enabled}
        onChange={(_, v) => onChange(name, v)}
        sx={{ flex: 1, mx: 0.5 }}
      />
      <Typography sx={{ fontSize: 10, color: 'text.secondary', width: 28, textAlign: 'right', fontFamily: 'monospace' }}>
        {enabled ? value.toFixed(2) : '—'}
      </Typography>
    </Stack>
  );
}

// ── Effect group (Accordion) ───────────────────────────────────────────────────
function EffectGroup({ group, augEffects, onChange, onToggle }) {
  const activeCount = group.effects.filter(e => augEffects[e.name] !== undefined).length;
  return (
    <Accordion disableGutters defaultExpanded={false}>
      <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ fontSize: 14 }} />}>
        <Typography sx={{ fontSize: 11, color: 'secondary.main' }}>{group.label}</Typography>
        {activeCount > 0 && (
          <Typography sx={{ fontSize: 10, color: 'success.main', ml: 1 }}>({activeCount})</Typography>
        )}
      </AccordionSummary>
      <AccordionDetails>
        {group.effects.map(eff => (
          <EffectRow
            key={eff.name}
            name={eff.name}
            label={eff.label}
            enabled={augEffects[eff.name] !== undefined}
            value={augEffects[eff.name] ?? 0.5}
            onChange={onChange}
            onToggle={onToggle}
          />
        ))}
      </AccordionDetails>
    </Accordion>
  );
}

// ── Lightbox modal ────────────────────────────────────────────────────────────
function Lightbox({ images, idx, onClose, onGoto }) {
  const img = images[idx];

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape')      { e.stopPropagation(); onClose(); }
      if (e.key === 'ArrowLeft'  && idx > 0)                  onGoto(idx - 1);
      if (e.key === 'ArrowRight' && idx < images.length - 1)  onGoto(idx + 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [idx, images.length, onClose, onGoto]);

  if (!img) return null;

  return (
    <Modal open onClose={onClose}>
      {/* Backdrop — click outside image to close */}
      <Box
        onClick={onClose}
        sx={{
          position: 'fixed', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          bgcolor: 'rgba(0,0,0,0.88)',
          outline: 'none',
        }}
      >
        {/* Inner card — stop propagation so clicking image doesn't close */}
        <Box
          onClick={e => e.stopPropagation()}
          sx={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', maxWidth: '92vw' }}
        >
          {/* Close button */}
          <IconButton
            onClick={onClose}
            size="small"
            sx={{ position: 'absolute', top: -36, right: 0, color: 'white', bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.18)' } }}
          >
            <CloseIcon sx={{ fontSize: 18 }} />
          </IconButton>

          {/* Image */}
          <Box
            component="img"
            src={img.src}
            alt={img.label}
            sx={{
              maxWidth: '88vw',
              maxHeight: '80vh',
              objectFit: 'contain',
              bgcolor: 'white',
              borderRadius: 1,
              boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
              display: 'block',
            }}
          />

          {/* Navigation bar */}
          <Stack direction="row" alignItems="center" justifyContent="space-between"
            sx={{ mt: 1.5, width: '100%', px: 0.5 }}>
            <IconButton
              disabled={idx === 0}
              onClick={() => onGoto(idx - 1)}
              sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.18)' }, '&.Mui-disabled': { color: 'rgba(255,255,255,0.2)' } }}
            >
              <ChevronLeftIcon />
            </IconButton>

            <Typography sx={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, fontFamily: 'monospace' }}>
              {img.label} &nbsp;·&nbsp; {idx + 1} / {images.length}
            </Typography>

            <IconButton
              disabled={idx === images.length - 1}
              onClick={() => onGoto(idx + 1)}
              sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.18)' }, '&.Mui-disabled': { color: 'rgba(255,255,255,0.2)' } }}
            >
              <ChevronRightIcon />
            </IconButton>
          </Stack>
        </Box>
      </Box>
    </Modal>
  );
}

// ── Smart grid: adaptive cols + pagination for large sets ─────────────────────
function SmartGrid({ images, label }) {
  const [page,        setPage]        = useState(0);
  const [lightboxIdx, setLightboxIdx] = useState(null);

  // Reset to first page whenever the image set changes
  useEffect(() => { setPage(0); setLightboxIdx(null); }, [images]);

  if (!images.length) return null;

  const n           = images.length;
  const needsPaging = n > PAGE_SIZE;
  const totalPages  = Math.ceil(n / PAGE_SIZE);
  const visible     = images.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const cols        = gridCols(n);

  const openLightbox = (absoluteIdx) => {
    // When navigating via lightbox arrows, sync the grid page if needed
    const targetPage = Math.floor(absoluteIdx / PAGE_SIZE);
    if (targetPage !== page) setPage(targetPage);
    setLightboxIdx(absoluteIdx);
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
          {label} &nbsp;·&nbsp; {n} image{n !== 1 ? 's' : ''}
        </Typography>
        {needsPaging && (
          <Stack direction="row" alignItems="center" gap={0.25}>
            <IconButton
              size="small" disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              <ChevronLeftIcon sx={{ fontSize: 14 }} />
            </IconButton>
            <Typography sx={{ fontSize: 10, color: 'text.secondary', minWidth: 44, textAlign: 'center' }}>
              {page + 1} / {totalPages}
            </Typography>
            <IconButton
              size="small" disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
            >
              <ChevronRightIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Stack>
        )}
      </Stack>

      <ImageList cols={cols} gap={3}>
        {visible.map((img, i) => {
          const absIdx = page * PAGE_SIZE + i;
          return (
            <ImageListItem
              key={absIdx}
              sx={{ cursor: 'zoom-in' }}
              onClick={() => openLightbox(absIdx)}
            >
              <Box
                component="img"
                src={img.src}
                alt={img.label}
                sx={{ width: '100%', aspectRatio: '1', objectFit: 'contain', bgcolor: 'white', borderRadius: 0.5 }}
              />
              <ImageListItemBar
                title={img.label}
                position="below"
                sx={{ '& .MuiImageListItemBar-title': { fontSize: 9, color: 'text.disabled' } }}
              />
            </ImageListItem>
          );
        })}
      </ImageList>

      {lightboxIdx !== null && (
        <Lightbox
          images={images}
          idx={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
          onGoto={openLightbox}
        />
      )}
    </Box>
  );
}

// ── Main AugmentTab ────────────────────────────────────────────────────────────
export default function AugmentTab() {
  const {
    currentPath, augEffects, augSize, augCount, augOutputDir, augRandomizePerImg,
    allSymbols,
    setAugEffect, removeAugEffect, setAugImages,
  } = useEditorStore();

  const [size,       setSize]       = useState(augSize);
  const [count,      setCount]      = useState(augCount);
  const [outDir,     setOutDir]     = useState(augOutputDir);
  const [randPer,    setRandPer]    = useState(augRandomizePerImg);
  const [previewing, setPreviewing] = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [images,     setImages]     = useState([]);
  const [imagesLabel, setImagesLabel] = useState('');
  const [msg,        setMsg]        = useState(null);

  // ── Batch state ──────────────────────────────────────────────────────────────
  const [batchSource,   setBatchSource]   = useState('');
  const [batchStandard, setBatchStandard] = useState('');
  const [batchOutDir,   setBatchOutDir]   = useState('');
  const [batchRunning,  setBatchRunning]  = useState(false);
  const [batchProgress, setBatchProgress] = useState(null); // {current,total,name,saved}
  const [batchResult,   setBatchResult]   = useState(null); // {processed,saved,skipped,errors,...}

  const batchSources   = useMemo(() => [...new Set(allSymbols.map(s => s.source).filter(Boolean))].sort(), [allSymbols]);
  const batchStandards = useMemo(() => [...new Set(allSymbols.map(s => s.standard).filter(Boolean))].sort(), [allSymbols]);
  const batchMatchCount = useMemo(() => allSymbols.filter(s => {
    if (batchSource   && s.source   !== batchSource)   return false;
    if (batchStandard && s.standard !== batchStandard) return false;
    return true;
  }).length, [allSymbols, batchSource, batchStandard]);

  const busy = previewing || saving || batchRunning;

  const handleToggle = useCallback((name, enabled) => {
    if (enabled) setAugEffect(name, 0.5);
    else         removeAugEffect(name);
  }, [setAugEffect, removeAugEffect]);

  const handleChange = useCallback((name, value) => {
    setAugEffect(name, value);
  }, [setAugEffect]);

  const handleRandomize = useCallback(() => {
    const n      = Math.floor(Math.random() * 4) + 3;
    const picked = [...ALL_EFFECT_NAMES].sort(() => Math.random() - 0.5).slice(0, n);
    ALL_EFFECT_NAMES.forEach(name => removeAugEffect(name));
    picked.forEach(name => setAugEffect(name, +(Math.random() * 0.7 + 0.2).toFixed(2)));
  }, [setAugEffect, removeAugEffect]);

  const handlePreview = useCallback(async () => {
    if (!currentPath) return;
    setPreviewing(true);
    setMsg(null);
    setImages([]);
    try {
      const { augEffects: effects } = useEditorStore.getState();
      const res = await fetch('/api/augment-preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path:                currentPath,
          effects,
          size,
          count,
          randomize_per_image: randPer,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const imgs = (data.images || []).map((src, i) => ({ src, label: `#${i + 1}` }));
      setImages(imgs);
      setImagesLabel('Preview (unsaved)');
    } catch (e) {
      setMsg({ err: '✗ Preview: ' + e.message });
    } finally {
      setPreviewing(false);
    }
  }, [currentPath, size, count, randPer]);

  const handleBatch = useCallback(async () => {
    setBatchRunning(true);
    setBatchProgress(null);
    setBatchResult(null);
    try {
      const { augEffects: effects } = useEditorStore.getState();
      const res = await fetch('/api/augment-batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source:              batchSource,
          standard:            batchStandard,
          effects,
          size,
          count,
          output_dir:          batchOutDir || outDir,
          randomize_per_image: randPer,
        }),
      });
      if (!res.ok) throw new Error(await res.text());

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); // keep last incomplete chunk
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === 'progress') {
            setBatchProgress({ current: event.current, total: event.total, name: event.name, saved: event.saved });
          }
          if (event.type === 'done') {
            setBatchResult(event);
          }
        }
      }
    } catch (e) {
      setBatchResult({ error: e.message });
    } finally {
      setBatchRunning(false);
    }
  }, [batchSource, batchStandard, batchOutDir, outDir, size, count, randPer]);

  const handleGenerate = useCallback(async () => {
    if (!currentPath) return;
    setSaving(true);
    setMsg(null);
    setImages([]);
    try {
      const { augEffects: effects } = useEditorStore.getState();
      const res = await fetch('/api/augment-generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path:                currentPath,
          effects,
          count,
          size,
          output_dir:          outDir,
          randomize_per_image: randPer,
          return_images:       true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Generation failed');
      const imgs = (data.images || []).map((src, i) => ({ src, label: `#${i + 1}` }));
      setImages(imgs);
      setAugImages(imgs);
      setImagesLabel(`Saved → ${data.output_dir}`);
      setMsg({ ok: `✓ ${data.saved} image(s) saved to ${data.output_dir}` });
    } catch (e) {
      setMsg({ err: '✗ ' + e.message });
    } finally {
      setSaving(false);
    }
  }, [currentPath, count, size, outDir, randPer, setAugImages]);

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>

        {/* Top actions */}
        <Stack direction="row" gap={0.75} sx={{ mb: 1 }}>
          <Button
            fullWidth
            startIcon={previewing ? <CircularProgress size={12} /> : <VisibilityIcon sx={{ fontSize: 14 }} />}
            onClick={handlePreview}
            disabled={!currentPath || busy}
            sx={{ fontSize: 11, borderColor: '#4ec9b0', color: '#4ec9b0' }}
          >
            {previewing ? 'Previewing…' : `Preview ${count}`}
          </Button>
          <Button
            fullWidth
            startIcon={<ShuffleIcon sx={{ fontSize: 14 }} />}
            onClick={handleRandomize}
            disabled={busy}
            sx={{ fontSize: 11, borderColor: '#cc88ff', color: '#cc88ff' }}
          >
            Randomize
          </Button>
        </Stack>

        <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1 }}>
          <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>Size</Typography>
          <TextField
            type="number" size="small"
            value={size} onChange={e => setSize(+e.target.value || 512)}
            inputProps={{ min: 64, max: 2048, step: 64, style: { width: 64, fontSize: 11 } }}
          />
          <Typography sx={{ fontSize: 10, color: 'text.disabled' }}>px</Typography>
        </Stack>

        {/* Effect groups */}
        {EFFECT_GROUPS.map(group => (
          <EffectGroup
            key={group.label}
            group={group}
            augEffects={augEffects}
            onChange={handleChange}
            onToggle={handleToggle}
          />
        ))}

        <Divider sx={{ my: 1 }} />

        {/* Generate section */}
        <FormControlLabel
          control={<Switch size="small" checked={randPer} onChange={e => setRandPer(e.target.checked)} />}
          label={<Typography sx={{ fontSize: 11 }}>Randomize effects per image</Typography>}
          sx={{ mb: 0.5, ml: 0 }}
        />
        <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 0.75 }}>
          <Typography sx={{ fontSize: 11, color: 'text.secondary', flexShrink: 0 }}>Count</Typography>
          <TextField
            type="number" size="small"
            value={count} onChange={e => setCount(Math.max(1, +e.target.value || 1))}
            inputProps={{ min: 1, max: 200, style: { width: 56, fontSize: 11 } }}
          />
        </Stack>
        <TextField
          fullWidth size="small" placeholder="output folder (default: ./augmented)"
          value={outDir} onChange={e => setOutDir(e.target.value)}
          inputProps={{ style: { fontSize: 11 } }}
          sx={{ mb: 0.75 }}
        />
        <Button
          fullWidth variant="outlined"
          startIcon={saving ? <CircularProgress size={12} /> : <SaveIcon sx={{ fontSize: 14 }} />}
          disabled={!currentPath || busy}
          onClick={handleGenerate}
          sx={{ fontSize: 11, borderColor: '#4ec994', color: '#4ec994', mb: 0.5 }}
        >
          {saving ? `Saving ${count} image(s)…` : `Generate & Save ${count}`}
        </Button>

        {msg && (
          <Alert severity={msg.ok ? 'success' : 'error'} sx={{ py: 0, fontSize: 11, mb: 0.5 }}>
            {msg.ok || msg.err}
          </Alert>
        )}

        <Divider sx={{ my: 1 }} />

        {/* ── Batch section ─────────────────────────────────────────────────── */}
        <Accordion disableGutters defaultExpanded={false}>
          <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ fontSize: 14 }} />}>
            <Typography sx={{ fontSize: 11, color: 'secondary.main' }}>Batch Augmentation</Typography>
            {(batchSource || batchStandard) && (
              <Typography sx={{ fontSize: 10, color: '#4ec9b0', ml: 1 }}>
                ({batchMatchCount} symbol{batchMatchCount !== 1 ? 's' : ''})
              </Typography>
            )}
          </AccordionSummary>
          <AccordionDetails sx={{ px: 1, pb: 1, pt: 0.5 }}>

            <FormControl fullWidth size="small" sx={{ mb: 0.75 }}>
              <Select
                displayEmpty value={batchSource}
                onChange={e => setBatchSource(e.target.value)}
                sx={{ fontSize: 11 }}
              >
                <MenuItem value=""><em>All origins</em></MenuItem>
                {batchSources.map(s => (
                  <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" sx={{ mb: 0.75 }}>
              <Select
                displayEmpty value={batchStandard}
                onChange={e => setBatchStandard(e.target.value)}
                sx={{ fontSize: 11 }}
              >
                <MenuItem value=""><em>All standards</em></MenuItem>
                {batchStandards.map(s => (
                  <MenuItem key={s} value={s} sx={{ fontSize: 11 }}>{s}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Typography sx={{ fontSize: 10, color: 'text.disabled', mb: 0.75 }}>
              {batchMatchCount} symbol{batchMatchCount !== 1 ? 's' : ''} matched
              {batchMatchCount > 0 && (
                <> &nbsp;·&nbsp; {batchMatchCount * count} image{batchMatchCount * count !== 1 ? 's' : ''} total</>
              )}
            </Typography>

            <TextField
              fullWidth size="small"
              placeholder={`output folder (default: ${outDir || './augmented'})`}
              value={batchOutDir} onChange={e => setBatchOutDir(e.target.value)}
              inputProps={{ style: { fontSize: 11 } }}
              sx={{ mb: 0.75 }}
            />

            <Button
              fullWidth variant="outlined"
              startIcon={batchRunning ? <CircularProgress size={12} /> : <SaveIcon sx={{ fontSize: 14 }} />}
              disabled={batchMatchCount === 0 || batchRunning || previewing || saving}
              onClick={handleBatch}
              sx={{ fontSize: 11, borderColor: '#ff9800', color: '#ff9800', mb: batchRunning || batchResult ? 0.75 : 0 }}
            >
              {batchRunning
                ? `Processing ${batchProgress ? `${batchProgress.current} / ${batchProgress.total}` : '…'}`
                : `Augment ${batchMatchCount} Symbol${batchMatchCount !== 1 ? 's' : ''}`}
            </Button>

            {/* Live progress */}
            {batchRunning && batchProgress && (
              <Box sx={{ mb: 0.5 }}>
                <LinearProgress
                  variant="determinate"
                  value={Math.round(batchProgress.current / batchProgress.total * 100)}
                  sx={{
                    height: 4, borderRadius: 1, mb: 0.5, bgcolor: '#333',
                    '& .MuiLinearProgress-bar': { bgcolor: '#ff9800' },
                  }}
                />
                <Typography sx={{ fontSize: 10, color: 'text.disabled', fontFamily: 'monospace' }} noWrap>
                  {batchProgress.name}
                  {batchProgress.saved != null && (
                    <> &nbsp;·&nbsp; {batchProgress.saved} saved</>
                  )}
                </Typography>
              </Box>
            )}

            {/* Result summary */}
            {batchResult && !batchRunning && (
              batchResult.error
                ? <Alert severity="error"   sx={{ py: 0, fontSize: 11 }}>{batchResult.error}</Alert>
                : <Alert severity={batchResult.errors > 0 ? 'warning' : 'success'} sx={{ py: 0, fontSize: 11 }}>
                    ✓ {batchResult.saved} image{batchResult.saved !== 1 ? 's' : ''} saved
                    {batchResult.skipped > 0 && `, ${batchResult.skipped} skipped`}
                    {batchResult.errors  > 0 && `, ${batchResult.errors} error${batchResult.errors !== 1 ? 's' : ''}`}
                    &nbsp;→&nbsp;{batchResult.output_dir}
                  </Alert>
            )}

          </AccordionDetails>
        </Accordion>

        {/* Per-symbol results */}
        {(previewing || saving) ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <SmartGrid images={images} label={imagesLabel} />
        )}

      </Box>
    </Box>
  );
}
