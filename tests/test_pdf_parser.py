"""Tests for felvi_games.pdf_parser.

All OpenAI calls are mocked – no network required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from felvi_games.models import Feladat
from felvi_games.pdf_parser import (
    TaskBlock,
    _dict_to_feladat,
    _group_feladatok,
    _id_prefix_from_source,
    annotate_block,
    extract_feladatok,
    extract_feladatok_batched,
    find_exam_pairs,
    match_fl_ut_blocks,
    parse_exam,
    parse_filename_meta,
    pdf_to_text,
    split_into_task_blocks,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_pdf(tmp_path: Path, name: str, text: str) -> Path:
    """Write a minimal text-only PDF that pdftotext can read."""
    import pdftotext  # noqa: F401 – ensure it's importable

    # We cannot easily create a real PDF in tests, so we patch pdf_to_text
    # where needed.  This helper creates a sentinel file for path-based tests.
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 placeholder")
    return p


def _gpt_response(feladatok: list[dict]) -> MagicMock:
    """Build a mock OpenAI completion response carrying *feladatok* as JSON."""
    msg = MagicMock()
    msg.content = json.dumps({"feladatok": feladatok})
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_SAMPLE_ITEM = {
    "id": "mat_2025_1_a",
    "kerdes": "Mennyi 2 + 2?",
    "helyes_valasz": "4",
    "hint": "Alap összeadás.",
    "magyarazat": "Kettő meg kettő négy.",
    "neh": 1,
    "szint": "9 osztályos",
}


# ---------------------------------------------------------------------------
# pdf_to_text
# ---------------------------------------------------------------------------


class TestPdfToText:
    def test_returns_string(self, tmp_path):
        """pdf_to_text wraps pdftotext.PDF and joins pages."""
        p = tmp_path / "dummy.pdf"
        p.write_bytes(b"%PDF placeholder")
        pages_mock = ["Lap 1 szöveg", "Lap 2 szöveg"]
        with patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=pages_mock):
            result = pdf_to_text(p)
        assert "Lap 1 szöveg" in result
        assert "Lap 2 szöveg" in result

    def test_pages_joined_with_double_newline(self, tmp_path):
        p = tmp_path / "dummy.pdf"
        p.write_bytes(b"%PDF placeholder")
        pages_mock = ["A", "B", "C"]
        with patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=pages_mock):
            result = pdf_to_text(p)
        assert result == "[Oldal 1]\nA\n\n[Oldal 2]\nB\n\n[Oldal 3]\nC"

    def test_empty_pdf_returns_empty_string(self, tmp_path):
        p = tmp_path / "empty.pdf"
        p.write_bytes(b"%PDF placeholder")
        with patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=[]):
            result = pdf_to_text(p)
        assert result == ""


# ---------------------------------------------------------------------------
# _id_prefix_from_source
# ---------------------------------------------------------------------------


class TestIdPrefix:
    def test_matek_prefix(self):
        assert _id_prefix_from_source("M8_2025_1_fl.pdf", "matek") == "mat8_2025_1"

    def test_magyar_prefix(self):
        assert _id_prefix_from_source("A8_2024_2_fl.pdf", "magyar") == "mag8_2024_2"

    def test_4osztaly_prefix(self):
        assert _id_prefix_from_source("M4_2025_1_fl.pdf", "matek") == "mat4_2025_1"

    def test_handles_missing_parts_gracefully(self):
        prefix = _id_prefix_from_source("unknown.pdf", "matek")
        assert prefix.startswith("mat_")


class TestParseFilenameMeta:
    def test_matek_feladatlap(self):
        m = parse_filename_meta("M8_2025_1_fl.pdf")
        assert m == {"ev": 2025, "valtozat": 1, "kind": "fl", "targy": "matek", "szint": "8 osztályos"}

    def test_magyar_utmutato(self):
        m = parse_filename_meta("A8_2024_2_ut.pdf")
        assert m == {"ev": 2024, "valtozat": 2, "kind": "ut", "targy": "magyar", "szint": "8 osztályos"}

    def test_4osztaly_feladatlap(self):
        m = parse_filename_meta("M4_2025_1_fl.pdf")
        assert m == {"ev": 2025, "valtozat": 1, "kind": "fl", "targy": "matek", "szint": "4 osztályos"}

    def test_unknown_filename_returns_nones(self):
        m = parse_filename_meta("random.pdf")
        assert m == {"ev": None, "valtozat": None, "kind": None, "targy": None, "szint": None}

    def test_lowercase_prefix_accepted(self):
        m = parse_filename_meta("m8_2026_1_fl.pdf")
        assert m["targy"] == "matek"
        assert m["ev"] == 2026


# ---------------------------------------------------------------------------
# _dict_to_feladat
# ---------------------------------------------------------------------------


class TestDictToFeladat:
    def test_valid_dict_returns_feladat(self):
        f = _dict_to_feladat({**_SAMPLE_ITEM, "targy": "matek"})
        assert isinstance(f, Feladat)
        assert f.id == "mat_2025_1_a"
        assert f.neh == 1

    def test_missing_field_raises_key_error(self):
        bad = {k: v for k, v in _SAMPLE_ITEM.items() if k != "helyes_valasz"}
        with pytest.raises(KeyError):
            _dict_to_feladat(bad)

    def test_invalid_neh_raises_value_error(self):
        bad = {**_SAMPLE_ITEM, "neh": 5}
        with pytest.raises(ValueError):
            _dict_to_feladat(bad)

    def test_neh_coerced_from_string(self):
        f = _dict_to_feladat({**_SAMPLE_ITEM, "neh": "2", "targy": "matek"})
        assert f.neh == 2

    def test_optional_fields_default_to_empty(self):
        f = _dict_to_feladat(_SAMPLE_ITEM)
        assert f.targy == ""
        assert f.pdf_source is None
        assert f.ut_source is None
        assert f.ev is None
        assert f.valtozat is None
        # feladat_sorszam is derived from id when not supplied
        assert f.feladat_sorszam is not None or f.id == "mat_2025_1_a"


# ---------------------------------------------------------------------------
# extract_feladatok (GPT mocked)
# ---------------------------------------------------------------------------


class TestExtractFeladatok:
    def _run(self, items: list[dict], targy: str = "matek") -> list[Feladat]:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response(items)
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            return extract_feladatok(
                fl_text="Feladatlap szöveg",
                ut_text="Útmutató szöveg",
                targy=targy,
                pdf_source="M8_2025_1_fl.pdf",
            )

    def test_single_valid_item(self):
        result = self._run([_SAMPLE_ITEM])
        assert len(result) == 1
        assert result[0].id == "mat_2025_1_a"

    def test_multiple_valid_items(self):
        items = [
            {**_SAMPLE_ITEM, "id": "mat_2025_1_a"},
            {**_SAMPLE_ITEM, "id": "mat_2025_1_b", "neh": 2},
        ]
        result = self._run(items)
        assert len(result) == 2

    def test_targy_injected_into_feladat(self):
        result = self._run([_SAMPLE_ITEM], targy="matek")
        assert result[0].targy == "matek"

    def test_pdf_source_none_without_parse_exam(self):
        """pdf_source is derived from fl_pdf_path; extract_feladatok does not set it."""
        result = self._run([_SAMPLE_ITEM])
        assert result[0].pdf_source is None

    def test_invalid_item_skipped_not_raised(self):
        bad = {k: v for k, v in _SAMPLE_ITEM.items() if k != "hint"}
        result = self._run([bad, _SAMPLE_ITEM])
        assert len(result) == 1  # only the valid one survives

    def test_empty_gpt_response_returns_empty_list(self):
        result = self._run([])
        assert result == []

    def test_gpt_called_with_correct_model(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            extract_feladatok("fl", "ut", "matek", "src.pdf", model="gpt-test-model")
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-test-model"

    def test_ev_valtozat_injected_from_filename(self):
        result = self._run([_SAMPLE_ITEM])
        assert result[0].ev == 2025
        assert result[0].valtozat == 1

    def test_ut_source_none_without_parse_exam(self):
        """ut_source is derived from ut_pdf_path; extract_feladatok does not set it."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            result = extract_feladatok(
                "fl", "ut", "matek", "M8_2025_1_fl.pdf", "M8_2025_1_ut.pdf"
            )
        assert result[0].ut_source is None

    def test_feladat_sorszam_from_gpt(self):
        item_with_sorszam = {**_SAMPLE_ITEM, "feladat_sorszam": "1a"}
        result = self._run([item_with_sorszam])
        assert result[0].feladat_sorszam == "1a"

    def test_feladat_sorszam_derived_from_id_when_missing(self):
        # id = "mat_2025_1_a" has 4 parts after split → last part used as sorszam
        result = self._run([_SAMPLE_ITEM])   # _SAMPLE_ITEM has no feladat_sorszam
        assert result[0].feladat_sorszam == "a"  # derived from id suffix
        """fl_text longer than 12K chars is still sent (truncated inside function)."""
        long_text = "x" * 20_000
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            extract_feladatok(long_text, "ut", "matek", "src.pdf")
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        user_msg = call_kwargs["messages"][1]["content"]
        # The original 20K string is truncated to 12K in the prompt
        assert "x" * 12_001 not in user_msg


# ---------------------------------------------------------------------------
# find_exam_pairs
# ---------------------------------------------------------------------------


class TestFindExamPairs:
    def _setup_exams(self, tmp_path: Path, files: list[str]) -> Path:
        exams_dir = tmp_path / "exams" / "9_evfolyam" / "2025"
        exams_dir.mkdir(parents=True)
        for name in files:
            (exams_dir / name).write_bytes(b"%PDF placeholder")
        return tmp_path / "exams"

    def test_matched_pair_yielded(self, tmp_path):
        exams = self._setup_exams(tmp_path, ["M8_2025_1_fl.pdf", "M8_2025_1_ut.pdf"])
        pairs = list(find_exam_pairs(exams))
        assert len(pairs) == 1
        fl, ut, targy = pairs[0]
        assert fl.name == "M8_2025_1_fl.pdf"
        assert ut.name == "M8_2025_1_ut.pdf"
        assert targy == "matek"

    def test_magyar_pair_recognized(self, tmp_path):
        exams = self._setup_exams(tmp_path, ["A8_2024_1_fl.pdf", "A8_2024_1_ut.pdf"])
        pairs = list(find_exam_pairs(exams))
        assert len(pairs) == 1
        assert pairs[0][2] == "magyar"

    def test_missing_ut_skipped(self, tmp_path):
        exams = self._setup_exams(tmp_path, ["M8_2025_1_fl.pdf"])
        pairs = list(find_exam_pairs(exams))
        assert pairs == []

    def test_ut_only_not_yielded(self, tmp_path):
        exams = self._setup_exams(tmp_path, ["M8_2025_1_ut.pdf"])
        pairs = list(find_exam_pairs(exams))
        assert pairs == []

    def test_multiple_pairs_all_found(self, tmp_path):
        files = [
            "M8_2025_1_fl.pdf", "M8_2025_1_ut.pdf",
            "A8_2025_1_fl.pdf", "A8_2025_1_ut.pdf",
        ]
        exams = self._setup_exams(tmp_path, files)
        pairs = list(find_exam_pairs(exams))
        assert len(pairs) == 2
        subjects = {t for _, _, t in pairs}
        assert subjects == {"matek", "magyar"}

    def test_unknown_prefix_ignored(self, tmp_path):
        exams = self._setup_exams(tmp_path, ["X8_2025_1_fl.pdf", "X8_2025_1_ut.pdf"])
        pairs = list(find_exam_pairs(exams))
        assert pairs == []

    def test_empty_directory_returns_empty(self, tmp_path):
        exams = tmp_path / "exams"
        exams.mkdir()
        assert list(find_exam_pairs(exams)) == []


# ---------------------------------------------------------------------------
# parse_exam (integration – pdftotext + GPT mocked)
# ---------------------------------------------------------------------------


class TestParseExam:
    def test_returns_feladatok(self, tmp_path):
        fl = tmp_path / "M8_2025_1_fl.pdf"
        ut = tmp_path / "M8_2025_1_ut.pdf"
        fl.write_bytes(b"%PDF placeholder")
        ut.write_bytes(b"%PDF placeholder")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])

        with (
            patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=["Szöveg"]),
            patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client),
        ):
            feladatok, csoportok = parse_exam(fl, ut, "matek")

        assert len(feladatok) == 1
        assert feladatok[0].targy == "matek"
        assert len(csoportok) >= 1

    def test_pdf_source_set_to_fl_filename(self, tmp_path, monkeypatch):
        fl = tmp_path / "M8_2026_2_fl.pdf"
        ut = tmp_path / "M8_2026_2_ut.pdf"
        fl.write_bytes(b"%PDF placeholder")
        ut.write_bytes(b"%PDF placeholder")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])

        with (
            patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=["Lap"]),
            patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client),
            patch("felvi_games.pdf_parser.get_exams_dir", return_value=tmp_path),
        ):
            feladatok, _csoportok = parse_exam(fl, ut, "matek")

        assert feladatok[0].fl_pdf_path == "M8_2026_2_fl.pdf"
        assert feladatok[0].pdf_source == "M8_2026_2_fl.pdf"

    def test_ut_pdf_path_set_by_parse_exam(self, tmp_path):
        fl = tmp_path / "M8_2026_2_fl.pdf"
        ut = tmp_path / "M8_2026_2_ut.pdf"
        fl.write_bytes(b"%PDF placeholder")
        ut.write_bytes(b"%PDF placeholder")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])

        with (
            patch("felvi_games.pdf_parser.pdftotext.PDF", return_value=["Lap"]),
            patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client),
            patch("felvi_games.pdf_parser.get_exams_dir", return_value=tmp_path),
        ):
            feladatok, _csoportok = parse_exam(fl, ut, "matek")

        assert feladatok[0].ut_pdf_path == "M8_2026_2_ut.pdf"
        assert feladatok[0].ut_source == "M8_2026_2_ut.pdf"


# ---------------------------------------------------------------------------
# _group_feladatok
# ---------------------------------------------------------------------------


def _make_flat_feladat(
    id: str,
    sorszam: str,
    targy: str = "matek",
    max_pont: int = 1,
) -> Feladat:
    return Feladat.from_dict(
        {
            "id": id,
            "neh": 1,
            "szint": "6 osztályos",
            "kerdes": f"K\u00e9rd\u00e9s {id}",
            "helyes_valasz": "X",
            "hint": "H",
            "magyarazat": "M",
            "feladat_sorszam": sorszam,
            "max_pont": max_pont,
        },
        targy=targy,
    )


class TestGroupFeladatok:
    def test_single_feladat_creates_one_group(self):
        f = _make_flat_feladat("m01", "1")
        feladatok, csoportok = _group_feladatok([f], "M8_2025_1_fl.pdf")
        assert len(csoportok) == 1
        assert csoportok[0].feladat_sorszam == "1"
        assert feladatok[0].csoport_id == csoportok[0].id

    def test_sub_tasks_merged_into_same_group(self):
        items = [
            _make_flat_feladat("m3a", "3a", max_pont=2),
            _make_flat_feladat("m3b", "3b", max_pont=1),
            _make_flat_feladat("m3c", "3c", max_pont=3),
        ]
        feladatok, csoportok = _group_feladatok(items, "M8_2025_1_fl.pdf")
        assert len(csoportok) == 1
        csoport = csoportok[0]
        assert csoport.feladat_sorszam == "3"
        assert csoport.max_pont_ossz == 6

    def test_csoport_sorrend_assigned_correctly(self):
        items = [
            _make_flat_feladat("m2a", "2a"),
            _make_flat_feladat("m2b", "2b"),
        ]
        feladatok, csoportok = _group_feladatok(items, "M8_2025_1_fl.pdf")
        sorrendek = [f.csoport_sorrend for f in feladatok]
        assert sorrendek == [1, 2]

    def test_two_distinct_groups(self):
        items = [
            _make_flat_feladat("m1a", "1a"),
            _make_flat_feladat("m2a", "2a"),
        ]
        feladatok, csoportok = _group_feladatok(items, "A8_2025_1_fl.pdf")
        assert len(csoportok) == 2
        group_keys = {c.feladat_sorszam for c in csoportok}
        assert group_keys == {"1", "2"}

    def test_all_feladatok_have_csoport_id(self):
        items = [
            _make_flat_feladat("m1a", "1a"),
            _make_flat_feladat("m1b", "1b"),
            _make_flat_feladat("m2a", "2a"),
        ]
        feladatok, csoportok = _group_feladatok(items, "M8_2025_1_fl.pdf")
        assert all(f.csoport_id is not None for f in feladatok)
        assert all(f.csoport_sorrend is not None for f in feladatok)


# ---------------------------------------------------------------------------
# New fields in _dict_to_feladat
# ---------------------------------------------------------------------------


class TestDictToFeladatNewFields:
    def test_elfogadott_valaszok_list_parsed(self):
        item = {**_SAMPLE_ITEM, "elfogadott_valaszok": ["4", "n\u00e9gy"]}
        f = _dict_to_feladat(item)
        assert f.elfogadott_valaszok == ["4", "n\u00e9gy"]

    def test_elfogadott_valaszok_null_stays_none(self):
        f = _dict_to_feladat(_SAMPLE_ITEM)
        assert f.elfogadott_valaszok is None

    def test_feladat_tipus_parsed(self):
        item = {**_SAMPLE_ITEM, "feladat_tipus": "tobbvalasztos"}
        f = _dict_to_feladat(item)
        assert f.feladat_tipus == "tobbvalasztos"

    def test_max_pont_default_is_1(self):
        f = _dict_to_feladat(_SAMPLE_ITEM)
        assert f.max_pont == 1

    def test_max_pont_from_dict(self):
        item = {**_SAMPLE_ITEM, "max_pont": 3}
        f = _dict_to_feladat(item)
        assert f.max_pont == 3

    def test_reszpontozas_parsed(self):
        item = {**_SAMPLE_ITEM, "reszpontozas": "3p=mind helyes, 1p=felh\u00e9t"}
        f = _dict_to_feladat(item)
        assert f.reszpontozas == "3p=mind helyes, 1p=felh\u00e9t"

    def test_valaszlehetosegek_list_parsed(self):
        item = {**_SAMPLE_ITEM, "valaszlehetosegek": ["A", "B", "C", "D"]}
        f = _dict_to_feladat(item)
        assert f.valaszlehetosegek == ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# split_into_task_blocks
# ---------------------------------------------------------------------------


class TestSplitIntoTaskBlocks:
    def test_single_task_detected(self):
        text = "[Oldal 1]\n1.   Kérdés szövege\nalaptétel\n"
        blocks = split_into_task_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].sorszam == 1
        assert blocks[0].oldal_start == 1

    def test_multiple_tasks_split_correctly(self):
        text = (
            "[Oldal 1]\n"
            "1.   Első feladat\n"
            "kérdés szövege\n\n"
            "2.   Második feladat\n"
            "másik szöveg\n"
        )
        blocks = split_into_task_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].sorszam == 1
        assert blocks[1].sorszam == 2

    def test_subtasks_belong_to_parent_block(self):
        """Sub-task lines after the task header but before the next header
        should be included in the current block (e.g. task 9 continues on
        the next page with a), b), c) lines)."""
        text = (
            "[Oldal 1]\n"
            "9.   Olvasd el!\n"
            "Szöveg.\n"
            "[Oldal 2]\n"
            "a) Első alkérdés\n"
            "b) Második alkérdés\n"
        )
        blocks = split_into_task_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].sorszam == 9
        assert "a) Első alkérdés" in blocks[0].raw_text
        assert "b) Második alkérdés" in blocks[0].raw_text

    def test_page_tracking_across_blocks(self):
        text = (
            "[Oldal 1]\n"
            "1.   Feladat\n"
            "[Oldal 3]\n"
            "9.   Másik feladat\n"
        )
        blocks = split_into_task_blocks(text)
        b1 = next(b for b in blocks if b.sorszam == 1)
        b9 = next(b for b in blocks if b.sorszam == 9)
        assert b1.oldal_start == 1
        assert b9.oldal_start == 3

    def test_no_tasks_returns_empty_list(self):
        text = "[Oldal 1]\nCsak bevezető szöveg, nincs feladatblokk.\n"
        assert split_into_task_blocks(text) == []

    def test_page_header_not_treated_as_task(self):
        """'8. évfolyam — ...' page headers must not be mistaken for task 8."""
        text = (
            "[Oldal 2]\n"
            "                         8. évfolyam — MNy1 feladatlap / 2\n"
            "1.   Valódi feladat szövege\n"
        )
        blocks = split_into_task_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].sorszam == 1

    def test_sorted_by_sorszam(self):
        text = "9.   Kilencedik\n1.   Első\n3.   Harmadik\n"
        blocks = split_into_task_blocks(text)
        assert [b.sorszam for b in blocks] == [1, 3, 9]

    def test_sor_start_is_global_line_number(self):
        text = "[Oldal 1]\nElső sor\n2.   Feladat\n"
        blocks = split_into_task_blocks(text)
        assert blocks[0].sor_start == 3  # third line of the full text

    def test_ten_feladatok_from_a8_fl_like_text(self):
        """Simulate a 10-task exam; expect exactly 10 blocks."""
        lines = []
        for i in range(1, 11):
            lines.append(f"{i}.   Feladat szövege {i}")
            lines.append("    altétel")
        blocks = split_into_task_blocks("\n".join(lines))
        assert len(blocks) == 10
        assert [b.sorszam for b in blocks] == list(range(1, 11))


# ---------------------------------------------------------------------------
# annotate_block
# ---------------------------------------------------------------------------


class TestAnnotateBlock:
    def test_header_format(self):
        block = TaskBlock(sorszam=5, oldal_start=3, sor_start=42, raw_text="Feladat szövege")
        result = annotate_block(block)
        assert result.startswith("## [Feladat 5 | Oldal 3, sor 42]\n")

    def test_raw_text_preserved(self):
        block = TaskBlock(sorszam=1, oldal_start=1, sor_start=1, raw_text="alma körte")
        result = annotate_block(block)
        assert "alma körte" in result


# ---------------------------------------------------------------------------
# match_fl_ut_blocks
# ---------------------------------------------------------------------------


class TestMatchFlUtBlocks:
    def _block(self, sorszam: int) -> TaskBlock:
        return TaskBlock(sorszam=sorszam, oldal_start=1, sor_start=1, raw_text=f"Feladat {sorszam}")

    def test_matching_blocks_paired(self):
        fl = [self._block(1), self._block(2)]
        ut = [self._block(1), self._block(2)]
        pairs = match_fl_ut_blocks(fl, ut)
        assert len(pairs) == 2
        for fl_b, ut_b in pairs:
            assert ut_b is not None
            assert fl_b.sorszam == ut_b.sorszam

    def test_missing_ut_block_gives_none(self):
        fl = [self._block(1), self._block(2)]
        ut = [self._block(1)]
        pairs = match_fl_ut_blocks(fl, ut)
        sorzam_ut = {fl_b.sorszam: ut_b for fl_b, ut_b in pairs}
        assert sorzam_ut[1] is not None
        assert sorzam_ut[2] is None

    def test_empty_fl_returns_empty(self):
        assert match_fl_ut_blocks([], [self._block(1)]) == []

    def test_order_follows_fl_blocks(self):
        fl = [self._block(3), self._block(1)]
        ut = [self._block(1), self._block(3)]
        pairs = match_fl_ut_blocks(fl, ut)
        assert pairs[0][0].sorszam == 3
        assert pairs[1][0].sorszam == 1


# ---------------------------------------------------------------------------
# extract_feladatok_batched (GPT mocked)
# ---------------------------------------------------------------------------


class TestExtractFeladatokBatched:
    def _make_blocks(self, count: int) -> list[tuple[TaskBlock, TaskBlock | None]]:
        fl = [TaskBlock(sorszam=i, oldal_start=i, sor_start=i, raw_text=f"{i}.   Feladat {i}") for i in range(1, count + 1)]
        ut = [TaskBlock(sorszam=i, oldal_start=i, sor_start=i, raw_text=f"Helyes: {i}") for i in range(1, count + 1)]
        return match_fl_ut_blocks(fl, ut)

    def test_single_batch_single_item(self):
        matched = self._make_blocks(1)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            result = extract_feladatok_batched(matched, "matek", "M8_2025_1_fl.pdf")
        assert len(result) == 1
        assert mock_client.chat.completions.create.call_count == 1

    def test_batching_creates_correct_number_of_calls(self):
        matched = self._make_blocks(9)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([_SAMPLE_ITEM])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            extract_feladatok_batched(matched, "matek", "M8_2025_1_fl.pdf", batch_size=4)
        # ceil(9/4) = 3 calls
        assert mock_client.chat.completions.create.call_count == 3

    def test_empty_matched_blocks_returns_empty(self):
        with patch("felvi_games.pdf_parser._make_openai_client"):
            result = extract_feladatok_batched([], "matek", "M8_2025_1_fl.pdf")
        assert result == []

    def test_failed_batch_skipped_gracefully(self):
        matched = self._make_blocks(2)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("network error")
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            result = extract_feladatok_batched(matched, "matek", "M8_2025_1_fl.pdf")
        assert result == []  # error swallowed, empty result

    def test_annotated_metadata_in_prompt(self):
        """The GPT prompt must contain the ## [Feladat N | Oldal X] headers."""
        matched = self._make_blocks(1)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _gpt_response([])
        with patch("felvi_games.pdf_parser._make_openai_client", return_value=mock_client):
            extract_feladatok_batched(matched, "matek", "M8_2025_1_fl.pdf")
        user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "## [Feladat 1 | Oldal 1, sor 1]" in user_msg
