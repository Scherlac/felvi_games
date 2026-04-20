"""Feladat extractor: PDF → text → GPT → Feladat objects → DB.

Pipeline
--------
1. pdf_to_text()          – pdftotext → one string per PDF
2. extract_feladatok()    – GPT parses text pair (feladatlap + útmutató)
                            and returns a list of Feladat objects
3. CLI main()             – glues everything together, upserts into DB
                            (optional: --review to run interactive CLI review)

Filename convention
-------------------
  A8_YYYY_N_fl.pdf  → Magyar feladatlap (Anyanyelv)
  M8_YYYY_N_fl.pdf  → Matek feladatlap
  *_ut.pdf          → Javítási útmutató (answer key) – paired with its _fl
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterator
import dataclasses

import pdftotext
from dotenv import load_dotenv
from openai import OpenAI

from felvi_games.config import get_db_path, get_exams_dir, relative_text_path, text_cache_path
from felvi_games.db import FeladatRepository
from felvi_games.models import Feladat
from felvi_games.review import print_feladat, review_feladatok

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Filename prefix → subject name
_TARGY_MAP: dict[str, str] = {"A": "magyar", "M": "matek"}

# Filename gym-type number → szint_ertek (matches models.KATEGORIA_INFO)
# A fájlnévben lévő szám a TANULÓ jelenlegi évfolyamát jelöli:
# A8_ / M8_ → 8. osztályos tanuló → 4 osztályos gimnázium felvételi
# A6_ / M6_ → 6. osztályos tanuló → 6 osztályos gimnázium felvételi
# A4_ / M4_ → 4. osztályos tanuló → 8 osztályos gimnázium felvételi
_SZINT_MAP: dict[int, str] = {8: "4 osztályos", 6: "6 osztályos", 4: "8 osztályos"}

# Difficulty descriptions passed to GPT
_NEH_SCALE = (
    "1 = könnyű (alapszintű számolás / szóértés, egyértelmű válasz), "
    "2 = közepes (több lépés / következtetés kell), "
    "3 = nehéz (komplex, ritka tudás vagy kreativitás kell)"
)

# ---------------------------------------------------------------------------
# Step 1 – PDF → text
# ---------------------------------------------------------------------------


def pdf_to_text(path: Path) -> str:
    """Extract all pages from *path* and return them joined as one string.
    Each page is prefixed with [Oldal N] so GPT can identify page numbers."""
    with open(path, "rb") as fh:
        pages = list(pdftotext.PDF(fh))
    return "\n\n".join(f"[Oldal {i + 1}]\n{page}" for i, page in enumerate(pages))


# ---------------------------------------------------------------------------
# Step 2 – text pair → Feladat list (via GPT)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Felvételi feladatsor elemző vagy. Feladatlapot és javítási útmutatót kapod.
Minden egyes részfeladatból (pl. 1a, 1b, 2a…) ONE JSON objektumot generálj.
Komplex számítási/rajz/táblázat feladatokat egyszerűsítsd: a kérdést úgy fogalmazd,
hogy szövegesen (egy válasszal) megválaszolható legyen, és add meg a helyes választ is.Fontos: ha több részfeladat egyazon bevezető szövegre, ábrára vagy táblázatra hivatkozik,
minden érintett feladat kontextus mezőjébe másold be a teljes közös részt."""

_USER_TEMPLATE = """\
## Sorozat adatok
- Tantárgy: {targy}
- Forrás PDF: {pdf_source}
- Szint: {szint}

## Feladatlap szövege
{fl_text}

## Javítási útmutató szövege
{ut_text}

---

Generálj egy JSON objektumot, amely egyetlen "feladatok" kulcsot tartalmaz.
Az érték egy lista; minden elem tartalmazza:
- "id": string – egyedi azonosító, formátum: "{id_prefix}_<feladat_szam>_<betű>"
  például "{id_prefix}_1_a", "{id_prefix}_2_b"
- "kerdes": string – a részfeladat kérdése, teljes mondatban (max 3 mondat)
- "helyes_valasz": string – a helyes válasz, rövid, tömör (max 1-2 mondat)
- "hint": string – egy segítő tipp a megoldáshoz (max 1 mondat)
- "magyarazat": string – rövid magyarázat miért helyes (max 2 mondat)
- "neh": int – nehézség 1–3 ({neh_scale})
- "szint": "{szint}"
- "kontextus": string | null – ha a feladat egy közös bevezető szövegre, ábrára vagy
  táblázatra hivatkozik, ide másold be a teljes közös szöveget; egyébként null
- "abra_van": bool – true ha a feladat szövege ábrára, grafikonra vagy rajzra hivatkozik
- "feladat_oldal": int | null – a PDF [Oldal N] jelölő alapján az az oldalszám, ahol
  a feladat (vagy az ábra) megjelenik; ha nem azonosítható egytelműen, null

A szöveg magyar; hagyj minden szaktermint, nevet, számot magyarul.
Ne generálj feladatot, ha a szövegből nem olvasható ki egyértelműen a helyes válasz.
"""


def _make_openai_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    )


def extract_feladatok(
    fl_text: str,
    ut_text: str,
    targy: str,
    pdf_source: str,
    ut_source: str = "",
    *,
    model: str | None = None,
) -> list[Feladat]:
    """Call GPT with the feladatlap + útmutató texts.

    Returns a list of *validated* Feladat objects.  Items that fail validation
    are logged and skipped (never raise to the caller).
    """
    client = _make_openai_client()
    model = model or os.getenv("LLM_MODEL", "gpt-4o")

    meta = parse_filename_meta(pdf_source)
    id_prefix = _id_prefix_from_source(pdf_source, targy)

    szint = meta.get("szint") or "(ismeretlen szint)"
    prompt = _USER_TEMPLATE.format(
        targy=targy,
        pdf_source=pdf_source,
        ut_source=ut_source or "(ismeretlen)",
        ev=meta["ev"] or "(ismeretlen)",
        valtozat=meta["valtozat"] or "(ismeretlen)",
        fl_text=fl_text[:12_000],   # keep within token budget
        ut_text=ut_text[:6_000],
        id_prefix=id_prefix,
        neh_scale=_NEH_SCALE,
        szint=szint,
    )

    logger.info("Calling GPT for %s …", pdf_source)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = json.loads(response.choices[0].message.content)
    items: list[dict] = raw.get("feladatok", [])

    feladatok: list[Feladat] = []
    for item in items:
        try:
            item["targy"] = targy
            item.setdefault("ev", meta["ev"])
            item.setdefault("valtozat", meta["valtozat"])
            feladatok.append(_dict_to_feladat(item))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping invalid item %s: %s", item.get("id"), exc)

    logger.info("Extracted %d feladatok from %s", len(feladatok), pdf_source)
    return feladatok


def _id_prefix_from_source(pdf_source: str, targy: str) -> str:
    """'M8_2025_1_fl.pdf' → 'mat4_2025_1' / 'mat8_2025_1'."""
    meta = parse_filename_meta(pdf_source)
    year = str(meta["ev"]) if meta["ev"] else "xx"
    seq = str(meta["valtozat"]) if meta["valtozat"] else "1"
    szint = meta.get("szint") or ""
    gym_num = szint.split()[0] if szint else ""   # "4", "6", "8" or ""
    short = "mat" if targy == "matek" else "mag"
    return f"{short}{gym_num}_{year}_{seq}"


def parse_filename_meta(filename: str) -> dict:
    """Extract structured metadata from a felvételi PDF filename.

    'M8_2025_1_fl.pdf' → {'ev': 2025, 'valtozat': 1, 'kind': 'fl', 'targy': 'matek', 'szint': '8 osztályos'}
    'A4_2025_2_ut.pdf' → {'ev': 2025, 'valtozat': 2, 'kind': 'ut', 'targy': 'magyar', 'szint': '4 osztályos'}
    Returns None values for any field that cannot be parsed.
    """
    m = re.match(
        r"^([AM])(\d+)_(\d{4})_(\d+)_(fl|ut)\.pdf$",
        Path(filename).name,
        re.IGNORECASE,
    )
    if not m:
        return {"ev": None, "valtozat": None, "kind": None, "targy": None, "szint": None}
    prefix, gym_num, year, seq, kind = m.groups()
    return {
        "ev": int(year),
        "valtozat": int(seq),
        "kind": kind.lower(),
        "targy": _TARGY_MAP.get(prefix.upper()),
        "szint": _SZINT_MAP.get(int(gym_num)),
    }


def _dict_to_feladat(d: dict) -> Feladat:
    """Convert a raw GPT dict to a Feladat, raising on missing required fields."""
    required = {"id", "kerdes", "helyes_valasz", "hint", "magyarazat", "neh", "szint"}
    missing = required - d.keys()
    if missing:
        raise KeyError(f"Missing fields: {missing}")
    neh = int(d["neh"])
    if neh not in (1, 2, 3):
        raise ValueError(f"neh must be 1-3, got {neh!r}")
    ev_raw = d.get("ev")
    val_raw = d.get("valtozat")
    # Derive feladat_sorszam from the id if GPT didn't return it explicitly
    # id format: {prefix}_{year}_{variant}_{num}_{letter}  e.g. mat_2025_1_3_b → "3b"
    raw_sorszam = d.get("feladat_sorszam")
    if not raw_sorszam:
        id_parts = str(d["id"]).split("_")
        if len(id_parts) >= 5:
            raw_sorszam = "".join(id_parts[-2:])   # e.g. "3" + "b" → "3b"
        elif len(id_parts) == 4:
            raw_sorszam = id_parts[-1]              # just the number
    return Feladat(
        id=str(d["id"]),
        neh=neh,
        szint=str(d["szint"]),
        kerdes=str(d["kerdes"]),
        helyes_valasz=str(d["helyes_valasz"]),
        hint=str(d["hint"]),
        magyarazat=str(d["magyarazat"]),
        targy=str(d.get("targy", "")),
        ev=int(ev_raw) if ev_raw is not None else None,
        valtozat=int(val_raw) if val_raw is not None else None,
        feladat_sorszam=str(raw_sorszam) if raw_sorszam else None,
        kontextus=str(d["kontextus"]) if d.get("kontextus") else None,
        abra_van=bool(d.get("abra_van", False)),
        feladat_oldal=int(d["feladat_oldal"]) if d.get("feladat_oldal") else None,
    )


# ---------------------------------------------------------------------------
# Pair discovery
# ---------------------------------------------------------------------------


def find_exam_pairs(exams_dir: Path | None = None) -> Iterator[tuple[Path, Path, str]]:
    """Yield (fl_path, ut_path, targy) for every matched feladatlap+útmutató pair."""
    if exams_dir is None:
        exams_dir = get_exams_dir()
    pattern = re.compile(r"^([AM])(\d+)_\d{4}_\d+_fl\.pdf$", re.IGNORECASE)

    for fl_path in sorted(exams_dir.rglob("*_fl.pdf")):
        m = pattern.match(fl_path.name)
        if not m:
            continue
        prefix_letter = m.group(1).upper()
        gym_num = int(m.group(2))
        targy = _TARGY_MAP.get(prefix_letter)
        if targy is None:
            continue
        if gym_num not in _SZINT_MAP:
            logger.warning("Ismeretlen évfolyamszám (%s) – kihagyva: %s", gym_num, fl_path.name)
            continue

        ut_name = fl_path.name.replace("_fl.pdf", "_ut.pdf")
        ut_path = fl_path.with_name(ut_name)
        if not ut_path.exists():
            logger.warning("Útmutató not found for %s – skipping pair", fl_path.name)
            continue

        yield fl_path, ut_path, targy


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------


def parse_exam(
    fl_path: Path,
    ut_path: Path,
    targy: str,
    *,
    model: str | None = None,
) -> list[Feladat]:
    """Full pipeline for one exam pair: pdf→text→GPT→Feladat list (no review, no DB)."""
    fl_text = pdf_to_text(fl_path)
    ut_text = pdf_to_text(ut_path)

    # Persist extracted text for later inspection
    fl_rel = _save_text_cache(fl_text, fl_path.stem)
    ut_rel = _save_text_cache(ut_text, ut_path.stem)

    feladatok = extract_feladatok(
        fl_text, ut_text, targy,
        pdf_source=fl_path.name,
        ut_source=ut_path.name,
        model=model,
    )
    # Attach text-cache paths and PDF paths to every extracted feladat
    try:
        fl_pdf_rel = str(fl_path.relative_to(get_exams_dir()))
    except ValueError:
        fl_pdf_rel = None

    try:
        ut_pdf_rel = str(ut_path.relative_to(get_exams_dir()))
    except ValueError:
        ut_pdf_rel = None

    return [
        dataclasses.replace(
            f,
            fl_szoveg_path=fl_rel,
            ut_szoveg_path=ut_rel,
            fl_pdf_path=fl_pdf_rel,
            ut_pdf_path=ut_pdf_rel,
        )
        for f in feladatok
    ]


def _save_text_cache(text: str, pdf_stem: str) -> str:
    """Write extracted plain text to the assets text cache, return relative path."""
    path = text_cache_path(pdf_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return relative_text_path(pdf_stem)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(
    year: int | None = None,
    targy: str | None = None,
    szint: str | None = None,
    dry_run: bool = False,
    review: bool = False,
    model: str | None = None,
    exams_dir: Path | None = None,
    limit: int = 0,
) -> None:
    """Feldolgozza a PDF párokat és elmenti a feladatokat a DB-be."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    repo = FeladatRepository(db_path=get_db_path()) if not dry_run else None

    # Build set of already-processed pdf_sources to skip
    already_done: set[str] = set()
    if repo:
        for f in repo.all():
            if f.pdf_source:
                already_done.add(f.pdf_source)

    ed = exams_dir or get_exams_dir()
    pairs = list(find_exam_pairs(ed))

    # Apply filters
    if year:
        pairs = [(fl, ut, t) for fl, ut, t in pairs if str(year) in fl.name]
    if targy:
        pairs = [(fl, ut, t) for fl, ut, t in pairs if t == targy]
    if szint:
        szint_filter = _SZINT_MAP[int(szint)]
        pairs = [(fl, ut, t) for fl, ut, t in pairs
                 if parse_filename_meta(fl.name).get("szint") == szint_filter]

    # Skip already processed
    pairs = [(fl, ut, t) for fl, ut, t in pairs if fl.name not in already_done]

    if limit:
        pairs = pairs[:limit]

    if not pairs:
        print("Nincs feldolgozandó PDF pár.")
        return

    print(f"Feldolgozandó PDF párok: {len(pairs)}")
    total_saved = 0

    for fl_path, ut_path, targy_val in pairs:
        print(f"\n{'─'*60}")
        print(f"  Feladatlap : {fl_path}")
        print(f"  Útmutató   : {ut_path}")
        print(f"  Tantárgy   : {targy_val}")
        print(f"{'─'*60}")

        try:
            feladatok = parse_exam(fl_path, ut_path, targy_val, model=model)
        except Exception as exc:
            logger.error("Extraction failed for %s: %s", fl_path.name, exc)
            continue

        if not feladatok:
            print("  Nem sikerült feladatot kinyerni.")
            continue

        print(f"  Extrahált feladatok: {len(feladatok)}")

        if review:
            feladatok = review_feladatok(feladatok)

        if not feladatok:
            continue

        if repo:
            repo.upsert_many(feladatok)
            print(f"  Mentve: {len(feladatok)} feladat → DB")
        else:
            print(f"  [dry-run] Mentett volna: {len(feladatok)} feladat")
            for f in feladatok:
                print_feladat(f)

        total_saved += len(feladatok)

    print(f"\nKész. Összesen mentett feladatok: {total_saved}")


if __name__ == "__main__":
    from felvi_games.cli import app
    app(["parse"], standalone_mode=True)
