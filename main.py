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
"""

import argparse
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


def processed_dir_for(classification: dict) -> Path:
    """Return the processed/ subdirectory for this classification."""
    cat = classification["category"]
    if cat in PIP_CATEGORIES:
        return PROCESSED_DIR / "pip" / cat
    return PROCESSED_DIR / _safe_std_slug(classification["standard"]) / cat


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


def build_metadata(svg_path: Path, final_stem: str, classification: dict) -> dict:
    """Assemble the complete metadata dict for one SVG."""
    svg_attrs  = parse_svg_attributes(svg_path)
    target_dir = processed_dir_for(classification)

    cat = classification["category"]
    if cat in PIP_CATEGORIES:
        symbol_id = f"pip/{cat}/{final_stem}"
    else:
        symbol_id = f"{_safe_std_slug(classification['standard'])}/{cat}/{final_stem}"

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
        "snap_points": [],
        "notes":       "",
    }


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
        help="Output directory for processed files (default: <repo>/processed)."
    )
    args = parser.parse_args()

    # Override module-level path globals when CLI args are provided
    global INPUT_DIR, PROCESSED_DIR
    if args.input:
        INPUT_DIR = Path(args.input).resolve()
    if args.output:
        PROCESSED_DIR = Path(args.output).resolve()

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

    for svg_path in svg_files:
        rel = svg_path.relative_to(REPO_ROOT)
        try:
            classification = classify(svg_path)
            target_dir     = processed_dir_for(classification)

            if target_dir not in used_stems:
                used_stems[target_dir] = set()

            base_stem  = _normalize_stem(svg_path.stem, classification["standard"])
            final_stem = resolve_stem(base_stem, target_dir, used_stems[target_dir])
            meta       = build_metadata(svg_path, final_stem, classification)
        except Exception as exc:
            print(f"  [ERROR] {rel}: {exc}")
            errors += 1
            continue

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

            # Write minified SVG (strips XML declaration, DOCTYPE, metadata bloat)
            raw_svg = svg_path.read_text(encoding="utf-8", errors="replace")
            (target_dir / (final_stem + ".svg")).write_text(
                _minify_svg(raw_svg), encoding="utf-8"
            )

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
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )

    # Summary
    print(f"\n{'='*60}")
    print(f"  Processed : {processed_count}")
    print(f"  Errors    : {errors}")
    print(f"  High conf : {conf_counts.get('high', 0)}")
    print(f"  Low conf  : {conf_counts.get('low', 0)}")
    print(f"  Unknown   : {conf_counts.get('none', 0)}")
    if not args.dry_run:
        print(f"  Output    : {PROCESSED_DIR}")
        print(f"  Registry  : {registry_path}")
    else:
        print("  [DRY RUN -- no files written]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
