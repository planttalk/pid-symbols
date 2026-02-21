"""
metadata.py
--------------------
Metadata assembly, path normalization, and processed-directory resolution.
"""

from pathlib import Path

import paths
from constants import PIP_CATEGORIES, SCHEMA_VERSION
from snap_points import detect_snap_points
from svg_utils import parse_svg_attributes
from constants import _STANDARD_RE
from utils import (
    _auto_tags,
    _display_name_from_stem,
    _rel_or_abs,
    _safe_std_slug,
    _slugify,
    _source_slug_from_path,
)


def _normalize_stem(stem: str, standard: str) -> str:
    """
    Produce a snake_case lowercase filename stem, prefixed with the standard slug.
    The embedded standard tag is stripped from the body to avoid duplication.

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

    for short in ("isa_", "iso_", "din_", "pip_"):
        if std_slug.startswith(short[:-1]) and body.startswith(short):
            body = body[len(short):]
            break

    return f"{std_slug}_{body}"


def processed_dir_for(classification: dict, source_path: str = "") -> Path:
    """Return the processed/ subdirectory for this classification.

    Layout: processed/{source_slug}/{standard_slug}/{category}/
    """
    cat         = classification["category"]
    source_slug = _source_slug_from_path(source_path) if source_path else "unknown_source"

    if cat in PIP_CATEGORIES:
        return paths.PROCESSED_DIR / source_slug / "pip" / cat
    return paths.PROCESSED_DIR / source_slug / _safe_std_slug(classification["standard"]) / cat


def resolve_stem(base_stem: str, target_dir: Path, used: set[str]) -> str:
    """
    Return a collision-free stem within target_dir.
    If 'base_stem' is already taken (in used or on disk), appends _2, _3, …
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
    src_path    = source_path or _rel_or_abs(svg_path, paths.REPO_ROOT)
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
        "source_path":       _rel_or_abs(svg_path, paths.REPO_ROOT),
        "svg_path":          _rel_or_abs(target_dir / (final_stem + ".svg"), paths.REPO_ROOT),
        "metadata_path":     _rel_or_abs(target_dir / (final_stem + ".json"), paths.REPO_ROOT),
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
