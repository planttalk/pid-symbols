"""
classifier.py
--------------------
Classification strategies for P&ID SVG symbols.

Strategies applied in order by classify():
  0. Reference sheet detection      (multi-symbol sheets → reference_sheet)
  1. autocad-parser folder naming   (isa_actuator_svg/ → ISA / actuator)
  2. Filename standard tag          ("(ISO 10628-2)" / "(DIN 2429)")
  3. Downloaded subfolder map       (agitators/ → agitator)
  4. Generated filename prefix      (valve_ball → valve)
  5. Filename keyword heuristics    (fallback)
  6. unknown                        (if nothing matches)
"""

from pathlib import Path

import paths
from constants import (
    AUTOCAD_FOLDER_MAP,
    DOWNLOADED_FOLDER_MAP,
    GENERATED_PREFIX_MAP,
    KEYWORD_HEURISTICS,
    PIPING_STEM_PREFIXES,
    _REFERENCE_RE,
    _STANDARD_RE,
)
from utils import _slugify, _extract_standard_from_name


def _strategy_reference_sheet(svg_path: Path) -> dict | None:
    """Strategy 0: Detect full reference sheets / drawings (not individual symbols)."""
    stem = svg_path.stem
    if _REFERENCE_RE.search(stem):
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
        rel_parts = svg_path.relative_to(paths.INPUT_DIR).parts
    except ValueError:
        return None

    if rel_parts[0] != "autocad-parser" or len(rel_parts) < 2:
        return None

    folder = rel_parts[1]
    if folder not in AUTOCAD_FOLDER_MAP:
        return None

    standard, category = AUTOCAD_FOLDER_MAP[folder]
    stem = svg_path.stem

    for pip_prefix in PIPING_STEM_PREFIXES:
        if stem.lower().startswith(pip_prefix):
            return {
                "standard":    "PIP",
                "category":    category,
                "subcategory": stem[len(pip_prefix):],
                "confidence":  "high",
                "method":      "autocad_folder_map",
            }

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

    parent = svg_path.parent.name
    category = DOWNLOADED_FOLDER_MAP.get(parent)

    if not category:
        stem_low = stem.lower()
        for kw, cat in KEYWORD_HEURISTICS:
            if kw in stem_low:
                category = cat
                break
        else:
            category = "uncategorized"

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
        rel_parts = svg_path.relative_to(paths.INPUT_DIR).parts
    except ValueError:
        return None

    if rel_parts[0] != "pid-symbols-generator":
        return None
    if len(rel_parts) < 2 or rel_parts[1] != "downloaded":
        return None
    if len(rel_parts) < 3:
        return None

    folder = rel_parts[2]
    category = DOWNLOADED_FOLDER_MAP.get(folder)
    if not category:
        return None

    stem = svg_path.stem
    clean_stem = _STANDARD_RE.sub("", stem).strip().strip(",").strip()

    return {
        "standard":    "ISO 10628-2",
        "category":    category,
        "subcategory": _slugify(clean_stem),
        "confidence":  "high",
        "method":      "downloaded_folder_map",
    }


def _strategy_generated_prefix(svg_path: Path) -> dict | None:
    """Strategy 4: pid-symbols-generator/generated filename prefix."""
    try:
        rel_parts = svg_path.relative_to(paths.INPUT_DIR).parts
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
    for keyword, category in sorted(KEYWORD_HEURISTICS, key=lambda x: -len(x[0])):
        if keyword in stem_low:
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
