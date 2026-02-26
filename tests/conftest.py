"""Pytest configuration and shared fixtures for the P&ID Symbol Library."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path for imports
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root path."""
    return REPO_ROOT


@pytest.fixture
def test_data_dir(repo_root: Path) -> Path:
    """Return the test data directory."""
    return repo_root / "tests" / "data"


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Return a temporary output directory for tests."""
    return tmp_path / "output"
