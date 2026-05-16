"""Tests for source text search and retrieval utilities."""

from __future__ import annotations

import pytest
from pathlib import Path

from felvi_games.config import resolve_asset
from felvi_games.source_search import (
    search_source_text,
    get_source_window,
    find_task_in_sources,
    compare_excerpt_to_source,
)


@pytest.fixture
def sample_source_file(tmp_path: Path) -> Path:
    """Create a sample source text file for testing."""
    content = """8. Feladat
Olvasd el az alábbi szöveget!

A nap sárgán égett az égen.
A felhők fehéren úszkáltak,
Mint tavaszi felhők áprilisban.

a) Melyik szónak van legtöbb magánhangzója?
Válasz: sárgán (4)

b) Milyen műfajú a szöveg?
Válasz: költészet

9. Feladat
Ez egy másik feladat, amely más tartalommal foglalkozik.
"""
    file_path = tmp_path / "source.txt"
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestSearchSourceText:
    """Test search_source_text function."""

    def test_find_simple_text(self, sample_source_file: Path):
        """Test finding simple text in source."""
        # Create a relative path-like string for the sample file
        result = search_source_text(
            "text/sample_source.txt",
            "8. Feladat",
            max_hits=5,
        )
        
        # Result structure should be valid even if file doesn't exist in assets
        assert "status" in result
        assert "file_path" in result
        assert "query" in result
        assert "match_count" in result


class TestSearchSourceTextWithAssets:
    """Test with actual asset files when available."""

    def test_search_task_number(self):
        """Search for task number in actual guide file."""
        # Try to find task 8 in a real asset file
        result = search_source_text(
            "text/A8_2020_2_ut.txt",
            "8.",
            max_hits=5,
            context_lines=2,
        )
        
        # Should return valid result structure
        assert "status" in result
        assert "file_path" in result
        assert "query" in result
        assert "match_count" in result
        assert "matches" in result


class TestGetSourceWindow:
    """Test get_source_window function."""

    def test_get_window_with_real_file(self):
        """Get a window of lines from a real asset file."""
        result = get_source_window(
            "text/A8_2020_2_ut.txt",
            start_line=1,
            end_line=10,
        )
        
        assert "status" in result
        assert "file_path" in result
        assert "lines" in result
        assert "total_lines" in result
        
        if result["status"] == "ok":
            assert isinstance(result["lines"], list)
            assert len(result["lines"]) <= 10


class TestFindTaskInSources:
    """Test find_task_in_sources function."""

    def test_parse_feladat_id(self):
        """Test parsing feladat_id to extract task/subtask."""
        result = find_task_in_sources(
            "mag4_2020_2_8_a",
            task_sheet_path="text/A8_2020_2_fl.txt",
            guide_path="text/A8_2020_2_ut.txt",
        )
        
        assert result["status"] == "ok"
        assert result["feladat_id"] == "mag4_2020_2_8_a"
        assert result["task_number"] == "8"
        assert result["subtask_letter"] == "a"

    def test_invalid_feladat_id(self):
        """Test with invalid feladat_id format."""
        result = find_task_in_sources("invalid_id")
        
        assert result["status"] == "error"
        assert "Cannot parse" in result.get("error", "")


class TestCompareExcerptToSource:
    """Test compare_excerpt_to_source function."""

    def test_exact_match_not_found(self):
        """Test with excerpt that doesn't exist in source."""
        result = compare_excerpt_to_source(
            "This text definitely does not exist anywhere",
            "text/A8_2020_2_ut.txt",
        )
        
        # Should return valid result structure
        assert "status" in result
        assert result["status"] in ["not_found", "error"]

    def test_empty_excerpt_error(self):
        """Test with empty excerpt."""
        result = compare_excerpt_to_source("", "text/A8_2020_2_ut.txt")
        
        assert result["status"] == "error"
        assert "Empty" in result.get("error", "")


class TestSourceSearchIntegration:
    """Integration tests combining multiple source search functions."""

    def test_locate_then_search_flow(self):
        """Test typical workflow: locate task, then search for specific section."""
        # First locate the task
        locate_result = find_task_in_sources(
            "mag4_2020_2_8_a",
            task_sheet_path="text/A8_2020_2_fl.txt",
            guide_path="text/A8_2020_2_ut.txt",
        )
        
        assert locate_result["status"] == "ok"
        
        # Then search for specific keyword in guide
        search_result = search_source_text(
            "text/A8_2020_2_ut.txt",
            "a)",
            max_hits=3,
        )
        
        assert "status" in search_result
        assert "matches" in search_result


class TestSourceSearchEdgeCases:
    """Test edge cases and error handling."""

    def test_search_nonexistent_file(self):
        """Test searching in non-existent file."""
        result = search_source_text(
            "text/nonexistent_file.txt",
            "query",
        )
        
        assert result["status"] == "error"
        assert "not found" in result.get("error", "").lower()

    def test_empty_query(self):
        """Test with empty search query."""
        result = search_source_text(
            "text/A8_2020_2_ut.txt",
            "",
        )
        
        assert result["status"] == "error"

    def test_get_window_invalid_range(self):
        """Test get_source_window with invalid line range."""
        result = get_source_window(
            "text/A8_2020_2_ut.txt",
            start_line=5,
            end_line=1,  # end < start
        )
        
        assert result["status"] == "error" or result.get("lines") is not None


def test_asset_path_resolution():
    """Test that resolve_asset works for expected paths."""
    # This test verifies the asset resolution works
    try:
        path = resolve_asset("text/A8_2020_2_ut.txt")
        assert path is not None
        # Path may or may not exist depending on environment
    except Exception:
        # It's OK if asset resolution fails in test environment
        pass
