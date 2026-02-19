#!/usr/bin/env python3
"""
generate_metadata.py
--------------------
Recursively scans input/ for SVG files, classifies each one,
and writes:
  - output/<standard>/<category>/<stem>.json  (individual metadata)
  - output/registry.json                       (master registry)

Classification strategies (applied in order):
  1. autocad-parser folder naming  (isa_actuator_svg/ → ISA / actuator)
  2. Filename standard tag          ("(ISO 10628-2)" / "(DIN 2429)")
  3. Downloaded subfolder map       (agitators/ → agitator)
  4. Generated filename prefix      (valve_ball → valve)
  5. Filename keyword heuristics    (fallback)
  6. unknown                        (if nothing matches)

Usage:
    python scripts/generate_metadata.py
    python scripts/generate_metadata.py --dry-run
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR  = REPO_ROOT / "input"
OUTPUT_DIR = REPO_ROOT / "output"

SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Classification maps
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Classification strategies
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Metadata assembly
# ---------------------------------------------------------------------------

def _safe_std_slug(standard: str) -> str:
    """Convert 'ISO 10628-2' → 'iso_10628-2' for use in output paths."""
    return _slugify(standard)


def output_path_for(svg_path: Path, classification: dict) -> Path:
    """
    Compute the output JSON path.
    Layout: output/<standard_slug>/<category>/<stem>.json
    Unknown symbols go to: output/unknown/<category>/<stem>.json
    """
    standard_slug = _safe_std_slug(classification["standard"])
    category      = classification["category"]
    return OUTPUT_DIR / standard_slug / category / (svg_path.stem + ".json")


def build_metadata(svg_path: Path) -> dict:
    """Assemble the complete metadata dict for one SVG."""
    classification = classify(svg_path)
    svg_attrs      = parse_svg_attributes(svg_path)

    rel_svg  = svg_path.relative_to(REPO_ROOT)
    out_path = output_path_for(svg_path, classification)
    rel_meta = out_path.relative_to(REPO_ROOT)

    # Stable ID: standard/category/stem
    symbol_id = (
        f"{_safe_std_slug(classification['standard'])}"
        f"/{classification['category']}"
        f"/{svg_path.stem}"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "id":             symbol_id,
        "filename":       svg_path.name,
        "display_name":   _display_name_from_stem(svg_path.stem),
        "standard":       classification["standard"],
        "category":       classification["category"],
        "subcategory":    classification["subcategory"],
        "source_path":    str(rel_svg).replace("\\", "/"),
        "metadata_path":  str(rel_meta).replace("\\", "/"),
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
        # Fields intended for manual / future-tooling enrichment
        "tags":        [],
        "snap_points": [],
        "notes":       "",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate symbol metadata JSON files from input/ SVGs."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and classify without writing any files."
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()

    svg_files = sorted(INPUT_DIR.rglob("*.svg"))
    total = len(svg_files)
    print(f"Found {total} SVG files under {INPUT_DIR}\n")

    registry: list[dict] = []
    processed = 0
    errors    = 0

    # Confidence counters for summary
    conf_counts: dict[str, int] = {"high": 0, "low": 0, "none": 0}

    for svg_path in svg_files:
        rel = svg_path.relative_to(REPO_ROOT)
        try:
            meta = build_metadata(svg_path)
        except Exception as exc:
            print(f"  [ERROR] {rel}: {exc}")
            errors += 1
            continue

        out_path = OUTPUT_DIR / Path(meta["metadata_path"]).relative_to("output")

        conf = meta["classification"]["confidence"]
        conf_counts[conf] = conf_counts.get(conf, 0) + 1

        label = {
            "high":   "OK",
            "low":    "~~",
            "none":   "??",
        }.get(conf, "??")

        print(
            f"  [{processed + 1:>4}/{total}] {label} "
            f"{meta['standard']:<14} {meta['category']:<20} {svg_path.name}"
        )

        if not args.dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2, ensure_ascii=False)

        registry.append(meta)
        processed += 1

    # Write registry
    registry_path = OUTPUT_DIR / "registry.json"
    if not args.dry_run:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
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
    print(f"  Processed : {processed}")
    print(f"  Errors    : {errors}")
    print(f"  High conf : {conf_counts.get('high', 0)}")
    print(f"  Low conf  : {conf_counts.get('low', 0)}")
    print(f"  Unknown   : {conf_counts.get('none', 0)}")
    if not args.dry_run:
        print(f"  Registry  : {registry_path}")
    else:
        print("  [DRY RUN — no files written]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
