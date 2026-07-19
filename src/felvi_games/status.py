"""
status.py
---------
Rendszerállapot összefoglalója: konfiguráció, letöltött PDF-ek, DB statisztika.

Belépési pont:
  run()  – teljes összefoglaló kiírása stdout-ra
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


def _pdf_summary(exams_dir: Path, szint_filter: str | None) -> None:
    """Kiírja a letöltött PDF-eket szint/év/változat bontásban."""
    _PDF_RE = re.compile(r"^([AM])(\d+)_(\d{4})_(\d+)_(fl|ut)\.pdf$", re.IGNORECASE)
    # fájlnév gym-szám → CLI szint kulcs (EvfolyamKulcs.value)
    _GYM_TO_CLI = {"8": "4", "6": "6", "4": "8"}
    _SZINT_LABEL = {"4": "4 osztályos", "6": "6 osztályos", "8": "8 osztályos"}
    _TARGY_LABEL = {"A": "magyar", "M": "matek"}

    groups: dict[tuple[str, int], dict[str, dict[int, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    unrecognized: list[str] = []
    for pdf in sorted(exams_dir.rglob("*.pdf")):
        m = _PDF_RE.match(pdf.name)
        if not m:
            unrecognized.append(pdf.name)
            continue
        targy_k, gym_num, ev, valtozat, tipus = m.groups()
        cli_szint = _GYM_TO_CLI.get(gym_num, gym_num)
        if szint_filter and szint_filter != cli_szint:
            continue
        szint_label = _SZINT_LABEL.get(cli_szint, cli_szint)
        groups[(szint_label, int(ev))][_TARGY_LABEL.get(targy_k.upper(), targy_k)][int(valtozat)].add(
            tipus.lower()
        )

    if not groups and not unrecognized:
        print("  (nincs PDF, futtasd: felvi scrape)")
        return

    if not groups:
        print("  (nincs ismert névkonvenciójú PDF)")
    else:
        for (szint_label, ev), targyek in sorted(groups.items()):
            print(f"\n  {szint_label} — {ev}:")
            for targy_nev, valtozatok in sorted(targyek.items()):
                for val, tipusok in sorted(valtozatok.items()):
                    fl = "fl✓" if "fl" in tipusok else "fl✗"
                    ut = "ut✓" if "ut" in tipusok else "ut✗"
                    print(f"    {targy_nev:8s}  {val}. változat  {fl}  {ut}")

    if unrecognized and not szint_filter:
        print(f"\n  [!] {len(unrecognized)} ismeretlen nevű PDF (nem illeszkedik a konvencióra)")


def _db_summary(db_path: Path, szint_filter: str | None) -> None:
    """Kiírja a DB feladat- és vizsgastatisztikákat."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from felvi_games.db import FeladatCsoportRecord, FeladatRecord, get_engine

    engine = get_engine(db_path)
    with Session(engine) as sess:
        total = sess.scalar(select(func.count()).select_from(FeladatRecord)) or 0
        total_groups = sess.scalar(select(func.count()).select_from(FeladatCsoportRecord)) or 0
        print(f"  Összes részfeladat: {total}")
        print(f"  Összes feladatcsoport: {total_groups}")

        rows = sess.execute(
            select(FeladatRecord.szint, FeladatRecord.targy, func.count())
            .group_by(FeladatRecord.szint, FeladatRecord.targy)
            .order_by(FeladatRecord.szint, FeladatRecord.targy)
        ).all()

        exam_rows = sess.execute(
            select(
                FeladatCsoportRecord.ev,
                FeladatCsoportRecord.fl_pdf_path,
                FeladatCsoportRecord.targy,
                FeladatCsoportRecord.szint,
                FeladatCsoportRecord.valtozat,
                func.count(FeladatCsoportRecord.id),
                func.coalesce(func.sum(FeladatCsoportRecord.max_pont_ossz), 0),
            )
            .group_by(
                FeladatCsoportRecord.ev,
                FeladatCsoportRecord.fl_pdf_path,
                FeladatCsoportRecord.targy,
                FeladatCsoportRecord.szint,
                FeladatCsoportRecord.valtozat,
            )
            .order_by(
                FeladatCsoportRecord.ev.desc(),
                FeladatCsoportRecord.fl_pdf_path,
            )
        ).all()

    if not rows:
        return

    print()
    print(f"  {'Szint':<18} {'Tárgy':<10} {'Feladat':>8}")
    print("  " + "-" * 38)
    for row_szint, row_targy, cnt in rows:
        if szint_filter and szint_filter not in (row_szint or ""):
            continue
        print(f"  {row_szint or '?':<18} {row_targy or '?':<10} {cnt:>8}")

    filtered_exam_rows = [
        row for row in exam_rows
        if not szint_filter or szint_filter in (row.szint or "")
    ]
    if not filtered_exam_rows:
        return

    print("\n=== Feldolgozott vizsgák (feladatcsoportok) ===")
    current_year: int | None | object = object()
    for row in filtered_exam_rows:
        if row.ev != current_year:
            current_year = row.ev
            print(f"\n  {row.ev if row.ev is not None else '?'}:")
        variant = f"{row.valtozat}. változat" if row.valtozat is not None else "? változat"
        print(
            f"    {row.targy or '?':<8} {row.szint or '?':<18} {variant:<12} "
            f"{row.count:>3} csoport  {row.coalesce:>3} max. pont"
        )
        print(f"      {row.fl_pdf_path or '(ismeretlen forrás PDF)'}")


def run(szint: str | None = None) -> None:
    """Konfiguráció, letöltött PDF-ek és DB állapot összefoglalója."""
    from felvi_games.config import get_assets_dir, get_db_path, get_exams_dir

    db_path = get_db_path()
    exams_dir = get_exams_dir()
    assets_dir = get_assets_dir()

    print("\n=== Konfiguráció ===")
    print(f"  DB:      {db_path}  {'[OK]' if db_path.exists() else '[NINCS]'}")
    print(f"  Exams:   {exams_dir}  {'[OK]' if exams_dir.exists() else '[NINCS]'}")
    print(f"  Assets:  {assets_dir}  {'[OK]' if assets_dir.exists() else '[NINCS]'}")

    print("\n=== Letöltött PDF-ek ===")
    if not exams_dir.exists():
        print("  [!] Exams mappa nem létezik — futtasd: felvi scrape")
    else:
        _pdf_summary(exams_dir, szint)

    print("\n=== DB statisztika ===")
    if not db_path.exists():
        print("  [!] DB nem létezik — futtasd: felvi parse")
    else:
        _db_summary(db_path, szint)

    print()
