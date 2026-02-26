"""Shared constants for studio augmentation utilities."""

from __future__ import annotations

from typing import Final

DEMOGRAPHIC_SIZE_MIN: Final[int] = 64
DEMOGRAPHIC_SIZE_MAX: Final[int] = 2048
PREVIEW_MAX_COUNT: Final[int] = 200
GENERATE_MAX_COUNT: Final[int] = 100
BATCH_MAX_COUNT: Final[int] = 200
RANDOM_EFFECTS_MIN: Final[int] = 3
RANDOM_EFFECTS_MAX: Final[int] = 7
COMBO_ATTEMPT_LIMIT: Final[int] = 12
YOLO_MASK_THRESHOLD: Final[int] = 240
EFFECT_MIN_SCALE: Final[float] = 0.15
EFFECT_MAX_SCALE: Final[float] = 0.65
EFFECT_STDEV_SCALE: Final[float] = 0.7
EFFECT_STDEV_RANGE: Final[float] = 1.3
