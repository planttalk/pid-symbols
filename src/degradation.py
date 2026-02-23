"""
degradation.py
--------------------
Paper and scanning degradation effects for data augmentation.

Each effect function:
  - Takes a numpy uint8 RGB array (H, W, 3)
  - Takes an intensity float in [0, 1]
  - Returns a numpy uint8 RGB array (H, W, 3)

Uses only numpy + Pillow (no extra dependencies).

Effect application order (physical → biological → chemical → scanning)
is enforced by apply_effects() to match how real degradation accumulates.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clip(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr, 0, 255).astype(np.uint8)


def _rng() -> np.random.Generator:
    return np.random.default_rng()


# ── Physical ──────────────────────────────────────────────────────────────────

def yellowing(img: np.ndarray, intensity: float) -> np.ndarray:
    """Warm-tone aging: paper base shifts toward sepia/cream."""
    t   = float(intensity)
    out = img.astype(np.float32)
    out[..., 0] = out[..., 0] * (1 + 0.08 * t) + 20 * t
    out[..., 1] = out[..., 1] * (1 + 0.02 * t) + 12 * t
    out[..., 2] = out[..., 2] * (1 - 0.15 * t)
    # Tint near-white areas to cream
    cream = np.array([245, 235, 200], dtype=np.float32)
    white = img.mean(axis=2) > 220
    for c in range(3):
        out[..., c][white] = out[..., c][white] * (1 - 0.4 * t) + cream[c] * 0.4 * t
    return _clip(out)


def foxing(img: np.ndarray, intensity: float) -> np.ndarray:
    """Scattered reddish-brown oxidation spots (metallic impurities in paper)."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)
    n    = int(intensity * 80) + 1

    for _ in range(n):
        cx = int(rng.integers(0, W))
        cy = int(rng.integers(0, H))
        r  = int(rng.integers(2, max(3, int(min(H, W) * 0.04 * intensity) + 3)))

        y0, y1 = max(0, cy - r * 2), min(H, cy + r * 2)
        x0, x1 = max(0, cx - r * 2), min(W, cx + r * 2)
        if y0 >= y1 or x0 >= x1:
            continue

        yy, xx = np.ogrid[y0:y1, x0:x1]
        dist  = np.sqrt(((xx - cx) / max(r, 1))**2 + ((yy - cy) / max(r * 1.3, 1))**2)
        blend = np.maximum(0.0, 1.0 - dist) * float(rng.uniform(0.3, 0.8)) * intensity

        sr, sg, sb = float(rng.uniform(100, 180)), float(rng.uniform(60, 110)), float(rng.uniform(20, 60))
        for c, v in enumerate([sr, sg, sb]):
            out[y0:y1, x0:x1, c] = out[y0:y1, x0:x1, c] * (1 - blend) + v * blend

    return _clip(out)


def crease(img: np.ndarray, intensity: float) -> np.ndarray:
    """Fold / score lines across the document."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    for _ in range(max(1, int(intensity * 4))):
        if rng.random() > 0.5:
            y0 = int(rng.integers(H // 4, 3 * H // 4))
            for dy in range(-2, 3):
                y = y0 + dy
                if 0 <= y < H:
                    w = max(0.0, 1.0 - abs(dy) * 0.4) * intensity
                    out[y, :] = out[y, :] * (1 - 0.3 * w)
                    out[y, :, 0] += 15 * w
                    out[y, :, 1] += 10 * w
                    out[y, :, 2] -= 5  * w
        else:
            x0 = int(rng.integers(W // 4, 3 * W // 4))
            for dx in range(-2, 3):
                x = x0 + dx
                if 0 <= x < W:
                    w = max(0.0, 1.0 - abs(dx) * 0.4) * intensity
                    out[:, x] = out[:, x] * (1 - 0.3 * w)
                    out[:, x, 0] += 15 * w
                    out[:, x, 1] += 10 * w
                    out[:, x, 2] -= 5  * w

    return _clip(out)


def water_stain(img: np.ndarray, intensity: float) -> np.ndarray:
    """Elliptical tide-mark stains from liquid damage."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    for _ in range(max(1, int(intensity * 3))):
        cx = int(rng.integers(W // 4, 3 * W // 4))
        cy = int(rng.integers(H // 4, 3 * H // 4))
        rx = int(rng.integers(W // 8, W // 3))
        ry = int(rng.integers(H // 8, H // 3))

        yy, xx = np.mgrid[0:H, 0:W]
        dist  = np.sqrt(((xx - cx) / max(rx, 1))**2 + ((yy - cy) / max(ry, 1))**2)
        ring  = np.exp(-((dist - 0.9)**2) / max(0.05 * intensity, 0.005))
        alpha = ring * intensity * 0.5

        out[..., 0] = out[..., 0] * (1 - alpha) + 200 * alpha
        out[..., 1] = out[..., 1] * (1 - alpha) + 180 * alpha
        out[..., 2] = out[..., 2] * (1 - alpha) + 140 * alpha

    return _clip(out)


def edge_wear(img: np.ndarray, intensity: float) -> np.ndarray:
    """Frayed / worn borders — noise and brightening near edges."""
    rng    = _rng()
    H, W   = img.shape[:2]
    out    = img.astype(np.float32)
    margin = max(2, int(min(H, W) * 0.08 * intensity))

    noise_h = rng.random((H, margin)).astype(np.float32) * intensity * 80
    noise_w = rng.random((margin, W)).astype(np.float32) * intensity * 80

    for c in range(3):
        out[:, :margin, c]  = np.clip(out[:, :margin, c]  + noise_h,       0, 255)
        out[:, -margin:, c] = np.clip(out[:, -margin:, c] + noise_h[:, ::-1], 0, 255)
        out[:margin, :, c]  = np.clip(out[:margin, :, c]  + noise_w,       0, 255)
        out[-margin:, :, c] = np.clip(out[-margin:, :, c] + noise_w[::-1, :], 0, 255)

    return _clip(out)


def fingerprint(img: np.ndarray, intensity: float) -> np.ndarray:
    """Grease smudge that reduces local contrast."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    cx = int(rng.integers(W // 4, 3 * W // 4))
    cy = int(rng.integers(H // 4, 3 * H // 4))
    rx = int(min(H, W) * float(rng.uniform(0.1, 0.25)))
    ry = int(rx * float(rng.uniform(0.5, 1.5)))
    rx, ry = max(rx, 1), max(ry, 1)

    yy, xx   = np.mgrid[0:H, 0:W]
    dist     = np.sqrt(((xx - cx) / rx)**2 + ((yy - cy) / ry)**2)
    alpha    = np.maximum(0.0, 1.0 - dist) * intensity * 0.4
    mean_c   = out.mean(axis=2, keepdims=True)
    out      = out * (1 - alpha[..., None]) + mean_c * alpha[..., None]
    out[..., 2] -= alpha * 20

    return _clip(out)


def binding_shadow(img: np.ndarray, intensity: float) -> np.ndarray:
    """Dark gradient at the left edge simulating a book spine."""
    H, W  = img.shape[:2]
    out   = img.astype(np.float32)
    width = max(1, int(W * 0.15 * intensity))
    ramp  = np.linspace(1.0 - 0.7 * intensity, 1.0, width)
    out[:, :width, :] *= ramp[None, :, None]
    return _clip(out)


def bleed_through(img: np.ndarray, intensity: float) -> np.ndarray:
    """Faint ghost of content from the reverse side of the sheet."""
    if intensity < 0.01:
        return img
    ghost      = np.fliplr(img).astype(np.float32)
    ghost_gray = ghost.mean(axis=2, keepdims=True)
    ghost_light = 255.0 - (255.0 - ghost_gray) * intensity * 0.35
    ghost_rgb   = np.repeat(ghost_light, 3, axis=2)
    out = img.astype(np.float32) * (1 - intensity * 0.1) + ghost_rgb * intensity * 0.1
    return _clip(out)


def hole_punch(img: np.ndarray, intensity: float) -> np.ndarray:
    """Circular punch holes along the left margin."""
    H, W  = img.shape[:2]
    out   = img.copy()
    n     = max(1, int(intensity * 4))
    r     = max(3, int(min(H, W) * 0.022))
    x_ctr = max(r + 2, int(W * 0.04))
    yy, xx = np.mgrid[0:H, 0:W]

    for i in range(n):
        yp   = H // (n + 1) * (i + 1)
        hole = (xx - x_ctr)**2 + (yy - yp)**2 < r**2
        out[hole] = 255
    return out


def tape_residue(img: np.ndarray, intensity: float) -> np.ndarray:
    """Yellowed adhesive tape strip."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    tape_y = int(rng.integers(H // 10, H // 4))
    tape_h = max(4, int(H * 0.04))
    alpha  = intensity * 0.5

    sl = slice(tape_y, min(H, tape_y + tape_h))
    out[sl, :, 0] = out[sl, :, 0] * (1 - alpha) + 220 * alpha
    out[sl, :, 1] = out[sl, :, 1] * (1 - alpha) + 200 * alpha
    out[sl, :, 2] = out[sl, :, 2] * (1 - alpha) + 130 * alpha
    return _clip(out)


# ── Chemical ──────────────────────────────────────────────────────────────────

def ink_fading(img: np.ndarray, intensity: float) -> np.ndarray:
    """Dark pigment degrades toward medium gray."""
    out    = img.astype(np.float32)
    target = 160.0
    dark   = out < 128
    blend  = intensity * 0.7
    out[dark] = out[dark] * (1 - blend) + target * blend
    return _clip(out)


def ink_bleed(img: np.ndarray, intensity: float) -> np.ndarray:
    """Dark ink spreads / bleeds into surrounding paper fibers."""
    radius   = max(1, int(intensity * 4))
    pil      = Image.fromarray(img)
    expanded = pil.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    out = (img.astype(np.float32) * (1 - intensity * 0.6) +
           np.array(expanded).astype(np.float32) * intensity * 0.6)
    return _clip(out)


def coffee_stain(img: np.ndarray, intensity: float) -> np.ndarray:
    """Brown ring stain from a beverage cup."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    cx = int(rng.integers(W // 4, 3 * W // 4))
    cy = int(rng.integers(H // 4, 3 * H // 4))
    r  = int(min(H, W) * float(rng.uniform(0.1, 0.25)))
    rw = max(3, int(r * 0.15))

    yy, xx = np.mgrid[0:H, 0:W]
    dist   = np.sqrt((xx - cx).astype(float)**2 + (yy - cy).astype(float)**2)
    blend  = np.maximum(0.0, 1.0 - np.abs(dist - r) / max(rw, 1)) * intensity * 0.7

    out[..., 0] = out[..., 0] * (1 - blend) + 160 * blend
    out[..., 1] = out[..., 1] * (1 - blend) + 110 * blend
    out[..., 2] = out[..., 2] * (1 - blend) + 60  * blend
    return _clip(out)


def oil_stain(img: np.ndarray, intensity: float) -> np.ndarray:
    """Translucent oil / grease patch."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    cx = int(rng.integers(W // 4, 3 * W // 4))
    cy = int(rng.integers(H // 4, 3 * H // 4))
    rx = int(min(H, W) * float(rng.uniform(0.08, 0.2)))
    ry = int(rx * float(rng.uniform(0.6, 1.6)))
    rx, ry = max(rx, 1), max(ry, 1)

    yy, xx = np.mgrid[0:H, 0:W]
    dist   = np.sqrt(((xx - cx) / rx).astype(float)**2 + ((yy - cy) / ry).astype(float)**2)
    alpha  = np.maximum(0.0, 1.0 - dist)**0.5 * intensity * 0.4

    out[..., 0] -= alpha * out[..., 0] * 0.2
    out[..., 1] -= alpha * out[..., 1] * 0.3
    out[..., 2] -= alpha * out[..., 2] * 0.5
    return _clip(out)


def acid_spots(img: np.ndarray, intensity: float) -> np.ndarray:
    """Dark burn patches from acidic contact."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    for _ in range(max(1, int(intensity * 5))):
        cx = int(rng.integers(0, W))
        cy = int(rng.integers(0, H))
        r  = int(rng.integers(3, max(4, int(min(H, W) * 0.06))))
        y0, y1 = max(0, cy - r), min(H, cy + r)
        x0, x1 = max(0, cx - r), min(W, cx + r)
        if y0 >= y1 or x0 >= x1:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dist   = np.sqrt(((xx - cx) / max(r, 1))**2 + ((yy - cy) / max(r, 1))**2)
        alpha  = np.maximum(0.0, 1.0 - dist) * intensity * 0.8
        for c, v in enumerate([60.0, 45.0, 20.0]):
            out[y0:y1, x0:x1, c] = out[y0:y1, x0:x1, c] * (1 - alpha) + v * alpha

    return _clip(out)


def bleaching(img: np.ndarray, intensity: float) -> np.ndarray:
    """UV-induced brightness loss and contrast reduction."""
    out = img.astype(np.float32)
    out = out + (255 - out) * intensity * 0.5
    out = out * (1 - intensity * 0.3) + 128 * intensity * 0.3
    return _clip(out)


def toner_flaking(img: np.ndarray, intensity: float) -> np.ndarray:
    """Patchy toner loss in electrostatic / laser prints."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    for _ in range(int(intensity * 20)):
        y0 = int(rng.integers(0, max(1, H - 5)))
        x0 = int(rng.integers(0, max(1, W - 5)))
        ph = int(rng.integers(2, 8))
        pw = int(rng.integers(2, 12))
        a  = float(rng.uniform(0.3, 0.8)) * intensity
        out[y0:y0+ph, x0:x0+pw] = out[y0:y0+ph, x0:x0+pw] * (1 - a) + 240 * a

    return _clip(out)


# ── Biological ────────────────────────────────────────────────────────────────

def mold(img: np.ndarray, intensity: float) -> np.ndarray:
    """Greenish-gray irregular mold colonies."""
    rng = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)

    for _ in range(max(1, int(intensity * 4))):
        cx = int(rng.integers(0, W))
        cy = int(rng.integers(0, H))
        r  = int(min(H, W) * float(rng.uniform(0.04, 0.15)) * intensity)
        if r < 2:
            continue
        y0, y1 = max(0, cy - r), min(H, cy + r)
        x0, x1 = max(0, cx - r), min(W, cx + r)
        if y0 >= y1 or x0 >= x1:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dist  = (np.sqrt(((xx - cx) / max(r, 1))**2 + ((yy - cy) / max(r, 1))**2) +
                 rng.random((y1-y0, x1-x0)) * 0.4)
        blend = np.maximum(0.0, 1.0 - dist) * float(rng.uniform(0.4, 0.8)) * intensity
        mr = float(rng.uniform(60, 120))
        mg = float(rng.uniform(80, 140))
        mb = float(rng.uniform(50, 100))
        for c, v in enumerate([mr, mg, mb]):
            out[y0:y1, x0:x1, c] = out[y0:y1, x0:x1, c] * (1 - blend) + v * blend

    return _clip(out)


def mildew(img: np.ndarray, intensity: float) -> np.ndarray:
    """Scattered small dark specks from mildew."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.copy()
    n    = int(intensity * 200)
    if n < 1:
        return out

    ys     = rng.integers(0, H, n)
    xs     = rng.integers(0, W, n)
    colors = rng.integers(30, 80, (n, 3)).astype(np.uint8)

    for y, x, c in zip(ys, xs, colors):
        r = int(rng.integers(1, 3))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = int(y) + dy, int(x) + dx
                if 0 <= ny < H and 0 <= nx < W:
                    out[ny, nx] = c
    return out


def bio_foxing(img: np.ndarray, intensity: float) -> np.ndarray:
    """Fungal foxing — denser, more orange-red than chemical foxing."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.astype(np.float32)
    n    = int(intensity * 120) + 1

    for _ in range(n):
        cx = int(rng.integers(0, W))
        cy = int(rng.integers(0, H))
        r  = int(rng.integers(1, max(2, int(min(H, W) * 0.025))))
        y0, y1 = max(0, cy - r * 2), min(H, cy + r * 2)
        x0, x1 = max(0, cx - r * 2), min(W, cx + r * 2)
        if y0 >= y1 or x0 >= x1:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dist  = np.sqrt(((xx - cx) / max(r, 1))**2 + ((yy - cy) / max(r, 1))**2)
        blend = np.maximum(0.0, 1.0 - dist) * float(rng.uniform(0.4, 0.9)) * intensity
        sr = float(rng.uniform(160, 210))
        sg = float(rng.uniform(80,  130))
        sb = float(rng.uniform(10,  50))
        for c, v in enumerate([sr, sg, sb]):
            out[y0:y1, x0:x1, c] = out[y0:y1, x0:x1, c] * (1 - blend) + v * blend

    return _clip(out)


def insect_damage(img: np.ndarray, intensity: float) -> np.ndarray:
    """Small irregular holes and nibbled edges from insects."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.copy()

    for _ in range(int(intensity * 15)):
        cx = int(rng.integers(0, W))
        cy = int(rng.integers(0, H))
        r  = int(rng.integers(1, max(2, int(min(H, W) * 0.02 * intensity) + 2)))
        y0, y1 = max(0, cy - r), min(H, cy + r)
        x0, x1 = max(0, cx - r), min(W, cx + r)
        if y0 >= y1 or x0 >= x1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        noise  = rng.random((y1-y0, x1-x0)) * r * 0.3
        hole   = np.sqrt((xx - cx).astype(float)**2 + (yy - cy).astype(float)**2) + noise < r
        out[y0:y1, x0:x1][hole] = 248
    return out


# ── Scanning ──────────────────────────────────────────────────────────────────

def noise(img: np.ndarray, intensity: float) -> np.ndarray:
    """Gaussian sensor / grain noise."""
    rng   = _rng()
    sigma = intensity * 30
    n     = rng.normal(0, sigma, img.shape).astype(np.float32)
    return _clip(img.astype(np.float32) + n)


def salt_pepper(img: np.ndarray, intensity: float) -> np.ndarray:
    """Dead / hot pixels (salt-and-pepper)."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.copy()
    n    = int(H * W * intensity * 0.03)
    if n < 1:
        return out

    ys = rng.integers(0, H, n); xs = rng.integers(0, W, n)
    out[ys, xs] = 255
    ys = rng.integers(0, H, n); xs = rng.integers(0, W, n)
    out[ys, xs] = 0
    return out


def vignette(img: np.ndarray, intensity: float) -> np.ndarray:
    """Darker corners from uneven scanner / camera illumination."""
    H, W  = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    cy, cx = H / 2.0, W / 2.0
    dist   = np.sqrt(((xx - cx) / cx)**2 + ((yy - cy) / cy)**2)
    shadow = np.clip(1.0 - dist * intensity * 0.6, 0.0, 1.0)[..., None]
    return _clip(img.astype(np.float32) * shadow)


def jpeg_artifacts(img: np.ndarray, intensity: float) -> np.ndarray:
    """JPEG block-quantisation artefacts from lossy compression."""
    quality = max(5, int(80 - intensity * 75))
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return np.array(Image.open(buf).convert("RGB"))


def skew(img: np.ndarray, intensity: float) -> np.ndarray:
    """Slight document rotation during scanner feeding."""
    angle = float(intensity) * 5.0
    rotated = Image.fromarray(img).rotate(angle, fillcolor=(255, 255, 255), expand=False)
    return np.array(rotated)


def barrel_distortion(img: np.ndarray, intensity: float) -> np.ndarray:
    """Barrel lens distortion."""
    H, W  = img.shape[:2]
    cy, cx = H / 2.0, W / 2.0
    k      = float(intensity) * 0.3

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    yn = (yy - cy) / cy
    xn = (xx - cx) / cx
    r  = np.sqrt(xn**2 + yn**2)
    f  = 1.0 + k * r**2

    src_x = np.clip(xn * f * cx + cx, 0, W - 1).astype(int)
    src_y = np.clip(yn * f * cy + cy, 0, H - 1).astype(int)

    out = np.zeros_like(img)
    for c in range(3):
        out[..., c] = img[src_y, src_x, c]
    return out


def moire(img: np.ndarray, intensity: float) -> np.ndarray:
    """Interference / moire pattern from scanning halftone originals."""
    H, W  = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    freq   = 12.0
    pat    = (np.sin(xx * freq * np.pi / W) *
              np.sin(yy * freq * np.pi / H))
    pat    = (pat + 1.0) / 2.0 * float(intensity) * 30.0
    return _clip(img.astype(np.float32) + pat[..., None])


def halftone(img: np.ndarray, intensity: float) -> np.ndarray:
    """Halftone dot-screen pattern from printed originals."""
    H, W  = img.shape[:2]
    cell  = max(4, int(8 * (1.0 - float(intensity) * 0.5)))
    out   = img.astype(np.float32)

    yy, xx      = np.mgrid[0:H, 0:W]
    cy_local    = (yy % cell) - cell // 2
    cx_local    = (xx % cell) - cell // 2
    dist_cell   = np.sqrt(cy_local.astype(float)**2 + cx_local.astype(float)**2)
    brightness  = img.mean(axis=2) / 255.0
    dot_r       = (1.0 - brightness) * (cell // 2) * 0.8
    is_dot      = dist_cell < dot_r
    out        += np.where(is_dot, -float(intensity) * 40.0, 0.0)[..., None]
    return _clip(out)


def color_cast(img: np.ndarray, intensity: float) -> np.ndarray:
    """Warm white-balance error (yellowish scanner light)."""
    out = img.astype(np.float32)
    out[..., 0] += float(intensity) * 20
    out[..., 1] += float(intensity) * 10
    out[..., 2] -= float(intensity) * 15
    return _clip(out)


def blur(img: np.ndarray, intensity: float) -> np.ndarray:
    """Soft focus from scanner vibration or poor calibration."""
    radius  = max(0.5, float(intensity) * 4.0)
    blurred = Image.fromarray(img).filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(blurred)


def dust(img: np.ndarray, intensity: float) -> np.ndarray:
    """Tiny dark particles on scanner glass."""
    rng  = _rng()
    H, W = img.shape[:2]
    out  = img.copy()
    n    = int(float(intensity) * 50)

    ys = rng.integers(0, H, n)
    xs = rng.integers(0, W, n)
    for y, x in zip(ys, xs):
        out[int(y), int(x)] = rng.integers(0, 60, 3).astype(np.uint8)
    return out


def overexpose(img: np.ndarray, intensity: float) -> np.ndarray:
    """Blown-out whites from excessive scanner illumination."""
    return _clip(img.astype(np.float32) * (1.0 + float(intensity) * 0.8))


def underexpose(img: np.ndarray, intensity: float) -> np.ndarray:
    """Muddy dark image from insufficient illumination."""
    return _clip(img.astype(np.float32) * (1.0 - float(intensity) * 0.6))


def motion_streak(img: np.ndarray, intensity: float) -> np.ndarray:
    """Horizontal motion blur from scanner vibration."""
    radius  = max(0.5, float(intensity) * 5.0)
    blurred = Image.fromarray(img).filter(ImageFilter.GaussianBlur(radius=(radius, 0.5)))
    return np.array(blurred)


def binarization(img: np.ndarray, intensity: float) -> np.ndarray:
    """Harsh threshold creating broken / jagged strokes."""
    gray      = img.mean(axis=2)
    threshold = 200 - float(intensity) * 100
    binary    = (gray > threshold).astype(np.uint8) * 255
    bw        = np.stack([binary, binary, binary], axis=2).astype(np.float32)
    out = img.astype(np.float32) * (1 - float(intensity) * 0.7) + bw * float(intensity) * 0.7
    return _clip(out)


def pixelation(img: np.ndarray, intensity: float) -> np.ndarray:
    """Low-DPI scan: downsample then upsample."""
    H, W   = img.shape[:2]
    factor = max(2, int(float(intensity) * 12))
    sw     = max(8, W // factor)
    sh     = max(8, H // factor)
    pil    = Image.fromarray(img)
    small  = pil.resize((sw, sh), Image.NEAREST)
    big    = small.resize((W, H), Image.NEAREST)
    return np.array(big)


# ── Registry + apply_effects ──────────────────────────────────────────────────

EFFECTS: dict[str, callable] = {
    # Physical
    "yellowing":         yellowing,
    "foxing":            foxing,
    "crease":            crease,
    "water_stain":       water_stain,
    "edge_wear":         edge_wear,
    "fingerprint":       fingerprint,
    "binding_shadow":    binding_shadow,
    "bleed_through":     bleed_through,
    "hole_punch":        hole_punch,
    "tape_residue":      tape_residue,
    # Chemical
    "ink_fading":        ink_fading,
    "ink_bleed":         ink_bleed,
    "coffee_stain":      coffee_stain,
    "oil_stain":         oil_stain,
    "acid_spots":        acid_spots,
    "bleaching":         bleaching,
    "toner_flaking":     toner_flaking,
    # Biological
    "mold":              mold,
    "mildew":            mildew,
    "bio_foxing":        bio_foxing,
    "insect_damage":     insect_damage,
    # Scanning
    "noise":             noise,
    "salt_pepper":       salt_pepper,
    "vignette":          vignette,
    "jpeg_artifacts":    jpeg_artifacts,
    "skew":              skew,
    "barrel_distortion": barrel_distortion,
    "moire":             moire,
    "halftone":          halftone,
    "color_cast":        color_cast,
    "blur":              blur,
    "dust":              dust,
    "overexpose":        overexpose,
    "underexpose":       underexpose,
    "motion_streak":     motion_streak,
    "binarization":      binarization,
    "pixelation":        pixelation,
}

# Canonical application order: physical → biological → chemical → scanning
_APPLY_ORDER: list[str] = [
    "yellowing", "foxing", "crease", "water_stain", "edge_wear",
    "fingerprint", "binding_shadow", "bleed_through", "hole_punch", "tape_residue",
    "mold", "mildew", "bio_foxing", "insect_damage",
    "ink_fading", "ink_bleed", "coffee_stain", "oil_stain", "acid_spots",
    "bleaching", "toner_flaking",
    "noise", "salt_pepper", "vignette", "jpeg_artifacts", "skew",
    "barrel_distortion", "moire", "halftone", "color_cast", "blur",
    "dust", "overexpose", "underexpose", "motion_streak", "binarization",
    "pixelation",
]


def apply_effects(img_arr: np.ndarray, effects: dict[str, float]) -> np.ndarray:
    """Apply multiple effects in the canonical physical order.

    Args:
        img_arr: uint8 RGB numpy array (H, W, 3).
        effects: mapping of effect name to intensity in [0.0, 1.0].
                 Absent or zero-intensity effects are skipped.

    Returns:
        uint8 RGB numpy array with all active effects applied.
    """
    result = img_arr.copy()
    for name in _APPLY_ORDER:
        intensity = float(effects.get(name, 0.0))
        if intensity > 0.0 and name in EFFECTS:
            try:
                result = EFFECTS[name](result, intensity)
            except Exception:
                pass   # never let a single effect crash the pipeline
    return result
