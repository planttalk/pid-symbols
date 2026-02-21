"""
augmentation.py
--------------------
Image augmentation (albumentations + Pillow) and YOLO v8 dataset export.

Heavy dependencies (cairosvg, albumentations, numpy, Pillow) are imported
lazily inside functions so the module can be imported without them installed.
"""

import io
import json
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
) -> None:
    """Export YOLO v8 datasets (one per standard) from the symbol registry."""
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

    if not symbols:
        print("No eligible symbols found in registry.")
        return

    by_standard: dict[str, list[dict]] = {}
    for sym in symbols:
        std = sym.get("standard", "unknown")
        by_standard.setdefault(std, []).append(sym)

    transform = _build_augment_transform_yolo()
    total_written = 0
    total_skipped = 0

    for std, sym_list in sorted(by_standard.items()):
        std_slug = _safe_std_slug(std)
        dataset_dir = output_dir / f"yolo-{std_slug}"
        img_dir     = dataset_dir / "images" / "train"
        lbl_dir     = dataset_dir / "labels" / "train"

        categories = sorted({s.get("category", "unknown") for s in sym_list})
        class_map  = {cat: idx for idx, cat in enumerate(categories)}

        yaml_content = (
            f"path: {dataset_dir.resolve()}\n"
            f"train: images/train\n"
            f"nc: {len(categories)}\n"
            f"names: [{', '.join(repr(c) for c in categories)}]\n"
        )

        print(f"\n[{std}]  {len(sym_list)} symbols, {len(categories)} classes")

        if not dry_run:
            dataset_dir.mkdir(parents=True, exist_ok=True)
            (dataset_dir / "data.yaml").write_text(yaml_content, encoding="utf-8")
            img_dir.mkdir(parents=True, exist_ok=True)
            lbl_dir.mkdir(parents=True, exist_ok=True)

        for sym in sym_list:
            cat        = sym.get("category", "unknown")
            class_idx  = class_map[cat]
            svg_rel    = sym.get("svg_path", "")
            svg_file   = (paths.REPO_ROOT / svg_rel) if svg_rel else None

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
                            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                            resample=Image.LANCZOS,
                        )
                base_arr = np.array(base)
            except Exception:
                total_skipped += 1
                continue

            bbox = _tight_bbox_normalized(base_arr)
            if bbox is None:
                total_skipped += 1
                continue

            cx, cy, bw, bh = bbox
            stem = sym.get("id", svg_file.stem).replace("/", "_")

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

                out_name = f"{stem}_aug{i + 1}"
                if not dry_run:
                    Image.fromarray(aug_img).save(img_dir / (out_name + ".png"), format="PNG")
                    lbl_lines = "\n".join(
                        f"{lbl} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}"
                        for lbl, box in zip(aug_labels, aug_bboxes)
                    )
                    (lbl_dir / (out_name + ".txt")).write_text(lbl_lines + "\n", encoding="utf-8")
                total_written += 1

    print(f"\n{'='*60}")
    print(f"  Standards : {len(by_standard)}")
    print(f"  Written   : {total_written if not dry_run else 0}")
    print(f"  Skipped   : {total_skipped}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output    : {output_dir}")
    print(f"{'='*60}")
