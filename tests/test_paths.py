"""Tests for src/paths module."""

from __future__ import annotations

from pathlib import Path


from src.paths import Paths


class TestPaths:
    """Test cases for the Paths configuration class."""

    def test_default_paths(self) -> None:
        """Test default path values."""
        paths = Paths.get_config()
        assert paths.repo_root.name == "automation-labs-pid-symbols"
        assert paths.input_dir.name == "input"
        assert paths.processed_dir.name == "processed"

    def test_configure_custom_paths(self, tmp_path: Path) -> None:
        """Test configuring custom paths."""
        custom_input = tmp_path / "custom_input"
        custom_output = tmp_path / "custom_output"
        custom_input.mkdir()
        custom_output.mkdir()

        Paths.configure(input_dir=custom_input, output_dir=custom_output)

        assert Paths.INPUT_DIR == custom_input
        assert Paths.PROCESSED_DIR == custom_output

        # Reset for other tests
        Paths.reset()

    def test_reset_paths(self) -> None:
        """Test resetting paths to defaults."""
        Paths.reset()
        paths = Paths.get_config()
        assert paths.input_dir.name == "input"
        assert paths.processed_dir.name == "processed"

    def test_backward_compatibility(self) -> None:
        """Test that old module-level variables still work."""
        from src import paths as paths_module

        Paths.reset()
        assert paths_module.INPUT_DIR.name == "input"
        assert paths_module.PROCESSED_DIR.name == "processed"
