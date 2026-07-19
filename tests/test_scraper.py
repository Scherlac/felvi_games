"""Tests for shared 6/8-year exam-page handling in the scraper."""

from __future__ import annotations

from felvi_games.scraper import (
    _archive_year,
    _shared_page_file_matches_category,
    kategoria_mappak,
)


def test_shared_6_8_page_is_available_to_both_programmes() -> None:
    href = "/kozponti_feladatsorok/2024evi_6_8osztalyos"

    assert kategoria_mappak(href) == ("6_osztaly", "8_osztaly")


def test_shared_6_8_page_files_are_routed_by_source_grade() -> None:
    filenames = ["A6_2024_1_fl.pdf", "M6_2024_1_ut.pdf", "A4_2024_1_fl.pdf"]

    assert [
        name for name in filenames
        if _shared_page_file_matches_category(name, "6_osztaly")
    ] == ["A6_2024_1_fl.pdf", "M6_2024_1_ut.pdf"]
    assert [
        name for name in filenames
        if _shared_page_file_matches_category(name, "8_osztaly")
    ] == ["A4_2024_1_fl.pdf"]


def test_archive_year_uses_the_page_url_over_its_table_row() -> None:
    href = "/kozponti_feladatsorok/2023evi_6_8osztalyos"

    assert _archive_year(href, "2024") == "2023"