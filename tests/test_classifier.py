"""Tests for src/classifier module."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.classifier import ClassificationResult, classify


class TestClassifier:
    """Test cases for the classifier module."""

    def test_classify_returns_classification_result(self, repo_root: Path) -> None:
        """Test that classify returns a ClassificationResult object."""
        # Create a minimal test SVG
        test_svg = repo_root / "input" / "test_symbol.svg"
        test_svg.parent.mkdir(parents=True, exist_ok=True)
        test_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>'
        )

        result = classify(test_svg)

        assert isinstance(result, ClassificationResult)
        assert isinstance(result.standard, str)
        assert isinstance(result.category, str)
        assert isinstance(result.subcategory, str)
        assert isinstance(result.confidence, str)
        assert isinstance(result.method, str)

        # Cleanup
        test_svg.unlink()

    def test_classification_result_is_immutable(self) -> None:
        """Test that ClassificationResult is immutable."""
        result = ClassificationResult(
            standard="ISA",
            category="valve",
            subcategory="ball",
            confidence="high",
            method="test",
        )

        with pytest.raises(AttributeError):
            result.standard = "ISO"

    def test_classify_unknown_file(self, tmp_path: Path) -> None:
        """Test classification of non-existent file."""
        fake_path = tmp_path / "nonexistent.svg"

        result = classify(fake_path)

        assert result.standard == "unknown"
        assert result.category == "unknown"
        assert result.confidence == "none"
