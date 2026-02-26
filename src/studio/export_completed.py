"""Export completed symbols from the studio."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .symbols import SYMBOLS_ROOT


def export_completed(output_dir_str: str) -> dict:
    """Copy every completed symbol (SVG + JSON) from SYMBOLS_ROOT to output_dir."""
    if SYMBOLS_ROOT is None:
        return {
            "output_dir": "",
            "copied": 0,
            "skipped": 0,
            "errors": 0,
            "message": "Symbols root not configured",
        }

    output_dir = (
        Path(output_dir_str) if output_dir_str else SYMBOLS_ROOT.parent / "completed"
    )

    copied = 0
    skipped = 0
    errors = 0

    for json_path in sorted(SYMBOLS_ROOT.rglob("*.json")):
        if json_path.name == "registry.json" or "_debug" in json_path.stem:
            continue
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        if not meta.get("completed", False):
            skipped += 1
            continue

        if meta.get("id", "").count("/") < 3:
            skipped += 1
            continue

        svg_path = json_path.with_suffix(".svg")
        if not svg_path.exists():
            errors += 1
            continue

        rel = json_path.relative_to(SYMBOLS_ROOT)
        dest_json = output_dir / rel
        dest_svg = dest_json.with_suffix(".svg")

        exported_meta = dict(meta)
        exported_meta["svg_path"] = rel.with_suffix(".svg").as_posix()
        exported_meta["metadata_path"] = rel.as_posix()

        try:
            dest_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg_path, dest_svg)
            dest_json.write_text(
                json.dumps(exported_meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            copied += 1
        except OSError:
            errors += 1

    return {
        "output_dir": str(output_dir),
        "copied": copied,
        "skipped": skipped,
        "errors": errors,
        "message": f"Exported {copied} symbol{'s' if copied != 1 else ''} to {output_dir}",
    }
