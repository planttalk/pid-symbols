"""
main.py
--------------------
Recursively scans input/ for SVG files, classifies each one,
and writes to processed/ (mirrored by standard/category):
  - processed/<standard>/<category>/<normalized_stem>.svg   (copy, snake_case)
  - processed/<standard>/<category>/<normalized_stem>.json  (metadata)
  - processed/registry.json                                  (master index)

Filename normalization: all output filenames are snake_case lowercase.
  "Agitator (general), stirrer (general) (ISO 10628-2).svg"
      -> "agitator_general_stirrer_general.svg"

Classification strategies (applied in order):
  0. Reference sheet detection      (multi-symbol sheets → reference_sheet)
  1. autocad-parser folder naming   (isa_actuator_svg/ → ISA / actuator)
  2. Filename standard tag          ("(ISO 10628-2)" / "(DIN 2429)")
  3. Downloaded subfolder map       (agitators/ → agitator)
  4. Generated filename prefix      (valve_ball → valve)
  5. Filename keyword heuristics    (fallback)
  6. unknown                        (if nothing matches)

Usage:
    python main.py
    python main.py --dry-run
    python main.py --augment --augment-count 5 --augment-min-size 256
    python main.py --augment-source processed --augment-count 5 --augment-min-size 256
    python main.py --augment-source completed --augment-count 5 --augment-min-size 256
    python main.py --export-completed ./exported
    python main.py --export-completed ./exported --export-source ./processed
    python main.py --migrate --dry-run
    python main.py --migrate
    python main.py --export-yolo ./yolo-out --augment-count 3
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Paths
REPO_ROOT     = Path(__file__).resolve().parent   # repo root = same dir as main.py
INPUT_DIR     = REPO_ROOT / "input"
PROCESSED_DIR = REPO_ROOT / "processed"

SCHEMA_VERSION = "1.0.0"

# Classification maps

# autocad-parser subfolder → (standard, category)
AUTOCAD_FOLDER_MAP: dict[str, tuple[str, str]] = {
    "isa_actuator_svg":      ("ISA",        "actuator"),
    "isa_equipment1_svg":    ("ISA",        "equipment"),
    "isa_equipment2_svg":    ("ISA",        "equipment"),
    "isa_flow_svg":          ("ISA",        "flow"),
    "isa_relief_valves_svg": ("ISA",        "relief_valve"),
    "isa_valves_svg":        ("ISA",        "valve"),
    "iso_agitators_svg":     ("ISO 10628-2","agitator"),
    "iso_equipment_svg":     ("ISO 10628-2","equipment"),
    "iso_instruments_svg":   ("ISO 10628-2","instrument"),
    "iso_nozzles_svg":       ("ISO 10628-2","nozzle"),
}

# pid-symbols-generator/downloaded subfolder → category
DOWNLOADED_FOLDER_MAP: dict[str, str] = {
    "agitators":                                    "agitator",
    "apparaturs_elements":                          "apparatus_element",
    "centrifuges":                                  "centrifuge",
    "check_valves":                                 "check_valve",
    "columns":                                      "column",
    "compressors":                                  "compressor",
    "cooling_towers":                               "cooling_tower",
    "crushing_machines":                            "crushing_machine",
    "driers":                                       "drier",
    "engines":                                      "engine",
    "fans":                                         "fan",
    "filters":                                      "filter",
    "fittings":                                     "fitting",
    "heat_exchangers":                              "heat_exchanger",
    "internals":                                    "internal",
    "lifting,_conveying_and_transport_equipment":   "lifting_equipment",
    "liquid_pumps":                                 "pump",
    "mixers_and_kneaders":                          "mixer",
    "pipes":                                        "pipe",
    "screening_devices,_sieves,_and_rakes":         "screening_device",
    "separators":                                   "separator",
    "shaping_machines":                             "shaping_machine",
    "steam_generators,_furnaces,_recooling_device": "steam_generator",
    "tanks_and_containers":                         "tank",
    "valves":                                       "valve",
    "ventilation":                                  "ventilation",
}

# pid-symbols-generator/generated filename prefix → (standard, category)
GENERATED_PREFIX_MAP: dict[str, tuple[str, str]] = {
    "valve_":     ("ISA", "valve"),
    "cv_":        ("ISA", "control_valve"),
    "actuator_":  ("ISA", "actuator"),
    "equip_":     ("ISA", "equipment"),
    "line_":      ("ISA", "line_type"),
    "logic_":     ("ISA", "logic"),
    "piping_":    ("ISA", "piping"),
    "safety_":    ("ISA", "safety"),
    "regulator_": ("ISA", "regulator"),
    "acc_":       ("ISA", "accessory"),
    "conn_":      ("ISA", "connection"),
    "ann_":       ("ISA", "annotation"),
    "primary_":   ("ISA", "primary_element"),
    "bubble_":    ("ISA", "instrument_bubble"),
    "fail_":      ("ISA", "fail_position"),
}

# Generic keyword heuristics applied to stem (lowercase) → category
KEYWORD_HEURISTICS: list[tuple[str, str]] = [
    ("valve",         "valve"),
    ("actuator",      "actuator"),
    ("pump",          "pump"),
    ("compressor",    "compressor"),
    ("agitator",      "agitator"),
    ("stirrer",       "agitator"),
    ("heat_exchanger","heat_exchanger"),
    ("exchanger",     "heat_exchanger"),
    ("filter",        "filter"),
    ("separator",     "separator"),
    ("centrifuge",    "centrifuge"),
    ("column",        "column"),
    ("tank",          "tank"),
    ("vessel",        "vessel"),
    ("reactor",       "reactor"),
    ("furnace",       "furnace"),
    ("boiler",        "steam_generator"),
    ("conveyor",      "lifting_equipment"),
    ("crusher",       "crushing_machine"),
    ("dryer",         "drier"),
    ("drier",         "drier"),
    ("fan",           "fan"),
    ("blower",        "fan"),
    ("instrument",    "instrument"),
    ("sensor",        "instrument"),
    ("nozzle",        "nozzle"),
    ("relief",        "relief_valve"),
    ("safety",        "safety"),
    ("solenoid",      "actuator"),
    ("diaphragm",     "actuator"),
    ("piston",        "actuator"),
    ("positioner",    "accessory"),
    ("handwheel",     "actuator"),
    ("bubble",        "instrument_bubble"),
    ("instrument",    "instrument"),
    ("logic",         "logic"),
    ("interlock",     "logic"),
    ("orifice",       "primary_element"),
    ("thermowell",    "primary_element"),
    ("venturi",       "primary_element"),
    ("pipe",          "piping"),
    ("fitting",       "fitting"),
    ("flange",        "fitting"),
    ("mixer",         "mixer"),
    ("kneader",       "mixer"),
    ("gear",          "drive"),
    ("motor",         "drive"),
    ("turbine",       "drive"),
    ("engine",        "drive"),
    # Additional heuristics for downloaded/ root files
    ("autoclave",     "reactor"),
    ("bag",           "tank"),
    ("funnel",        "fitting"),
    ("gas bottle",    "tank"),
    ("gas cylinder",  "tank"),
    ("knock-out",     "separator"),
    ("knockout",      "separator"),
    ("knock_out",     "separator"),
    ("liftequip",     "lifting_equipment"),
    ("lift equip",    "lifting_equipment"),
    ("sieve",         "screening_device"),
    ("steam trap",    "fitting"),
    ("steam_trap",    "fitting"),
    ("dust trap",     "filter"),
    ("dust_trap",     "filter"),
    ("elutriator",    "separator"),
    ("viewing glass", "instrument"),
    ("viewing_glass", "instrument"),
    ("computer function", "instrument_bubble"),
    ("control function",  "instrument_bubble"),
    ("discrete instrument", "instrument_bubble"),
    ("scrubber",      "separator"),
    ("cyclone",       "separator"),
    ("strainer",      "filter"),
    ("screen",        "screening_device"),
    ("hopper",        "tank"),
    ("bin",           "tank"),
    ("silo",          "tank"),
    ("evaporator",    "heat_exchanger"),
    ("condenser",     "heat_exchanger"),
    ("reboiler",      "heat_exchanger"),
    ("cooler",        "heat_exchanger"),
    ("heater",        "heat_exchanger"),
    ("spray nozzle",  "nozzle"),
    ("spray_nozzle",  "nozzle"),
    ("manhole",       "apparatus_element"),
    ("support",       "apparatus_element"),
    ("socket",        "nozzle"),
    ("vent",          "piping"),
]

# Files that are reference sheets / full drawings — not individual symbols
_REFERENCE_SHEET_PATTERNS: list[str] = [
    r"symbols\s+sheet\s+\d",
    r"symbols\s+iso",
    r"p&id\s+x\d",
    r"p&id\s+drawing",
]
_REFERENCE_RE = re.compile(
    "|".join(_REFERENCE_SHEET_PATTERNS), re.IGNORECASE
)

# Pattern to extract standard from filename: "(ISO 10628-2)" or "(DIN 2429)"
_STANDARD_RE = re.compile(r'\(\s*((?:ISO|DIN|ISA)\s*[\d\-]+(?:-\d+)?)\s*\)', re.IGNORECASE)

# Helpers

def _extract_standard_from_name(stem: str) -> str | None:
    """Return 'ISO 10628-2', 'DIN 2429', etc. if embedded in filename, else None."""
    m = _STANDARD_RE.search(stem)
    if m:
        return m.group(1).strip()
    return None


def _slugify(text: str) -> str:
    """Lowercase, replace spaces/hyphens/commas with underscores, strip extras."""
    text = text.lower()
    text = re.sub(r"[\s\-,/\\]+", "_", text)
    text = re.sub(r"[^\w]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _display_name_from_stem(stem: str) -> str:
    """Convert snake_case or any stem to Title Case display name."""
    clean = _STANDARD_RE.sub("", stem).strip()
    words = re.split(r"[_\s,\-]+", clean)
    return " ".join(w.capitalize() for w in words if w)


def _rel_or_abs(path: Path, base: Path) -> str:
    """Return path relative to base, or absolute string if outside base."""
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _source_slug_from_path(source_path: str) -> str:
    """Derive a source slug from the relative source path.

    Examples
    --------
    input/autocad-parser/...                       → 'autocad_parser'
    input/pid-symbols-generator/downloaded/...     → 'pid_symbols_generator_downloaded'
    input/pid-symbols-generator/generated/...      → 'pid_symbols_generator_generated'
    anything else                                  → 'unknown_source'
    """
    parts = source_path.replace("\\", "/").split("/")
    # parts[0] should be 'input', parts[1] is the immediate subdirectory
    if len(parts) < 2:
        return "unknown_source"
    top = parts[1]
    if top == "autocad-parser":
        return "autocad_parser"
    if top == "pid-symbols-generator":
        if len(parts) >= 3:
            sub = parts[2].lower()
            return f"pid_symbols_generator_{_slugify(sub)}"
        return "pid_symbols_generator"
    return _slugify(top) or "unknown_source"


def _svg_sha256(content: str) -> str:
    """Return the SHA-256 hex digest of an SVG string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _metadata_quality(meta: dict) -> int:
    """Score a metadata record; higher = better quality (used for deduplication)."""
    score = 0
    score += len(meta.get("snap_points", []))
    if meta.get("notes"):
        score += 2
    if meta.get("completed"):
        score += 5
    conf = meta.get("classification", {}).get("confidence", "none")
    score += {"high": 3, "low": 1, "none": 0}.get(conf, 0)
    return score


def _auto_tags(category: str, subcategory: str) -> list[str]:
    """
    Build a de-duplicated tag list from category + subcategory words.
      category="valve", subcategory="ball"              -> ["valve", "ball"]
      category="actuator", subcategory="diaphragm_actuator" -> ["actuator", "diaphragm"]
    """
    seen: set[str] = set()
    tags: list[str] = []
    for word in [category] + subcategory.split("_"):
        word = word.strip()
        if word and word not in seen:
            seen.add(word)
            tags.append(word)
    return tags


# Ordered list of (compiled regex, replacement) for SVG minification
_MINIFY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # XML declaration
    (re.compile(r'<\?xml[^?]*\?>\s*\n?'), ''),
    # DOCTYPE declaration (handles quoted system identifiers)
    (re.compile(r'<!DOCTYPE[^[>]*(?:\[[^\]]*\])?\s*>\s*\n?', re.DOTALL), ''),
    # <metadata>...</metadata> block
    (re.compile(r'\s*<metadata\b[^>]*>.*?</metadata>\s*', re.DOTALL), '\n'),
    # Inkscape / sodipodi self-closing elements
    (re.compile(r'\s*<(?:sodipodi|inkscape):[^\s>][^/]*/>\s*', re.DOTALL), ''),
    # Inkscape / sodipodi block elements
    (re.compile(
        r'\s*<(sodipodi|inkscape):[^\s>][^>]*>.*?</\1:[^>]*>\s*', re.DOTALL
    ), ''),
    # Collapse 3+ consecutive blank lines to one
    (re.compile(r'\n{3,}'), '\n\n'),
]


def _minify_svg(content: str) -> str:
    """Strip XML declaration, DOCTYPE, and editor metadata bloat from SVG."""
    for pattern, replacement in _MINIFY_PATTERNS:
        content = pattern.sub(replacement, content)
    return content.strip()


def _parse_svg_size(svg_text: str) -> tuple[int, int] | None:
    """Return (width, height) from SVG width/height or viewBox if available."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return None

    def _num(value: str | None) -> float | None:
        if not value:
            return None
        m = re.search(r"[-+]?\d*\.?\d+", value)
        return float(m.group(0)) if m else None

    width = _num(root.get("width"))
    height = _num(root.get("height"))
    if width and height:
        return int(round(width)), int(round(height))

    view_box = root.get("viewBox")
    if view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) >= 4:
            vb_w = _num(parts[2])
            vb_h = _num(parts[3])
            if vb_w and vb_h:
                return int(round(vb_w)), int(round(vb_h))
    return None


def _render_svg_to_png(svg_path: Path) -> bytes:
    """Render an SVG file to PNG bytes at its intrinsic size."""
    import cairosvg

    svg_text = svg_path.read_text(encoding="utf-8", errors="replace")
    size = _parse_svg_size(svg_text)
    if size:
        return cairosvg.svg2png(
            bytestring=svg_text.encode("utf-8"),
            output_width=size[0],
            output_height=size[1],
            background_color="white",
        )
    return cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), background_color="white")


def _build_augment_transform():
    """Return the default Albumentations augmentation pipeline."""
    import albumentations as A

    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=15, p=0.5),
        A.RandomBrightnessContrast(p=0.3),
        A.GaussNoise(p=0.2),
    ])


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

    # Treat pixels with mean value < 250 as non-background
    gray = img_arr.mean(axis=2)
    mask = gray < 250

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    if not rows.any():
        return None  # blank image

    r_min, r_max = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    c_min, c_max = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))

    H, W = img_arr.shape[:2]
    cx = ((c_min + c_max) / 2) / W
    cy = ((r_min + r_max) / 2) / H
    bw = (c_max - c_min + 1) / W
    bh = (r_max - r_min + 1) / H

    # Clamp to [0, 1]
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    bw = max(0.0, min(1.0, bw))
    bh = max(0.0, min(1.0, bh))

    return (cx, cy, bw, bh)


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

    # Filter out reference sheets and truly unknown symbols
    symbols = [
        s for s in symbols
        if s.get("standard", "").lower() not in ("", "unknown")
        and s.get("classification", {}).get("confidence", "none") != "none"
    ]

    if not symbols:
        print("No eligible symbols found in registry.")
        return

    # Group by standard
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

        # Build sorted category list for this standard
        categories = sorted({s.get("category", "unknown") for s in sym_list})
        class_map  = {cat: idx for idx, cat in enumerate(categories)}

        # Write data.yaml (no PyYAML dependency)
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
            svg_file   = (REPO_ROOT / svg_rel) if svg_rel else None

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


def parse_svg_attributes(svg_path: Path) -> dict:
    """Extract dimensions, element count, text presence, creator from SVG."""
    result = {
        "width":         None,
        "height":        None,
        "view_box":      None,
        "element_count": 0,
        "has_text":      False,
        "creator":       None,
    }
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        result["width"]    = root.get("width")
        result["height"]   = root.get("height")
        result["view_box"] = root.get("viewBox")

        drawing_tags = {"path", "circle", "rect", "line",
                        "polyline", "polygon", "ellipse", "use"}
        count = 0
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local in drawing_tags:
                count += 1
            if local == "text":
                result["has_text"] = True
            # Grab creator from RDF dc:title
            if local == "title" and elem.text and result["creator"] is None:
                result["creator"] = elem.text.strip()

        result["element_count"] = count
    except ET.ParseError:
        pass
    return result


# Snap point detection

# Valve-like categories: horizontal in/out connection geometry
_VALVE_CATS = {"valve", "check_valve", "relief_valve", "control_valve", "regulator", "safety"}
# Categories whose connection geometry is best found via open-end stub detection
_OPEN_END_CATS = _VALVE_CATS | {"pump", "compressor", "pipe", "fitting", "connection", "piping", "line_type"}
# Categories rendered as instrument bubbles (circle → cardinal points)
_BUBBLE_CATS = {"instrument_bubble", "instrument", "annotation"}
# Categories whose connection geometry is top/bottom (process/signal)
_ACTUATOR_CATS = {"actuator", "fail_position"}


def _path_open_endpoints(d: str) -> list[tuple[float, float]]:
    """
    Return the start and end coordinates of each non-closed subpath that
    contains at least one straight-line command (L/H/V).
    Pure arc/curve subpaths are skipped — they represent symbol bodies, not stubs.
    Handles both absolute (L/H/V) and relative (l/h/v) commands.
    """
    results: list[tuple[float, float]] = []
    for sub in re.split(r'(?=[Mm])', d.strip()):
        sub = sub.strip()
        if not sub or sub[0].upper() != 'M':
            continue
        if re.search(r'[Zz]', sub):
            continue  # closed path — no open ends
        if not re.search(r'[LlHhVv]', sub):
            continue  # only curves/arcs — skip
        cur = [0.0, 0.0]
        start: tuple[float, float] | None = None
        end: tuple[float, float] | None = None
        for cmd, args in re.findall(r'([MLHVmlhv])((?:[^MLHVZACSQTmlhvzacsqt])*)', sub):
            nums = [float(n) for n in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', args)]
            is_rel = cmd.islower()
            cu = cmd.upper()
            if cu == 'M' and len(nums) >= 2:
                cur[:] = [cur[0] + nums[0] if is_rel else nums[0],
                          cur[1] + nums[1] if is_rel else nums[1]]
                if start is None:
                    start = (cur[0], cur[1])
                end = (cur[0], cur[1])
            elif cu == 'L':
                for i in range(0, len(nums) - 1, 2):
                    cur[:] = [cur[0] + nums[i] if is_rel else nums[i],
                              cur[1] + nums[i + 1] if is_rel else nums[i + 1]]
                    end = (cur[0], cur[1])
            elif cu == 'H':
                for x in nums:
                    cur[0] = cur[0] + x if is_rel else x
                    end = (cur[0], cur[1])
            elif cu == 'V':
                for y in nums:
                    cur[1] = cur[1] + y if is_rel else y
                    end = (cur[0], cur[1])
        if start is not None:
            results.append(start)
        if end is not None and end != start:
            results.append(end)
    return results


def _straight_segments(root) -> list[tuple[tuple, tuple]]:
    """
    Extract straight line segments from <line> elements and M/L/H/V path commands.
    Used to test whether a candidate snap point is an internal junction.
    Handles both absolute (L/H/V) and relative (l/h/v) commands.
    """
    segs: list[tuple[tuple, tuple]] = []
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local == "line":
            try:
                segs.append((
                    (float(elem.get("x1", 0)), float(elem.get("y1", 0))),
                    (float(elem.get("x2", 0)), float(elem.get("y2", 0))),
                ))
            except ValueError:
                pass
        elif local == "path":
            cur = [0.0, 0.0]
            for cmd, args in re.findall(
                r'([MLHVmlhv])((?:[^MLHVZACSQTmlhvzacsqt])*)', elem.get("d", "")
            ):
                nums = [float(n) for n in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', args)]
                is_rel = cmd.islower()
                cu = cmd.upper()
                if cu == 'M' and len(nums) >= 2:
                    cur[:] = [cur[0] + nums[0] if is_rel else nums[0],
                              cur[1] + nums[1] if is_rel else nums[1]]
                elif cu == 'L':
                    for i in range(0, len(nums) - 1, 2):
                        nxt = (cur[0] + nums[i] if is_rel else nums[i],
                               cur[1] + nums[i + 1] if is_rel else nums[i + 1])
                        segs.append((tuple(cur), nxt))
                        cur[:] = list(nxt)
                elif cu == 'H':
                    for x in nums:
                        nxt = (cur[0] + x if is_rel else x, cur[1])
                        segs.append((tuple(cur), nxt))
                        cur[0] = nxt[0]
                elif cu == 'V':
                    for y in nums:
                        nxt = (cur[0], cur[1] + y if is_rel else y)
                        segs.append((tuple(cur), nxt))
                        cur[1] = nxt[1]
    return segs


def _on_segment(px: float, py: float, s: tuple, e: tuple, tol: float = 1.5) -> bool:
    """Return True if (px, py) lies on segment s→e within tolerance."""
    x1, y1, x2, y2 = s[0], s[1], e[0], e[1]
    if not (min(x1, x2) - tol <= px <= max(x1, x2) + tol and
            min(y1, y2) - tol <= py <= max(y1, y2) + tol):
        return False
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-10:
        return abs(px - x1) <= tol and abs(py - y1) <= tol
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / (len_sq ** 0.5) <= tol


def _label_floating(
    floating: list[tuple[int, int]], category: str
) -> list[dict]:
    """Assign semantic IDs to floating endpoints based on category geometry."""
    if not floating:
        return []

    if category in _VALVE_CATS | _OPEN_END_CATS:
        by_x = sorted(floating, key=lambda p: p[0])
        by_y = sorted(floating, key=lambda p: p[1])
        x_span = by_x[-1][0] - by_x[0][0]
        y_span = by_y[-1][1] - by_y[0][1]
        # Choose the dominant axis to determine "in" and "out" ends.
        horizontal = x_span >= y_span
        primary_lo, primary_hi = (
            (by_x[0], by_x[-1]) if horizontal else (by_y[0], by_y[-1])
        )
        result = [
            {"id": "in",  "x": float(primary_lo[0]), "y": float(primary_lo[1])},
            {"id": "out", "x": float(primary_hi[0]), "y": float(primary_hi[1])},
        ]
        # Extra ports (3-way, 4-way, …): preserve all endpoints, labeled p1, p2, …
        extras = [p for p in floating if p != primary_lo and p != primary_hi]
        for i, (x, y) in enumerate(sorted(extras), 1):
            result.append({"id": f"p{i}", "x": float(x), "y": float(y)})
        return result

    pts = sorted(floating)
    if len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        if abs(x1 - x0) >= abs(y1 - y0):
            return [{"id": "in",  "x": float(x0), "y": float(y0)},
                    {"id": "out", "x": float(x1), "y": float(y1)}]
        return [{"id": "signal",  "x": float(x0), "y": float(y0)},
                {"id": "process", "x": float(x1), "y": float(y1)}]

    return [{"id": f"p{i + 1}", "x": float(x), "y": float(y)}
            for i, (x, y) in enumerate(pts)]


def detect_snap_points(svg_path: Path, category: str) -> list[dict]:
    """
    Detect connection snap points for a P&ID SVG symbol.

    Strategy 1 — ID-based: elements whose id/class contains
                 port / conn / inlet / outlet / signal / terminal / snap.
    Strategy 2 — Open-end: floating endpoints of non-closed straight-line paths,
                 filtered to remove internal junctions.
                 Applied only to valve/pipe-like categories where stubs are reliable.
    Strategy 3 — Bubble cardinal: N/S/E/W of the largest <circle> or <ellipse>.
                 Applied to instrument bubble / annotation categories.
    Strategy 4 — Category bbox: bounding-box extremes derived from all segments.
                 Fallback for actuators, equipment, and anything else.

    Returns list of {"id": str, "x": float, "y": float}.
    """
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
    except ET.ParseError:
        return []

    vb_parts = [float(v) for v in (root.get("viewBox") or "").split()]
    if len(vb_parts) >= 4:
        vb_x0, vb_y0, vb_w, vb_h = vb_parts[0], vb_parts[1], vb_parts[2], vb_parts[3]
    else:
        vb_x0 = vb_y0 = vb_w = vb_h = None

    # Strategy 1: semantically labelled elements
    id_pts: list[dict] = []
    for elem in root.iter():
        eid = (elem.get("id") or "").lower()
        ecl = (elem.get("class") or "").lower()
        if any(kw in eid or kw in ecl
               for kw in ("port", "conn", "inlet", "outlet", "signal", "terminal", "snap")):
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            x = y = None
            if local in ("circle", "ellipse"):
                x, y = float(elem.get("cx", 0)), float(elem.get("cy", 0))
            elif local == "rect":
                x = float(elem.get("x", 0)) + float(elem.get("width", 0)) / 2
                y = float(elem.get("y", 0)) + float(elem.get("height", 0)) / 2
            elif local == "line":
                x = (float(elem.get("x1", 0)) + float(elem.get("x2", 0))) / 2
                y = (float(elem.get("y1", 0)) + float(elem.get("y2", 0))) / 2
            if x is not None:
                id_pts.append({"id": eid or f"p{len(id_pts) + 1}",
                               "x": round(x, 2), "y": round(y, 2)})
    if id_pts:
        return id_pts

    segs = _straight_segments(root)

    # Strategy 2: open-end floating endpoint detection (valve/pipe categories only)
    if category in _OPEN_END_CATS:
        all_eps: list[tuple[float, float]] = []
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local == "line":
                try:
                    all_eps += [
                        (float(elem.get("x1", 0)), float(elem.get("y1", 0))),
                        (float(elem.get("x2", 0)), float(elem.get("y2", 0))),
                    ]
                except ValueError:
                    pass
            elif local == "path":
                all_eps.extend(_path_open_endpoints(elem.get("d", "")))

        count: dict[tuple[int, int], int] = {}
        for x, y in all_eps:
            k = (round(x), round(y))
            count[k] = count.get(k, 0) + 1

        floating = [
            pt for pt, n in count.items()
            if n == 1 and not any(
                _on_segment(pt[0], pt[1], s, e)
                for s, e in segs
                if (round(s[0]), round(s[1])) != pt and (round(e[0]), round(e[1])) != pt
            )
        ]
        if floating:
            return _label_floating(floating, category)

    # Strategy 3: circle/ellipse cardinal points for instrument bubbles
    if category in _BUBBLE_CATS:
        bubbles: list[tuple[float, float, float, float]] = []  # (rx, ry, cx, cy)
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local == "circle":
                try:
                    r = float(elem.get("r", 0))
                    bubbles.append((r, r, float(elem.get("cx", 0)), float(elem.get("cy", 0))))
                except ValueError:
                    pass
            elif local == "ellipse":
                try:
                    bubbles.append((
                        float(elem.get("rx", 0)),
                        float(elem.get("ry", 0)),
                        float(elem.get("cx", 0)),
                        float(elem.get("cy", 0)),
                    ))
                except ValueError:
                    pass
        if bubbles:
            rx, ry, ccx, ccy = max(bubbles, key=lambda b: b[0] * b[1])
            return [
                {"id": "north", "x": round(ccx, 2),        "y": round(ccy - ry, 2)},
                {"id": "south", "x": round(ccx, 2),        "y": round(ccy + ry, 2)},
                {"id": "east",  "x": round(ccx + rx, 2),   "y": round(ccy, 2)},
                {"id": "west",  "x": round(ccx - rx, 2),   "y": round(ccy, 2)},
            ]

    # Strategy 4: category bounding-box extremes.
    # Exclude segments that lie entirely on the viewBox boundary — these are
    # Matplotlib background rectangles, not symbol geometry.
    def _on_vb(x: float, y: float) -> bool:
        if vb_w is None or vb_h is None:
            return False
        return (
            abs(x - vb_x0) < 1 or abs(x - (vb_x0 + vb_w)) < 1 or
            abs(y - vb_y0) < 1 or abs(y - (vb_y0 + vb_h)) < 1
        )

    all_pts: list[tuple[float, float]] = [
        p for s, e in segs for p in (s, e)
        if not (_on_vb(*s) and _on_vb(*e))
    ]
    # Also include circle/ellipse extremes (covers symbols with no straight-line segments)
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local == "circle":
            try:
                ccx = float(elem.get("cx", 0))
                ccy = float(elem.get("cy", 0))
                cr  = float(elem.get("r",  0))
                all_pts += [(ccx - cr, ccy), (ccx + cr, ccy),
                            (ccx, ccy - cr), (ccx, ccy + cr)]
            except ValueError:
                pass
        elif local == "ellipse":
            try:
                ccx = float(elem.get("cx", 0))
                ccy = float(elem.get("cy", 0))
                erx = float(elem.get("rx", 0))
                ery = float(elem.get("ry", 0))
                all_pts += [(ccx - erx, ccy), (ccx + erx, ccy),
                            (ccx, ccy - ery), (ccx, ccy + ery)]
            except ValueError:
                pass
    if not all_pts:
        return []

    xs, ys   = [p[0] for p in all_pts], [p[1] for p in all_pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    cx_g = (x_min + x_max) / 2
    cy_g = (y_min + y_max) / 2

    if category in _VALVE_CATS:
        return [
            {"id": "in",      "x": round(x_min, 2), "y": round(cy_g, 2)},
            {"id": "out",     "x": round(x_max, 2), "y": round(cy_g, 2)},
        ]
    if category in _ACTUATOR_CATS:
        return [
            {"id": "signal",  "x": round(cx_g, 2),  "y": round(y_min, 2)},
            {"id": "process", "x": round(cx_g, 2),  "y": round(y_max, 2)},
        ]
    return [
        {"id": "north", "x": round(cx_g, 2),  "y": round(y_min, 2)},
        {"id": "south", "x": round(cx_g, 2),  "y": round(y_max, 2)},
        {"id": "east",  "x": round(x_max, 2), "y": round(cy_g, 2)},
        {"id": "west",  "x": round(x_min, 2), "y": round(cy_g, 2)},
    ]


# Classification strategies

def _strategy_reference_sheet(svg_path: Path) -> dict | None:
    """Strategy 0: Detect full reference sheets / drawings (not individual symbols)."""
    stem = svg_path.stem
    if _REFERENCE_RE.search(stem):
        # Detect standard if present
        standard = _extract_standard_from_name(stem) or "ISO 10628-2"
        return {
            "standard":    standard,
            "category":    "reference_sheet",
            "subcategory": _slugify(stem),
            "confidence":  "high",
            "method":      "reference_sheet_detection",
        }
    return None


def _strategy_autocad_folder(svg_path: Path) -> dict | None:
    """Strategy 1: autocad-parser subfolder naming."""
    try:
        rel_parts = svg_path.relative_to(INPUT_DIR).parts
    except ValueError:
        return None

    if rel_parts[0] != "autocad-parser" or len(rel_parts) < 2:
        return None

    folder = rel_parts[1]
    if folder not in AUTOCAD_FOLDER_MAP:
        return None

    standard, category = AUTOCAD_FOLDER_MAP[folder]
    stem = svg_path.stem

    # pip_/pipa_ prefix → PIP standard, category from folder
    for pip_prefix in PIPING_STEM_PREFIXES:
        if stem.lower().startswith(pip_prefix):
            return {
                "standard":    "PIP",
                "category":    category,
                "subcategory": stem[len(pip_prefix):],
                "confidence":  "high",
                "method":      "autocad_folder_map",
            }

    # Subcategory: strip known standard+category prefix from stem
    subcategory = stem
    for prefix in (
        f"isa_{category}_", f"iso_{category}_",
        "isa_", "iso_", "pip_", "pipa_",
    ):
        if stem.lower().startswith(prefix):
            subcategory = stem[len(prefix):]
            break

    return {
        "standard":    standard,
        "category":    category,
        "subcategory": subcategory,
        "confidence":  "high",
        "method":      "autocad_folder_map",
    }


def _strategy_filename_standard(svg_path: Path) -> dict | None:
    """Strategy 2: Standard tag embedded in filename e.g. '(ISO 10628-2)'."""
    stem = svg_path.stem
    standard = _extract_standard_from_name(stem)
    if not standard:
        return None

    # Try to get category from parent folder
    parent = svg_path.parent.name
    category = DOWNLOADED_FOLDER_MAP.get(parent)

    if not category:
        # Fallback to keyword heuristics on the stem
        stem_low = stem.lower()
        for kw, cat in KEYWORD_HEURISTICS:
            if kw in stem_low:
                category = cat
                break
        else:
            category = "uncategorized"

    # Subcategory: stem minus the standard tag, slugified
    clean_stem = _STANDARD_RE.sub("", stem).strip().strip(",").strip()
    subcategory = _slugify(clean_stem)

    return {
        "standard":    standard,
        "category":    category,
        "subcategory": subcategory,
        "confidence":  "high",
        "method":      "filename_standard_tag",
    }


def _strategy_downloaded_folder(svg_path: Path) -> dict | None:
    """Strategy 3: pid-symbols-generator/downloaded subfolder map."""
    try:
        rel_parts = svg_path.relative_to(INPUT_DIR).parts
    except ValueError:
        return None

    if rel_parts[0] != "pid-symbols-generator":
        return None
    if len(rel_parts) < 2 or rel_parts[1] != "downloaded":
        return None

    # Need at least one more folder level (the category folder)
    if len(rel_parts) < 3:
        return None

    folder = rel_parts[2]
    category = DOWNLOADED_FOLDER_MAP.get(folder)
    if not category:
        return None

    stem = svg_path.stem
    clean_stem = _STANDARD_RE.sub("", stem).strip().strip(",").strip()

    return {
        "standard":    "ISO 10628-2",   # downloaded/ is almost entirely ISO
        "category":    category,
        "subcategory": _slugify(clean_stem),
        "confidence":  "high",
        "method":      "downloaded_folder_map",
    }


def _strategy_generated_prefix(svg_path: Path) -> dict | None:
    """Strategy 4: pid-symbols-generator/generated filename prefix."""
    try:
        rel_parts = svg_path.relative_to(INPUT_DIR).parts
    except ValueError:
        return None

    if rel_parts[0] != "pid-symbols-generator":
        return None
    if len(rel_parts) < 2 or rel_parts[1] != "generated":
        return None

    stem = svg_path.stem
    for prefix, (standard, category) in GENERATED_PREFIX_MAP.items():
        if stem.startswith(prefix):
            return {
                "standard":    standard,
                "category":    category,
                "subcategory": stem[len(prefix):],
                "confidence":  "high",
                "method":      "generated_prefix_map",
            }

    return None


def _strategy_keyword_heuristics(svg_path: Path) -> dict | None:
    """Strategy 5: Generic keyword scan of the filename stem.
    Longer/more-specific keywords are checked before shorter ones."""
    stem_low = svg_path.stem.lower()
    # Sort by keyword length descending so "discrete instrument" beats "instrument"
    for keyword, category in sorted(KEYWORD_HEURISTICS, key=lambda x: -len(x[0])):
        if keyword in stem_low:
            # Try to detect standard from folder ancestry
            standard = "unknown"
            for part in svg_path.parts:
                if part.lower().startswith("isa"):
                    standard = "ISA"
                    break
                if part.lower().startswith("iso"):
                    standard = "ISO 10628-2"
                    break
            return {
                "standard":    standard,
                "category":    category,
                "subcategory": _slugify(svg_path.stem),
                "confidence":  "low",
                "method":      "keyword_heuristic",
            }
    return None


def classify(svg_path: Path) -> dict:
    """Run all strategies in order; fall back to 'unknown'."""
    for strategy in (
        _strategy_reference_sheet,
        _strategy_autocad_folder,
        _strategy_filename_standard,
        _strategy_downloaded_folder,
        _strategy_generated_prefix,
        _strategy_keyword_heuristics,
    ):
        result = strategy(svg_path)
        if result:
            return result

    return {
        "standard":    "unknown",
        "category":    "unknown",
        "subcategory": _slugify(svg_path.stem),
        "confidence":  "none",
        "method":      "unclassified",
    }


# Metadata assembly

# Categories that belong under processed/pip/ regardless of standard
PIP_CATEGORIES = {"piping", "line_type", "pipe"}

# Filename prefixes that identify PIP (Process Industry Practices) standard symbols
PIPING_STEM_PREFIXES = ("pip_", "pipa_")


def _safe_std_slug(standard: str) -> str:
    """Convert 'ISO 10628-2' → 'iso_10628_2' for use in output paths."""
    return _slugify(standard)


def _normalize_stem(stem: str, standard: str) -> str:
    """
    Produce a snake_case lowercase filename stem, prefixed with the standard slug.
    The embedded standard tag is stripped from the body to avoid duplication.
    If the body already starts with the standard slug, or standard is 'unknown',
    no prefix is added.

      "Agitator (general), stirrer (general) (ISO 10628-2)", "ISO 10628-2"
          -> "iso_10628_2_agitator_general_stirrer_general"
      "valve_ball", "ISA"
          -> "isa_valve_ball"
      "isa_actuator_diaphragm_actuator", "ISA"
          -> "isa_actuator_diaphragm_actuator"   (already prefixed)
      "Pump", "unknown"
          -> "pump"                               (no prefix for unknown)
    """
    clean = _STANDARD_RE.sub("", stem).strip().strip(",").strip()
    body  = _slugify(clean) or _slugify(stem)

    std_slug = _safe_std_slug(standard)
    if standard == "unknown" or body.startswith(std_slug + "_") or body == std_slug:
        return body

    # Strip short standard abbreviation prefix to avoid double-prefixing.
    # e.g. body="iso_agitator_foo", std_slug="iso_10628_2" → strip "iso_" → "agitator_foo"
    for short in ("isa_", "iso_", "din_", "pip_"):
        if std_slug.startswith(short[:-1]) and body.startswith(short):
            body = body[len(short):]
            break

    return f"{std_slug}_{body}"


def processed_dir_for(classification: dict, source_path: str = "") -> Path:
    """Return the processed/ subdirectory for this classification.

    New layout: processed/{source_slug}/{standard_slug}/{category}/
    """
    cat         = classification["category"]
    source_slug = _source_slug_from_path(source_path) if source_path else "unknown_source"

    if cat in PIP_CATEGORIES:
        return PROCESSED_DIR / source_slug / "pip" / cat
    return PROCESSED_DIR / source_slug / _safe_std_slug(classification["standard"]) / cat


def resolve_stem(base_stem: str, target_dir: Path, used: set[str]) -> str:
    """
    Return a collision-free stem within target_dir.
    If 'base_stem' is already taken (in used or on disk), appends _2, _3, ...
    Adds the chosen stem to `used`.
    """
    stem = base_stem
    counter = 2
    while stem in used or (target_dir / (stem + ".svg")).exists():
        stem = f"{base_stem}_{counter}"
        counter += 1
    used.add(stem)
    return stem


def build_metadata(svg_path: Path, final_stem: str, classification: dict,
                   source_path: str = "") -> dict:
    """Assemble the complete metadata dict for one SVG."""
    svg_attrs   = parse_svg_attributes(svg_path)
    src_path    = source_path or _rel_or_abs(svg_path, REPO_ROOT)
    source_slug = _source_slug_from_path(src_path)
    target_dir  = processed_dir_for(classification, src_path)

    cat = classification["category"]
    if cat in PIP_CATEGORIES:
        symbol_id = f"{source_slug}/pip/{cat}/{final_stem}"
    else:
        symbol_id = f"{source_slug}/{_safe_std_slug(classification['standard'])}/{cat}/{final_stem}"

    return {
        "schema_version":    SCHEMA_VERSION,
        "id":                symbol_id,
        "filename":          final_stem + ".svg",
        "original_filename": svg_path.name,
        "display_name":      _display_name_from_stem(svg_path.stem),
        "standard":          classification["standard"],
        "category":          classification["category"],
        "subcategory":       classification["subcategory"],
        "source_path":       _rel_or_abs(svg_path, REPO_ROOT),
        "svg_path":          _rel_or_abs(target_dir / (final_stem + ".svg"), REPO_ROOT),
        "metadata_path":     _rel_or_abs(target_dir / (final_stem + ".json"), REPO_ROOT),
        "svg": {
            "width":         svg_attrs["width"],
            "height":        svg_attrs["height"],
            "view_box":      svg_attrs["view_box"],
            "element_count": svg_attrs["element_count"],
            "has_text":      svg_attrs["has_text"],
            "creator":       svg_attrs["creator"],
        },
        "file": {
            "size_bytes": svg_path.stat().st_size,
        },
        "classification": {
            "confidence": classification["confidence"],
            "method":     classification["method"],
        },
        "tags":        _auto_tags(classification["category"], classification["subcategory"]),
        "snap_points": detect_snap_points(svg_path, classification["category"]),
        "notes":       "",
    }


def export_completed_symbols(source_dir: Path, export_dir: Path, dry_run: bool) -> None:
    """Copy completed symbols (JSON + SVG) from source_dir to export_dir."""
    if not source_dir.is_dir():
        print(f"Error: source directory not found: {source_dir}")
        return

    json_files = sorted(source_dir.rglob("*.json"))
    completed = 0
    copied = 0
    errors = 0
    registry: list[dict] = []

    for json_path in json_files:
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        if not meta.get("completed", False):
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            errors += 1
            continue

        rel = json_path.relative_to(source_dir)
        target_json = export_dir / rel
        target_svg = target_json.with_suffix(".svg")

        completed += 1
        if not dry_run:
            target_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, target_json)
            shutil.copy2(svg_path, target_svg)
        copied += 1
        registry.append(meta)

    if not dry_run:
        export_dir.mkdir(parents=True, exist_ok=True)
        registry_path = export_dir / "registry.json"
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at":   datetime.now(timezone.utc).isoformat(),
                    "total_symbols":  len(registry),
                    "symbols":        registry,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    print(f"\n{'='*60}")
    print(f"  Completed : {completed}")
    print(f"  Copied    : {copied if not dry_run else 0}")
    print(f"  Errors    : {errors}")
    if dry_run:
        print("  [DRY RUN -- no files written]")
    else:
        print(f"  Output    : {export_dir}")
        print("  Registry  : registry.json")
    print(f"{'='*60}")


def migrate_to_source_hierarchy(processed_dir: Path, dry_run: bool) -> None:
    """Migrate processed/ from 3-part IDs to 4-part source-aware hierarchy.

    For each symbol JSON found in processed_dir:
    1. Reads source_path to determine source_slug via _source_slug_from_path.
    2. Computes new target directory and 4-part ID.
    3. Detects duplicates by content hash; keeps the higher-quality copy.
    4. Moves SVG + JSON to new paths (dry_run = only print, no writes).
    5. Rewrites registry.json with updated entries and hashes map.
    """
    if not processed_dir.is_dir():
        print(f"Error: processed directory not found: {processed_dir}")
        return

    reg_path = processed_dir / "registry.json"
    # Back up registry before doing anything
    if not dry_run and reg_path.exists():
        ts      = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak     = reg_path.with_name(f"registry.{ts}.bak.json")
        shutil.copy2(reg_path, bak)
        print(f"Registry backed up → {bak.name}")

    json_files = sorted(processed_dir.rglob("*.json"))
    moves: list[tuple] = []  # (old_json, new_json, old_svg, new_svg, meta)

    # Track new stems per target dir
    used_stems: dict[Path, set[str]] = {}
    hash_map:   dict[str, dict]      = {}  # content_hash → best meta dict
    hashes:     dict[str, list[str]] = {}

    skipped = 0

    for json_path in json_files:
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        # Skip files already in the new 4-part hierarchy (heuristic: 4 levels deep)
        try:
            rel_parts = json_path.relative_to(processed_dir).parts
        except ValueError:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"  [SKIP] cannot read {json_path}")
            skipped += 1
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            print(f"  [SKIP] missing SVG for {json_path.name}")
            skipped += 1
            continue

        # Compute content hash
        try:
            content = svg_path.read_text(encoding="utf-8", errors="replace")
            content_hash = _svg_sha256(content)
        except OSError:
            content_hash = ""

        # Determine source slug from stored source_path field
        source_path_field = meta.get("source_path", "")
        source_slug       = _source_slug_from_path(source_path_field) if source_path_field else "unknown_source"

        # Reconstruct classification from meta fields
        cat       = meta.get("category", "unknown")
        standard  = meta.get("standard", "unknown")
        confidence = meta.get("classification", {}).get("confidence", "none")
        method     = meta.get("classification", {}).get("method", "")
        classification = {
            "category":   cat,
            "standard":   standard,
            "subcategory": meta.get("subcategory", ""),
            "confidence": confidence,
            "method":     method,
        }

        new_target_dir = PROCESSED_DIR / source_slug / (
            "pip" if cat in PIP_CATEGORIES else _safe_std_slug(standard)
        ) / cat
        new_target_dir = new_target_dir

        if new_target_dir not in used_stems:
            used_stems[new_target_dir] = set()

        # Generate stem
        base_stem  = json_path.stem  # keep existing stem
        final_stem = base_stem
        if final_stem in used_stems[new_target_dir] or (new_target_dir / (final_stem + ".svg")).exists():
            final_stem = resolve_stem(base_stem, new_target_dir, used_stems[new_target_dir])
        else:
            used_stems[new_target_dir].add(final_stem)

        # Build new 4-part ID
        if cat in PIP_CATEGORIES:
            new_id = f"{source_slug}/pip/{cat}/{final_stem}"
        else:
            new_id = f"{source_slug}/{_safe_std_slug(standard)}/{cat}/{final_stem}"

        new_json = new_target_dir / (final_stem + ".json")
        new_svg  = new_target_dir / (final_stem + ".svg")

        # Deduplication by content hash
        if content_hash and content_hash in hash_map:
            existing_meta = hash_map[content_hash]
            new_quality   = _metadata_quality(meta)
            old_quality   = _metadata_quality(existing_meta)
            if new_quality <= old_quality:
                print(f"  [DUP ] {json_path.name}: duplicate of {existing_meta.get('id')}, skipping")
                hashes.setdefault(content_hash, []).append(new_id)
                skipped += 1
                continue
            else:
                print(f"  [DUP+] {json_path.name}: better quality than {existing_meta.get('id')}, replacing")
                hashes.setdefault(content_hash, []).append(existing_meta.get("id", ""))
                hash_map[content_hash] = meta
        elif content_hash:
            hash_map[content_hash] = meta
            hashes[content_hash]   = [new_id]

        old_json = json_path
        old_svg  = svg_path

        # Update meta fields
        meta["id"]            = new_id
        meta["svg_path"]      = _rel_or_abs(new_svg, REPO_ROOT)
        meta["metadata_path"] = _rel_or_abs(new_json, REPO_ROOT)
        if content_hash:
            meta["content_hash"] = content_hash

        print(
            f"  {'[DRY]' if dry_run else '[MOVE]'} "
            f"{old_json.relative_to(processed_dir)}  →  {new_json.relative_to(processed_dir)}"
        )
        moves.append((old_json, new_json, old_svg, new_svg, meta))

    if dry_run:
        print(f"\n{'='*60}")
        print(f"  Would move : {len(moves)}")
        print(f"  Skipped    : {skipped}")
        print("  [DRY RUN -- no files written]")
        print(f"{'='*60}")
        return

    # Execute moves
    moved   = 0
    m_errors = 0
    new_registry: list[dict] = []
    for old_json, new_json, old_svg, new_svg, meta in moves:
        try:
            new_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_svg),  str(new_svg))
            shutil.move(str(old_json), str(new_json))
            new_json.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            new_registry.append(meta)
            moved += 1
        except OSError as exc:
            print(f"  [ERROR] {old_json.name}: {exc}")
            m_errors += 1

    # Write new registry
    new_reg_path = processed_dir / "registry.json"
    with open(new_reg_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at":   datetime.now(timezone.utc).isoformat(),
                "total_symbols":  len(new_registry),
                "symbols":        new_registry,
                "hashes":         hashes,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n{'='*60}")
    print(f"  Moved   : {moved}")
    print(f"  Skipped : {skipped}")
    print(f"  Errors  : {m_errors}")
    print(f"  Registry: {new_reg_path}")
    print(f"{'='*60}")


# Main

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify input/ SVGs and write processed/ with normalized names."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and classify without writing any files."
    )
    parser.add_argument(
        "--input", default=None, metavar="DIR",
        help="Input directory to scan for SVGs (default: <repo>/input)."
    )
    parser.add_argument(
        "--output", default=None, metavar="DIR",
        help=(
            "Output directory for processed files "
            "(default: <repo>/processed, or <input>-augmented when using --input/--augment-source/--augment)."
        )
    )
    parser.add_argument(
        "--augment", action="store_true",
        help="Generate augmented PNGs instead of processed SVG/JSON."
    )
    parser.add_argument(
        "--augment-count", type=int, default=5, metavar="N",
        help="Number of augmented PNGs to generate per SVG (default: 5)."
    )
    parser.add_argument(
        "--augment-min-size", type=int, default=256, metavar="PX",
        help="Minimum short-side size in pixels for augmented PNGs (default: 256)."
    )
    parser.add_argument(
        "--augment-source", choices=["completed", "processed"], default=None,
        help="Use completed/ or processed/ as the input source."
    )
    parser.add_argument(
        "--export-completed", default=None, metavar="DIR",
        help="Export completed symbols (copy SVG+JSON) to DIR."
    )
    parser.add_argument(
        "--export-source", default=None, metavar="DIR",
        help="Source symbols root for export (default: <repo>/processed)."
    )
    parser.add_argument(
        "--migrate", action="store_true",
        help="Migrate processed/ to source-aware 4-part folder hierarchy."
    )
    parser.add_argument(
        "--export-yolo", default=None, metavar="DIR",
        help="Export YOLO v8 datasets (one per standard) to DIR."
    )
    args = parser.parse_args()

    # Override module-level path globals when CLI args are provided
    global INPUT_DIR, PROCESSED_DIR
    if args.input:
        INPUT_DIR = Path(args.input).resolve()
    if args.augment_source and not args.input:
        INPUT_DIR = (REPO_ROOT / args.augment_source).resolve()
    if args.output:
        PROCESSED_DIR = Path(args.output).resolve()
    elif args.input or args.augment_source or args.augment:
        # Default to <input>-augmented alongside the chosen input folder.
        PROCESSED_DIR = INPUT_DIR.parent / f"{INPUT_DIR.name}-augmented"

    if args.export_completed:
        export_dir = Path(args.export_completed).resolve()
        source_dir = (Path(args.export_source).resolve()
                      if args.export_source else PROCESSED_DIR)
        export_completed_symbols(source_dir, export_dir, args.dry_run)
        return

    if args.migrate:
        migrate_to_source_hierarchy(PROCESSED_DIR, args.dry_run)
        return

    if args.export_yolo:
        yolo_out = Path(args.export_yolo).resolve()
        registry_path = PROCESSED_DIR / "registry.json"
        export_yolo_datasets(
            registry_path, yolo_out,
            args.augment_count, args.dry_run, args.augment_min_size,
        )
        return

    augment_mode = bool(args.augment or args.augment_source)
    if augment_mode:
        if args.augment_count < 1:
            print("Error: --augment-count must be >= 1")
            return
        if args.augment_min_size < 1:
            print("Error: --augment-min-size must be >= 1")
            return
        augment_svgs(INPUT_DIR, PROCESSED_DIR, args.augment_count, args.dry_run, args.augment_min_size)
        return

    generated_at = datetime.now(timezone.utc).isoformat()

    svg_files = sorted(INPUT_DIR.rglob("*.svg"))
    total = len(svg_files)
    print(f"Found {total} SVG files under {INPUT_DIR}\n")

    registry: list[dict]        = []
    processed_count             = 0
    errors                      = 0
    conf_counts: dict[str, int] = {}

    # Track used stems per target directory to avoid collisions
    used_stems: dict[Path, set[str]] = {}
    # Track content hashes for deduplication: hash → first symbol_id
    hash_map: dict[str, str] = {}
    # Full hash registry: hash → [symbol_id, ...]
    hashes: dict[str, list[str]] = {}
    duplicates = 0

    for svg_path in svg_files:
        if "_debug" in svg_path.stem:
            continue
        rel = svg_path.relative_to(REPO_ROOT)
        src_rel = str(rel).replace("\\", "/")
        try:
            classification = classify(svg_path)
            target_dir     = processed_dir_for(classification, src_rel)

            if target_dir not in used_stems:
                used_stems[target_dir] = set()

            base_stem  = _normalize_stem(svg_path.stem, classification["standard"])
            final_stem = resolve_stem(base_stem, target_dir, used_stems[target_dir])
            meta       = build_metadata(svg_path, final_stem, classification, src_rel)
        except Exception as exc:
            print(f"  [ERROR] {rel}: {exc}")
            errors += 1
            continue

        # Compute content hash from minified SVG
        raw_svg     = svg_path.read_text(encoding="utf-8", errors="replace")
        minified    = _minify_svg(raw_svg)
        content_hash = _svg_sha256(minified)
        meta["content_hash"] = content_hash

        # Deduplication: if we've seen this hash, compare quality
        if content_hash in hash_map:
            existing_id = hash_map[content_hash]
            existing_meta = next(
                (m for m in registry if m.get("id") == existing_id), None
            )
            if existing_meta is not None:
                new_quality = _metadata_quality(meta)
                old_quality = _metadata_quality(existing_meta)
                if new_quality <= old_quality:
                    print(
                        f"  [DUP ] {rel}: duplicate of {existing_id} "
                        f"(quality {new_quality} <= {old_quality}), skipping"
                    )
                    hashes.setdefault(content_hash, []).append(meta["id"])
                    duplicates += 1
                    continue
                else:
                    print(
                        f"  [DUP+] {rel}: replacing {existing_id} "
                        f"(quality {new_quality} > {old_quality})"
                    )
                    registry.remove(existing_meta)
                    hashes.setdefault(content_hash, []).append(existing_id)
                    hash_map[content_hash] = meta["id"]
            else:
                hash_map[content_hash] = meta["id"]
        else:
            hash_map[content_hash] = meta["id"]
        hashes.setdefault(content_hash, [meta["id"]])

        conf = meta["classification"]["confidence"]
        conf_counts[conf] = conf_counts.get(conf, 0) + 1

        label   = {"high": "OK", "low": "~~", "none": "??"}.get(conf, "??")
        renamed = f" -> {final_stem}.svg" if final_stem != _slugify(svg_path.stem) else ""

        print(
            f"  [{processed_count + 1:>4}/{total}] {label} "
            f"{meta['standard']:<14} {meta['category']:<20} "
            f"{svg_path.name}{renamed}"
        )

        if not args.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

            (target_dir / (final_stem + ".svg")).write_text(minified, encoding="utf-8")

            # Write metadata JSON
            json_path = target_dir / (final_stem + ".json")
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2, ensure_ascii=False)

        registry.append(meta)
        processed_count += 1

    # Write registry
    registry_path = PROCESSED_DIR / "registry.json"
    if not args.dry_run:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at":   generated_at,
                    "total_symbols":  len(registry),
                    "symbols":        registry,
                    "hashes":         hashes,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    # Summary
    print(f"\n{'='*60}")
    print(f"  Processed  : {processed_count}")
    print(f"  Duplicates : {duplicates}")
    print(f"  Errors     : {errors}")
    print(f"  High conf  : {conf_counts.get('high', 0)}")
    print(f"  Low conf   : {conf_counts.get('low', 0)}")
    print(f"  Unknown    : {conf_counts.get('none', 0)}")
    if not args.dry_run:
        print(f"  Output    : {PROCESSED_DIR}")
        print(f"  Registry  : {registry_path}")
    else:
        print("  [DRY RUN -- no files written]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
