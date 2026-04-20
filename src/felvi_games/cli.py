"""
cli.py
------
Parancssori felületek a felvi_games eszközökhöz (typer).

Belépési pont:
  felvi          →  app()
    felvi scrape   – PDF-ek letöltése
    felvi parse    – PDF-ek feldolgozása DB-be
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="felvi",
    help="Felvételi feladatsor eszközök",
    add_completion=False,
)


class EvfolyamKulcs(str, Enum):
    negy = "4"
    hat = "6"
    nyolc = "8"


class Targy(str, Enum):
    matek = "matek"
    magyar = "magyar"


# ---------------------------------------------------------------------------
# felvi scrape
# ---------------------------------------------------------------------------

@app.command()
def scrape(
    zip_mode: Annotated[
        bool, typer.Option("--zip", help="Bulk ZIP letöltés (gyors, minden évet egyszerre)")
    ] = False,
    years: Annotated[
        int, typer.Option("--years", help="Csak az utolsó N év (0 = mind)")
    ] = 0,
    only: Annotated[
        Optional[EvfolyamKulcs], typer.Option("--only", help="Csak egy évfolyam: 4, 6 vagy 8")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Csak listáz, nem tölt le semmit")
    ] = False,
    output: Annotated[
        Optional[Path], typer.Option("--output", help="Kimeneti mappa (alap: FELVI_EXAMS env)")
    ] = None,
) -> None:
    """Letölti a feladatsorokat az oktatas.hu-ról."""
    from felvi_games.scraper import run as _run

    _run(
        zip_mode=zip_mode,
        years=years,
        only=only.value if only else None,
        dry_run=dry_run,
        output=output,
    )


# ---------------------------------------------------------------------------
# felvi parse
# ---------------------------------------------------------------------------

@app.command()
def parse(
    year: Annotated[
        Optional[int], typer.Option("--year", help="Csak ebből az évből")
    ] = None,
    targy: Annotated[
        Optional[Targy], typer.Option("--targy", help="Tantárgy szűrő")
    ] = None,
    szint: Annotated[
        Optional[EvfolyamKulcs], typer.Option("--szint", help="Évfolyam szűrő (4/6/8)")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Ne mentse DB-be")
    ] = False,
    review: Annotated[
        bool, typer.Option("--review", help="CLI review futtatása kinyerés után")
    ] = False,
    model: Annotated[
        Optional[str], typer.Option("--model", help="LLM modell neve")
    ] = None,
    exams_dir: Annotated[
        Optional[Path], typer.Option("--exams-dir", help="PDF mappa (alap: FELVI_EXAMS env)")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="Max feldolgozandó pár (0 = mind)")
    ] = 0,
) -> None:
    """PDF párokat dolgoz fel és menti a feladatokat DB-be."""
    from felvi_games.pdf_parser import run as _run

    _run(
        year=year,
        targy=targy.value if targy else None,
        szint=szint.value if szint else None,
        dry_run=dry_run,
        review=review,
        model=model,
        exams_dir=exams_dir,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Entry point (pyproject.toml → project.scripts)
# ---------------------------------------------------------------------------

def run() -> None:
    app()
