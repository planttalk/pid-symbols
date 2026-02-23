import { useState, useCallback, useRef } from 'react';
import {
  Box, Typography, Button, Slider, Checkbox, FormControlLabel,
  TextField, Stack, Accordion, AccordionSummary, AccordionDetails,
  Alert, CircularProgress, Switch, ImageList, ImageListItem,
  ImageListItemBar, Tooltip, Divider,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ShuffleIcon from '@mui/icons-material/Shuffle';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SaveIcon from '@mui/icons-material/Save';
import { useEditorStore } from '../store';
import { EFFECT_GROUPS, ALL_EFFECT_NAMES } from '../constants';

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

// ── Generated image grid ───────────────────────────────────────────────────────
function AugmentGrid({ images }) {
  if (!images.length) return null;
  return (
    <Box sx={{ mt: 1 }}>
      <Typography sx={{ fontSize: 11, color: 'text.secondary', mb: 0.5 }}>
        {images.length} image{images.length !== 1 ? 's' : ''} generated
      </Typography>
      <ImageList cols={3} gap={4}>
        {images.map((img, i) => (
          <ImageListItem key={i} sx={{ cursor: 'pointer' }}
            onClick={() => window.open(img.src, '_blank')}
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
        ))}
      </ImageList>
    </Box>
  );
}

// ── Main AugmentTab ────────────────────────────────────────────────────────────
export default function AugmentTab() {
  const {
    currentPath, augEffects, augSize, augCount, augOutputDir, augRandomizePerImg,
    augImages, augGenerating, augPreviewLoading, augPreviewSrc,
    setAugEffect, removeAugEffect, setAugImages, setAugPreviewSrc,
  } = useEditorStore();

  const [size,    setSize]    = useState(augSize);
  const [count,   setCount]   = useState(augCount);
  const [outDir,  setOutDir]  = useState(augOutputDir);
  const [randPer, setRandPer] = useState(augRandomizePerImg);
  const [loading, setLoading] = useState(false);
  const [prevLoad, setPrevLoad] = useState(false);
  const [prevSrc,  setPrevSrc]  = useState(augPreviewSrc);
  const [images,   setImages]   = useState(augImages);
  const [msg,      setMsg]      = useState(null);
  const previewTimer = useRef(null);

  const handleToggle = useCallback((name, enabled) => {
    if (enabled) setAugEffect(name, 0.5);
    else         removeAugEffect(name);
    schedulePreview();
  }, [setAugEffect, removeAugEffect]);

  const handleChange = useCallback((name, value) => {
    setAugEffect(name, value);
    schedulePreview();
  }, [setAugEffect]);

  const schedulePreview = () => {
    if (previewTimer.current) clearTimeout(previewTimer.current);
    previewTimer.current = setTimeout(doPreview, 700);
  };

  const doPreview = useCallback(async () => {
    if (!currentPath) return;
    setPrevLoad(true);
    try {
      const { augEffects: effects } = useEditorStore.getState();
      const res  = await fetch('/api/augment-preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentPath, effects, size }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPrevSrc(data.image);
    } catch (e) {
      setMsg({ err: '✗ Preview: ' + e.message });
    } finally {
      setPrevLoad(false);
    }
  }, [currentPath, size]);

  const handleRandomize = useCallback(() => {
    // Pick 3–6 random effects with random intensities
    const n      = Math.floor(Math.random() * 4) + 3;
    const picked = [...ALL_EFFECT_NAMES].sort(() => Math.random() - 0.5).slice(0, n);
    // Clear existing, set new
    ALL_EFFECT_NAMES.forEach(name => removeAugEffect(name));
    picked.forEach(name => setAugEffect(name, +(Math.random() * 0.7 + 0.2).toFixed(2)));
    schedulePreview();
  }, [setAugEffect, removeAugEffect]);

  const handleGenerate = useCallback(async () => {
    if (!currentPath) return;
    setLoading(true);
    setMsg(null);
    setImages([]);
    try {
      const { augEffects: effects } = useEditorStore.getState();
      const res = await fetch('/api/augment-generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path:               currentPath,
          effects,
          count,
          size,
          output_dir:         outDir,
          randomize_per_image: randPer,
          return_images:      true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Generation failed');
      const imgs = (data.images || []).map((src, i) => ({
        src,
        label: `#${i+1}`,
      }));
      setImages(imgs);
      setAugImages(imgs);
      setMsg({ ok: `✓ ${data.saved} image(s) saved to ${data.output_dir}` });
    } catch (e) {
      setMsg({ err: '✗ ' + e.message });
    } finally {
      setLoading(false);
    }
  }, [currentPath, count, size, outDir, randPer, setAugImages]);

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Preview area */}
      <Box sx={{
        flexShrink: 0, bgcolor: '#2a2a2a', borderBottom: '1px solid #444',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: 140, maxHeight: 220, position: 'relative', overflow: 'hidden',
      }}>
        {prevLoad && (
          <CircularProgress size={24} sx={{ position: 'absolute' }} />
        )}
        {prevSrc ? (
          <Box component="img" src={prevSrc} alt="preview"
            sx={{ maxWidth: '100%', maxHeight: 216, objectFit: 'contain',
                  opacity: prevLoad ? 0.3 : 1, transition: 'opacity 0.2s' }} />
        ) : (
          !prevLoad && (
            <Typography sx={{ fontSize: 11, color: '#555' }}>
              {currentPath ? 'Select effects, then Preview' : 'Select a symbol first'}
            </Typography>
          )
        )}
      </Box>

      {/* Controls */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>
        {/* Top actions */}
        <Stack direction="row" gap={0.75} sx={{ mb: 1 }}>
          <Button fullWidth startIcon={<VisibilityIcon sx={{ fontSize: 14 }} />}
            onClick={doPreview} disabled={!currentPath || prevLoad}
            sx={{ fontSize: 11, borderColor: '#4ec9b0', color: '#4ec9b0' }}>
            Preview
          </Button>
          <Button fullWidth startIcon={<ShuffleIcon sx={{ fontSize: 14 }} />}
            onClick={handleRandomize} disabled={!currentPath}
            sx={{ fontSize: 11, borderColor: '#cc88ff', color: '#cc88ff' }}>
            Randomize
          </Button>
        </Stack>

        <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1 }}>
          <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>Size</Typography>
          <TextField type="number" size="small"
            value={size} onChange={e => setSize(+e.target.value || 512)}
            inputProps={{ min: 64, max: 2048, step: 64, style: { width: 64, fontSize: 11 } }} />
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
          <TextField type="number" size="small"
            value={count} onChange={e => setCount(Math.max(1, +e.target.value || 1))}
            inputProps={{ min: 1, max: 100, style: { width: 56, fontSize: 11 } }} />
        </Stack>
        <TextField
          fullWidth size="small" placeholder="output folder (default: ./augmented)"
          value={outDir} onChange={e => setOutDir(e.target.value)}
          inputProps={{ style: { fontSize: 11 } }}
          sx={{ mb: 0.75 }}
        />
        <Button
          fullWidth variant="outlined" startIcon={loading ? <CircularProgress size={12} /> : <SaveIcon sx={{ fontSize: 14 }} />}
          disabled={!currentPath || loading}
          onClick={handleGenerate}
          sx={{ fontSize: 11, borderColor: '#4ec994', color: '#4ec994', mb: 0.5 }}>
          {loading ? `Generating ${count} image(s)…` : `Generate ${count} Image(s)`}
        </Button>

        {msg && (
          <Alert severity={msg.ok ? 'success' : 'error'} sx={{ py: 0, fontSize: 11, mb: 0.5 }}>
            {msg.ok || msg.err}
          </Alert>
        )}

        {/* Generated image grid */}
        <AugmentGrid images={images} />
      </Box>
    </Box>
  );
}
