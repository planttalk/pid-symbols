"""Tests for src/utils module."""

from __future__ import annotations


from src.utils import (
    _display_name_from_stem,
    _extract_standard_from_name,
    _safe_std_slug,
    _slugify,
    _source_slug_from_path,
)


class TestSlugify:
    """Test cases for _slugify function."""

    def test_lowercase(self) -> None:
        assert _slugify("HELLO") == "hello"

    def test_spaces_to_underscores(self) -> None:
        assert _slugify("hello world") == "hello_world"

    def test_hyphens_to_underscores(self) -> None:
        assert _slugify("hello-world") == "hello_world"

    def test_multiple_underscores_collapsed(self) -> None:
        assert _slugify("hello___world") == "hello_world"

    def test_strips_leading_trailing(self) -> None:
        assert _slugify("_hello_") == "hello"


class TestSafeStdSlug:
    """Test cases for _safe_std_slug function."""

    def test_iso_standard(self) -> None:
        assert _safe_std_slug("ISO 10628-2") == "iso_10628_2"

    def test_din_standard(self) -> None:
        assert _safe_std_slug("DIN 2429") == "din_2429"


class TestDisplayNameFromStem:
    """Test cases for _display_name_from_stem function."""

    def test_snake_case(self) -> None:
        assert _display_name_from_stem("ball_valve") == "Ball Valve"

    def test_with_standard_tag(self) -> None:
        result = _display_name_from_stem("ball_valve (ISO 10628-2)")
        assert "Ball Valve" in result


class TestExtractStandardFromName:
    """Test cases for _extract_standard_from_name function."""

    def test_iso_standard(self) -> None:
        assert _extract_standard_from_name("valve (ISO 10628-2)") == "ISO 10628-2"

    def test_din_standard(self) -> None:
        assert _extract_standard_from_name("valve (DIN 2429)") == "DIN 2429"

    def test_no_standard(self) -> None:
        assert _extract_standard_from_name("valve") is None


class TestSourceSlugFromPath:
    """Test cases for _source_slug_from_path function."""

    def test_autocad_parser(self) -> None:
        result = _source_slug_from_path("input/autocad-parser/valves/test.svg")
        assert result == "autocad_parser"

    def test_pid_symbols_generator_downloaded(self) -> None:
        result = _source_slug_from_path(
            "input/pid-symbols-generator/downloaded/valves/test.svg"
        )
        assert result == "pid_symbols_generator_downloaded"

    def test_unknown_source(self) -> None:
        result = _source_slug_from_path("random/path.svg")
        assert result == "unknown_source"
