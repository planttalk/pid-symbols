"""
snap_points.py
--------------------
Automatic snap-point / connection-port detection for P&ID SVG symbols.

Four strategies applied in order:
  1. ID-based: elements whose id/class contains port/conn/inlet/outlet/…
  2. Open-end: floating endpoints of non-closed straight-line paths.
               Applied only to valve/pipe-like categories.
  3. Bubble cardinal: N/S/E/W of the largest circle/ellipse.
                      Applied to instrument bubble / annotation categories.
  4. Bounding-box extremes: fallback for anything else.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .constants import _VALVE_CATS, _OPEN_END_CATS, _BUBBLE_CATS, _ACTUATOR_CATS


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
        horizontal = x_span >= y_span
        primary_lo, primary_hi = (
            (by_x[0], by_x[-1]) if horizontal else (by_y[0], by_y[-1])
        )
        result = [
            {"id": "in",  "x": float(primary_lo[0]), "y": float(primary_lo[1])},
            {"id": "out", "x": float(primary_hi[0]), "y": float(primary_hi[1])},
        ]
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
    # Exclude segments that lie entirely on the viewBox boundary.
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
