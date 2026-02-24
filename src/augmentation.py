"""
augmentation.py
--------------------
Image augmentation (albumentations + Pillow) and YOLO dataset export.

Generates:
  - Per-symbol augmented images (single object, N augmentations each).
  - Multi-symbol composite images (several symbols placed on one canvas).

Both splits (train / val, 80/20) are produced for each dataset.
data.yaml uses the dict-format names compatible with YOLOv8-v12.

Heavy dependencies (cairosvg, albumentations, numpy, Pillow) are imported
lazily inside functions so the module can be imported without them installed.
"""

import io
import json
import random
from pathlib import Path

from . import paths
from .svg_utils import _render_svg_to_png
from .utils import _safe_std_slug, _source_slug_from_path


def _build_augment_transform():
    """Return the default Albumentations augmentation pipeline."""
    import albumentations as A

    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=15, p=0.5),
        A.RandomBrightnessContrast(p=0.3),
        A.GaussNoise(p=0.2),
    ])


def _build_augment_transform_yolo():
    """Return an Albumentations pipeline compatible with YOLO bounding-box labels."""
    import albumentations as A

    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=15, p=0.5),
            A.RandomBrightnessContrast(p=0.3),
            A.GaussNoise(p=0.2),
        ],
        bbox_params=A.BboxParams(
            format="yolo",
            label_fields=["class_labels"],
            min_visibility=0.1,
        ),
    )


def _tight_bbox_normalized(img_arr) -> tuple | None:
    """Return (cx, cy, w, h) normalized to [0,1] for the non-white region, or None if blank."""
    import numpy as np

    gray = img_arr.mean(axis=2)
    mask = gray < 250

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    if not rows.any():
        return None

    r_min, r_max = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    c_min, c_max = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))

    H, W = img_arr.shape[:2]
    cx = ((c_min + c_max) / 2) / W
    cy = ((r_min + r_max) / 2) / H
    bw = (c_max - c_min + 1) / W
    bh = (r_max - r_min + 1) / H

    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    bw = max(0.0, min(1.0, bw))
    bh = max(0.0, min(1.0, bh))

    return (cx, cy, bw, bh)


def _scale_to_canvas(img_arr, canvas_size: int,
                     min_frac: float = 0.12, max_frac: float = 0.32):
    """Scale img_arr so its longest side occupies a random fraction of canvas_size."""
    from PIL import Image
    h, w   = img_arr.shape[:2]
    target = random.uniform(min_frac, max_frac) * canvas_size
    scale  = target / max(h, w, 1)
    nw     = max(1, int(round(w * scale)))
    nh     = max(1, int(round(h * scale)))
    return __import__('numpy').array(
        Image.fromarray(img_arr).resize((nw, nh), Image.LANCZOS)
    )


def _box_iou(a: tuple, b: tuple) -> float:
    """Pixel-space intersection-over-union for two (x1,y1,x2,y2) boxes."""
    ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    return inter / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter)


def _compose_symbols_image(
    pool: list[tuple],   # [(img_arr, class_idx), …]  — mixed categories OK
    canvas_size: int = 640,
) -> tuple:             # (canvas_arr, [(class_idx, cx, cy, w, h), …])
    """Place a random selection of symbols from the pool onto a white canvas.

    Uses random.choices so the same symbol can appear more than once (useful
    when the pool is small).  Tries up to 40 positions per symbol to keep
    IoU < 0.15 with already-placed boxes.  Returns the composite array and
    the normalized YOLO bounding boxes for every successfully placed symbol.
    """
    import numpy as np

    if not pool:
        return np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8), []

    n_sym    = random.randint(min(2, len(pool)), min(8, len(pool)))
    selected = random.choices(pool, k=n_sym)

    canvas  = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    labels: list[tuple] = []
    placed: list[tuple] = []      # (x1, y1, x2, y2) pixel boxes

    for img_arr, class_idx in selected:
        scaled = _scale_to_canvas(img_arr, canvas_size)
        sh, sw = scaled.shape[:2]
        if sw > canvas_size or sh > canvas_size:
            continue

        for _ in range(40):
            x1  = random.randint(0, canvas_size - sw)
            y1  = random.randint(0, canvas_size - sh)
            box = (x1, y1, x1 + sw, y1 + sh)
            if any(_box_iou(box, p) > 0.15 for p in placed):
                continue

            # Composite: non-white pixels of symbol overwrite canvas
            mask = scaled.mean(axis=2) < 250
            canvas[y1:y1+sh, x1:x1+sw][mask] = scaled[mask]
            placed.append(box)

            # Tight bbox of symbol content in canvas coords
            rows = __import__('numpy').any(mask, axis=1)
            cols = __import__('numpy').any(mask, axis=0)
            if not rows.any():
                break
            r_min = int(__import__('numpy').argmax(rows))
            r_max = int(len(rows) - 1 - __import__('numpy').argmax(rows[::-1]))
            c_min = int(__import__('numpy').argmax(cols))
            c_max = int(len(cols) - 1 - __import__('numpy').argmax(cols[::-1]))

            cx = (x1 + (c_min + c_max) / 2) / canvas_size
            cy = (y1 + (r_min + r_max) / 2) / canvas_size
            bw = (c_max - c_min + 1)         / canvas_size
            bh = (r_max - r_min + 1)         / canvas_size
            labels.append((class_idx,
                           max(0., min(1., cx)), max(0., min(1., cy)),
                           max(0., min(1., bw)), max(0., min(1., bh))))
            break

    return canvas, labels


def augment_single_svg(
    svg_path: Path,
    output_dir: Path,
    count: int,
    dry_run: bool,
    transform,
    min_size: int,
) -> tuple[int, int]:
    """Render a single SVG and write N augmented PNGs to output_dir."""
    import numpy as np
    from PIL import Image

    try:
        png_bytes = _render_svg_to_png(svg_path)
        base = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if min_size > 0:
            w, h = base.size
            short = min(w, h)
            if short < min_size:
                scale = min_size / max(short, 1)
                new_w = max(1, int(round(w * scale)))
                new_h = max(1, int(round(h * scale)))
                base = base.resize((new_w, new_h), resample=Image.LANCZOS)
        base_arr = np.array(base)
    except Exception:
        return 0, 1

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for i in range(count):
        try:
            augmented = transform(image=base_arr)["image"]
            if not dry_run:
                out_name = f"{svg_path.stem}_aug{i + 1}.png"
                Image.fromarray(augmented).save(output_dir / out_name, format="PNG")
            created += 1
        except Exception:
            return created, 1

    return created, 0


def augment_svgs(input_dir: Path, output_dir: Path, count: int, dry_run: bool, min_size: int) -> None:
    """Augment SVGs in input_dir and write PNGs to output_dir (no JSON/registry)."""
    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}")
        return

    svg_files = [p for p in sorted(input_dir.rglob("*.svg")) if "_debug" not in p.stem]
    total = len(svg_files)
    transform = _build_augment_transform()

    created = 0
    errors = 0

    for idx, svg_path in enumerate(svg_files, 1):
        rel = svg_path.relative_to(input_dir)
        target_dir = output_dir / rel.parent
        made, err = augment_single_svg(svg_path, target_dir, count, dry_run, transform, min_size)
        created += made
        errors += err
        print(f"  [{idx:>4}/{total}] {rel}")

    print(f"\n{'='*60}")
    print(f"  Inputs   : {total}")
    print(f"  PNGs     : {created if not dry_run else 0}")
    print(f"  Errors   : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output   : {output_dir}")
    print(f"{'='*60}")


def export_yolo_datasets(
    registry_path: Path,
    output_dir: Path,
    count: int,
    dry_run: bool,
    min_size: int,
    origin: str | None = None,
    standard: str | None = None,
    compose_count: int = 20,
) -> None:
    """Export YOLO-format datasets (one per standard group) from the symbol registry.

    For each standard group this generates:
      images/train/   images/val/    (80 / 20 split)
      labels/train/   labels/val/

    Two kinds of images:
      1. Per-symbol augmented — one symbol per image, `count` augmentations each.
      2. Multi-symbol composite — `compose_count` images with 2–8 randomly placed
         symbols from the full pool (mixed categories; each gets its own label row).

    data.yaml uses the dict-format `names` field required by YOLOv8–v12.
    """
    import numpy as np
    from PIL import Image

    if not registry_path.exists():
        print(f"Error: registry not found: {registry_path}")
        return

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error loading registry: {exc}")
        return

    symbols = registry.get("symbols", [])
    symbols = [
        s for s in symbols
        if s.get("standard", "").lower() not in ("", "unknown")
        and s.get("classification", {}).get("confidence", "none") != "none"
    ]

    # Apply origin / standard filters
    if origin:
        symbols = [s for s in symbols if s.get("id", "").split("/")[0] == origin]
    if standard:
        symbols = [s for s in symbols
                   if s.get("standard", "").lower() == standard.lower()]

    if not symbols:
        print("No eligible symbols found after filtering.")
        return

    by_standard: dict[str, list[dict]] = {}
    for sym in symbols:
        by_standard.setdefault(sym.get("standard", "unknown"), []).append(sym)

    transform     = _build_augment_transform_yolo()
    total_written = 0
    total_skipped = 0

    for std, sym_list in sorted(by_standard.items()):
        std_slug    = _safe_std_slug(std)
        dataset_dir = output_dir / f"yolo-{std_slug}"
        img_train   = dataset_dir / "images" / "train"
        img_val     = dataset_dir / "images" / "val"
        lbl_train   = dataset_dir / "labels" / "train"
        lbl_val     = dataset_dir / "labels" / "val"

        categories = sorted({s.get("category", "unknown") for s in sym_list})
        class_map  = {cat: idx for idx, cat in enumerate(categories)}

        # dict-format names required by YOLOv8-v12
        names_lines = "\n".join(f"  {i}: {c}" for i, c in enumerate(categories))
        yaml_content = (
            f"path: {dataset_dir.resolve()}\n"
            f"train: images/train\n"
            f"val: images/val\n"
            f"nc: {len(categories)}\n"
            f"names:\n{names_lines}\n"
        )

        print(f"\n[{std}]  {len(sym_list)} symbols, {len(categories)} classes"
              + (f"  [origin: {origin}]" if origin else ""))

        if not dry_run:
            for d in (img_train, img_val, lbl_train, lbl_val):
                d.mkdir(parents=True, exist_ok=True)
            (dataset_dir / "data.yaml").write_text(yaml_content, encoding="utf-8")

        # Render all symbols; build pool for composite generation
        pool: list[tuple] = []      # (img_arr, class_idx) — all categories mixed
        aug_global = 0              # monotonic counter for train/val split (mod 5)

        for sym in sym_list:
            cat       = sym.get("category", "unknown")
            class_idx = class_map[cat]
            svg_rel   = sym.get("svg_path", "")
            svg_file  = (paths.REPO_ROOT / svg_rel) if svg_rel else None

            if not svg_file or not svg_file.exists():
                total_skipped += 1
                continue

            try:
                png_bytes = _render_svg_to_png(svg_file)
                base      = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                if min_size > 0:
                    w, h  = base.size
                    short = min(w, h)
                    if short < min_size:
                        scale = min_size / max(short, 1)
                        base  = base.resize(
                            (max(1, int(round(w * scale))),
                             max(1, int(round(h * scale)))),
                            resample=Image.LANCZOS,
                        )
                base_arr = np.array(base)
            except Exception:
                total_skipped += 1
                continue

            pool.append((base_arr, class_idx))

            bbox = _tight_bbox_normalized(base_arr)
            if bbox is None:
                total_skipped += 1
                continue

            cx, cy, bw, bh = bbox
            stem = sym.get("id", svg_file.stem).replace("/", "_")

            # Per-symbol augmented images
            for i in range(count):
                try:
                    result = transform(
                        image=base_arr,
                        bboxes=[[cx, cy, bw, bh]],
                        class_labels=[class_idx],
                    )
                    aug_img    = result["image"]
                    aug_bboxes = result["bboxes"]
                    aug_labels = result["class_labels"]
                except Exception:
                    continue

                if not aug_bboxes:
                    continue

                is_val   = (aug_global % 5 == 0)
                out_name = f"{stem}_aug{i + 1}"
                i_dir    = img_val   if is_val else img_train
                l_dir    = lbl_val   if is_val else lbl_train

                if not dry_run:
                    Image.fromarray(aug_img).save(i_dir / (out_name + ".png"), format="PNG")
                    lbl_lines = "\n".join(
                        f"{lbl} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}"
                        for lbl, box in zip(aug_labels, aug_bboxes)
                    )
                    (l_dir / (out_name + ".txt")).write_text(lbl_lines + "\n", encoding="utf-8")

                total_written += 1
                aug_global    += 1

        # Multi-symbol composite images
        if pool and compose_count > 0:
            print(f"  Compositing {compose_count} multi-symbol images...")
            for i in range(compose_count):
                canvas, comp_labels = _compose_symbols_image(pool)
                if not comp_labels:
                    continue

                is_val    = (i % 5 == 0)
                comp_name = f"composite_{std_slug}_{i + 1}"
                i_dir     = img_val   if is_val else img_train
                l_dir     = lbl_val   if is_val else lbl_train

                if not dry_run:
                    Image.fromarray(canvas).save(
                        i_dir / (comp_name + ".png"), format="PNG"
                    )
                    lbl_lines = "\n".join(
                        f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"
                        for cls, cx, cy, bw, bh in comp_labels
                    )
                    (l_dir / (comp_name + ".txt")).write_text(
                        lbl_lines + "\n", encoding="utf-8"
                    )
                total_written += 1

    print(f"\n{'='*60}")
    print(f"  Standards     : {len(by_standard)}")
    if origin:
        print(f"  Origin filter : {origin}")
    if standard:
        print(f"  Std filter    : {standard}")
    print(f"  Written       : {total_written if not dry_run else 0}")
    print(f"  Skipped       : {total_skipped}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output        : {output_dir}")
    print(f"{'='*60}")
