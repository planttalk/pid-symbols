"""
paths.py
--------------------
Repository-level path constants.
Mutable so that main.py CLI overrides (--input / --output) propagate to all
modules that import this module (not `from paths import ...`).

Usage in other modules:
    import paths
    ...
    svg_file = paths.REPO_ROOT / "processed" / ...
"""

from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parent.parent   # src/../ = repo root
INPUT_DIR     = REPO_ROOT / "input"
PROCESSED_DIR = REPO_ROOT / "processed"
