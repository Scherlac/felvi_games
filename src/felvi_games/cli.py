"""
cli.py
------
Parancssori felületek a felvi_games eszközökhöz (typer).

Belépési pont:
  felvi          →  app()
    felvi info     – Konfiguráció, PDF-ek és DB állapot kiírása
    felvi scrape   – PDF-ek letöltése
    felvi parse    – PDF-ek feldolgozása DB-be
    felvi review   – AI review futtatása egy vagy több feladaton
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from felvi_games.config import setup_logging

if TYPE_CHECKING:
    from felvi_games.db import FeladatRepository

# Ensure stdout/stderr can handle all Unicode characters when redirected on Windows.
# Set the console output code page to UTF-8 first so PowerShell interprets the pipe correctly.
# if sys.platform == "win32":
#     try:
#         import ctypes
#         # isolation level 1
#         ctypes.windll.kernel32.SetConsoleOutputCP()
#     except Exception:
#         pass

# for _stream in (sys.stdout, sys.stderr):
#     if hasattr(_stream, "reconfigure"):
#         try:
#             _stream.reconfigure(encoding="utf-8", errors="replace")
#         except Exception:
#             pass

setup_logging()

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
# felvi info
# ---------------------------------------------------------------------------

@app.command()
def info(
    szint: Annotated[
        EvfolyamKulcs | None, typer.Option("--szint", help="Csak egy évfolyam: 4, 6 vagy 8")
    ] = None,
) -> None:
    """Konfiguráció, letöltött PDF-ek és DB állapot áttekintése."""
    from felvi_games.status import run as _run

    _run(szint=szint.value if szint else None)


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
        EvfolyamKulcs | None, typer.Option("--only", help="Csak egy évfolyam: 4, 6 vagy 8")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Csak listáz, nem tölt le semmit")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", help="Kimeneti mappa (alap: FELVI_EXAMS env)")
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
        int | None, typer.Option("--year", help="Csak ebből az évből")
    ] = None,
    targy: Annotated[
        Targy | None, typer.Option("--targy", help="Tantárgy szűrő")
    ] = None,
    szint: Annotated[
        EvfolyamKulcs | None, typer.Option("--szint", help="Évfolyam szűrő (4/6/8)")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Ne mentse DB-be")
    ] = False,
    review: Annotated[
        bool, typer.Option("--review", help="CLI review futtatása kinyerés után")
    ] = False,
    model: Annotated[
        str | None, typer.Option("--model", help="LLM modell neve")
    ] = None,
    exams_dir: Annotated[
        Path | None, typer.Option("--exams-dir", help="PDF mappa (alap: FELVI_EXAMS env)")
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
# felvi usage
# ---------------------------------------------------------------------------

@app.command("usage")
def usage(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Csak egy felhasználó adatai")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="Max. kilistázott menetszám felhasználónként")
    ] = 5,
) -> None:
    """Felhasználói aktivitás és haladás riport a játék DB-ből."""
    from sqlalchemy import case, func, select
    from sqlalchemy.orm import Session

    from felvi_games.config import get_db_path
    from felvi_games.db import (
        FelhasznaloRecord,
        MegoldasRecord,
        MenetRecord,
        get_engine,
    )

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)
    if limit < 1:
        typer.echo("[!] A --limit értéke legalább 1 legyen.")
        raise typer.Exit(code=2)

    engine = get_engine(db_path)
    with Session(engine) as sess:
        total_users = sess.scalar(select(func.count()).select_from(FelhasznaloRecord)) or 0
        total_sessions = sess.scalar(select(func.count()).select_from(MenetRecord)) or 0
        total_attempts = sess.scalar(select(func.count()).select_from(MegoldasRecord)) or 0

        attempt_rows = sess.execute(
            select(
                MegoldasRecord.felhasznalo_nev,
                func.count().label("attempts"),
                func.sum(case((MegoldasRecord.helyes.is_(True), 1), else_=0)).label("correct"),
                func.avg(MegoldasRecord.elapsed_sec).label("avg_sec"),
            )
            .where(MegoldasRecord.felhasznalo_nev != "")
            .group_by(MegoldasRecord.felhasznalo_nev)
        ).all()
        attempt_map = {
            r.felhasznalo_nev: {
                "attempts": int(r.attempts or 0),
                "correct": int(r.correct or 0),
                "avg_sec": float(r.avg_sec) if r.avg_sec is not None else None,
            }
            for r in attempt_rows
        }

        session_stmt = (
            select(
                MenetRecord.felhasznalo_nev,
                func.count(MenetRecord.id).label("sessions"),
                func.sum(MenetRecord.megoldott).label("solved"),
                func.sum(MenetRecord.feladat_limit).label("planned"),
                func.sum(MenetRecord.pont).label("points"),
                func.sum(case((MenetRecord.ended_at.is_not(None), 1), else_=0)).label("closed"),
                func.max(MenetRecord.started_at).label("last_started"),
            )
            .group_by(MenetRecord.felhasznalo_nev)
            .order_by(MenetRecord.felhasznalo_nev)
        )
        if user:
            session_stmt = session_stmt.where(MenetRecord.felhasznalo_nev == user)
        session_rows = sess.execute(session_stmt).all()

        typer.echo("\n=== Usage Report ===")
        typer.echo(f"DB: {db_path}")
        typer.echo(
            f"Users: {total_users} | Sessions: {total_sessions} | Attempts: {total_attempts}"
        )

        if not session_rows:
            if user:
                typer.echo(f"\nNincs session adat ehhez a felhasználóhoz: {user}")
            else:
                typer.echo("\nNincs session adat a DB-ben.")
            return

        typer.echo("\nPer-user summary:")
        typer.echo("  Megjegyzés: a MenetRecord.feladat_limit mező jelenleg pont-célként működik (legacy mezőnév).")
        for row in session_rows:
            solved = int(row.solved or 0)
            point_target = int(row.planned or 0)
            points = int(row.points or 0)
            sessions = int(row.sessions or 0)
            closed = int(row.closed or 0)
            point_progress_pct = (100.0 * points / point_target) if point_target else 0.0

            a = attempt_map.get(row.felhasznalo_nev, {"attempts": 0, "correct": 0, "avg_sec": None})
            attempts = a["attempts"]
            correct = a["correct"]
            accuracy = (100.0 * correct / attempts) if attempts else 0.0
            avg_sec = a["avg_sec"]
            avg_sec_text = f"{avg_sec:.1f}s" if avg_sec is not None else "-"

            typer.echo(
                "- "
                f"{row.felhasznalo_nev}: "
                f"sessions={sessions}, closed={closed}, "
                f"tasks_solved={solved}, "
                f"points={points}/{point_target} ({point_progress_pct:.1f}%), "
                f"attempts={attempts}, accuracy={accuracy:.1f}%, avg_time={avg_sec_text}, "
                f"last_started={row.last_started}"
            )

            details = sess.execute(
                select(
                    MenetRecord.id,
                    MenetRecord.targy,
                    MenetRecord.szint,
                    MenetRecord.megoldott,
                    MenetRecord.feladat_limit,
                    MenetRecord.pont,
                    MenetRecord.started_at,
                    MenetRecord.ended_at,
                )
                .where(MenetRecord.felhasznalo_nev == row.felhasznalo_nev)
                .order_by(MenetRecord.started_at.desc())
                .limit(limit)
            ).all()

            for d in details:
                done_flag = "done" if d.ended_at else "open"
                typer.echo(
                    "    "
                    f"#{d.id} [{done_flag}] {d.targy}/{d.szint} "
                    f"tasks={d.megoldott} point_target={d.feladat_limit} points={d.pont} "
                    f"start={d.started_at}"
                )

        typer.echo()


# ---------------------------------------------------------------------------
# felvi medals
# ---------------------------------------------------------------------------

@app.command("medals")
def medals(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Szűrés egy felhasználóra")
    ] = None,
    list_all: Annotated[
        bool, typer.Option("--list", help="Az összes lehetséges érem katalógusának kiírása")
    ] = False,
    include_expired: Annotated[
        bool, typer.Option("--expired", help="Lejárt ideiglenes érmek megjelenítése is")
    ] = False,
    dynamic: Annotated[
        bool, typer.Option("--dynamic", help="Csak a dinamikus (LLM-generált) éremszabályok listázása, időrend szerint")
    ] = False,
    conditions: Annotated[
        bool, typer.Option("--conditions", help="Dinamikus feltételek listázása (felhasználóra szűrhető)")
    ] = False,
    today: Annotated[
        bool, typer.Option("--today", help="--conditions esetén csak a ma létrehozott dinamikus érmek")
    ] = False,
    generate_dry_run: Annotated[
        bool, typer.Option("--generate-dry-run", help="Új dinamikus éremjavaslat generálása mentés nélkül")
    ] = False,
    generate: Annotated[
        bool, typer.Option("--generate", help="Új dinamikus érem generálása és mentése a katalógusba")
    ] = False,
    generator_inputs: Annotated[
        bool, typer.Option("--generator-inputs", help="A dinamikus éremgenerátornak átadott bemeneti adatok kiírása")
    ] = False,
    review_time_gating: Annotated[
        bool,
        typer.Option(
            "--review-time-gating",
            help="Időszakot sugalló éremnevek és feltételek összhangjának ellenőrzése",
        ),
    ] = False,
    review_time_gating_llm: Annotated[
        bool, typer.Option("--review-time-gating-llm", help="--review-time-gating eredmény rövid LLM-összegzése")
    ] = False,
    review_time_gating_fix: Annotated[
        bool,
        typer.Option(
            "--review-time-gating-fix",
            help="--review-time-gating során automatikusan javítja a hiányzó/ellentmondó before/after feltételeket",
        ),
    ] = False,
    review_time_gating_interactive: Annotated[
        bool,
        typer.Option(
            "--review-time-gating-interactive",
            help="Interaktív javítás: eltérésenként rákérdez a before/after feltétel javítására",
        ),
    ] = False,
    window_hours: Annotated[
        int, typer.Option("--window-hours", help="Dry-run javaslat időablaka órában (1-18)")
    ] = 18,
    delete_id: Annotated[
        str | None, typer.Option("--delete-id", help="Érem törlése az id alapján (csak dinamikus/privát érmekre)")
    ] = None,
) -> None:
    """Érmek / achievements: katalógus és felhasználói haladás."""
    import json as _json
    import math
    import re
    from datetime import datetime, timezone

    from sqlalchemy import select, text
    from sqlalchemy.orm import Session

    from felvi_games.achievements import (
        EREM_KATALOGUS,
        _eval_dynamic_condition,
        evaluate_dynamic_condition_progress,
        get_all_medals_for_user,
        get_awardability_now,
        get_next_award_basis,
    )
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository, FelhasznaloRecord, get_engine
    from felvi_games.models import Erem
    from felvi_games.progress_check import normalize_medal_candidate_time_gate, review_time_gate_alignment

    def _collect_generator_inputs(
        repo: FeladatRepository,
        player: str,
        hours: int,
        basis=None,
    ) -> dict[str, object]:
        basis = basis or get_next_award_basis(player, repo)
        awardability = get_awardability_now(player, repo)
        awardability_payload = awardability.payload()
        return {
            "user": player,
            "window_hours": hours,
            "earned_count": basis.earned_count,
            "stats": basis.stats,
            "close_medals": basis.close_medals_payload(),
            "awardable_now": awardability_payload["awardable_now"],
            "would_repeat_now": awardability_payload["would_repeat_now"],
        }

    def _resolve_db_path() -> Path:
        return db or get_db_path()

    def _ensure_db_exists(db_path: Path) -> None:
        if not db_path.exists():
            typer.echo(f"[!] DB nem található: {db_path}")
            raise typer.Exit(code=1)

    def _handle_delete(db_path: Path) -> None:
        engine = get_engine(db_path)
        with Session(engine) as s:
            row = s.execute(
                text("SELECT id, nev, ikon, condition_json FROM eremek WHERE id = :eid"),
                {"eid": delete_id},
            ).first()
            if not row:
                typer.echo(f"[!] Nem található érem ezzel az id-vel: {delete_id}")
                raise typer.Exit(code=1)
            if not row.condition_json:
                typer.echo(f"[!] Ez nem dinamikus érem (nincs condition_json), törlés megtagadva: {delete_id}")
                raise typer.Exit(code=1)
            s.execute(text("DELETE FROM eremek WHERE id = :eid"), {"eid": delete_id})
            s.commit()
        typer.echo(f"✅ Törölve: {row.ikon}  {row.nev}  (id={delete_id})")

    def _handle_generator_inputs(db_path: Path) -> None:
        if not user:
            typer.echo("[!] A --generator-inputs használatához add meg a --user opciót.")
            raise typer.Exit(code=2)
        if window_hours < 1 or window_hours > 18:
            typer.echo("[!] A --window-hours értéke 1 és 18 közé essen.")
            raise typer.Exit(code=2)

        repo = FeladatRepository(db_path)
        payload = _collect_generator_inputs(repo, user, window_hours)

        typer.echo(f"\n=== Dinamikus generátor bemenet  (DB: {db_path}) ===\n")
        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
        typer.echo("\nMegjegyzés: ez a strukturált payload megy a dinamikus éremgenerátorhoz a prompt részeként.\n")

    def _handle_generate(db_path: Path) -> None:
        from felvi_games.ai import generate_daily_insight

        if not user:
            typer.echo("[!] A --generate/--generate-dry-run használatához add meg a --user opciót.")
            raise typer.Exit(code=2)
        if window_hours < 1 or window_hours > 18:
            typer.echo("[!] A --window-hours értéke 1 és 18 közé essen.")
            raise typer.Exit(code=2)

        repo = FeladatRepository(db_path)
        basis = get_next_award_basis(user, repo)
        _collect_generator_inputs(repo, user, window_hours, basis=basis)
        stats = basis.stats
        close = basis.close_medals
        earned_count = basis.earned_count

        insight = generate_daily_insight(
            user,
            stats,
            close,
            earned_count,
            window_hours=window_hours,
        )

        title = "Dinamikus érem generálás" if generate else "Dinamikus érem dry-run"
        typer.echo(f"\n=== {title}  (DB: {db_path}) ===\n")
        typer.echo(f"👤 Felhasználó: {user}")
        typer.echo(f"🕒 Időablak:    {window_hours} óra")
        typer.echo(f"\nÜzenet:\n  {insight.get('greeting', '-')}")

        nm = insight.get("new_medal")
        if not nm:
            typer.echo("\nJavasolt új érem: nincs (new_medal = null)\n")
            return

        normalized_nm, note = normalize_medal_candidate_time_gate(nm if isinstance(nm, dict) else None)
        if isinstance(normalized_nm, dict):
            nm = normalized_nm

        cond = nm.get("condition") if isinstance(nm, dict) else None
        typer.echo("\nJavasolt új érem:")
        typer.echo(f"  Név:       {nm.get('nev', '-')}")
        typer.echo(f"  Ikon:      {nm.get('ikon', '🏅')}")
        typer.echo(f"  Kategória: {nm.get('kategoria', '-')}")
        typer.echo(f"  Leírás:    {nm.get('leiras', '-')}")
        typer.echo(f"  Feltétel:  {_json.dumps(cond, ensure_ascii=False)}")
        if isinstance(note, dict) and note.get("time_gate_status") == "normalized":
            typer.echo(
                "  🔧 Time-gate normalizálás: "
                f"hozzáadva {note.get('expected_type')} (hour={note.get('expected_hour')})"
            )
        # Check if the condition is ALREADY satisfied at creation time (bad – n should require future effort)
        try:
            already_done = _eval_dynamic_condition(
                user,
                cond or {},
                repo._engine,
                valid_from=datetime.now(timezone.utc),
            )
            if already_done:
                typer.echo("  ⚠️  Figyelem: a feltétel már most teljesül – nem jó kihívás!")
                if generate:
                    typer.echo("  ❌ Mentés megtagadva: a kihívás már teljesítve.")
                    typer.echo("     Próbáld újra: felvi medals --generate --user ...\n")
                    return
            else:
                typer.echo("  ✅ A feltétel még nem teljesül – jó jövőbeli kihívás.")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"  Ellenőrzés: hiba ({exc})")

        if generate:
            safe_user = re.sub(r"[^a-z0-9]+", "_", user.lower()).strip("_") or "user"
            erem_id = f"dyn_{safe_user}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            erem = Erem(
                id=erem_id,
                nev=str(nm.get("nev", "Napi kihívás")),
                leiras=str(nm.get("leiras", "Időkorlátos napi kihívás")),
                ikon=str(nm.get("ikon", "🏅")),
                kategoria=str(nm.get("kategoria", "teljesitmeny")),
                ideiglenes=True,
                ervenyes_napig=int(nm.get("ervenyes_napig", 1) or 1),
                ismetelheto=True,
                privat=True,
                cel_felhasznalo=user,
                condition=cond if isinstance(cond, (dict, list)) else None,
            )
            repo.upsert_erem(erem)
            typer.echo(f"\n✅ Mentve: id={erem.id}")
            typer.echo("   A feltétel mostantól látható a --conditions listában.")
            typer.echo()
        else:
            typer.echo("\n(Mentés nem történt, ez csak dry-run.)\n")

    def _handle_review_time_gating(db_path: Path) -> None:
        if not user:
            typer.echo("[!] A --review-time-gating használatához add meg a --user opciót.")
            raise typer.Exit(code=2)

        repo = FeladatRepository(db_path)
        findings = review_time_gate_alignment(user, repo)
        findings = [f for f in findings if f.get("status") != "ok"]

        typer.echo(f"\n=== Time-gate review  (DB: {db_path})  user={user}  eltérés: {len(findings)} ===\n")
        if not findings:
            typer.echo("  ✅ Nincs eltérés a név/leírás és az időkapu-feltétel között.\n")
            return

        for f in findings:
            typer.echo(f"  {f.get('id')}  |  {f.get('nev')}")
            typer.echo(
                "    "
                f"status={f.get('status')}  expected={f.get('expected_type')}(hour={f.get('expected_hour')})"
            )
            typer.echo(f"    javaslat: {f.get('recommendation')}")
            typer.echo(f"    condition: {_json.dumps(f.get('condition'), ensure_ascii=False)}")

        if review_time_gating_fix and review_time_gating_interactive:
            typer.echo("[i] A --review-time-gating-interactive elsőbbséget élvez a --review-time-gating-fix mellett.")

        if review_time_gating_fix or review_time_gating_interactive:
            fixes = 0
            with Session(get_engine(db_path)) as s:
                for f in findings:
                    candidate = {
                        "nev": f.get("nev"),
                        "leiras": "",
                        "condition": f.get("condition"),
                    }
                    normalized, note = normalize_medal_candidate_time_gate(candidate)
                    if not isinstance(normalized, dict):
                        continue
                    if not isinstance(note, dict) or note.get("time_gate_status") != "normalized":
                        continue
                    condition = normalized.get("condition")

                    if review_time_gating_interactive:
                        typer.echo(f"\n  ? Javítsam ezt: {f.get('id')} | {f.get('nev')}")
                        typer.echo(f"    régi: {_json.dumps(f.get('condition'), ensure_ascii=False)}")
                        typer.echo(f"    új:   {_json.dumps(condition, ensure_ascii=False)}")
                        if not typer.confirm("    Alkalmazzam a javítást?", default=True):
                            continue

                    s.execute(
                        text("UPDATE eremek SET condition_json = :cj WHERE id = :eid"),
                        {
                            "eid": f.get("id"),
                            "cj": _json.dumps(condition, ensure_ascii=False),
                        },
                    )
                    fixes += 1
                s.commit()
            typer.echo(f"\n🔧 Javítások alkalmazva: {fixes} db")

        if review_time_gating_llm:
            try:
                from felvi_games.ai import review_time_gate_findings

                llm = review_time_gate_findings(findings)
                typer.echo("\nLLM review összegzés:")
                typer.echo(f"  {llm.get('summary', '')}")
                actions = llm.get("actions", [])
                if isinstance(actions, list) and actions:
                    typer.echo("  Javasolt lépések:")
                    for a in actions:
                        typer.echo(f"    - {a}")
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"\nLLM review hiba: {exc}")

        typer.echo()

    def _handle_conditions(db_path: Path) -> None:
        engine = get_engine(db_path)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        where_parts = ["condition_json IS NOT NULL", "condition_json != ''"]
        params: dict[str, object] = {}
        if user:
            where_parts.append("(cel_felhasznalo IS NULL OR cel_felhasznalo = :u)")
            params["u"] = user
        if today:
            where_parts.append("created_at >= :today_start")
            params["today_start"] = today_start

        where_sql = " AND ".join(where_parts)
        with Session(engine) as s:
            rows = s.execute(
                text(
                    "SELECT id, nev, ikon, kategoria, condition_json, created_at, cel_felhasznalo "
                    f"FROM eremek WHERE {where_sql} ORDER BY created_at DESC"
                ),
                params,
            ).all()

        who = f"  user={user}" if user else ""
        only_today = "  today_only" if today else ""
        typer.echo(f"\n=== Dinamikus feltételek  (DB: {db_path}){who}{only_today}  összesen: {len(rows)} ===\n")
        if not rows:
            typer.echo("  (Nincs találat.)")
            if user:
                typer.echo("  Tipp: próbáld: felvi medals --generate-dry-run --user \"NÉV\"")
                typer.echo("        vagy mentéshez: felvi medals --generate --user \"NÉV\"")
            typer.echo()
            return

        repo = FeladatRepository(db_path)
        for r in rows:
            cel = f" → {r.cel_felhasznalo}" if r.cel_felhasznalo else ""
            typer.echo(f"  {r.created_at}  {r.ikon}  {r.nev}  [{r.kategoria}]{cel}")
            typer.echo(f"    id: {r.id}")
            try:
                cond = _json.loads(r.condition_json)
                typer.echo(f"    condition: {_json.dumps(cond, ensure_ascii=False)}")
                if user:
                    try:
                        ok, cur, target, vf = evaluate_dynamic_condition_progress(
                            user,
                            cond,
                            repo._engine,
                            valid_from=r.created_at,
                        )
                        progress_str = ""
                        if cur is not None and target is not None:
                            max_progress = max(int(cur), int(target), 1)
                            bar_len = max(1, int(round(10 * math.log10(max_progress))))
                            ratio = 0.0 if int(target) <= 0 else min(float(cur) / float(target), 1.0)
                            bar_filled = int(round(bar_len * ratio))
                            bar = "█" * bar_filled + "░" * max(0, bar_len - bar_filled)
                            progress_str = f"  [{bar}]  {cur}/{target}"
                        status = "✅ teljesítve" if ok else "⏳ folyamatban"
                        typer.echo(f"    haladás({user}): {status}{progress_str}")
                        typer.echo(f"    (számít: {vf} óta)")
                    except Exception as exc:  # noqa: BLE001
                        typer.echo(f"    teljesül({user}): hiba ({exc})")
            except Exception:
                typer.echo(f"    condition_json: {r.condition_json}")
        typer.echo()

    def _handle_dynamic(db_path: Path) -> None:
        engine = get_engine(db_path)
        with Session(engine) as s:
            rows = s.execute(
                text(
                    "SELECT id, nev, ikon, kategoria, condition_json, created_at, cel_felhasznalo "
                    "FROM eremek WHERE condition_json IS NOT NULL AND condition_json != '' "
                    "ORDER BY created_at DESC"
                )
            ).all()
        typer.echo(f"\n=== Dinamikus éremszabályok  (DB: {db_path})  összesen: {len(rows)} ===\n")
        if not rows:
            typer.echo("  (Még nem jött létre dinamikus érem.)\n")
            return
        for r in rows:
            cel = f"  → {r.cel_felhasznalo}" if r.cel_felhasznalo else ""
            typer.echo(f"  {r.created_at}  {r.ikon}  {r.nev}  [{r.kategoria}]{cel}")
            typer.echo(f"    id: {r.id}")
            try:
                cond = _json.loads(r.condition_json)
                typer.echo(f"    condition: {_json.dumps(cond, ensure_ascii=False)}")
            except Exception:
                typer.echo(f"    condition_json: {r.condition_json}")
        typer.echo()

    def _handle_list_all() -> None:
        typer.echo("\n=== Érem katalógus ===")
        by_cat: dict[str, list] = {}
        for e in EREM_KATALOGUS.values():
            by_cat.setdefault(e.kategoria, []).append(e)
        for cat in sorted(by_cat):
            typer.echo(f"\n{cat.upper()}")
            for e in by_cat[cat]:
                flags = []
                if e.ismetelheto:
                    flags.append("ismételhető")
                if e.ideiglenes:
                    flags.append(f"ideiglenes ({e.ervenyes_napig}n)")
                flag_str = f"  [{', '.join(flags)}]" if flags else ""
                typer.echo(f"  {e.ikon}  {e.nev}{flag_str}")
                typer.echo(f"     {e.leiras}")
        typer.echo()

    def _handle_default_listing(db_path: Path) -> None:
        from collections import defaultdict

        repo = FeladatRepository(db_path)
        engine = get_engine(db_path)

        with Session(engine) as sess:
            if user:
                users = [user]
            else:
                users = list(sess.scalars(select(FelhasznaloRecord.nev).order_by(FelhasznaloRecord.nev)))

        typer.echo(f"\n=== Earned Medals  (DB: {db_path}) ===\n")
        typer.echo(
            "Megjegyzés: a 'Szerezve' időpont a kiosztás/rögzítés ideje UTC-ben. "
            "Ez nem mindig egyezik meg a feltételt kiváltó tanulási esemény pontos idejével, "
            "mert több érem egy menet végén vagy egy későbbi ellenőrzés során együtt kerülhet kiosztásra.\n"
        )
        for nev in users:
            pairs = get_all_medals_for_user(nev, repo, include_expired=include_expired)
            szerzes_map = repo.get_erem_szerzesek_map(nev)
            typer.echo(f"👤 {nev}  ({len(pairs)} érem)")
            if not pairs:
                typer.echo("   (még nincs érem)")
            else:
                id_to_label: dict[str, str] = {}
                for erem, fe in sorted(pairs, key=lambda p: p[0].kategoria):
                    id_to_label[erem.id] = f"{erem.ikon} {erem.nev}"
                    szamlalo = f" ×{fe.szamlalo}" if fe.szamlalo > 1 else ""
                    lejarat = ""
                    if fe.lejarat:
                        lejarat = f"  [lejár: {fe.lejarat.strftime('%Y-%m-%d')}]"
                    typer.echo(
                        f"  {erem.ikon}  {erem.nev}{szamlalo}"
                        f"  [{erem.kategoria}]{lejarat}"
                    )
                    szerzesek = szerzes_map.get(erem.id, [])
                    if szerzesek:
                        stamps = [s.strftime('%Y-%m-%d %H:%M:%S') for s in szerzesek[:fe.szamlalo]]
                        typer.echo(f"      Kiosztva (UTC): {'; '.join(stamps)}")
                        if fe.szamlalo > len(stamps):
                            missing = fe.szamlalo - len(stamps)
                            plural = "alkalom" if missing == 1 else "alkalom"
                            typer.echo(
                                f"      (+{missing} korábbi {plural}, dátum nélkül - régi adatok)"
                            )
                    else:
                        typer.echo(f"      Kiosztva (UTC): {fe.szerzett.strftime('%Y-%m-%d %H:%M:%S')}")

                # Same-minute cluster diagnostics: helps explain "identical timestamps" in reports.
                minute_groups: dict[str, list[str]] = defaultdict(list)
                for erem_id, dt_list in szerzes_map.items():
                    label = id_to_label.get(erem_id, erem_id)
                    for ts in dt_list:
                        minute_groups[ts.strftime('%Y-%m-%d %H:%M')].append(label)

                cluster_rows = [(k, v) for k, v in sorted(minute_groups.items()) if len(v) >= 2]
                if cluster_rows:
                    typer.echo("      Időbélyeg-cluster (azonos grant perc):")
                    for minute_key, labels in cluster_rows:
                        typer.echo(
                            f"        {minute_key}  -> {len(labels)} szerzés "
                            f"({'; '.join(labels[:5])}{' ...' if len(labels) > 5 else ''})"
                        )
            typer.echo()

    if generate and generate_dry_run:
        typer.echo("[!] A --generate és --generate-dry-run együtt nem használható.")
        raise typer.Exit(code=2)

    db_path = _resolve_db_path()

    if delete_id:
        _ensure_db_exists(db_path)
        _handle_delete(db_path)
        return
    if generator_inputs:
        _ensure_db_exists(db_path)
        _handle_generator_inputs(db_path)
        return
    if review_time_gating or review_time_gating_llm or review_time_gating_fix or review_time_gating_interactive:
        _ensure_db_exists(db_path)
        _handle_review_time_gating(db_path)
        return
    if generate_dry_run or generate:
        _ensure_db_exists(db_path)
        _handle_generate(db_path)
        return
    if conditions:
        _ensure_db_exists(db_path)
        _handle_conditions(db_path)
        return
    if dynamic:
        _ensure_db_exists(db_path)
        _handle_dynamic(db_path)
        return
    if list_all:
        _handle_list_all()
        return

    _ensure_db_exists(db_path)
    _handle_default_listing(db_path)


# ---------------------------------------------------------------------------
# felvi medal-assets
# ---------------------------------------------------------------------------

@app.command("medal-assets")
def medal_assets_cmd(
    erem_id: Annotated[
        str | None, typer.Option("--erem-id", help="Csak ehhez az éremhez generál")
    ] = None,
    kinds: Annotated[
        str, typer.Option("--kinds", help="Vesszővel elválasztott asset típusok: kep,hang")
    ] = "kep,hang",
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Meglévő asseteket is újra generálja")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Csak listázza, mi hiányzik – nem generál")
    ] = False,
    status: Annotated[
        bool, typer.Option("--status", help="Meglévő asset fájlok állapota")
    ] = False,
) -> None:
    """Medal asset képek és hangok generálása (DALL-E 3 + TTS)."""
    from felvi_games.achievements import EREM_KATALOGUS
    from felvi_games.medal_assets import generate_medal_assets, medal_asset_exists

    kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
    catalog = (
        {erem_id: EREM_KATALOGUS[erem_id]}
        if erem_id and erem_id in EREM_KATALOGUS
        else EREM_KATALOGUS
    )
    if erem_id and erem_id not in EREM_KATALOGUS:
        typer.echo(f"[!] Ismeretlen érem: {erem_id}")
        raise typer.Exit(code=1)

    if status:
        typer.echo("\n=== Medal asset állapot ===\n")
        typer.echo(f"  {'Érem':<28} {'kep':>5}  {'hang':>5}  {'gif':>5}")
        typer.echo("  " + "-" * 50)
        for eid, erem in catalog.items():
            cols = {k: ("✓" if medal_asset_exists(eid, k) else "✗") for k in ("kep", "hang", "gif")}
            typer.echo(f"  {erem.ikon} {erem.nev:<26} {cols['kep']:>5}  {cols['hang']:>5}  {cols['gif']:>5}")
        typer.echo()
        return

    typer.echo(f"\nGenerálandó: {', '.join(kind_list)}")
    typer.echo(f"Érmek: {len(catalog)}  |  overwrite={overwrite}  |  dry_run={dry_run}\n")

    for eid, erem in catalog.items():
        missing = [k for k in kind_list if k != "gif" and (overwrite or not medal_asset_exists(eid, k))]
        if not missing:
            typer.echo(f"  ✓ {erem.ikon} {erem.nev} – már kész")
            continue
        if dry_run:
            typer.echo(f"  ? {erem.ikon} {erem.nev} – hiányzik: {', '.join(missing)}")
            continue
        typer.echo(f"  ⏳ {erem.ikon} {erem.nev} – generálás: {', '.join(missing)} …")
        try:
            saved = generate_medal_assets(erem, kinds=tuple(missing), overwrite=overwrite)
            for k, path in saved.items():
                typer.echo(f"      ✓ {k}: {path}")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"      ✗ hiba: {exc}")

    typer.echo()


# ---------------------------------------------------------------------------
# felvi medal-add  /  medal-edit  /  medal-grant  /  medal-delete
# ---------------------------------------------------------------------------

def _get_repo_for_medals(db: Path | None) -> FeladatRepository:
    from felvi_games.db import FeladatRepository
    return FeladatRepository(db)


@app.command("medal-add")
def medal_add_cmd(
    db: Annotated[Path | None, typer.Option("--db", help="DB fájl útvonala")] = None,
    id: Annotated[str, typer.Option("--id", help="Egyedi slug, pl. 'kivalosag_2026'")] = ...,
    nev: Annotated[str, typer.Option("--nev", help="Magyar megjelenítési név")] = ...,
    leiras: Annotated[str, typer.Option("--leiras", help="Rövid leírás")] = ...,
    ikon: Annotated[str, typer.Option("--ikon", help="Emoji ikon")] = "🏅",
    kategoria: Annotated[str, typer.Option("--kategoria")] = "teljesitmeny",
    ideiglenes: Annotated[bool, typer.Option("--ideiglenes")] = False,
    ervenyes_napig: Annotated[int | None, typer.Option("--ervenyes-napig")] = None,
    ismetelheto: Annotated[bool, typer.Option("--ismetelheto")] = False,
    privat: Annotated[bool, typer.Option("--privat", help="Privát érem (csak a célfelhasználónak látható)")] = False,
    cel_felhasznalo: Annotated[
        str | None,
        typer.Option("--cel-felhasznalo", help="Privát érem célfelhasználója"),
    ] = None,
) -> None:
    """Új érem hozzáadása a katalógushoz (azonnal érvényes, újraindítás nélkül)."""
    from felvi_games.models import Erem

    if privat and not cel_felhasznalo:
        typer.echo("[!] Privát éremnél kötelező megadni --cel-felhasznalo-t.")
        raise typer.Exit(code=1)

    repo = _get_repo_for_medals(db)
    catalog = repo.get_erem_katalogus()
    if id in catalog:
        typer.echo(f"[!] Az '{id}' azonosítójú érem már létezik. Használd a medal-edit parancsot.")
        raise typer.Exit(code=1)

    erem = Erem(
        id=id, nev=nev, leiras=leiras, ikon=ikon, kategoria=kategoria,
        ideiglenes=ideiglenes, ervenyes_napig=ervenyes_napig,
        ismetelheto=ismetelheto, privat=privat, cel_felhasznalo=cel_felhasznalo,
    )
    repo.upsert_erem(erem)
    scope = f"privát → {cel_felhasznalo}" if privat else "globális"
    typer.echo(f"✓ Érem hozzáadva: {ikon} {nev}  [{scope}]  (id={id})")


@app.command("medal-edit")
def _medal_edit_cmd(
    db: Annotated[Path | None, typer.Option("--db")] = None,
    id: Annotated[str, typer.Option("--id", help="Szerkesztendő érem azonosítója")] = ...,
    nev: Annotated[str | None, typer.Option("--nev")] = None,
    leiras: Annotated[str | None, typer.Option("--leiras")] = None,
    ikon: Annotated[str | None, typer.Option("--ikon")] = None,
    kategoria: Annotated[str | None, typer.Option("--kategoria")] = None,
    ideiglenes: Annotated[bool | None, typer.Option("--ideiglenes/--nem-ideiglenes")] = None,
    ervenyes_napig: Annotated[int | None, typer.Option("--ervenyes-napig")] = None,
    ismetelheto: Annotated[bool | None, typer.Option("--ismetelheto/--nem-ismetelheto")] = None,
    privat: Annotated[bool | None, typer.Option("--privat/--globalis")] = None,
    cel_felhasznalo: Annotated[str | None, typer.Option("--cel-felhasznalo")] = None,
    condition_json: Annotated[
        str | None,
        typer.Option("--condition-json", help="Dinamikus feltétel JSON (pl. '{\"type\":\"after_hour\",...}')"),
    ] = None,
    clear_condition: Annotated[
        bool,
        typer.Option("--clear-condition", help="Dinamikus feltétel törlése"),
    ] = False,
) -> None:
    """Meglévő érem metaadatainak szerkesztése (újraindítás nélkül érvényes)."""
    import dataclasses
    import json as _json

    from sqlalchemy.orm import Session as _Session

    from felvi_games.db import EremRecord

    repo = _get_repo_for_medals(db)
    with _Session(repo._engine) as s:
        rec = s.get(EremRecord, id)

    if rec is None:
        typer.echo(f"[!] Ismeretlen érem azonosító: '{id}'")
        raise typer.Exit(code=1)

    existing = rec.to_domain()
    if condition_json is not None and clear_condition:
        typer.echo("[!] A --condition-json és --clear-condition együtt nem használható.")
        raise typer.Exit(code=2)

    parsed_condition = existing.condition
    if clear_condition:
        parsed_condition = None
    elif condition_json is not None:
        try:
            parsed = _json.loads(condition_json)
        except _json.JSONDecodeError as exc:
            typer.echo(f"[!] Érvénytelen JSON a --condition-json paraméterben: {exc}")
            raise typer.Exit(code=2) from exc
        if parsed is not None and not isinstance(parsed, dict):
            typer.echo("[!] A --condition-json csak objektum (dict) vagy null lehet.")
            raise typer.Exit(code=2)
        parsed_condition = parsed

    updated = dataclasses.replace(
        existing,
        nev=nev if nev is not None else existing.nev,
        leiras=leiras if leiras is not None else existing.leiras,
        ikon=ikon if ikon is not None else existing.ikon,
        kategoria=kategoria if kategoria is not None else existing.kategoria,
        ideiglenes=ideiglenes if ideiglenes is not None else existing.ideiglenes,
        ervenyes_napig=ervenyes_napig if ervenyes_napig is not None else existing.ervenyes_napig,
        ismetelheto=ismetelheto if ismetelheto is not None else existing.ismetelheto,
        privat=privat if privat is not None else existing.privat,
        cel_felhasznalo=cel_felhasznalo if cel_felhasznalo is not None else existing.cel_felhasznalo,
        condition=parsed_condition,
    )
    repo.upsert_erem(updated)
    typer.echo(f"✓ Érem frissítve: {updated.ikon} {updated.nev}  (id={id})")


@app.command("medal-grant")
def medal_grant_cmd(
    db: Annotated[Path | None, typer.Option("--db")] = None,
    id: Annotated[str, typer.Option("--id", help="Érem azonosítója")] = ...,
    felhasznalo: Annotated[str, typer.Option("--felhasznalo", help="Felhasználó neve")] = ...,
    ervenyes_napig: Annotated[int | None, typer.Option("--ervenyes-napig", help="Lejárat napokban")] = None,
) -> None:
    """Érem manuális odaítélése egy felhasználónak (privát érmekhez hasznos)."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.orm import Session as _Session

    from felvi_games.db import EremRecord

    repo = _get_repo_for_medals(db)
    with _Session(repo._engine) as s:
        rec = s.get(EremRecord, id)
    if rec is None:
        typer.echo(f"[!] Ismeretlen érem azonosító: '{id}'")
        raise typer.Exit(code=1)

    erem = rec.to_domain()
    if ervenyes_napig and not erem.ismetelheto:
        typer.echo("[i] Nem ismételhető éremnél a lejárat figyelmen kívül lesz hagyva (örökre megmarad).")
        ervenyes_napig = None

    expires_at = None
    if ervenyes_napig:
        expires_at = datetime.now(timezone.utc) + timedelta(days=ervenyes_napig)

    fe = repo.grant_erem(felhasznalo, id, lejarat_at=expires_at)
    typer.echo(f"✓ {erem.ikon} {erem.nev} → {felhasznalo}  (szerzett #{fe.szamlalo})")
    if expires_at:
        typer.echo(f"  Lejárat: {expires_at.strftime('%Y-%m-%d')}")


@app.command("medal-delete")
def medal_delete_cmd(
    db: Annotated[Path | None, typer.Option("--db")] = None,
    id: Annotated[str, typer.Option("--id", help="Törlendő érem azonosítója")] = ...,
    force: Annotated[bool, typer.Option("--force", help="Megerősítés kihagyása")] = False,
) -> None:
    """Érem törlése a katalógusból (a kiosztott érmeket NEM törli)."""
    repo = _get_repo_for_medals(db)
    if not force:
        confirm = typer.confirm(f"Biztosan törlöd az '{id}' érmet a katalógusból?")
        if not confirm:
            typer.echo("Megszakítva.")
            raise typer.Exit()
    removed = repo.delete_erem(id)
    if removed:
        typer.echo(f"✓ Érem törölve: {id}")
    else:
        typer.echo(f"[!] Nem található: {id}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# felvi stats
# ---------------------------------------------------------------------------

@app.command("stats")
def stats_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
) -> None:
    """Feladatok és megoldások összefoglaló statisztikája a DB-ből."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRecord, MegoldasRecord, get_engine

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    engine = get_engine(db_path)
    with Session(engine) as sess:
        total_feladatok = sess.scalar(select(func.count()).select_from(FeladatRecord)) or 0
        total_attempts = sess.scalar(select(func.count()).select_from(MegoldasRecord)) or 0
        total_correct = sess.scalar(
            select(func.count()).select_from(MegoldasRecord).where(MegoldasRecord.helyes.is_(True))
        ) or 0
        accuracy = round(100.0 * total_correct / total_attempts, 1) if total_attempts else 0.0

        by_targy_szint = sess.execute(
            select(FeladatRecord.targy, FeladatRecord.szint, func.count().label("n"))
            .group_by(FeladatRecord.targy, FeladatRecord.szint)
            .order_by(FeladatRecord.targy, FeladatRecord.szint)
        ).all()

        by_ev = sess.execute(
            select(FeladatRecord.ev, func.count().label("n"))
            .group_by(FeladatRecord.ev)
            .order_by(FeladatRecord.ev)
        ).all()

        reviewed = sess.scalar(
            select(func.count()).select_from(FeladatRecord).where(FeladatRecord.review_elvegezve.is_(True))
        ) or 0

    typer.echo(f"\n=== DB Statistics  ({db_path}) ===\n")
    typer.echo(f"  Feladatok összesen:   {total_feladatok}")
    typer.echo(f"  Felülvizsgált:        {reviewed} / {total_feladatok}")
    typer.echo(f"  Megoldási kísérletek: {total_attempts}")
    typer.echo(f"  Helyes válaszok:      {total_correct}  ({accuracy:.1f}%)")

    if by_targy_szint:
        typer.echo("\n  Tárgy / Szint:")
        for row in by_targy_szint:
            typer.echo(f"    {row.targy:<10} {row.szint:<6}  {row.n} feladat")

    if by_ev:
        typer.echo("\n  Évenkénti bontás:")
        for row in by_ev:
            label = str(row.ev) if row.ev is not None else "(ismeretlen)"
            typer.echo(f"    {label:<10}  {row.n} feladat")

    typer.echo()


# ---------------------------------------------------------------------------
# felvi wrong  – hibásan megoldott feladatok listája
# ---------------------------------------------------------------------------

@app.command("wrong")
def wrong_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Szűrés egy felhasználóra")
    ] = None,
    targy: Annotated[
        Targy | None, typer.Option("--targy", help="Tantárgy szűrő")
    ] = None,
    szint: Annotated[
        EvfolyamKulcs | None, typer.Option("--szint", help="Évfolyam szűrő (4/6/8)")
    ] = None,
    min_hibas: Annotated[
        int, typer.Option("--min-hibas", help="Csak legalább ennyi hibás kísérlettel rendelkező feladatok")
    ] = 1,
    limit: Annotated[
        int, typer.Option("--limit", help="Max. kilistázott feladatok száma (0 = mind)")
    ] = 20,
    detail: Annotated[
        bool, typer.Option("--detail", help="A ténylegesen beírt hibás válaszok is jelenjenek meg")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", help="Kimenet fájl útvonala (üres = stdout)")
    ] = None,
) -> None:
    """Feladatok, amelyekre legalább egy hibás választ adtak (legtöbbet rontottak elöl)."""
    from collections import Counter

    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    rows = repo.get_wrong_feladatok(
        felhasznalo_nev=user,
        targy=targy.value if targy else None,
        szint=szint.value if szint else None,
        min_hibas=min_hibas,
        limit=limit,
        include_wrong_answers=detail,
    )

    scope = f"  (user={user})" if user else ""
    lines = [f"\n=== Hibásan megoldott feladatok  (DB: {db_path}){scope} ===\n"]

    if not rows:
        lines.append("  Nincs találat (még senki sem rontott el egy feladatot sem ebben a körben).")
        lines.append("")
    else:
        for r in rows:
            ev_label = str(r.ev) if r.ev else "?"
            tipus = r.feladat_tipus or "-"
            kerdes_short = (r.kerdes[:90] + "…") if len(r.kerdes) > 90 else r.kerdes
            helyes_short = (r.helyes_valasz[:50] + "…") if len(r.helyes_valasz) > 50 else r.helyes_valasz

            lines.append(
                f"  [{r.targy}/{r.szint}/{ev_label}] {tipus}  "
                f"hibás: {r.hibas_db}/{r.osszes_db}  ({r.rontas_pct:.0f}% rontás)"
            )
            lines.append(f"    Kérdés:        {kerdes_short}")
            lines.append(f"    Helyes válasz: {helyes_short}")
            lines.append(f"    ID:            {r.feladat_id}")

            if detail and r.hibas_valaszok:
                cnt = Counter(r.hibas_valaszok)
                parts = [f'"{v}"×{c}' if c > 1 else f'"{v}"' for v, c in cnt.most_common()]
                lines.append(f"    Hibás válaszok: {', '.join(parts)}")

            lines.append("")

        lines.append(f"  Összesen: {len(rows)} feladat listázva.\n")

    output_text = "\n".join(lines)
    if output:
        output.write_text(output_text, encoding="utf-8")
        typer.echo(f"✓ Kiírva: {output}")
    else:
        typer.echo(output_text, nl=False)


# ---------------------------------------------------------------------------
# felvi check-answer  – GPT-alapú válaszellenőrzés egy feladatra
# ---------------------------------------------------------------------------

@app.command("check-answer")
def check_answer_cmd(
    feladat_id: Annotated[str, typer.Argument(help="Feladat ID (pl. mag4_2021_3_8_a)")],
    valasz: Annotated[str, typer.Argument(help="Ellenőrizendő válasz")],
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    apply_latest: Annotated[
        bool,
        typer.Option(
            "--apply-latest",
            help="A legfrissebb, tárolt válaszkísérletet újraértékeli ezzel az eredménnyel"
        ),
    ] = False,
    user: Annotated[
        str | None,
        typer.Option("--user", help="Felhasználó szűrő --apply-latest használatakor"),
    ] = None,
) -> None:
    """GPT-tel ellenőriz egy választ egy adott feladatra.

    Alapból csak kiírja az eredményt. ``--apply-latest`` esetén a legfrissebb,
    eltárolt megoldásra rá is menti az újraértékelt pontszámot.
    """
    from sqlalchemy.orm import Session

    from felvi_games.ai import check_answer
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRecord, FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    with Session(repo._engine) as s:
        f = s.get(FeladatRecord, feladat_id)

    if not f:
        typer.echo(f"[!] Feladat nem található: {feladat_id}")
        raise typer.Exit(code=1)

    typer.echo("\n=== GPT válaszellenőrzés ===\n")
    typer.echo(f"  Feladat:       {feladat_id}  [{f.targy}/{f.szint}]")
    typer.echo(f"  Kérdés:        {f.kerdes[:120]}")
    typer.echo(f"  Helyes válasz: {f.helyes_valasz}")

    elfogadott = None
    if f.elfogadott_valaszok:
        import json as _json
        try:
            elfogadott = _json.loads(f.elfogadott_valaszok)
            typer.echo(f"  Elfogadott:    {', '.join(elfogadott[:5])}{'…' if len(elfogadott) > 5 else ''}")
        except Exception:
            pass

    typer.echo(f"  Beküldött:     {valasz}")
    typer.echo("")

    with typer.progressbar(length=1, label="GPT értékel") as progress:
        ert = check_answer(
            f.kerdes,
            f.helyes_valasz,
            valasz,
            f.magyarazat,
            elfogadott_valaszok=elfogadott,
            feladat_tipus=f.feladat_tipus,
            max_pont=f.max_pont,
            reszpontozas=f.reszpontozas,
        )
        progress.update(1)

    eredmeny = "✅ HELYES" if ert.helyes else ("⚠️  RÉSZLEGES" if ert.pont > 0 else "❌ HELYTELEN")
    typer.echo(f"  Eredmény:      {eredmeny}  ({ert.pont}/{f.max_pont} pont)")
    typer.echo(f"  Visszajelzés:  {ert.visszajelzes}")
    typer.echo("")

    if apply_latest:
        megoldas_id = repo.get_latest_megoldas_id(
            feladat_id,
            felhasznalo_nev=user,
            adott_valasz=valasz,
        )
        if megoldas_id is None:
            who = f" user={user}" if user else ""
            typer.echo(f"[!] Nem található eltárolt kísérlet ehhez: {feladat_id}{who}")
            raise typer.Exit(code=1)

        rv = repo.reevaluate_megoldas(
            megoldas_id,
            ertekeles=ert,
            source="cli_check_answer",
            note="Újraértékelés check-answer parancsból",
        )
        typer.echo("=== Újraértékelés mentve ===")
        typer.echo(f"  Megoldás ID:   {rv['megoldas_id']}")
        typer.echo(f"  Pontszám:      {rv['old_pont']} → {rv['new_pont']} / {rv['max_pont']}")
        if rv["deferred_reward"]:
            typer.echo("  Jutalom:       Függőben (következő interakciónál ellenőrizve)")
        else:
            typer.echo("  Jutalom:       Nincs új, függő reevaluation-jutalom")
        typer.echo("")


# ---------------------------------------------------------------------------
# felvi medal-check  – dinamikus érem-feltételek újraértékelése
# ---------------------------------------------------------------------------

def _medal_check_policy_fix(repo: FeladatRepository, user: str, dry_run: bool) -> None:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import Session

    from felvi_games.db import EremRecord, FelhasznaloEremRecord

    with Session(repo._engine) as s:
        temp_one_time = s.execute(
            select(EremRecord)
            .where(
                EremRecord.ideiglenes.is_(True),
                EremRecord.ismetelheto.is_(False),
                or_(
                    EremRecord.cel_felhasznalo.is_(None),
                    EremRecord.cel_felhasznalo == user,
                ),
            )
            .order_by(EremRecord.created_at.desc())
        ).scalars().all()

        non_repeatable_ids = list(s.scalars(
            select(EremRecord.id).where(EremRecord.ismetelheto.is_(False))
        ))
        expiring_one_time_rows = []
        if non_repeatable_ids:
            expiring_one_time_rows = s.execute(
                select(FelhasznaloEremRecord)
                .where(
                    FelhasznaloEremRecord.felhasznalo_nev == user,
                    FelhasznaloEremRecord.lejarat_at.is_not(None),
                    FelhasznaloEremRecord.erem_id.in_(non_repeatable_ids),
                )
            ).scalars().all()

        typer.echo("\n=== Érem policy fix (non-repeatable=örök, temporary=újra szerezhető) ===")
        typer.echo(f"  Temporary one-time → repeatable: {len(temp_one_time)}")
        for rec in temp_one_time[:20]:
            typer.echo(f"    • {rec.id}  ({rec.nev})")
        if len(temp_one_time) > 20:
            typer.echo(f"    ... +{len(temp_one_time) - 20} további")

        typer.echo(f"  Expiring one-time earned rows to normalize: {len(expiring_one_time_rows)}")

        if not dry_run:
            for rec in temp_one_time:
                rec.ismetelheto = True
            for row in expiring_one_time_rows:
                row.lejarat_at = None
            s.commit()
            typer.echo("  ✅ Policy fix mentve.")
        else:
            typer.echo("  (dry-run: nincs mentés)")
        typer.echo()


def _medal_check_collect_awards(
    repo: FeladatRepository,
    user: str,
) -> tuple[list[tuple[int, str, object, int]], dict[str, int], dict[str, int]]:
    from collections import Counter

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from felvi_games.db import FelhasznaloEremRecord

    with Session(repo._engine) as s:
        award_rows = s.execute(
            select(FelhasznaloEremRecord)
            .where(FelhasznaloEremRecord.felhasznalo_nev == user)
            .order_by(FelhasznaloEremRecord.erem_id, FelhasznaloEremRecord.szerzett_at)
        ).scalars().all()
        awards = [(r.id, r.erem_id, r.szerzett_at, r.szamlalo) for r in award_rows]

    counts = Counter(eid for _, eid, _, _ in awards)
    duplicates = {eid: cnt for eid, cnt in counts.items() if cnt > 1}
    return awards, dict(counts), duplicates


def _medal_check_simulate(
    repo: FeladatRepository,
    user: str,
    db_path: Path,
    counts: dict[str, int],
    duplicates: dict[str, int],
    awards: list[tuple[int, str, object, int]],
    apply: bool,
) -> None:
    from datetime import datetime, timedelta
    from datetime import timezone as _tz

    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select
    from sqlalchemy import update as sa_update
    from sqlalchemy.orm import Session

    from felvi_games.achievements import _eval_dynamic_condition, _simulation_as_of
    from felvi_games.db import FelhasznaloEremRecord, MegoldasRecord, MenetRecord

    SKIP_SIM = {"tokeletes_menet", "maraton", "pentek_matek_honap"}

    with Session(repo._engine) as s:
        megoldas_ts = list(s.scalars(
            select(MegoldasRecord.created_at)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        ).all())
        menet_ts = list(s.scalars(
            select(MenetRecord.ended_at)
            .where(MenetRecord.felhasznalo_nev == user,
                   MenetRecord.ended_at.is_not(None))
            .order_by(MenetRecord.ended_at)
        ).all())

    def _utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=_tz.utc) if dt.tzinfo is None else dt

    all_ts = sorted({_utc(t) for t in megoldas_ts + menet_ts})

    if not all_ts:
        typer.echo(f"  Nincs esemény a DB-ban ({user}) – semmi szimulálható.")
        return

    catalog = repo.get_erem_katalogus(user)
    first_fire: dict[str, datetime] = {}

    typer.echo(f"\n=== Érem időrendi szimuláció: {user}  (DB: {db_path}) ===")
    typer.echo(f"  {len(all_ts)} esemény · {len(catalog)} katalógus-érem\n")

    for ts in all_ts:
        token = _simulation_as_of.set(ts)
        try:
            for erem_id, erem in catalog.items():
                if erem_id in first_fire or erem_id in SKIP_SIM:
                    continue
                if not erem.condition:
                    continue
                if erem.condition_valid_from is not None:
                    vf = erem.condition_valid_from
                    vf = vf if vf.tzinfo else vf.replace(tzinfo=_tz.utc)
                    if ts < vf:
                        continue
                try:
                    earned = _eval_dynamic_condition(
                        user, erem.condition, repo._engine,
                        valid_from=erem.condition_valid_from,
                    )
                except Exception:
                    earned = False
                if earned:
                    first_fire[erem_id] = ts
        finally:
            _simulation_as_of.reset(token)

    typer.echo(f"  Szimulált eredmény: {len(first_fire)} érem\n")
    for eid, ts in sorted(first_fire.items(), key=lambda x: x[1]):
        e = catalog.get(eid)
        label = f"{e.ikon}  {e.nev}" if e else eid
        typer.echo(f"    • {label:40s}  {ts.strftime('%Y-%m-%d %H:%M:%S')}")

    current_ids = set(counts.keys())
    would_ids = set(first_fire.keys())
    lost = current_ids - would_ids
    new_ = would_ids - current_ids
    if lost:
        typer.echo(f"\n  ⚠️  Elveszne (feltétel már nem teljesül): {', '.join(lost)}")
    if new_:
        typer.echo(f"\n  ✨ Újként kerülne kiosztásra: {', '.join(new_)}")
    if duplicates:
        typer.echo(f"\n  ✅ Duplikált sorok megszűnnek: {', '.join(duplicates.keys())}")

    if not apply:
        typer.echo("\n  (Semmi nem változott. Adj hozzá --apply-t a tényleges clear+újraosztáshoz.)\n")
        return

    typer.echo(f"\n  Alkalmazás: {len(awards)} sor törlése + {len(first_fire)} érem újraosztása helyes időbélyeggel...")
    with Session(repo._engine) as s:
        s.execute(sa_delete(FelhasznaloEremRecord)
                  .where(FelhasznaloEremRecord.felhasznalo_nev == user))
        s.commit()

    for eid, ts in sorted(first_fire.items(), key=lambda x: x[1]):
        e = catalog.get(eid)
        if e is None:
            continue
        expires = ts + timedelta(days=e.ervenyes_napig) if e.ideiglenes and e.ervenyes_napig else None
        repo.grant_erem(user, eid, lejarat_at=expires)
        with Session(repo._engine) as s:
            s.execute(
                sa_update(FelhasznaloEremRecord)
                .where(FelhasznaloEremRecord.felhasznalo_nev == user,
                       FelhasznaloEremRecord.erem_id == eid)
                .values(szerzett_at=ts)
            )
            s.commit()

    typer.echo(f"  ✅ Kész. {len(first_fire)} érem újraosztva helyes időbélyeggel.\n")


def _medal_check_dry_run(
    repo: FeladatRepository,
    user: str,
    db_path: Path,
    awards: list[tuple[int, str, object, int]],
    counts: dict[str, int],
    duplicates: dict[str, int],
) -> None:
    from datetime import datetime
    from datetime import timezone as _tz

    from felvi_games.achievements import _eval_dynamic_condition

    typer.echo(f"\n=== Érem dry-run szimulació: {user}  (DB: {db_path}) ===\n")

    typer.echo("  JELENLEGI ÁLLAPOT")
    typer.echo(f"  Szerzett éremsorok száma: {len(awards)}")
    typer.echo(f"  Egyedi érem-id-k:         {len(counts)}")

    if duplicates:
        typer.echo(f"\n  ⚠️  Duplikált sorok ({len(duplicates)} érem):")
        for eid, cnt in duplicates.items():
            rows_for = [(rid, ts) for rid, eid2, ts, _ in awards if eid2 == eid]
            typer.echo(f"    {eid}  → {cnt} sor  (row id-k: {[r[0] for r in rows_for]})")
            for rid, ts in rows_for:
                typer.echo(f"       row id={rid}  szerzett={ts}")
    else:
        typer.echo("  ✅ Nincs duplikált érem-sor.")

    typer.echo("\n  SZIMULÁCIÓ (ha --clear futna most)")
    typer.echo(f"  Törlésre kerülne: {len(awards)} award-sor")

    first_earned: dict[str, object] = {}
    for _, eid, ts, _ in sorted(awards, key=lambda r: r[2] or ""):
        if eid not in first_earned:
            first_earned[eid] = ts

    catalog = repo.get_erem_katalogus(user)
    now = datetime.now(_tz.utc)
    would_grant: list[tuple[str, object, object, str]] = []

    for erem_id, erem in catalog.items():
        if not erem.condition:
            continue
        try:
            earned = _eval_dynamic_condition(
                user, erem.condition, repo._engine,
                valid_from=erem.condition_valid_from,
            )
        except Exception:
            earned = False

        if earned:
            orig = first_earned.get(erem_id)
            would_grant.append((erem_id, erem, orig, ""))

    typer.echo(f"  Újra kiosztható érmek: {len(would_grant)}")
    typer.echo("")

    kept_ids = {eid for eid, _, _, _ in would_grant}
    lost_ids = [eid for eid in counts if eid not in kept_ids]

    if would_grant:
        typer.echo(f"  ✅ MEGMARADNA ({len(would_grant)} érem):")
        for _eid, erem, orig, _ in would_grant:
            orig_str = f"  ← eredeti: {orig}" if orig else ""
            typer.echo(f"    • {erem.ikon}  {erem.nev:30s}  [{erem.kategoria}]{orig_str}")

    if lost_ids:
        typer.echo(f"\n  ❌ ELVESZNE ({len(lost_ids)} érem – a feltétel most már nem teljesül):")
        for eid in lost_ids:
            e = catalog.get(eid)
            label = f"{e.ikon}  {e.nev}" if e else eid
            typer.echo(f"    • {label}")

    typer.echo("\n  ⏰ IDŐBÉLYEG FIGYELMEZTETÉS:")
    typer.echo("  A grant_erem mindig datetime.now()-t használ szerzett_at-nak.")
    typer.echo("  Az eredeti szerzési dátumok ELVESZNEK a --clear után!")
    typer.echo(f"  Pl. '🥇 Félszázad' eredetileg: {first_earned.get('felszazad', 'ismeretlen')}")
    typer.echo(f"      újra kiosztva: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC (mai dátum)")
    typer.echo("\n  (Semmi nem változott – ez dry-run volt.)\n")


def _medal_check_clear(
    repo: FeladatRepository,
    user: str,
    db_path: Path,
    awards: list[tuple[int, str, object, int]],
) -> None:
    from sqlalchemy import delete as sa_delete
    from sqlalchemy.orm import Session

    from felvi_games.achievements import check_new_medals
    from felvi_games.db import FelhasznaloEremRecord

    typer.echo(f"\n=== Érem clear + újraértékelés: {user}  (DB: {db_path}) ===\n")
    typer.echo(f"  Törlés: {len(awards)} award-sor...")
    with Session(repo._engine) as s:
        s.execute(
            sa_delete(FelhasznaloEremRecord)
            .where(FelhasznaloEremRecord.felhasznalo_nev == user)
        )
        s.commit()
    typer.echo("  ✅ Törölve.")
    typer.echo("  Újraértékelés futtatása...")
    earned = check_new_medals(user, None, repo)
    if earned:
        typer.echo(f"\n  ✅ Kiosztott érmek ({len(earned)} db):")
        for erem in earned:
            typer.echo(f"    • {erem.ikon}  {erem.nev}  [{erem.kategoria}]")
    else:
        typer.echo("  Nem sikerült egyetlen érmet sem visszaállítani.")
    typer.echo("")


def _medal_check_default(
    repo: FeladatRepository,
    user: str,
    db_path: Path,
    duplicates: dict[str, int],
) -> None:
    from felvi_games.achievements import check_new_medals

    typer.echo(f"\n=== Érem-feltételek ellenőrzése: {user}  (DB: {db_path}) ===\n")

    if duplicates:
        typer.echo(f"  ⚠️  Duplikált sorok találhatók ({len(duplicates)} érem) – futtasd: --dry-run  vagy --clear")
        for eid, cnt in duplicates.items():
            typer.echo(f"    {eid}  → {cnt} sor")
        typer.echo("")

    earned = check_new_medals(user, None, repo)

    if earned:
        typer.echo(f"  ✅ Kiosztott érmek ({len(earned)} db):")
        for erem in earned:
            typer.echo(f"    • {erem.ikon}  {erem.nev}  [{erem.kategoria}]")
    else:
        typer.echo("  Nincs új teljesített érem.")
    typer.echo("")

@app.command("medal-check")
def medal_check_cmd(
    user: Annotated[str, typer.Argument(help="Felhasználó neve (pl. 'Lóri')")],
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Megmutatja a duplikátumokat és mit ér el a törlés+újraértékelés, de NEM ment",
        ),
    ] = False,
    clear: Annotated[
        bool, typer.Option("--clear", help="Törli az összes szerzett érmet és újra futtatja a check_new_medals-t")
    ] = False,
    simulate: Annotated[
        bool,
        typer.Option(
            "--simulate",
            help="Időrendi visszajátszás: megmutatja mikor sült volna el minden érem először",
        ),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="--simulate után ténylegesen törli és helyes időbélyeggel újraosztja az érmeket",
        ),
    ] = False,
    policy_fix: Annotated[
        bool,
        typer.Option(
            "--policy-fix",
            help="Szabályjavítás: ideiglenes egyedi érmeket ismételhetővé tesz és az egyszeri érmek lejáratát törli",
        ),
    ] = False,
) -> None:
    """Kiértékeli az összes érem-feltételt és kiosztja a teljesített érmeket.

    --dry-run:  duplikátum-ellenőrzés + szimulációs összefoglaló, nem módosít.
    --simulate: időrendi visszajátszás – megmutatja mikor szerezte volna az egyes érmeket.
    --simulate --apply: clear + újraosztás helyes (első tüzelés) időbélyegekkel.
    --clear:    törli az összes szerzett érmet és nulláról értékeli újra (mai dátummal).
    """
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository

    if dry_run and clear:
        typer.echo("[!] A --dry-run és --clear együtt nem használható.")
        raise typer.Exit(code=2)
    if apply and not simulate:
        typer.echo("[!] Az --apply csak --simulate-tal együtt használható.")
        raise typer.Exit(code=2)

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)

    if policy_fix:
        _medal_check_policy_fix(repo, user, dry_run)

    awards, counts, duplicates = _medal_check_collect_awards(repo, user)

    if simulate:
        _medal_check_simulate(repo, user, db_path, counts, duplicates, awards, apply)
        return

    if dry_run:
        _medal_check_dry_run(repo, user, db_path, awards, counts, duplicates)
        return

    if clear:
        _medal_check_clear(repo, user, db_path, awards)
        return

    _medal_check_default(repo, user, db_path, duplicates)


# ---------------------------------------------------------------------------
# felvi reeval  – GPT-alapú újraértékelés parancssori eszköz
# ---------------------------------------------------------------------------

@app.command("reeval")
def reeval_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Szűrés egy felhasználóra")
    ] = None,
    feladat_id: Annotated[
        str | None, typer.Option("--feladat-id", help="Szűrés egy feladatra")
    ] = None,
    megoldas_id: Annotated[
        int | None, typer.Option("--id", help="Egy konkrét megoldás újraértékelése ID alapján")
    ] = None,
    pending: Annotated[
        bool, typer.Option("--pending", help="Csak függő jutalom-feldolgozást futtasson (nem küld GPT-nek)")
    ] = False,
    list_cmd: Annotated[
        bool, typer.Option("--list", help="Listázza az újraértékelhető (nyílt válasz) megoldásokat")
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", help="Maximum feldolgozandó megoldások száma")
    ] = 10,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Csak kiírja mit csinálna, nem ment")
    ] = False,
) -> None:
    """GPT-alapú újraértékelés: nyílt válaszok pontszámának felülvizsgálata.

    Alap: listázza az újraértékelhető megoldásokat (--list).
    --pending: feldolgozza a függőben lévő jutalmakat (nem kér GPT-t).
    --id N: egy megoldást értékel újra GPT-vel.
    --user / --feladat-id: tömeges újraértékelés (--limit darabot).
    """
    import json as _json

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from felvi_games.ai import check_answer
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRecord, FeladatRepository, MegoldasRecord

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)

    # --pending: process deferred rewards only, no GPT calls
    if pending:
        if not user:
            typer.echo("[!] --pending használatához add meg a --user opciót.")
            raise typer.Exit(code=2)
        earned = repo.process_pending_ujraertekeles_jutalom(user, trigger_tipus="cli_reeval")
        if earned:
            typer.echo(f"✅ Jutalmak kiosztva ({user}): {', '.join(earned)}")
        else:
            typer.echo(f"  Nincs függő jutalom ({user}).")
        return

    # Query candidate rows
    with Session(repo._engine) as s:
        stmt = (
            select(
                MegoldasRecord.id,
                MegoldasRecord.felhasznalo_nev,
                MegoldasRecord.feladat_id,
                MegoldasRecord.adott_valasz,
                MegoldasRecord.pont,
                MegoldasRecord.helyes,
                MegoldasRecord.ujraertekelt,
                MegoldasRecord.created_at,
            )
            .where(MegoldasRecord.adott_valasz.is_not(None))
        )
        if megoldas_id is not None:
            stmt = stmt.where(MegoldasRecord.id == megoldas_id)
        else:
            if user:
                stmt = stmt.where(MegoldasRecord.felhasznalo_nev == user)
            if feladat_id:
                stmt = stmt.where(MegoldasRecord.feladat_id == feladat_id)
            # For bulk: prefer not-yet-reevaluated, open-answer tasks
            from felvi_games.db import FeladatRecord as FR
            open_ids = set(s.scalars(
                select(FR.id).where(FR.feladat_tipus == "nyilt_valasz")
            ).all())
            if not feladat_id:
                stmt = stmt.where(MegoldasRecord.feladat_id.in_(open_ids))
            stmt = stmt.order_by(MegoldasRecord.ujraertekelt.asc(), MegoldasRecord.created_at.desc())
            stmt = stmt.limit(limit)

        rows = s.execute(stmt).all()

    if not rows:
        typer.echo("  Nincs újraértékelhető megoldás a feltételek alapján.")
        return

    # --list mode
    if list_cmd or (megoldas_id is None and not user and not feladat_id):
        typer.echo(f"\n=== Újraértékelhető megoldások  (DB: {db_path})  összesen: {len(rows)} ===\n")
        for r in rows:
            flag = "✓" if r.ujraertekelt else " "
            eredmeny = "✅" if r.helyes else "❌"
            typer.echo(
                f"  [{flag}] id={r.id:5d}  {eredmeny} {r.pont}pt  "
                f"{r.feladat_id}  {r.felhasznalo_nev}  "
                f"  válasz: {str(r.adott_valasz or '')[:60]}"
            )
        typer.echo("\nTipp: felvi reeval --id <ID>   egy konkrét újraértékeléshez")
        typer.echo(      "      felvi reeval --user <NÉV>  tömeges újraértékeléshez\n")
        return

    # Reevaluate rows with GPT
    total = len(rows)
    improved = skipped = errors = 0

    typer.echo(f"\n=== GPT újraértékelés  (DB: {db_path})  {'DRY-RUN  ' if dry_run else ''}{total} megoldás ===\n")

    with Session(repo._engine) as s:
        for r in rows:
            f = s.get(FeladatRecord, r.feladat_id)
            if not f:
                typer.echo(f"  [!] Feladat nem található: {r.feladat_id} — kihagyva")
                skipped += 1
                continue

            elfogadott = None
            if f.elfogadott_valaszok:
                try:
                    elfogadott = _json.loads(f.elfogadott_valaszok)
                except Exception:
                    pass

            try:
                ert = check_answer(
                    f.kerdes,
                    f.helyes_valasz,
                    r.adott_valasz or "",
                    f.magyarazat,
                    elfogadott_valaszok=elfogadott,
                    feladat_tipus=f.feladat_tipus,
                    max_pont=f.max_pont,
                    reszpontozas=f.reszpontozas,
                )
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"  [!] GPT hiba  id={r.id}: {exc}")
                errors += 1
                continue

            arrow = f"{r.pont} → {ert.pont}" if ert.pont != r.pont else f"{r.pont} (változatlan)"
            flag = "📈" if ert.pont > r.pont else ("📉" if ert.pont < r.pont else "➡️ ")
            typer.echo(
                f"  {flag} id={r.id:5d}  {r.feladat_id}  {r.felhasznalo_nev}  "
                f"pont: {arrow} / {f.max_pont}   {ert.visszajelzes[:60]}"
            )

            if not dry_run:
                rv = repo.reevaluate_megoldas(
                    r.id,
                    ertekeles=ert,
                    source="cli_reeval",
                    note="Tömeges CLI újraértékelés",
                )
                if rv["new_pont"] > rv["old_pont"]:
                    improved += 1
                    if rv["deferred_reward"]:
                        typer.echo(f"          ⭐ Jutalom függőben ({r.felhasznalo_nev})")

    if not dry_run:
        typer.echo(f"\n  Mentve: {total - skipped - errors} db, javult: {improved}, hiba: {errors}\n")
        # Auto-process pending rewards for targeted user
        if user:
            earned = repo.process_pending_ujraertekeles_jutalom(user, trigger_tipus="cli_reeval")
            if earned:
                typer.echo(f"  ✅ Jutalmak kiosztva: {', '.join(earned)}\n")
    else:
        typer.echo("\n  (Dry-run, semmi nem lett mentve.)\n")


# ---------------------------------------------------------------------------
# felvi user-stats
# ---------------------------------------------------------------------------

@app.command("user-stats")
def user_stats_cmd(
    user: Annotated[str, typer.Argument(help="Felhasználó neve (pl. 'Lackó')")],
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    simulate: Annotated[
        bool, typer.Option("--simulate", help="Éremszabályok szimulációja (nem ment semmit)")
    ] = False,
) -> None:
    """Egy felhasználó részletes statisztikája és éremszabály-kiértékelése."""
    from felvi_games.achievements import EREM_KATALOGUS, simulate_medal_rules
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository, get_engine

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    stats = repo.get_user_stats(user)
    if stats is None:
        typer.echo(f"[!] Ismeretlen felhasználó: '{user}'")
        raise typer.Exit(code=1)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"  Felhasználó: {stats.nev}  (id={stats.id})")
    typer.echo(f"  Regisztrált: {stats.created_at}")
    typer.echo(f"{'='*60}")

    typer.echo("\n--- Menetek ---")
    typer.echo(f"  Összes menet:       {stats.menetek_ossz}")
    typer.echo(f"  Befejezett:         {stats.menetek_befejezett}")
    typer.echo(f"  Megoldott feladat:  {stats.megoldott_ossz} / {stats.tervezett_ossz}")
    typer.echo(f"  Összpontszám:       {stats.pont_ossz}")
    typer.echo(f"  Első menet:         {stats.elso_menet}")
    typer.echo(f"  Utolsó menet:       {stats.utolso_menet}")

    typer.echo("\n--- Válaszok ---")
    typer.echo(f"  Összes válasz:      {stats.valaszok_ossz}")
    typer.echo(f"  Helyes:             {stats.helyes_ossz}  ({stats.accuracy_pct:.1f}%)")
    typer.echo(f"  Átlag idő:          {f'{stats.atlag_mp:.1f}s' if stats.atlag_mp else '-'}")
    typer.echo(f"  Leggyorsabb:        {f'{stats.min_mp:.1f}s' if stats.min_mp else '-'}")
    typer.echo(f"  Segítséget kért:    {stats.hint_ossz}")

    typer.echo("\n--- Tárgyak / Szintek ---")
    for targy, szint, n in stats.targy_szint:
        typer.echo(f"  {targy} / {szint}: {n} menet")

    typer.echo(f"\n--- Játéknapok ({len(stats.jateknapok)} különböző nap) ---")
    for nap, n in stats.jateknapok:
        typer.echo(f"  {nap}  ({n} menet)")

    typer.echo(f"\n--- Megszerzett érmek ({len(stats.eremek)}) ---")
    if not stats.eremek:
        typer.echo("  (még nincs)")
    for fe in stats.eremek:
        erem = EREM_KATALOGUS.get(fe.erem_id)
        nev = erem.nev if erem else fe.erem_id
        ikon = erem.ikon if erem else "🏅"
        szamlalo = f" ×{fe.szamlalo}" if fe.szamlalo > 1 else ""
        lejarat = f"  [lejár: {fe.lejarat}]" if fe.lejarat else ""
        typer.echo(f"  {ikon} {nev}{szamlalo}  ({fe.szerzett}){lejarat}")

    if simulate:
        engine = get_engine(db_path)
        earned_ids = {fe.erem_id for fe in stats.eremek}
        sim_results = simulate_medal_rules(user, engine, earned_ids)
        typer.echo("\n--- Éremszabály szimuláció ---")
        typer.echo(f"  {'Érem':<32} {'Teljesül':>8}  Megjegyzés")
        typer.echo("  " + "-" * 60)
        for r in sim_results:
            if r.error:
                typer.echo(f"  ❌ {r.nev:<32}    HIBA  {r.error}")
                continue
            if r.result:
                if r.already_earned and not r.ismetelheto:
                    mark, note = "✓", "már megvan"
                elif r.already_earned:
                    mark, note = "✓", "ismételné"
                else:
                    mark, note = "🏅", ">>> ÚJ ÉREM <<<"
            else:
                mark, note = "·", ""
            typer.echo(f"  {mark} {r.nev:<32} {str(r.result):>8}  {note}")
        typer.echo()

    typer.echo()


# ---------------------------------------------------------------------------
# felvi medal-clear  – összes kiosztott érem törlése
# ---------------------------------------------------------------------------

@app.command("medal-clear")
def medal_clear_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Csak egy felhasználó érmeinek törlése")
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Megerősítés kérése nélkül töröl")
    ] = False,
) -> None:
    """Kiosztott érmek törlése a DB-ből.

    \b
    felvi medal-clear               # minden felhasználó érme
    felvi medal-clear --user Lóri   # csak Lóri érme
    felvi medal-clear --yes         # megerősítés nélkül
    """
    from sqlalchemy import text

    from felvi_games.config import get_db_path
    from felvi_games.db import get_engine

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    engine = get_engine(db_path)
    with engine.connect() as conn:
        if user:
            cnt = conn.execute(
                text("SELECT COUNT(*) FROM felhasznalo_eremek WHERE felhasznalo_nev = :u"),
                {"u": user},
            ).scalar() or 0
        else:
            cnt = conn.execute(text("SELECT COUNT(*) FROM felhasznalo_eremek")).scalar() or 0

    scope = f"'{user}'" if user else "minden felhasználó"
    typer.echo(f"\n{cnt} érem lesz törölve ({scope}).")

    if cnt == 0:
        typer.echo("Nincs mit törölni.")
        return

    if not yes:
        typer.confirm("Folytatod?", abort=True)

    with engine.begin() as conn:
        if user:
            conn.execute(
                text("DELETE FROM felhasznalo_eremek WHERE felhasznalo_nev = :u"),
                {"u": user},
            )
        else:
            conn.execute(text("DELETE FROM felhasznalo_eremek"))

    typer.echo(f"✅ {cnt} érem törölve.\n")


# ---------------------------------------------------------------------------
# felvi medal-recheck  – retroaktív éremkiértékelés minden felhasználóra
# ---------------------------------------------------------------------------

@app.command("medal-recheck")
def medal_recheck_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Csak egy felhasználó kiértékelése")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Csak listázza a várható érmeket, nem ment")
    ] = False,
) -> None:
    """Retroaktív éremkiértékelés – minden felhasználóra lefuttatja az összes szabályt.

    Hasznos akkor, ha új érmek kerültek a katalógusba, vagy ha valaki lezáratlan
    menettel rendelkezik, ahol a session-end éremcheck nem futott le.

    \b
    felvi medal-recheck               # minden felhasználó
    felvi medal-recheck --user Lóri   # csak Lóri
    felvi medal-recheck --dry-run     # csak kiírja, nem ment
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session as _Session

    from felvi_games.achievements import (
        MedalCheckDetails,
        check_new_medals,
    )
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository, FelhasznaloRecord, get_engine

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    engine = get_engine(db_path)

    with _Session(engine) as s:
        if user:
            users = [user]
        else:
            users = list(s.scalars(select(FelhasznaloRecord.nev).order_by(FelhasznaloRecord.nev)))

    typer.echo(f"\n=== Érem újrakiértékelés  (DB: {db_path})  dry_run={dry_run} ===\n")

    total_granted = 0
    for nev in users:
        typer.echo(f"👤 {nev}")
        if dry_run:
            details = MedalCheckDetails()
            new_pending = check_new_medals(nev, None, repo, dry_run=True, details=details)
            would_repeat = details.would_repeat

            if new_pending:
                for e in new_pending:
                    typer.echo(f"  🏅 {e.ikon} {e.nev}  → ÚJ")
            if would_repeat:
                for e in would_repeat:
                    typer.echo(f"  🔁 {e.ikon} {e.nev}  → ismételné")
            if not new_pending and not would_repeat:
                typer.echo("  (nincs új érem)")
        else:
            newly = check_new_medals(nev, None, repo)
            if newly:
                for e in newly:
                    typer.echo(f"  ✅ {e.ikon} {e.nev}")
                total_granted += len(newly)
            else:
                typer.echo("  (nincs új érem)")
        typer.echo()

    if not dry_run:
        typer.echo(f"Összesen kiosztva: {total_granted} érem\n")


# ---------------------------------------------------------------------------
# felvi review  – AI review futtatása feladatokon
# ---------------------------------------------------------------------------

@app.command("review")
def review_cmd(
    feladat_id: Annotated[
        str | None, typer.Argument(help="Feladat ID, amire review-t futtatunk")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    wrong: Annotated[
        bool, typer.Option("--wrong", help="A legtöbbet rontott feladatokat veszi alapul")
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", help="Max. feldolgozandó feladatok száma (--wrong esetén)")
    ] = 5,
    megjegyzes: Annotated[
        str | None, typer.Option("--megjegyzes", help="Kézi megjegyzés az AI-nak")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="LLM modell neve (alap: LLM_MODEL env)")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Futtatja az AI review-t, de nem ment DB-be")
    ] = False,
) -> None:
    """AI review futtatása egy vagy több feladaton.

    Háromféleképpen hívható:

    \b
    felvi review M8_2023_1_3          # egy konkrét feladat
    felvi review --wrong --limit 3    # top-3 legtöbbet rontott
    felvi review --wrong              # top-5 (alap)
    """
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository
    from felvi_games.review import run_feladat_review

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)

    # ---- Determine feladat list ----
    feladatok_to_review: list = []

    if feladat_id:
        f = repo.get(feladat_id)
        if f is None:
            typer.echo(f"[!] Feladat nem található: {feladat_id}")
            raise typer.Exit(code=1)
        feladatok_to_review = [f]
    elif wrong:
        rows = repo.get_wrong_feladatok(limit=limit, min_hibas=1)
        if not rows:
            typer.echo("  Nincs hibásan megoldott feladat.")
            return
        ids = [r.feladat_id for r in rows]
        feladatok_to_review = [f for fid in ids if (f := repo.get(fid)) is not None]
    else:
        typer.echo("[!] Adj meg egy feladat ID-t, vagy használd a --wrong flaget.")
        raise typer.Exit(code=1)

    typer.echo(f"\n=== AI Review  ({len(feladatok_to_review)} feladat)  dry_run={dry_run} ===\n")

    for feladat in feladatok_to_review:
        typer.echo(f"  ▶ {feladat.id}  [{feladat.targy}/{feladat.szint}]")
        kerdes_short = (feladat.kerdes[:80] + "…") if len(feladat.kerdes) > 80 else feladat.kerdes
        typer.echo(f"    Kérdés:  {kerdes_short}")
        typer.echo(f"    Helyes:  {feladat.helyes_valasz}")

        typer.echo("    AI review fut…", nl=False)
        try:
            result = run_feladat_review(
                feladat, repo,
                megjegyzes=megjegyzes, model=model, dry_run=dry_run,
            )
        except Exception as exc:
            typer.echo(f" HIBA: {exc}")
            continue
        typer.echo(" kész.")

        for field in result.changed_fields:
            old_s = str(getattr(feladat, field))[:60]
            new_s = str(getattr(result.updated, field))[:60]
            typer.echo(f"    ~ {field}:")
            typer.echo(f"        előtte: {old_s}")
            typer.echo(f"        utána:  {new_s}")

        if result.updated.review_megjegyzes:
            typer.echo(f"    AI megjegyzés: {result.updated.review_megjegyzes}")

        if not result.changed_fields:
            typer.echo("    → Tartalom nem változott.")
        else:
            typer.echo(f"    → Változott mezők: {', '.join(result.changed_fields)}")

        if dry_run:
            typer.echo("    [dry-run] Nem mentve.")
        elif result.versioned:
            typer.echo(
                f"    ✓ Új verzió: {result.original_id}  →  "
                f"{result.updated.id}  (archivált: {result.original_id})"
            )
        else:
            typer.echo(f"    ✓ In-place frissítve: {result.updated.id}")

        typer.echo()

    typer.echo("Kész.\n")


# ---------------------------------------------------------------------------
# felvi medal-promote-candidates  – cross-user private medal review
# ---------------------------------------------------------------------------

@app.command("medal-promote-candidates")
def _medal_promote_candidates_cmd(
    db: Annotated[Path | None, typer.Option("--db", help="SQLite DB útvonala")] = None,
    min_users: Annotated[
        int,
        typer.Option("--min-users", help="Minimum felhasználók száma, akiknél megjelent (alap: 2)"),
    ] = 2,
    promote_id: Annotated[
        str | None,
        typer.Option("--promote", help="Érem azonosítója, amelyet nyilvánossá tesz"),
    ] = None,
    new_id: Annotated[
        str | None,
        typer.Option("--new-id", help="Új nyilvános azonosító a promóció során (--promote esetén kötelező)"),
    ] = None,
    new_nev: Annotated[str | None, typer.Option("--new-nev")] = None,
    new_leiras: Annotated[str | None, typer.Option("--new-leiras")] = None,
    new_ikon: Annotated[str | None, typer.Option("--new-ikon")] = None,
    new_kategoria: Annotated[str | None, typer.Option("--new-kategoria")] = None,
    ismetelheto: Annotated[
        bool,
        typer.Option("--ismetelheto/--nem-ismetelheto", help="Ismételhető legyen-e a nyilvános érem"),
    ] = True,
    show_signals: Annotated[
        bool,
        typer.Option("--signals/--no-signals", help="Mutassa a generálás közben blokkolt cross-user találatokat"),
    ] = True,
) -> None:
    """Listázza a több felhasználónál is megjelent hasonló privát kihívásérmeket.

    Ha ugyanaz a feltételtípus (pl. after_hour, feladat_count) strukturálisan azonos
    feltétellel két vagy több felhasználónál is felbukkant, az jó jelölt arra, hogy
    nyilvános rémmé alakítsák.

    \b
    felvi medal-promote-candidates                     # listázás
    felvi medal-promote-candidates --min-users 3       # csak 3+ felhasználónál megjelent
    felvi medal-promote-candidates \\
        --promote daily_lori_20260503_0830 \\
        --new-id esti_ottos \\
        --new-nev "Esti ötös" \\
        --new-leiras "Oldj meg 5 feladatot 22:00 után!" \\
        --new-ikon 🌙
    """
    import dataclasses
    import json as _json

    from felvi_games.progress_check import find_cross_user_medal_clusters

    repo = _get_repo_for_medals(db)
    clusters = find_cross_user_medal_clusters(repo, min_users=min_users)
    signal_rows = repo.list_interakciok_by_tipus("medal_public_candidate_hit", limit=500) if show_signals else []

    if promote_id is None:
        # ── List-only mode ────────────────────────────────────────────────
        signal_groups: dict[str, dict] = {}
        for row in signal_rows:
            if not row.meta:
                continue
            try:
                payload = _json.loads(row.meta)
            except Exception:
                continue
            match = payload.get("match") if isinstance(payload, dict) else None
            if not isinstance(match, dict):
                continue
            src_id = str(match.get("source_erem_id", "")).strip()
            if not src_id:
                continue
            bucket = signal_groups.setdefault(
                src_id,
                {
                    "source_erem_id": src_id,
                    "source_user": match.get("source_user"),
                    "source_nev": match.get("source_nev"),
                    "reason": match.get("reason"),
                    "users": set(),
                    "hits": 0,
                },
            )
            bucket["hits"] += 1
            if row.felhasznalo_nev:
                bucket["users"].add(row.felhasznalo_nev)

        if not clusters and not signal_groups:
            typer.echo(
                f"\n(Nincs {min_users}+ felhasználónál megjelent klaszter és nincs blokkolt cross-user jelzés sem.)\n"
            )
            raise typer.Exit()

        typer.echo(
            f"\n{'='*60}\n"
            f"Potenciálisan nyilvánossá tehető kihívásérmek "
            f"({min_users}+ felhasználónál)\n"
            f"{'='*60}"
        )
        for i, cluster in enumerate(clusters, 1):
            rep = cluster.representative
            typer.echo(
                f"\n#{i}  {rep.ikon}  {rep.nev}  "
                f"[{cluster.user_count} felhasználó — {cluster.overlap_reason}]"
            )
            typer.echo(f"     Leírás   : {rep.leiras}")
            typer.echo(f"     Feltétel : {_json.dumps(rep.condition, ensure_ascii=False)}")
            typer.echo("     Tagok    :")
            for m in cluster.members:
                user_label = m.cel_felhasznalo or "?"
                cond_str = _json.dumps(m.condition, ensure_ascii=False) if m.condition else "—"
                typer.echo(f"       • {m.id}  ({user_label})  cond={cond_str}")

        if signal_groups:
            typer.echo(
                f"\n{'='*60}\n"
                "Blokkolt cross-user találatok (promóciós jelzések)\n"
                f"{'='*60}"
            )
            sorted_groups = sorted(
                signal_groups.values(),
                key=lambda g: (len(g["users"]), g["hits"]),
                reverse=True,
            )
            for item in sorted_groups:
                users = sorted(item["users"])
                user_list = ", ".join(users[:6]) + (" ..." if len(users) > 6 else "")
                typer.echo(
                    f"\n- source={item['source_erem_id']}  nev={item.get('source_nev') or '—'}\n"
                    f"  owner={item.get('source_user') or '—'}  reason={item.get('reason') or '—'}\n"
                    f"  distinct_users={len(users)}  hits={item['hits']}\n"
                    f"  users={user_list or '—'}"
                )
        typer.echo(
            f"\n{'-'*60}\n"
            f"Tipp: --promote <érem-id> --new-id <új-id> --new-nev <név> paranccsal tehetsz "
            f"egyet nyilvánossá.\n"
        )
        raise typer.Exit()

    # ── Promote mode ──────────────────────────────────────────────────────
    if not new_id:
        typer.echo("[!] A --new-id megadása kötelező --promote esetén.")
        raise typer.Exit(code=2)

    from sqlalchemy.orm import Session as _Session

    from felvi_games.db import EremRecord

    repo2 = _get_repo_for_medals(db)
    with _Session(repo2._engine) as s:
        source_rec = s.get(EremRecord, promote_id)
        if source_rec is None:
            typer.echo(f"[!] Nem található: '{promote_id}'")
            raise typer.Exit(code=1)
        if s.get(EremRecord, new_id) is not None:
            typer.echo(f"[!] A '{new_id}' azonosító már létezik. Válassz más --new-id-t.")
            raise typer.Exit(code=1)
        source_erem = source_rec.to_domain()


    public_medal = dataclasses.replace(
        source_erem,
        id=new_id,
        nev=new_nev if new_nev is not None else source_erem.nev,
        leiras=new_leiras if new_leiras is not None else source_erem.leiras,
        ikon=new_ikon if new_ikon is not None else source_erem.ikon,
        kategoria=new_kategoria if new_kategoria is not None else source_erem.kategoria,
        privat=False,
        cel_felhasznalo=None,
        ideiglenes=False,
        ervenyes_napig=None,
        ismetelheto=ismetelheto,
        condition_valid_from=None,
    )
    repo2.upsert_erem(public_medal)
    typer.echo(
        f"\n✅ Nyilvános érem létrehozva:\n"
        f"   {public_medal.ikon}  {public_medal.nev}  (id: {public_medal.id})\n"
        f"   Leírás   : {public_medal.leiras}\n"
        f"   Kategória: {public_medal.kategoria}  |  ismételhető: {public_medal.ismetelheto}\n"
    )
    if public_medal.condition:
        typer.echo(f"   Feltétel : {_json.dumps(public_medal.condition, ensure_ascii=False)}")
        typer.echo()
        typer.echo(
            "[i] FONTOS: a feltételt vagy töröld (--clear-condition via medal-edit) "
            "hogy statikus érem legyen, vagy adj hozzá SZABALY_REGISTRY bejegyzést achievements.py-ban "
            "ha saját logikát akarsz."
        )
    typer.echo()


# ---------------------------------------------------------------------------
# felvi report  – heti használati riport (markdown + matplotlib PNG-k)
# ---------------------------------------------------------------------------

@app.command("report")
def report_cmd(
    days: Annotated[
        int, typer.Option("--days", help="Hány napra visszamenőleg (alap: 7)")
    ] = 7,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Kimeneti mappa (alap: ./reports/<dátum>_<napok>d/)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Csak egy felhasználó adatai")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    open_report: Annotated[
        bool, typer.Option("--open", help="Megnyitja a kimeneti mappát fájlkezelőben")
    ] = False,
) -> None:
    """Heti (vagy tetszőleges időtartamú) használati riport generálása.

    Kimenet: markdown összefoglaló + matplotlib PNG grafikonok egy mappában.

    \b
    felvi report                          # utolsó 7 nap, minden felhasználó
    felvi report --days 14                # utolsó 14 nap
    felvi report --user Lóri              # csak Lóri adatai
    felvi report --output-dir my_reports  # egyedi kimeneti mappa
    """
    from felvi_games.config import get_db_path
    from felvi_games.report import run as _run_report

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)
    if days < 1:
        typer.echo("[!] A --days értéke legalább 1 legyen.")
        raise typer.Exit(code=2)

    typer.echo(f"\nRiport generálása  (DB: {db_path}  |  {days} nap  |  user={user or 'mind'})\n")

    out_dir = _run_report(
        db_path=db_path,
        days=days,
        output_dir=output_dir,
        user_filter=user,
    )

    files = sorted(out_dir.iterdir())
    typer.echo(f"✅ Riport kész: {out_dir}")
    for f in files:
        typer.echo(f"   {f.name}")

    if open_report:
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(out_dir)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(out_dir)])
        else:
            subprocess.Popen(["xdg-open", str(out_dir)])

    typer.echo()


# ---------------------------------------------------------------------------
# felvi tts-clear  – TTS szöveg törlése (újrageneráláshoz)
# ---------------------------------------------------------------------------

@app.command("tts-clear")
def tts_clear_cmd(
    feladat_id: Annotated[
        str | None, typer.Argument(help="Csak ezt a feladatot érinti")
    ] = None,
    targy: Annotated[
        Targy | None, typer.Option("--targy", help="Csak ezt a tárgyat érinti (matek/magyar)")
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
) -> None:
    """TTS kérdésszöveg (tts_kerdes_szoveg) törlése DB-ből.

    A törölt rekordok a következő lejátszáskor az aktuális kontextussal
    (csoport-szöveg + kérdés) újragenerálódnak.

    \b
    felvi tts-clear                  # minden feladat
    felvi tts-clear --targy matek    # csak matek
    felvi tts-clear M8_2023_1_3a    # egy feladat
    """
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    count = repo.clear_tts_szoveg(
        feladat_id=feladat_id,
        targy=targy.value if targy else None,
    )
    scope = feladat_id or (f"targy={targy.value}" if targy else "összes")
    typer.echo(f"✓ {count} feladat tts_kerdes_szoveg törölve ({scope}).")


# ---------------------------------------------------------------------------
# felvi medal-diagnose  – inspect medal condition state
# ---------------------------------------------------------------------------

@app.command("medal-diagnose")
def medal_diagnose_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    user: Annotated[
        str | None, typer.Option("--user", help="Csak egy felhasználó nyilvános érmei")
    ] = None,
) -> None:
    """Diagnosztika: melyik érmek vannak betöltve feltétellel a DB-ben.
    
    Segít azonosítani, ha a bootstrap érmeket nem frissítette még a DB.
    """
    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    catalog = repo.get_erem_katalogus(user)

    has_condition = []
    no_condition = []

    for erem_id, erem in catalog.items():
        if erem.condition:
            has_condition.append((erem_id, erem.nev, erem.condition))
        else:
            no_condition.append((erem_id, erem.nev))

    typer.echo(f"\n=== Medal Condition Diagnostic (DB: {db_path}) ===")
    typer.echo(f"Scope: {'user=' + user if user else 'all public medals'}\n")
    
    typer.echo(f"✓ {len(has_condition)} érem FELTÉTELLEL betöltve:")
    for mid, nev, cond in sorted(has_condition, key=lambda x: x[0]):
        ctype = cond.get("type") if isinstance(cond, dict) else "list"
        if isinstance(cond, list):
            ctypes = ", ".join(c.get("type", "?") for c in cond)
            typer.echo(f"  • {mid:30s}  {nev[:40]:40s}  [compound: {ctypes}]")
        else:
            typer.echo(f"  • {mid:30s}  {nev[:40]:40s}  [{ctype}]")

    if no_condition:
        typer.echo(f"\n✗ {len(no_condition)} érem NINCS feltétellel (manuális kiosztás vagy eljárandó):")
        for mid, nev in sorted(no_condition, key=lambda x: x[0]):
            typer.echo(f"  • {mid:30s}  {nev[:40]:40s}")
        typer.echo("\nMegjegyzés: Ha az első csoport túl kicsi, a bootstrap érmeket")
        typer.echo("újra kell tölteni: felvi medal-check <user> --clear --apply")
    
    typer.echo()


# ---------------------------------------------------------------------------
# felvi medal-compare  – compare actual vs simulated medals
# ---------------------------------------------------------------------------

@app.command("medal-compare")
def _medal_compare_cmd(
    user: Annotated[
        str, typer.Argument(help="Felhasználó neve")
    ],
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
) -> None:
    """Összehasonlítja a ténylegesen szerzett érmeket az elméleti lehetőséggel.
    
    Segít diagnosztizálni miért van eltérés az aktuális és szimulált érmek között.
    Megjegyzés: a szimulált eredményt a 'felvi medal-check --simulate' futtatja.
    """
    from datetime import datetime
    from datetime import timezone as _tz

    from felvi_games.config import get_db_path
    from felvi_games.db import FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    catalog = repo.get_erem_katalogus(user)
    
    # Get actual earned medals (including expired for full picture)
    actual = repo.get_eremek(user, include_expired=True)
    actual_ids = {e.erem_id for e in actual}
    
    now = datetime.now(_tz.utc)
    
    typer.echo(f"\n=== Érem Összevetés: {user}  (DB: {db_path}) ===\n")
    typer.echo(f"  Ténylegesen szerzett:    {len(actual_ids):2d} érem\n")
    
    # Group medals by status
    active = []      # non-expired
    expired = []     # expired temp medals
    no_condition = []  # no condition in catalog
    
    for rec in actual:
        if not rec.aktiv:
            expired.append(rec)
        else:
            erem = catalog.get(rec.erem_id)
            if not erem or not erem.condition:
                no_condition.append(rec)
            else:
                active.append(rec)
    
    typer.echo("  📊 Szétbontás:")
    typer.echo(f"    • Aktív (nincs lejárat):        {len(active):2d}")
    typer.echo(f"    • Lejárt (ideiglenes, vége):   {len(expired):2d}")
    typer.echo(f"    • Nincs feltétel (manuális):   {len(no_condition):2d}\n")
    
    if expired:
        typer.echo(f"⏰ Lejárt ideiglenes érmek ({len(expired)}):")
        for rec in sorted(expired, key=lambda r: r.lejarat or datetime.now(_tz.utc), reverse=True):
            e = catalog.get(rec.erem_id)
            label = f"{e.ikon}  {e.nev}" if e else rec.erem_id
            lejarat = rec.lejarat.replace(tzinfo=_tz.utc) if rec.lejarat and rec.lejarat.tzinfo is None else rec.lejarat
            if lejarat:
                expired_ago = (now - lejarat).total_seconds()
                if expired_ago < 86400:
                    mins = int(expired_ago // 60)
                    typer.echo(f"  • {rec.erem_id:30s}  {label:40s}  [{mins // 60}h {mins % 60}m ezelőtt]")
                else:
                    days = int(expired_ago // 86400)
                    typer.echo(f"  • {rec.erem_id:30s}  {label:40s}  [{days}d ezelőtt]")
    
    if no_condition:
        typer.echo(f"\n🔧 Nincs feltétel betöltve ({len(no_condition)}):")
        for rec in no_condition:
            e = catalog.get(rec.erem_id)
            label = f"{e.ikon}  {e.nev}" if e else rec.erem_id
            typer.echo(f"  • {rec.erem_id:30s}  {label:40s}")
    
    if active:
        typer.echo(f"\n✅ Aktív érmek feltétellel ({len(active)}):")
        for rec in sorted(active, key=lambda r: r.szerzett):
            e = catalog.get(rec.erem_id)
            label = f"{e.ikon}  {e.nev}" if e else rec.erem_id
            typer.echo(f"  • {rec.erem_id:30s}  {label:40s}  [{rec.szerzett.strftime('%Y-%m-%d %H:%M')}]")
    
    typer.echo()


# ---------------------------------------------------------------------------
# felvi medal-resync  – update DB medals with bootstrap conditions
# ---------------------------------------------------------------------------

@app.command("medal-resync")
def medal_resync_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Megmutatja mit csinálna, de nem módosít")
    ] = False,
) -> None:
    """Bootstrap érmeket feltételekkel szinkronizálja a DB-re.
    
    Frissíti a meglévő érmeket az aktuális bootstrap JSON feltételeivel.
    Ez szükséges, ha a DB-t egy régebbi verzió hozta létre (feltételek nélkül).
    """
    import json as _json

    from sqlalchemy.orm import Session

    from felvi_games.config import get_db_path
    from felvi_games.db import EremRecord, FeladatRepository
    from felvi_games.medal_catalog import load_bootstrap_erem_catalog

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    bootstrap = load_bootstrap_erem_catalog()

    updated_count = 0
    with Session(repo._engine) as s:
        for erem_id, bootstrap_erem in bootstrap.items():
            record = s.get(EremRecord, erem_id)
            if record is None:
                continue

            # Build condition_json and condition_valid_from
            condition_json = (
                _json.dumps(bootstrap_erem.condition, ensure_ascii=False)
                if bootstrap_erem.condition
                else None
            )
            condition_valid_from = bootstrap_erem.condition_valid_from

            # Only update if the DB record is missing condition_json
            if record.condition_json is None and condition_json is not None:
                if dry_run:
                    typer.echo(f"  [DRY] {erem_id:30s}  ← {bootstrap_erem.condition.get('type', '?')}")
                else:
                    record.condition_json = condition_json
                    record.condition_valid_from = condition_valid_from
                    s.commit()
                    typer.echo(f"  ✓ {erem_id:30s}  ← {bootstrap_erem.condition.get('type', '?')}")
                updated_count += 1

    if dry_run:
        typer.echo(
            f"\n[DRY-RUN] {updated_count} érem frissítésére kerülne sor "
            "(valódi futáshoz hiányzik a --dry-run flag).\n"
        )
    else:
        typer.echo(f"\n✓ {updated_count} érem szinkronizálva bootstrap feltételekkel.\n")


# ---------------------------------------------------------------------------
# felvi medal-backup  – backup medals with conditions to repository
# ---------------------------------------------------------------------------

@app.command("medal-backup")
def medal_backup_cmd(
    db: Annotated[
        Path | None, typer.Option("--db", help="SQLite DB útvonala (alap: FELVI_DB env)")
    ] = None,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Kimeneti JSON fájl útvonala")
    ] = Path("data/eremek.backup.json"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Megmutatja mit csinálna, de nem ment fájlt")
    ] = False,
) -> None:
    """Lementi az összes érem-feltételt a DB-ból egy JSON fájlba (repository backup).
    
    Ez az ellentéte a medal-resync-nek: a DB-ból exportál az aktuális feltételekkel.
    Hasznos a feltételek megőrzésére és verziókezelésre.
    """
    import json as _json

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from felvi_games.config import get_db_path
    from felvi_games.db import EremRecord, FeladatRepository

    db_path = db or get_db_path()
    if not db_path.exists():
        typer.echo(f"[!] DB nem található: {db_path}")
        raise typer.Exit(code=1)

    repo = FeladatRepository(db_path)
    
    # Collect all medals with conditions from DB
    backup_medals = {}
    backed_up_count = 0
    
    with Session(repo._engine) as s:
        records = s.scalars(select(EremRecord).order_by(EremRecord.id)).all()
        
        for record in records:
            if record.condition_json:
                try:
                    condition = _json.loads(record.condition_json)
                    backup_medals[record.id] = {
                        "nev": record.nev,
                        "leiras": record.leiras,
                        "ikon": record.ikon,
                        "kategoria": record.kategoria,
                        "ideiglenes": record.ideiglenes,
                        "ismetelheto": record.ismetelheto,
                        "condition": condition,
                        "condition_valid_from": (
                            record.condition_valid_from.isoformat()
                            if record.condition_valid_from
                            else None
                        ),
                    }
                    backed_up_count += 1
                except Exception as e:
                    typer.echo(f"  ⚠️  Hiba: {record.id} feltételének olvasása: {e}")
    
    typer.echo(f"\n=== Medal Backup (DB: {db_path}) ===\n")
    typer.echo(f"  Talált érmek feltétellel:  {backed_up_count}")
    
    if dry_run:
        typer.echo(f"  [DRY-RUN] Lemenne: {output}")
        typer.echo(
            f"\n[DRY-RUN] {backed_up_count} érem feltételét exportálná "
            "(valódi futáshoz hiányzik a --dry-run flag).\n"
        )
    else:
        # Create output directory if needed
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # Write backup file
        with open(output, 'w', encoding='utf-8') as f:
            _json.dump(backup_medals, f, indent=2, ensure_ascii=False)
        
        typer.echo(f"  ✓ Mentve:                  {output}")
        typer.echo(f"\n✓ {backed_up_count} érem feltétele lementve.\n")
        
        # Show sample
        if backup_medals:
            first_id = next(iter(backup_medals))
            typer.echo(f"  📋 Minta ({first_id}):")
            sample = backup_medals[first_id]
            typer.echo(f"    Név: {sample['nev']}")
            typer.echo(f"    Feltétel: {sample['condition'].get('type', '?')}")


# ---------------------------------------------------------------------------
# Entry point (pyproject.toml → project.scripts)
# ---------------------------------------------------------------------------

def run() -> None:
    app()
