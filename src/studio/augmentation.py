"""Augmentation utilities for the studio editor (lint-driven refactor)."""

from __future__ import annotations

import base64
import io
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from random import Random
from typing import cast

import numpy as np
from PIL import Image

from .reports import combo_overlaps_flagged, compute_effect_caps, compute_flagged_combos
from .symbols import _safe_path, list_symbols


EffectIntensities = dict[str, float]


def _cap_intensity(value: float, cap: float) -> float:
    return max(0.0, min(cap, value))


def _encode_image(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _normalize_image(source_data: bytes, size: int) -> np.ndarray:
    with Image.open(io.BytesIO(source_data)) as opened:
        rgb = opened.convert("RGB")
        if rgb.size != (size, size):
            rgb = rgb.resize((size, size), Image.Resampling.LANCZOS)
        return np.array(rgb, dtype=np.uint8)


def _select_non_flagged_combo(
    rng: Random,
    apply_order: Sequence[str],
    flagged_combos: Sequence[frozenset[str]],
    min_len: int = 3,
    max_len: int = 7,
    attempts: int = 12,
) -> list[str]:
    available = list(apply_order)
    if not available:
        return []

    max_len = min(max_len, len(available))
    min_len = min(min_len, max_len)

    for _ in range(attempts):
        n = rng.randint(min_len, max_len)
        picked = rng.sample(available, n)
        if not combo_overlaps_flagged(frozenset(picked), flagged_combos):
            return picked

    return rng.sample(available, max_len)


def _sample_effects(
    rng: Random,
    effect_caps: Mapping[str, float],
    flagged_combos: Sequence[frozenset[str]],
    apply_order: Sequence[str],
    explicit_effects: Mapping[str, float],
    randomize_per_image: bool,
) -> EffectIntensities:
    if randomize_per_image:
        picked = _select_non_flagged_combo(rng, apply_order, flagged_combos)
        return {
            name: round(
                _cap_intensity(rng.uniform(0.15, 0.65), effect_caps.get(name, 1.0)), 2
            )
            for name in picked
        }

    if explicit_effects:
        variations = {}
        for name, intensity in explicit_effects.items():
            if intensity <= 0.0:
                continue
            cap = effect_caps.get(name, 1.0)
            scaled = intensity * rng.uniform(0.7, 1.3)
            variations[name] = round(_cap_intensity(scaled, cap), 3)
        return variations

    return {}


def random_geometry_transform(
    arr: np.ndarray, rng: Random | None = None
) -> tuple[np.ndarray, dict[str, float]]:
    """Apply PIL Transpose transforms; returns transformed array and geom metadata."""

    if rng is None:
        rng = Random()

    geom: dict[str, float] = {}
    img = Image.fromarray(arr)

    if rng.random() < 0.5:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        geom["mirror_h"] = 1.0

    if rng.random() < 0.5:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        geom["mirror_v"] = 1.0

    rot = rng.choice((0, 90, 180, 270))
    rotation_map = {
        90: Image.Transpose.ROTATE_90,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_270,
    }
    if rot in rotation_map:
        img = img.transpose(rotation_map[rot])
        geom[f"rot_{rot}"] = 1.0

    return np.array(img, dtype=arr.dtype), geom


def augment_preview(body: dict) -> tuple[dict | None, str]:
    """Render SVG to N PNGs, return base64 previews."""

    rel = body.get("path", "")
    effects = {k: float(v) for k, v in body.get("effects", {}).items()}
    size = max(64, min(2048, int(body.get("size", 512))))
    count = max(1, min(200, int(body.get("count", 1))))
    randomize_per = bool(body.get("randomize_per_image", False))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"

    try:
        from src.degradation import _APPLY_ORDER, apply_effects
        from src.svg_utils import _render_svg_to_png

        png_bytes = cast(bytes, _render_svg_to_png(svg_path))
        base_arr = _normalize_image(png_bytes, size)

        effect_caps = compute_effect_caps()
        flagged_combos = compute_flagged_combos()
        rng = Random()

        images_out: list[dict] = []
        for _ in range(count):
            varied = _sample_effects(
                rng,
                effect_caps,
                flagged_combos,
                _APPLY_ORDER,
                effects,
                randomize_per,
            )
            frame, geom = random_geometry_transform(base_arr, rng)
            frame_effects = {**geom, **varied}
            out_arr = apply_effects(frame, frame_effects)
            images_out.append({"src": _encode_image(out_arr), "effects": frame_effects})

        return {"images": images_out}, ""
    except Exception as exc:
        return None, str(exc)


def augment_generate(body: dict) -> tuple[dict | None, str]:
    """Generate count PNGs, optionally return previews."""

    rel = body.get("path", "")
    effects = {k: float(v) for k, v in body.get("effects", {}).items()}
    count = max(1, min(100, int(body.get("count", 5))))
    size = max(64, min(2048, int(body.get("size", 512))))
    output_dir = (body.get("output_dir") or "").strip() or "./augmented"
    randomize_per = bool(body.get("randomize_per_image", False))
    return_images = bool(body.get("return_images", False))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"

    try:
        import cairosvg

        from src.degradation import _APPLY_ORDER, apply_effects

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        svg_text = svg_path.read_text(encoding="utf-8")
        png_bytes = cast(
            bytes,
            cairosvg.svg2png(
                bytestring=svg_text.encode("utf-8"),
                output_width=size,
                output_height=size,
            ),
        )
        base_arr = _normalize_image(png_bytes, size)
        stem = base.stem

        effect_caps = compute_effect_caps()
        flagged_combos = compute_flagged_combos()
        rng = Random()
        images_b64: list[dict] = []

        for index in range(count):
            varied = _sample_effects(
                rng,
                effect_caps,
                flagged_combos,
                _APPLY_ORDER,
                effects,
                randomize_per,
            )
            frame, geom = random_geometry_transform(base_arr, rng)
            frame_effects = {**geom, **varied}
            out_arr = apply_effects(frame, frame_effects)

            fname = out_dir / f"{stem}_aug_{index + 1:04d}.png"
            Image.fromarray(out_arr).save(fname)

            if return_images:
                images_b64.append(
                    {"src": _encode_image(out_arr), "effects": frame_effects}
                )

        result: dict[str, object] = {
            "saved": count,
            "output_dir": str(out_dir.resolve()),
        }
        if return_images:
            result["images"] = images_b64
        return result, ""
    except Exception as exc:
        return None, str(exc)


def tight_bbox_yolo(arr: np.ndarray) -> tuple[float, float, float, float] | None:
    """Return YOLO-normalised (cx, cy, w, h) bounding box for non-white pixels."""

    gray = arr.mean(axis=2)
    mask = gray < 240
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None

    H, W = arr.shape[:2]
    r0, r1 = int(rows[0]), int(rows[-1])
    c0, c1 = int(cols[0]), int(cols[-1])
    cx = ((c0 + c1) / 2.0) / W
    cy = ((r0 + r1) / 2.0) / H
    bw = (c1 - c0 + 1.0) / W
    bh = (r1 - r0 + 1.0) / H
    return cx, cy, bw, bh


def _symbol_class_name(sym_id: str) -> str:
    parts = sym_id.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1]


def _setup_yolo_layout(
    out_dir: Path, symbols: Sequence[dict[str, str]]
) -> tuple[Path, Path, dict[str, int]]:
    img_dir = out_dir / "images" / "train"
    lbl_dir = out_dir / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    classes = sorted({_symbol_class_name(sym["path"]) for sym in symbols})
    class_map = {cls: idx for idx, cls in enumerate(classes)}
    names_block = "\n".join(f"  {idx}: {cls}" for idx, cls in enumerate(classes))
    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve()}\n"
        f"train: images/train\n"
        f"nc: {len(classes)}\n"
        f"names:\n{names_block}\n",
        encoding="utf-8",
    )
    return img_dir, lbl_dir, class_map


def augment_batch(body: dict, batch_cancel: threading.Event):
    """Generator: yields SSE progress events while augmenting symbols."""

    source = body.get("source", "").strip()
    standard = body.get("standard", "").strip()
    effects = {k: float(v) for k, v in body.get("effects", {}).items()}
    size = max(64, min(2048, int(body.get("size", 512))))
    count = max(1, min(200, int(body.get("count", 1))))
    out_str = (body.get("output_dir") or "").strip() or "./augmented"
    randomize_per = bool(body.get("randomize_per_image", False))
    fmt = body.get("format", "png").lower()

    symbols = list_symbols()
    if source:
        symbols = [s for s in symbols if s.get("source") == source]
    if standard:
        symbols = [s for s in symbols if s.get("standard") == standard]
    total = len(symbols)

    if total == 0:
        yield {
            "type": "done",
            "processed": 0,
            "saved": 0,
            "skipped": 0,
            "errors": 0,
            "output_dir": out_str,
            "format": fmt,
        }
        return

    batch_cancel.clear()
    yield {"type": "start", "total": total}

    try:
        from src.degradation import _APPLY_ORDER, apply_effects
        from src.svg_utils import _render_svg_to_png
    except Exception as exc:
        yield {
            "type": "done",
            "processed": 0,
            "saved": 0,
            "skipped": total,
            "errors": 1,
            "output_dir": out_str,
            "format": fmt,
            "error": str(exc),
        }
        return

    out_dir = Path(out_str)
    out_dir.mkdir(parents=True, exist_ok=True)

    img_dir = out_dir
    lbl_dir: Path | None = None
    class_map: dict[str, int] = {}
    n_classes = 0

    if fmt == "yolo":
        img_dir, lbl_dir, class_map = _setup_yolo_layout(out_dir, symbols)
        n_classes = len(class_map)

    processed = saved = skipped = errors = 0
    rng = Random()

    for i, sym in enumerate(symbols):
        if batch_cancel.is_set():
            yield {
                "type": "cancelled",
                "processed": processed,
                "saved": saved,
                "skipped": skipped + (total - i),
                "errors": errors,
            }
            return

        effect_caps = compute_effect_caps()
        flagged_combos = compute_flagged_combos()

        sym_id = sym["path"]
        base = _safe_path(sym_id)
        name = sym.get("name", sym_id)

        if base is None:
            errors += 1
            yield {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "name": name,
                "status": "error",
                "saved": saved,
            }
            continue

        svg_path = base.with_suffix(".svg")
        if not svg_path.exists():
            skipped += 1
            yield {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "name": name,
                "status": "skipped",
                "saved": saved,
            }
            continue

        try:
            png_bytes = cast(bytes, _render_svg_to_png(svg_path))
            arr = _normalize_image(png_bytes, size)
            stem = sym_id.replace("/", "_")

            cls_idx = class_map.get(_symbol_class_name(sym_id), 0)

            for attempt in range(count):
                varied = _sample_effects(
                    rng,
                    effect_caps,
                    flagged_combos,
                    _APPLY_ORDER,
                    effects,
                    randomize_per,
                )
                frame, geom = random_geometry_transform(arr, rng)
                frame_effects = {**geom, **varied}
                out_arr = apply_effects(frame, frame_effects)
                fname = f"{stem}_aug_{attempt + 1:04d}"
                Image.fromarray(out_arr).save(img_dir / f"{fname}.png")

                if fmt == "yolo" and lbl_dir is not None:
                    bbox = tight_bbox_yolo(out_arr)
                    if bbox:
                        cx, cy, bw, bh = bbox
                        (lbl_dir / f"{fname}.txt").write_text(
                            f"{cls_idx} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n",
                            encoding="utf-8",
                        )

                saved += 1

            processed += 1
            yield {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "name": name,
                "status": "ok",
                "saved": saved,
            }

        except Exception as exc:
            errors += 1
            yield {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "name": name,
                "status": "error",
                "saved": saved,
                "error": str(exc),
            }

    done: dict[str, object] = {
        "type": "done",
        "processed": processed,
        "saved": saved,
        "skipped": skipped,
        "errors": errors,
        "output_dir": str(out_dir.resolve()),
        "format": fmt,
    }
    if fmt == "yolo":
        done["class_count"] = n_classes
    yield done


def augment_combo(body: dict) -> tuple[dict | None, str]:
    """Render 1-3 combinations of selected effects as PNGs."""

    rel = body.get("path", "")
    effects = {k: float(v) for k, v in body.get("effects", {}).items() if float(v) > 0}
    size = max(64, min(2048, int(body.get("size", 512))))
    max_combo = max(1, min(3, int(body.get("max_combo", 3))))

    base = _safe_path(rel)
    if base is None:
        return None, "invalid path"
    svg_path = base.with_suffix(".svg")
    if not svg_path.exists():
        return None, "SVG not found"
    if not effects:
        return None, "no effects selected"

    try:
        import itertools

        from src.degradation import apply_effects
        from src.svg_utils import _render_svg_to_png

        png_bytes = cast(bytes, _render_svg_to_png(svg_path))
        base_arr = _normalize_image(png_bytes, size)

        effect_names = list(effects.keys())
        combos: list[dict[str, object]] = []
        upper = min(max_combo, len(effect_names))

        for n in range(1, upper + 1):
            for combo in itertools.combinations(effect_names, n):
                combo_effects = {name: effects[name] for name in combo}
                out_arr = apply_effects(base_arr.copy(), combo_effects)
                combos.append(
                    {
                        "src": _encode_image(out_arr),
                        "label": " + ".join(combo),
                        "effects": combo_effects,
                    }
                )

        return {"combos": combos, "total": len(combos)}, ""
    except Exception as exc:
        return None, str(exc)
