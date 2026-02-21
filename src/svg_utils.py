"""
svg_utils.py
--------------------
SVG parsing, minification, attribute extraction, and PNG rendering.
"""

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .constants import _MINIFY_PATTERNS


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
            if local == "title" and elem.text and result["creator"] is None:
                result["creator"] = elem.text.strip()

        result["element_count"] = count
    except ET.ParseError:
        pass
    return result
