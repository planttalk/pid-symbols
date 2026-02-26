"""
Repository-level path configuration.

Uses a class-based approach to allow for dependency injection while
maintaining backward compatibility with the existing CLI override pattern.

Usage:
    # Default paths (read-only)
    from src.paths import Paths

    repo_root = Paths.REPO_ROOT
    input_dir = Paths.INPUT_DIR
    processed_dir = Paths.PROCESSED_DIR

    # Custom paths (for testing or alternative configurations)
    from src.paths import Paths
    Paths.configure(input_dir="/custom/input", output_dir="/custom/output")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PathConfig:
    """Immutable path configuration."""

    repo_root: Path
    input_dir: Path
    processed_dir: Path


class Paths:
    """
    Path configuration manager.

    Provides class-level path constants and methods to override them.
    This approach maintains backward compatibility with the CLI while
    enabling proper dependency injection for testing.
    """

    _repo_root: Path = Path(__file__).resolve().parent.parent
    _input_dir: Path | None = None
    _processed_dir: Path | None = None
    _configured: bool = False

    @classmethod
    def configure(
        cls, input_dir: Path | str | None = None, output_dir: Path | str | None = None
    ) -> None:
        """
        Configure custom paths.

        Args:
            input_dir: Custom input directory path
            output_dir: Custom output/processed directory path
        """
        if input_dir is not None:
            cls._input_dir = Path(input_dir).resolve()
        if output_dir is not None:
            cls._processed_dir = Path(output_dir).resolve()
        cls._configured = True

    @classmethod
    def reset(cls) -> None:
        """Reset to default paths."""
        cls._input_dir = None
        cls._processed_dir = None
        cls._configured = False

    @classmethod
    @property
    def REPO_ROOT(cls) -> Path:
        """Root directory of the repository."""
        return cls._repo_root

    @classmethod
    @property
    def INPUT_DIR(cls) -> Path:
        """Input directory for raw SVG files."""
        if cls._input_dir is not None:
            return cls._input_dir
        return cls._repo_root / "input"

    @classmethod
    @property
    def PROCESSED_DIR(cls) -> Path:
        """Processed output directory."""
        if cls._processed_dir is not None:
            return cls._processed_dir
        return cls._repo_root / "processed"

    @classmethod
    def get_config(cls) -> PathConfig:
        """Get current path configuration as an immutable dataclass."""
        return PathConfig(
            repo_root=cls.REPO_ROOT,
            input_dir=cls.INPUT_DIR,
            processed_dir=cls.PROCESSED_DIR,
        )


# Backward compatibility - these work as before but should be considered deprecated
REPO_ROOT = Paths.REPO_ROOT
INPUT_DIR = Paths.INPUT_DIR
PROCESSED_DIR = Paths.PROCESSED_DIR
