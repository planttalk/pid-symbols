"""
utils.py
--------------------
Pure helper utilities shared across modules.
No heavy dependencies — only stdlib + constants.
"""

import hashlib
import re
from pathlib import Path

from .constants import _STANDARD_RE


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


def _safe_std_slug(standard: str) -> str:
    """Convert 'ISO 10628-2' → 'iso_10628_2' for use in output paths."""
    return _slugify(standard)


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


def _canonicalize_svg_ids(content: str) -> str:
    """Replace all SVG id="…" values and their url(#…)/href="#…" references
    with stable sequential names so that structurally identical SVGs that only
    differ in randomly-generated IDs (e.g. from matplotlib/autocad exporters)
    hash to the same value.
    """
    # Collect all id values in document order — keeps mapping stable regardless
    # of how the exporter names them.
    id_re  = re.compile(r'\bid="([^"]+)"')
    ids    = list(dict.fromkeys(m.group(1) for m in id_re.finditer(content)))
    if not ids:
        return content

    mapping = {old: f"_cid{i}" for i, old in enumerate(ids)}

    # Replace definitions: id="old" → id="_cidN"
    def _repl_def(m: re.Match) -> str:
        return f'id="{mapping[m.group(1)]}"'
    content = id_re.sub(_repl_def, content)

    # Replace all reference forms that point to an id:
    #   url(#old)   href="#old"   xlink:href="#old"
    ref_re = re.compile(
        r'(?P<url>url\(#)(?P<id>[^)]+)(?P<close>\))'
        r'|(?P<href>(?:xlink:)?href=")#(?P<hid>[^"]+)(?P<hclose>")'
    )

    def _repl_ref(m: re.Match) -> str:
        if m.group("url"):
            old = m.group("id")
            new = mapping.get(old, old)
            return f'{m.group("url")}{new}{m.group("close")}'
        old = m.group("hid")
        new = mapping.get(old, old)
        return f'{m.group("href")}#{new}{m.group("hclose")}'

    return ref_re.sub(_repl_ref, content)


def _svg_sha256(content: str) -> str:
    """Return the SHA-256 hex digest of an SVG string, after canonicalizing
    internal IDs so that structurally identical SVGs with different random IDs
    hash identically.
    """
    canonical = _canonicalize_svg_ids(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
      category="valve", subcategory="ball"               -> ["valve", "ball"]
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
