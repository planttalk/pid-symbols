"""
src package - P&ID Symbol Library core modules.

Public API:
    classifier   - Symbol classification strategies
    constants   - Shared constants and domain types
    degradation - Image degradation effects
    augmentation - Image augmentation for training
    export      - Export utilities
    metadata    - Metadata assembly and path resolution
    snap_points - Port/snap point detection
    svg_utils   - SVG manipulation utilities
    paths       - Repository path constants
    studio      - Browser-based symbol editor (separate CLI)
"""

from . import (
    augmentation,
    classifier,
    constants,
    degradation,
    export,
    metadata,
    paths,
    snap_points,
    svg_utils,
    utils,
)

__all__ = [
    "augmentation",
    "classifier",
    "constants",
    "degradation",
    "export",
    "metadata",
    "paths",
    "snap_points",
    "svg_utils",
    "utils",
]
