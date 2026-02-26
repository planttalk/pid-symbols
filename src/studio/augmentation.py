"""Augmentation functions for the studio editor."""

from __future__ import annotations

import base64
import io
import random
import threading
from pathlib import Path

from .reports import combo_overlaps_flagged, compute_effect_caps, compute_flagged_combos
from .symbols import _safe_path, list_symbols


def random_geometry_transform(arr, rng=None):
    """Apply random mirror / rotation using PIL. Returns (new_arr, geom_dict)."""
    from PIL import Image
    import numpy as np

    if rng is None:
        rng = random

    geom = {}
    img = Image.fromarray(arr)

    if rng.random() < 0.5:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        geom["mirror_h"] = 1.0

    if rng.random() < 0.5:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        geom["mirror_v"] = 1.0

    rot = rng.choice([0, 90, 180, 270])
    if rot == 90:
        img = img.transpose(Image.ROTATE_90)
        geom["rot_90"] = 1.0
    elif rot == 180:
        img = img.transpose(Image.ROTATE_180)
        geom["rot_180"] = 1.0
    elif rot == 270:
        img = img.transpose(Image.ROTATE_270)
        geom["rot_270"] = 1.0

    return np.array(img, dtype=arr.dtype), geom


def augment_preview(body: dict) -> tuple[dict | None, str]:
    """Render SVG → N augmented PNGs in memory, return base64 list."""
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
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER
        from src.svg_utils import _render_svg_to_png

        png_bytes = _render_svg_to_png(svg_path)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if img.width != size or img.height != size:
            img = img.resize((size, size), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)

        effect_caps = compute_effect_caps()
        flagged_combos = compute_flagged_combos()

        images_out: list[dict] = []
        rng = random.Random()
        for _ in range(count):
            if randomize_per:
                for _attempt in range(12):
                    n = rng.randint(3, 7)
                    picked = rng.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                    if not combo_overlaps_flagged(picked, flagged_combos):
                        break
                varied = {
                    name: round(
                        min(rng.uniform(0.15, 0.65), effect_caps.get(name, 1.0)), 2
                    )
                    for name in picked
                }
            elif effects:
                varied = {
                    name: round(
                        float(
                            np.clip(
                                intensity * rng.uniform(0.7, 1.3),
                                0.0,
                                effect_caps.get(name, 1.0),
                            )
                        ),
                        3,
                    )
                    for name, intensity in effects.items()
                    if intensity > 0.0
                }
            else:
                varied = {}
            frame, geom = random_geometry_transform(arr, rng)
            varied = {**geom, **varied}
            out = apply_effects(frame, varied)
            buf = io.BytesIO()
            Image.fromarray(out).save(buf, format="PNG")
            images_out.append(
                {
                    "src": "data:image/png;base64,"
                    + base64.b64encode(buf.getvalue()).decode("ascii"),
                    "effects": varied,
                }
            )

        return {"images": images_out}, ""
    except Exception as exc:
        return None, str(exc)


def augment_generate(body: dict) -> tuple[dict | None, str]:
    """Generate count augmented PNG variants to disk."""
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
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        svg_text = svg_path.read_text(encoding="utf-8")
        png_bytes = cairosvg.svg2png(
            bytestring=svg_text.encode("utf-8"),
            output_width=size,
            output_height=size,
        )
        base_arr = np.array(
            Image.open(io.BytesIO(png_bytes)).convert("RGB"), dtype=np.uint8
        )
        stem = base.stem
        images_b64 = []
        effect_caps = compute_effect_caps()
        flagged_combos = compute_flagged_combos()
        rng = random.Random()

        for i in range(count):
            if randomize_per:
                for _attempt in range(12):
                    n = rng.randint(3, 7)
                    picked = rng.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                    if not combo_overlaps_flagged(picked, flagged_combos):
                        break
                varied = {
                    name: round(
                        min(rng.uniform(0.15, 0.65), effect_caps.get(name, 1.0)), 2
                    )
                    for name in picked
                }
            else:
                varied = {
                    name: float(
                        np.clip(
                            intensity * rng.uniform(0.7, 1.3),
                            0.0,
                            effect_caps.get(name, 1.0),
                        )
                    )
                    for name, intensity in effects.items()
                    if intensity > 0.0
                }

            frame, geom = random_geometry_transform(base_arr, rng)
            varied = {**geom, **varied}
            arr = apply_effects(frame, varied)
            fname = out_dir / f"{stem}_aug_{i + 1:04d}.png"
            Image.fromarray(arr).save(fname)

            if return_images:
                buf = io.BytesIO()
                Image.fromarray(arr).save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                images_b64.append(
                    {
                        "src": f"data:image/png;base64,{b64}",
                        "effects": varied,
                    }
                )

        result: dict = {"saved": count, "output_dir": str(out_dir.resolve())}
        if return_images:
            result["images"] = images_b64
        return result, ""
    except Exception as exc:
        return None, str(exc)


def tight_bbox_yolo(arr) -> tuple | None:
    """Return YOLO-normalised (cx, cy, w, h) bounding box for non-white pixels."""
    import numpy as np

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
    return (cx, cy, bw, bh)




def augment_batch(body: dict, batch_cancel: threading.Event):
    """Generator: yields SSE progress events while augmenting a filtered symbol set."""
    source = body.get("source", "").strip()
    standard = body.get("standard", "").strip()
    effects = {k: float(v) for k, v in body.get("effects", {}).items()}
    size = max(64, min(2048, int(body.get("size", 512))))
    count = max(1, min(200, int(body.get("count", 1))))
    out_str = (body.get("output_dir") or "").strip() or "./augmented"
    rand_per = bool(body.get("randomize_per_image", False))
    fmt = body.get("format", "png")

    symbols = list_symbols()
    if source:
        symbols = [s for s in symbols if s["source"] == source]
    if standard:
        symbols = [s for s in symbols if s["standard"] == standard]
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
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects, _APPLY_ORDER
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

    def sym_cls_name(sym_id: str) -> str:
        parts = sym_id.split("/")
        return f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else parts[-1]

    class_map = {}
    n_classes = 0
    img_dir = out_dir

    if fmt == "yolo":
        all_cats = sorted({sym_cls_name(sym["path"]) for sym in symbols})
        class_map = {cls: i for i, cls in enumerate(all_cats)}
        n_classes = len(all_cats)
        img_dir = out_dir / "images" / "train"
        lbl_dir = out_dir / "labels" / "train"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        names_block = "\n".join(f"  {i}: {c}" for i, c in enumerate(all_cats))
        (out_dir / "data.yaml").write_text(
            f"path: {out_dir.resolve()}\n"
            f"train: images/train\n"
            f"nc: {n_classes}\n"
            f"names:\n{names_block}\n",
            encoding="utf-8",
        )

    processed = saved = skipped = errors = 0
    rng = random.Random()

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
            png_bytes = _render_svg_to_png(svg_path)
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            if img.width != size or img.height != size:
                img = img.resize((size, size), Image.LANCZOS)
            arr = np.array(img, dtype=np.uint8)

            stem = sym_id.replace("/", "_")

            if fmt == "yolo":
                cls_idx = class_map.get(sym_cls_name(sym_id), 0)

            for j in range(count):
                if rand_per:
                    for _attempt in range(12):
                        n = rng.randint(3, 7)
                        picked = rng.sample(_APPLY_ORDER, min(n, len(_APPLY_ORDER)))
                        if not combo_overlaps_flagged(picked, flagged_combos):
                            break
                    varied = {
                        nm: round(
                            min(rng.uniform(0.15, 0.65), effect_caps.get(nm, 1.0)), 2
                        )
                        for nm in picked
                    }
                elif effects:
                    varied = {
                        nm: float(
                            np.clip(
                                intensity * rng.uniform(0.7, 1.3),
                                0.0,
                                effect_caps.get(nm, 1.0),
                            )
                        )
                        for nm, intensity in effects.items()
                        if intensity > 0.0
                    }
                else:
                    varied = {}

                out_arr = apply_effects(arr.copy(), varied)
                fname = f"{stem}_aug_{j + 1:04d}"
                Image.fromarray(out_arr).save(img_dir / f"{fname}.png")

                if fmt == "yolo":
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

    done = {
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
    """Generate all 1-, 2-, and 3-effect combinations of the selected effects."""
    import itertools

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
        import numpy as np
        from PIL import Image
        from src.degradation import apply_effects
        from src.svg_utils import _render_svg_to_png

        png_bytes = _render_svg_to_png(svg_path)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if img.width != size or img.height != size:
            img = img.resize((size, size), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)

        effect_names = list(effects.keys())
        combos: list[dict] = []

        for n in range(1, min(max_combo, len(effect_names)) + 1):
            for combo in itertools.combinations(effect_names, n):
                combo_effects = {name: effects[name] for name in combo}
                out = apply_effects(arr.copy(), combo_effects)
                buf = io.BytesIO()
                Image.fromarray(out).save(buf, format="PNG")
                b64 = "data:image/png;base64," + base64.b64encode(
                    buf.getvalue()
                ).decode("ascii")
                combos.append(
                    {"src": b64, "label": " + ".join(combo), "effects": combo_effects}
                )

        return {"combos": combos, "total": len(combos)}, ""
    except Exception as exc:
        return None, str(exc)
