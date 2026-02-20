#!/usr/bin/env python3
"""
visualize_snap_points.py
------------------------
For every processed SVG that has snap_points in its metadata JSON,
generates a *_debug.svg next to it with coloured circles and ID labels
overlaid at the detected connection points.

Color scheme:
  in      → blue     out     → red
  signal  → purple   process → orange
  north/south/east/west → green
  p1, p2, … / anything else → grey

Usage:
    python scripts/visualize_snap_points.py
    python scripts/visualize_snap_points.py --processed path/to/processed
    python scripts/visualize_snap_points.py --only-missing
"""

import argparse
import json
import re
from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "processed"

_PORT_COLORS: dict[str, str] = {
    "in":      "#2196F3",  # blue
    "out":     "#F44336",  # red
    "in_out":  "#009688",  # teal  (bidirectional)
    "signal":  "#9C27B0",  # purple
    "process": "#FF9800",  # orange
    "north":   "#4CAF50",  # green
    "south":   "#4CAF50",
    "east":    "#4CAF50",
    "west":    "#4CAF50",
}
_DEFAULT_COLOR = "#607D8B"  # slate-grey for p1, p2, …


def _overlay_svg(svg_text: str, snap_points: list[dict]) -> str:
    """Return the SVG string with a snap-point overlay group injected."""
    if not snap_points:
        return svg_text

    # Derive a sensible marker radius from the viewBox
    radius = 4.0
    label_size = 5.0
    vb_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_text)
    if vb_match:
        try:
            parts = [float(v) for v in vb_match.group(1).split()]
            if len(parts) >= 4:
                shorter = min(parts[2], parts[3])
                radius     = max(2.0, round(shorter * 0.025, 2))
                label_size = max(3.0, round(shorter * 0.04,  2))
        except ValueError:
            pass

    stroke_w   = round(radius * 0.3,       2)
    text_sw    = round(label_size * 0.15,  2)
    label_dx   = round(radius * 1.3,       2)
    label_dy   = round(label_size * 0.35,  2)

    lines: list[str] = [
        '<g id="snap-points" style="pointer-events:none;font-family:sans-serif;">',
    ]
    for pt in snap_points:
        pid   = str(pt.get("id", "?"))
        x, y  = pt["x"], pt["y"]
        color = _PORT_COLORS.get(pid, _DEFAULT_COLOR)
        disp  = "in/out" if pid == "in_out" else pid
        lines.append(
            f'  <circle cx="{x}" cy="{y}" r="{radius}"'
            f' fill="{color}" fill-opacity="0.8"'
            f' stroke="white" stroke-width="{stroke_w}"/>'
        )
        lines.append(
            f'  <text x="{x + label_dx}" y="{y + label_dy}"'
            f' font-size="{label_size}" fill="{color}"'
            f' stroke="white" stroke-width="{text_sw}" paint-order="stroke"'
            f'>{disp}</text>'
        )
    lines.append("</g>")

    overlay   = "\n".join(lines)
    close_idx = svg_text.rfind("</svg>")
    if close_idx == -1:
        return svg_text + "\n" + overlay
    return svg_text[:close_idx] + "\n" + overlay + "\n" + svg_text[close_idx:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate *_debug.svg files with snap-point overlays."
    )
    parser.add_argument(
        "--processed", default=None, metavar="DIR",
        help="Processed directory to scan (default: <repo>/processed).",
    )
    parser.add_argument(
        "--only-missing", action="store_true",
        help="Skip symbols that already have a _debug.svg.",
    )
    args = parser.parse_args()

    processed_dir = Path(args.processed).resolve() if args.processed else PROCESSED_DIR

    json_files = [
        j for j in sorted(processed_dir.rglob("*.json"))
        if j.stem != "registry" and not j.stem.endswith("_debug")
    ]

    generated = skipped = no_points = errors = 0

    for json_path in json_files:
        svg_path   = json_path.with_suffix(".svg")
        debug_path = json_path.with_name(json_path.stem + "_debug.svg")

        if args.only_missing and debug_path.exists():
            skipped += 1
            continue

        if not svg_path.exists():
            skipped += 1
            continue

        try:
            with open(json_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [ERROR] {json_path.relative_to(processed_dir)}: {exc}")
            errors += 1
            continue

        snap_points: list[dict] = meta.get("snap_points", [])
        if not snap_points:
            no_points += 1
            continue

        try:
            svg_text  = svg_path.read_text(encoding="utf-8", errors="replace")
            debug_svg = _overlay_svg(svg_text, snap_points)
            debug_path.write_text(debug_svg, encoding="utf-8")
            generated += 1
        except OSError as exc:
            print(f"  [ERROR] {svg_path.relative_to(processed_dir)}: {exc}")
            errors += 1

    print(f"Generated  : {generated}")
    print(f"No points  : {no_points}")
    print(f"Skipped    : {skipped}")
    print(f"Errors     : {errors}")


if __name__ == "__main__":
    main()
