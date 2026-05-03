"""
achievements.py
---------------
Medal/achievement catalog and rule engine.

Design:
  - EREM_KATALOGUS   – static dict of all possible medals (id → Erem)
  - check_new_medals – run after every session; returns medals to award
  - Rules are plain functions querying megoldasok / menetek / interakciok

Icon strategy
  Default : emoji  (works in terminal + Streamlit, zero dependencies)
  Better  : SVG from game-icons.net  (CC BY 3.0, pip install requests)
  Premium : AI-generated PNG via DALL-E 3 – hook in ai.py
            ai.generate_medal_ikon(erem_id: str, leiras: str) → bytes

Adding a new medal:
  1. Add an Erem entry to EREM_KATALOGUS
  2. Write a _rule_<id>(user, session_id, engine) → bool function below
  3. Register it in SZABALY_REGISTRY at the bottom of this file
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass as _dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from felvi_games.models import Erem, FelhasznaloErem, InterakcioTipus

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from felvi_games.db import FeladatRepository

logger = logging.getLogger(__name__)

# Context variable used by --simulate to replay history as of a given timestamp.
# Set this to a datetime before calling rule functions to make them behave as if
# that moment is "now" (i.e. only events up to that timestamp are visible).
_simulation_as_of: ContextVar[datetime | None] = ContextVar("_simulation_as_of", default=None)

# Repeatable medals should not trigger back-to-back from historical data.
# Cooldown is in hours, per medal id. Unlisted repeatables use the default.
_REPEATABLE_COOLDOWN_DEFAULT_HOURS = 12
_REPEATABLE_COOLDOWN_HOURS: dict[str, int] = {
    "villam": 2,
    "reggeli_tanulas": 20,
    "esti_tanulas": 20,
    "heti_haromszor": 24,
    "het_egymas_utan": 24,
    "heti_bajnok": 24,
    "pentek_matek_honap": 24,
    "tokeletes_menet": 4,
}


# ---------------------------------------------------------------------------
# Medal catalog
# ---------------------------------------------------------------------------

EREM_KATALOGUS: dict[str, Erem] = {
    # ── Mérföldkövek ─────────────────────────────────────────────────────────
    "elso_menet": Erem(
        id="elso_menet",
        nev="Első lépés",
        leiras="Teljesítettél egy egész menetet.",
        ikon="🏁",
        kategoria="merfoldko",
    ),
    "szaz_feladat": Erem(
        id="szaz_feladat",
        nev="Centurion",
        leiras="100 feladatot oldottál meg.",
        ikon="💯",
        kategoria="merfoldko",
    ),
    "otszaz_feladat": Erem(
        id="otszaz_feladat",
        nev="Veterán",
        leiras="500 feladatot oldottál meg.",
        ikon="🏆",
        kategoria="merfoldko",
    ),
    "ezer_feladat": Erem(
        id="ezer_feladat",
        nev="Legenda",
        leiras="1 000 feladatot oldottál meg.",
        ikon="🌟",
        kategoria="merfoldko",
    ),

    # ── Teljesítmény ─────────────────────────────────────────────────────────
    "tokeletes_menet": Erem(
        id="tokeletes_menet",
        nev="Tökéletes menet",
        leiras="100%-os pontszámot értél el egy menetben.",
        ikon="💎",
        kategoria="teljesitmeny",
        ismetelheto=True,
    ),
    "sorozat_5": Erem(
        id="sorozat_5",
        nev="5-ös sorozat",
        leiras="5 egymást követő helyes válasz.",
        ikon="🔥",
        kategoria="teljesitmeny",
    ),
    "sorozat_10": Erem(
        id="sorozat_10",
        nev="10-es sorozat",
        leiras="10 egymást követő helyes válasz.",
        ikon="🔥🔥",
        kategoria="teljesitmeny",
    ),
    "sorozat_20": Erem(
        id="sorozat_20",
        nev="20-as sorozat",
        leiras="20 egymást követő helyes válasz.",
        ikon="⚡",
        kategoria="teljesitmeny",
    ),
    "villam": Erem(
        id="villam",
        nev="Villámsebességű",
        leiras="Helyes választ adtál 10 másodpercen belül.",
        ikon="⚡",
        kategoria="teljesitmeny",
        ismetelheto=True,
    ),
    "hint_nelkul_20": Erem(
        id="hint_nelkul_20",
        nev="Független gondolkodó",
        leiras="20 egymást követő feladatot tipp nélkül oldottál meg.",
        ikon="🧠",
        kategoria="teljesitmeny",
    ),
    "magas_pontossag": Erem(
        id="magas_pontossag",
        nev="Precíz",
        leiras="Legalább 80%-os pontosság 50+ kísérlet után.",
        ikon="🎯",
        kategoria="teljesitmeny",
    ),

    # ── Rendszeresség ─────────────────────────────────────────────────────────
    "het_egymas_utan": Erem(
        id="het_egymas_utan",
        nev="Egy hetes sorozat",
        leiras="7 egymást követő napon játszottál.",
        ikon="📅",
        kategoria="rendszeresseg",
        ismetelheto=True,
    ),
    "harom_het_egymas_utan": Erem(
        id="harom_het_egymas_utan",
        nev="Három hetes sorozat",
        leiras="21 egymást követő napon játszottál.",
        ikon="🗓️",
        kategoria="rendszeresseg",
    ),
    "pentek_matek_honap": Erem(
        id="pentek_matek_honap",
        nev="Pénteki matekes",
        leiras="Minden pénteken matekot oldottál meg egy naptári hónapban.",
        ikon="📐",
        kategoria="rendszeresseg",
        ismetelheto=True,
    ),
    "heti_haromszor": Erem(
        id="heti_haromszor",
        nev="Szorgalmas",
        leiras="Egy héten belül legalább 3 különböző napon játszottál.",
        ikon="📆",
        kategoria="rendszeresseg",
        ismetelheto=True,
    ),
    "reggeli_tanulas": Erem(
        id="reggeli_tanulas",
        nev="Korai madár",
        leiras="Reggel 8 előtt oldottál meg feladatot.",
        ikon="🌅",
        kategoria="rendszeresseg",
        ismetelheto=True,
    ),

    # ── Felfedezés ────────────────────────────────────────────────────────────
    "mindket_targy": Erem(
        id="mindket_targy",
        nev="Sokoldalú",
        leiras="Matekot és magyart is gyakoroltál.",
        ikon="🌈",
        kategoria="felfedezes",
    ),
    "minden_szint": Erem(
        id="minden_szint",
        nev="Mindentudó",
        leiras="Mindhárom szinten (4, 6, 8 osztályos) oldottál meg feladatot.",
        ikon="🎓",
        kategoria="felfedezes",
    ),
    "minden_feladattipus": Erem(
        id="minden_feladattipus",
        nev="Változatos",
        leiras="Minden feladattípusból legalább egyet megoldottál.",
        ikon="🔮",
        kategoria="felfedezes",
    ),

    # ── Mérföldkövek (közbülső) ───────────────────────────────────────────────
    "tiz_feladat": Erem(
        id="tiz_feladat",
        nev="Tíz feladat",
        leiras="10 feladatot oldottál meg.",
        ikon="🔟",
        kategoria="merfoldko",
    ),
    "huszonot_feladat": Erem(
        id="huszonot_feladat",
        nev="Negyedszázad",
        leiras="25 feladatot oldottál meg.",
        ikon="🥈",
        kategoria="merfoldko",
    ),
    "otven_feladat": Erem(
        id="otven_feladat",
        nev="Félszázad",
        leiras="50 feladatot oldottál meg.",
        ikon="🥇",
        kategoria="merfoldko",
    ),

    # ── Teljesítmény (új) ─────────────────────────────────────────────────────
    "szaz_pont": Erem(
        id="szaz_pont",
        nev="Százpontos",
        leiras="Összesen 100 pontot gyűjtöttél.",
        ikon="💰",
        kategoria="teljesitmeny",
    ),
    "otszaz_pont": Erem(
        id="otszaz_pont",
        nev="Pontgyűjtő",
        leiras="Összesen 500 pontot gyűjtöttél.",
        ikon="💎",
        kategoria="teljesitmeny",
    ),
    "esti_tanulas": Erem(
        id="esti_tanulas",
        nev="Éjjeli bagoly",
        leiras="22:00 után oldottál meg feladatot.",
        ikon="🦉",
        kategoria="rendszeresseg",
        ismetelheto=True,
    ),

    # ── Kitartás ──────────────────────────────────────────────────────────────
    "visszatero": Erem(
        id="visszatero",
        nev="Visszatérő",
        leiras="Legalább 3 különböző napon játszottál összesen.",
        ikon="🔄",
        kategoria="kitartas",
    ),
    "visszatero_tiz": Erem(
        id="visszatero_tiz",
        nev="Hűséges tanuló",
        leiras="Legalább 10 különböző napon játszottál.",
        ikon="🏅",
        kategoria="kitartas",
    ),
    "maraton": Erem(
        id="maraton",
        nev="Maraton",
        leiras="Egy menetben 30 vagy több feladatot teljesítettél.",
        ikon="🏃",
        kategoria="kitartas",
    ),

    # ── Ideiglenes (temporary streak shields) ────────────────────────────────
    "heti_bajnok": Erem(
        id="heti_bajnok",
        nev="Heti bajnok",
        leiras="Ezen a héten legalább 5 napot játszottál – csak a hétig érvényes!",
        ikon="🥇",
        kategoria="rendszeresseg",
        ideiglenes=True,
        ervenyes_napig=7,
        ismetelheto=True,
    ),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SZINTEK_OSSZ = {"4 osztályos", "6 osztályos", "8 osztályos"}
_FELADAT_TIPUSOK_OSSZ = {"nyilt_valasz", "tobbvalasztos", "parositas", "igaz_hamis", "fogalmazas", "kitoltes"}


def _nap(dt: datetime) -> datetime:
    """Truncate to calendar date (UTC)."""
    d = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _sim_now() -> datetime:
    """Return the simulation reference time, or actual now."""
    t = _simulation_as_of.get()
    return t if t is not None else datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _cooldown_elapsed(erem_id: str, last_award_at: datetime, now: datetime) -> bool:
    hours = _REPEATABLE_COOLDOWN_HOURS.get(erem_id, _REPEATABLE_COOLDOWN_DEFAULT_HOURS)
    return now >= (_as_utc(last_award_at) + timedelta(hours=hours))


def _has_new_attempt_after(user: str, engine: Engine, since: datetime, *, hour_cmp: str | None = None, hour_val: int | None = None, require_fast_correct: bool = False) -> bool:
    from felvi_games.db import MegoldasRecord

    since_utc = _as_utc(since)
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (
            select(func.count()).select_from(MegoldasRecord)
            .where(
                MegoldasRecord.felhasznalo_nev == user,
                MegoldasRecord.created_at > since_utc,
            )
        )
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        if require_fast_correct:
            stmt = stmt.where(
                MegoldasRecord.helyes.is_(True),
                MegoldasRecord.elapsed_sec.is_not(None),
                MegoldasRecord.elapsed_sec <= 10.0,
            )
        if hour_cmp is not None and hour_val is not None:
            hh = f"{hour_val:02d}"
            local_h = func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime"))
            if hour_cmp == "lt":
                stmt = stmt.where(local_h < hh)
            elif hour_cmp == "ge":
                stmt = stmt.where(local_h >= hh)
        return (s.scalar(stmt) or 0) > 0


def _has_new_activity_after(user: str, engine: Engine, since: datetime) -> bool:
    from felvi_games.db import InterakcioRecord, MegoldasRecord, MenetRecord

    since_utc = _as_utc(since)
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        m_stmt = (
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at > since_utc)
        )
        n_stmt = (
            select(func.count()).select_from(MenetRecord)
            .where(MenetRecord.felhasznalo_nev == user, MenetRecord.started_at > since_utc)
        )
        i_stmt = (
            select(func.count()).select_from(InterakcioRecord)
            .where(InterakcioRecord.felhasznalo_nev == user, InterakcioRecord.created_at > since_utc)
        )
        if _as_of is not None:
            m_stmt = m_stmt.where(MegoldasRecord.created_at <= _as_of)
            n_stmt = n_stmt.where(MenetRecord.started_at <= _as_of)
            i_stmt = i_stmt.where(InterakcioRecord.created_at <= _as_of)
        return (s.scalar(m_stmt) or 0) > 0 or (s.scalar(n_stmt) or 0) > 0 or (s.scalar(i_stmt) or 0) > 0


def _repeatable_has_fresh_signal(erem_id: str, user: str, engine: Engine, last_award_at: datetime) -> bool:
    if erem_id == "villam":
        return _has_new_attempt_after(user, engine, last_award_at, require_fast_correct=True)
    if erem_id == "reggeli_tanulas":
        return _has_new_attempt_after(user, engine, last_award_at, hour_cmp="lt", hour_val=8)
    if erem_id == "esti_tanulas":
        return _has_new_attempt_after(user, engine, last_award_at, hour_cmp="ge", hour_val=22)
    return _has_new_activity_after(user, engine, last_award_at)


def _distinct_play_days(session: Session, user: str, from_dt: datetime | None = None) -> list[datetime]:
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    stmt = (
        select(MenetRecord.started_at)
        .where(MenetRecord.felhasznalo_nev == user)
        .order_by(MenetRecord.started_at)
    )
    if from_dt:
        stmt = stmt.where(MenetRecord.started_at >= from_dt)
    if _as_of is not None:
        stmt = stmt.where(MenetRecord.started_at <= _as_of)
    rows = session.scalars(stmt).all()
    seen: set[str] = set()
    days: list[datetime] = []
    for dt in rows:
        key = _nap(dt).strftime("%Y-%m-%d")
        if key not in seen:
            seen.add(key)
            days.append(_nap(dt))
    return sorted(days)


def _consecutive_days(days: list[datetime]) -> int:
    """Return the longest streak of consecutive calendar days."""
    if not days:
        return 0
    best = current = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _current_streak(days: list[datetime]) -> int:
    """Days in the current trailing streak (must include today or yesterday)."""
    if not days:
        return 0
    today = _nap(datetime.now(timezone.utc))
    streak = 0
    prev = today
    for d in reversed(days):
        if (prev - d).days <= 1:
            streak += 1
            prev = d
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# Rules
# (Each rule is: rule_fn(user, session_id, engine) → bool)
# ---------------------------------------------------------------------------

def _rule_elso_menet(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MenetRecord)
                .where(MenetRecord.felhasznalo_nev == user,
                       MenetRecord.ended_at.is_not(None)))
        if _as_of is not None:
            stmt = stmt.where(MenetRecord.ended_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 1


def _rule_szaz_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 100


def _rule_otszaz_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 500


def _rule_ezer_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 1000


def _rule_tokeletes_menet(user: str, session_id: int | None, engine: Engine) -> bool:
    """True when the current session completed all tasks fully correctly."""
    from felvi_games.db import MegoldasRecord, MenetRecord
    if session_id is None:
        return False
    with Session(engine) as s:
        rec = s.get(MenetRecord, session_id)
        if rec is None or rec.feladat_limit <= 0 or rec.megoldott < rec.feladat_limit:
            return False
        total = s.scalar(
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.menet_id == session_id)
        ) or 0
        helyes_cnt = s.scalar(
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.menet_id == session_id,
                   MegoldasRecord.helyes == True)  # noqa: E712
        ) or 0
    return total > 0 and total == helyes_cnt == rec.feladat_limit


def _rule_sorozat_5(user: str, session_id: int | None, engine: Engine) -> bool:
    return _max_helyes_sorozat(user, engine) >= 5


def _rule_sorozat_10(user: str, session_id: int | None, engine: Engine) -> bool:
    return _max_helyes_sorozat(user, engine) >= 10


def _rule_sorozat_20(user: str, session_id: int | None, engine: Engine) -> bool:
    return _max_helyes_sorozat(user, engine) >= 20


def _max_helyes_sorozat(user: str, engine: Engine) -> int:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (
            select(MegoldasRecord.helyes)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        )
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    best = cur = 0
    for h in rows:
        if h:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _rule_villam(user: str, session_id: int | None, engine: Engine) -> bool:
    """Any answer that scored points (including partial) within 10 seconds."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MegoldasRecord.pont > 0,
                       MegoldasRecord.elapsed_sec.is_not(None),
                       MegoldasRecord.elapsed_sec <= 10.0))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 1


def _rule_hint_nelkul_20(user: str, session_id: int | None, engine: Engine) -> bool:
    """Last 20 answers (any outcome) without asking for a hint."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(MegoldasRecord.segitseg_kert)
                .where(MegoldasRecord.felhasznalo_nev == user)
                .order_by(MegoldasRecord.created_at.desc())
                .limit(20))
        if _as_of is not None:
            stmt = (select(MegoldasRecord.segitseg_kert)
                    .where(MegoldasRecord.felhasznalo_nev == user,
                           MegoldasRecord.created_at <= _as_of)
                    .order_by(MegoldasRecord.created_at.desc())
                    .limit(20))
        rows = s.scalars(stmt).all()
    return len(rows) == 20 and not any(rows)


def _rule_magas_pontossag(user: str, session_id: int | None, engine: Engine) -> bool:
    """At least 80% of total possible points earned across 50+ attempts."""
    from felvi_games.db import FeladatRecord, MegoldasRecord
    _as_of = _simulation_as_of.get()
    _f = [MegoldasRecord.felhasznalo_nev == user]
    if _as_of is not None:
        _f.append(MegoldasRecord.created_at <= _as_of)
    with Session(engine) as s:
        total = s.scalar(
            select(func.count()).select_from(MegoldasRecord).where(*_f)
        ) or 0
        if total < 50:
            return False
        earned = s.scalar(
            select(func.sum(MegoldasRecord.pont)).where(*_f)
        ) or 0
        max_possible = s.scalar(
            select(func.sum(FeladatRecord.max_pont))
            .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
            .where(*_f)
        ) or 0
    return max_possible > 0 and (earned / max_possible) >= 0.80


def _rule_het_egymas_utan(user: str, session_id: int | None, engine: Engine) -> bool:
    with Session(engine) as s:
        days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
    return _current_streak(days) >= 7


def _rule_harom_het_egymas_utan(user: str, session_id: int | None, engine: Engine) -> bool:
    with Session(engine) as s:
        days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
    return _consecutive_days(days) >= 21


def _rule_pentek_matek_honap(user: str, session_id: int | None, engine: Engine) -> bool:
    """All Fridays of the *previous* calendar month were covered with matek sessions."""
    from felvi_games.db import MenetRecord
    now = datetime.now(timezone.utc)
    # previous month
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev = first_this - timedelta(seconds=1)
    first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # find all Fridays in that month
    fridays: set[str] = set()
    d = first_prev
    while d <= last_prev:
        if d.weekday() == 4:  # Friday
            fridays.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    if not fridays:
        return False

    with Session(engine) as s:
        rows = s.scalars(
            select(MenetRecord.started_at)
            .where(
                MenetRecord.felhasznalo_nev == user,
                MenetRecord.targy == "matek",
                MenetRecord.started_at >= first_prev,
                MenetRecord.started_at <= last_prev,
            )
        ).all()

    played_fridays = {_nap(dt).strftime("%Y-%m-%d") for dt in rows if _nap(dt).weekday() == 4}
    return fridays.issubset(played_fridays)


def _rule_heti_haromszor(user: str, session_id: int | None, engine: Engine) -> bool:
    """At least 3 distinct days in the most recent 7-day window."""
    with Session(engine) as s:
        cutoff = _sim_now() - timedelta(days=7)
        days = _distinct_play_days(s, user, from_dt=cutoff)
    return len(days) >= 3


def _rule_reggeli_tanulas(user: str, session_id: int | None, engine: Engine) -> bool:
    """Any answer submitted before 08:00 local time (timestamps stored as UTC)."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(MegoldasRecord.created_at)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) < "08"))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    return len(rows) > 0


def _rule_mindket_targy(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = select(MenetRecord.targy).where(MenetRecord.felhasznalo_nev == user)
        if _as_of is not None:
            stmt = stmt.where(MenetRecord.started_at <= _as_of)
        targyek = set(s.scalars(stmt).all())
    return {"matek", "magyar"}.issubset(targyek)


def _rule_minden_szint(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = select(MenetRecord.szint).where(MenetRecord.felhasznalo_nev == user)
        if _as_of is not None:
            stmt = stmt.where(MenetRecord.started_at <= _as_of)
        szintek = set(s.scalars(stmt).all())
    return _SZINTEK_OSSZ.issubset(szintek)


def _rule_minden_feladattipus(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import FeladatRecord, MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(FeladatRecord.feladat_tipus)
                .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    return _FELADAT_TIPUSOK_OSSZ.issubset({r for r in rows if r})


def _rule_visszatero(user: str, session_id: int | None, engine: Engine) -> bool:
    with Session(engine) as s:
        days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
    return len(days) >= 3


def _rule_maraton(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MenetRecord
    if session_id is None:
        return False
    with Session(engine) as s:
        rec = s.get(MenetRecord, session_id)
        if rec is None:
            return False
        return rec.feladat_limit >= 30 and rec.megoldott >= 30


def _rule_tiz_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 10


def _rule_huszonot_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 25


def _rule_otven_feladat(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 50


def _rule_szaz_pont(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.sum(MegoldasRecord.pont))
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        total = s.scalar(stmt) or 0
    return total >= 100


def _rule_otszaz_pont(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.sum(MegoldasRecord.pont))
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        total = s.scalar(stmt) or 0
    return total >= 500


def _rule_esti_tanulas(user: str, session_id: int | None, engine: Engine) -> bool:
    """Any answer submitted at or after 22:00 local time (timestamps stored as UTC)."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(MegoldasRecord.created_at)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) >= "22"))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    return len(rows) > 0


def _rule_visszatero_tiz(user: str, session_id: int | None, engine: Engine) -> bool:
    with Session(engine) as s:
        days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
    return len(days) >= 10


def _rule_heti_bajnok(user: str, session_id: int | None, engine: Engine) -> bool:
    """5+ distinct play days in the current week (Mon–Sun)."""
    now = _sim_now()
    start_of_week = _nap(now) - timedelta(days=now.weekday())
    with Session(engine) as s:
        days = _distinct_play_days(s, user, from_dt=start_of_week)  # upper bound via _simulation_as_of
    return len(days) >= 5


# ---------------------------------------------------------------------------
# Dynamic condition evaluator
# Evaluates LLM-generated structured conditions stored in Erem.condition.
#
# Supported condition types:
#   feladat_count        – solve N tasks within window_hours
#   helyes_count         – N correct answers within window_hours
#   pont_sum             – earn N total points within window_hours
#   streak               – N consecutive correct answers (all-time best)
#   session_count        – start N sessions within window_hours
#   tokeletes_session    – complete a perfect session within window_hours
#   feladat_subject      – N tasks of given subject within window_hours
#   before_hour          – N answers submitted before hour H within window_hours
#   after_hour           – N answers submitted at or after hour H within window_hours
#   special_date         – feladat_count tasks on a specific date MM-DD
#   interakcio_count     – N interaction events of a given type within window_hours
#   interakcio_exists    – at least one interaction event of a given type within window_hours
# ---------------------------------------------------------------------------

def _eval_dynamic_condition(
    user: str,
    condition: dict,
    engine: Engine,
    valid_from: datetime | None = None,
) -> bool:
    """Evaluate a dynamic (LLM-generated) medal condition. Returns bool.

    ``valid_from``: when set (e.g. erem.created_at), only events AFTER that
    timestamp are counted.  This is the correct anchor for saved dynamic medals
    so that a condition cannot already be satisfied at creation time.
    If None, falls back to the legacy ``now - window_hours`` rolling window.
    """
    from felvi_games.db import InterakcioRecord, MegoldasRecord, MenetRecord

    ctype = condition.get("type", "")
    n = int(condition.get("n", 1))
    window_h = float(condition.get("window_hours", 24))
    # If an explicit start anchor is provided, count only events AFTER that
    # timestamp; otherwise fall back to a rolling window from now.
    if valid_from is not None:
        cutoff = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=timezone.utc)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_h)

    # Simulation upper-bound: when replaying history, don't count future events
    _as_of = _simulation_as_of.get()
    upper = _as_of if _as_of is not None else None

    with Session(engine) as s:
        if ctype == "feladat_count":
            stmt = (select(func.count()).select_from(MegoldasRecord)
                    .where(MegoldasRecord.felhasznalo_nev == user,
                           MegoldasRecord.created_at >= cutoff))
            if upper is not None:
                stmt = stmt.where(MegoldasRecord.created_at <= upper)
            cnt = s.scalar(stmt) or 0
            return cnt >= n

        elif ctype == "helyes_count":
            stmt = (select(func.count()).select_from(MegoldasRecord)
                    .where(MegoldasRecord.felhasznalo_nev == user,
                           MegoldasRecord.helyes == True,  # noqa: E712
                           MegoldasRecord.created_at >= cutoff))
            if upper is not None:
                stmt = stmt.where(MegoldasRecord.created_at <= upper)
            cnt = s.scalar(stmt) or 0
            return cnt >= n

        elif ctype == "pont_sum":
            stmt = (select(func.sum(MegoldasRecord.pont))
                    .where(MegoldasRecord.felhasznalo_nev == user,
                           MegoldasRecord.created_at >= cutoff))
            if upper is not None:
                stmt = stmt.where(MegoldasRecord.created_at <= upper)
            total = s.scalar(stmt) or 0
            return total >= n

        elif ctype == "streak":
            stmt = (select(MegoldasRecord.helyes)
                    .where(MegoldasRecord.felhasznalo_nev == user)
                    .order_by(MegoldasRecord.created_at))
            if upper is not None:
                stmt = stmt.where(MegoldasRecord.created_at <= upper)
            rows = s.scalars(stmt).all()
            best = cur = 0
            for h in rows:
                if h:
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 0
            return best >= n

        elif ctype == "session_count":
            stmt = (select(func.count()).select_from(MenetRecord)
                    .where(MenetRecord.felhasznalo_nev == user,
                           MenetRecord.started_at >= cutoff))
            if upper is not None:
                stmt = stmt.where(MenetRecord.started_at <= upper)
            cnt = s.scalar(stmt) or 0
            return cnt >= n

        elif ctype == "tokeletes_session":
            from felvi_games.db import MenetRecord as MR
            menet_ids = list(s.scalars(
                select(MR.id)
                .where(MR.felhasznalo_nev == user,
                       MR.ended_at.is_not(None),
                       MR.started_at >= cutoff)
            ).all())
            for mid in menet_ids:
                rec = s.get(MR, mid)
                if rec is None or rec.feladat_limit <= 0 or rec.megoldott < rec.feladat_limit:
                    continue
                total = s.scalar(
                    select(func.count()).select_from(MegoldasRecord)
                    .where(MegoldasRecord.menet_id == mid)
                ) or 0
                helyes_cnt = s.scalar(
                    select(func.count()).select_from(MegoldasRecord)
                    .where(MegoldasRecord.menet_id == mid,
                           MegoldasRecord.helyes == True)  # noqa: E712
                ) or 0
                if total > 0 and total == helyes_cnt == rec.feladat_limit:
                    return True
            return False

        elif ctype == "feladat_subject":
            subject = condition.get("subject", "")
            from felvi_games.db import MenetRecord as MR
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .join(MR, MR.id == MegoldasRecord.menet_id)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MR.targy == subject,
                       MegoldasRecord.created_at >= cutoff)
            ) or 0
            return cnt >= n

        elif ctype == "before_hour":
            hour = int(condition.get("hour", 8))
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(
                    MegoldasRecord.felhasznalo_nev == user,
                    MegoldasRecord.created_at >= cutoff,
                    func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) < f"{hour:02d}",
                )
            ) or 0
            return cnt >= n

        elif ctype == "after_hour":
            hour = int(condition.get("hour", 22))
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(
                    MegoldasRecord.felhasznalo_nev == user,
                    MegoldasRecord.created_at >= cutoff,
                    func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) >= f"{hour:02d}",
                )
            ) or 0
            return cnt >= n

        elif ctype == "special_date":
            date_mmdd = condition.get("date", "")  # e.g. "05-01"
            feladat_n = int(condition.get("feladat_count", 1))
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(
                    MegoldasRecord.felhasznalo_nev == user,
                    func.strftime("%m-%d", MegoldasRecord.created_at) == date_mmdd,
                )
            ) or 0
            return cnt >= feladat_n

        elif ctype in {"interakcio_count", "interakcio_exists"}:
            raw_event_type = condition.get("event_type", "")
            if isinstance(raw_event_type, InterakcioTipus):
                event_type = raw_event_type.value
            else:
                event_type = str(raw_event_type).strip()
            if not event_type:
                return False

            stmt = (
                select(func.count()).select_from(InterakcioRecord)
                .where(
                    InterakcioRecord.felhasznalo_nev == user,
                    InterakcioRecord.tipus == event_type,
                    InterakcioRecord.created_at >= cutoff,
                )
            )
            if upper is not None:
                stmt = stmt.where(InterakcioRecord.created_at <= upper)

            targy = condition.get("targy")
            if isinstance(targy, str) and targy.strip():
                stmt = stmt.where(InterakcioRecord.targy == targy.strip())

            szint = condition.get("szint")
            if isinstance(szint, str) and szint.strip():
                stmt = stmt.where(InterakcioRecord.szint == szint.strip())

            feladat_id = condition.get("feladat_id")
            if isinstance(feladat_id, str) and feladat_id.strip():
                stmt = stmt.where(InterakcioRecord.feladat_id == feladat_id.strip())

            meta_contains = condition.get("meta_contains")
            if isinstance(meta_contains, str) and meta_contains.strip():
                stmt = stmt.where(InterakcioRecord.meta.contains(meta_contains.strip()))

            cnt = s.scalar(stmt) or 0
            if ctype == "interakcio_exists":
                return cnt >= 1
            return cnt >= n

    return False


def _count_dynamic_condition(
    user: str,
    condition: dict,
    engine: Engine,
    valid_from: datetime | None = None,
) -> tuple[int | None, int | None]:
    """Return (current_value, target_n) for progress display.

    Returns (None, None) for condition types where a scalar count doesn't
    make sense (e.g. tokeletes_session, special_date).
    """
    from felvi_games.db import InterakcioRecord, MegoldasRecord, MenetRecord

    ctype = condition.get("type", "")
    n = int(condition.get("n", 1))
    window_h = float(condition.get("window_hours", 24))
    if valid_from is not None:
        cutoff = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=timezone.utc)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_h)

    with Session(engine) as s:
        if ctype == "feladat_count":
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MegoldasRecord.created_at >= cutoff)
            ) or 0
            return cnt, n

        elif ctype == "feladat_subject":
            subject = condition.get("subject", "")
            from felvi_games.db import MenetRecord as MR
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .join(MR, MR.id == MegoldasRecord.menet_id)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MR.targy == subject,
                       MegoldasRecord.created_at >= cutoff)
            ) or 0
            return cnt, n

        elif ctype == "before_hour":
            hour = int(condition.get("hour", 8))
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MegoldasRecord.created_at >= cutoff,
                       func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) < f"{hour:02d}")
            ) or 0
            return cnt, n

        elif ctype == "after_hour":
            hour = int(condition.get("hour", 22))
            cnt = s.scalar(
                select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MegoldasRecord.created_at >= cutoff,
                       func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) >= f"{hour:02d}")
            ) or 0
            return cnt, n

        elif ctype == "session_count":
            cnt = s.scalar(
                select(func.count()).select_from(MenetRecord)
                .where(MenetRecord.felhasznalo_nev == user,
                       MenetRecord.started_at >= cutoff)
            ) or 0
            return cnt, n

        elif ctype in {"interakcio_count", "interakcio_exists"}:
            raw_event_type = condition.get("event_type", "")
            event_type = raw_event_type.value if isinstance(raw_event_type, InterakcioTipus) else str(raw_event_type).strip()
            target = 1 if ctype == "interakcio_exists" else n
            if not event_type:
                return None, None
            cnt = s.scalar(
                select(func.count()).select_from(InterakcioRecord)
                .where(InterakcioRecord.felhasznalo_nev == user,
                       InterakcioRecord.tipus == event_type,
                       InterakcioRecord.created_at >= cutoff)
            ) or 0
            return cnt, target

    return None, None


# ---------------------------------------------------------------------------
# Rule registry
# Each entry: (rule_fn, permanent_only=False|True)
# permanent_only=True  → only award once; never re-check once earned
# repeatable medals    → use Erem.ismetelheto flag
# ---------------------------------------------------------------------------

RuleFn = Callable[[str, int | None, "Engine"], bool]

SZABALY_REGISTRY: dict[str, RuleFn] = {
    "elso_menet": _rule_elso_menet,
    "tiz_feladat": _rule_tiz_feladat,
    "huszonot_feladat": _rule_huszonot_feladat,
    "otven_feladat": _rule_otven_feladat,
    "szaz_feladat": _rule_szaz_feladat,
    "otszaz_feladat": _rule_otszaz_feladat,
    "ezer_feladat": _rule_ezer_feladat,
    "tokeletes_menet": _rule_tokeletes_menet,
    "sorozat_5": _rule_sorozat_5,
    "sorozat_10": _rule_sorozat_10,
    "sorozat_20": _rule_sorozat_20,
    "villam": _rule_villam,
    "hint_nelkul_20": _rule_hint_nelkul_20,
    "magas_pontossag": _rule_magas_pontossag,
    "het_egymas_utan": _rule_het_egymas_utan,
    "harom_het_egymas_utan": _rule_harom_het_egymas_utan,
    "pentek_matek_honap": _rule_pentek_matek_honap,
    "heti_haromszor": _rule_heti_haromszor,
    "reggeli_tanulas": _rule_reggeli_tanulas,
    "esti_tanulas": _rule_esti_tanulas,
    "mindket_targy": _rule_mindket_targy,
    "minden_szint": _rule_minden_szint,
    "minden_feladattipus": _rule_minden_feladattipus,
    "visszatero": _rule_visszatero,
    "visszatero_tiz": _rule_visszatero_tiz,
    "maraton": _rule_maraton,
    "szaz_pont": _rule_szaz_pont,
    "otszaz_pont": _rule_otszaz_pont,
    "heti_bajnok": _rule_heti_bajnok,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_new_medals(
    user: str,
    session_id: int | None,
    repo: FeladatRepository,
) -> list[Erem]:
    """Evaluate all rules and grant any newly earned medals.

    Loads the catalog from DB (global medals + private medals targeted at
    *user*) so new medals can be added mid-game without a restart.
    Returns the list of Erem objects that were freshly awarded this call.
    """
    engine = repo._engine
    newly_earned: list[Erem] = []
    now = _sim_now()

    catalog = repo.get_erem_katalogus(user)
    earned_any_ids = {fe.erem_id for fe in repo.get_eremek(user, include_expired=True)}
    szerzes_map = repo.get_erem_szerzesek_map(user)
    latest_award_by_id = {
        erem_id: _as_utc(stamps[0])
        for erem_id, stamps in szerzes_map.items()
        if stamps
    }

    logger.info(
        "check_new_medals start | user=%s session=%s catalog_size=%d",
        user, session_id, len(catalog),
    )

    skipped_already_has = 0
    skipped_cooldown = 0
    skipped_no_new_signal = 0
    skipped_no_rule = 0
    rule_errors: list[str] = []

    for erem_id, erem in catalog.items():
        last_award_at = latest_award_by_id.get(erem_id)

        # Non-repeatable + already earned → skip
        if not erem.ismetelheto and erem_id in earned_any_ids:
            skipped_already_has += 1
            logger.debug("skip already_earned | user=%s medal=%s", user, erem_id)
            continue

        # Repeatable medals need a cooldown so historical truth does not re-fire instantly.
        if erem.ismetelheto and last_award_at is not None and not _cooldown_elapsed(erem_id, last_award_at, now):
            skipped_cooldown += 1
            logger.debug(
                "skip cooldown | user=%s medal=%s last_award=%s now=%s",
                user,
                erem_id,
                last_award_at.isoformat(),
                now.isoformat(),
            )
            continue

        # No rule registered → check for dynamic condition, else manual-grant only
        rule_fn = SZABALY_REGISTRY.get(erem_id)
        if rule_fn is None:
            if erem.condition:
                # Dynamic LLM-generated condition: use creation timestamp as anchor
                # so only events AFTER the medal was created count towards the goal.
                try:
                    earned = _eval_dynamic_condition(
                        user, erem.condition, engine,
                        valid_from=erem.condition_valid_from,
                    )
                except Exception as exc:  # noqa: BLE001
                    rule_errors.append(erem_id)
                    logger.warning(
                        "dynamic_rule_error | user=%s medal=%s error=%s",
                        user, erem_id, exc, exc_info=True,
                    )
                    continue
            else:
                skipped_no_rule += 1
                logger.debug("skip no_rule | user=%s medal=%s", user, erem_id)
                continue
        else:
            try:
                earned = rule_fn(user, session_id, engine)
            except Exception as exc:  # noqa: BLE001 – rules must not crash the game
                rule_errors.append(erem_id)
                logger.warning(
                    "rule_error | user=%s medal=%s error=%s",
                    user, erem_id, exc, exc_info=True,
                )
                continue

        logger.debug(
            "rule_result | user=%s medal=%s session=%s result=%s",
            user, erem_id, session_id, earned,
        )

        if earned:
            if erem.ismetelheto and last_award_at is not None:
                if erem.condition:
                    cond_anchor = erem.condition_valid_from
                    cond_anchor_utc = _as_utc(cond_anchor) if cond_anchor is not None else None
                    from_anchor = last_award_at + timedelta(microseconds=1)
                    if cond_anchor_utc is not None and cond_anchor_utc > from_anchor:
                        from_anchor = cond_anchor_utc
                    try:
                        fresh_signal = _eval_dynamic_condition(
                            user,
                            erem.condition,
                            engine,
                            valid_from=from_anchor,
                        )
                    except Exception:
                        fresh_signal = False
                else:
                    fresh_signal = _repeatable_has_fresh_signal(erem_id, user, engine, last_award_at)

                if not fresh_signal:
                    skipped_no_new_signal += 1
                    logger.debug(
                        "skip no_new_signal | user=%s medal=%s last_award=%s",
                        user,
                        erem_id,
                        last_award_at.isoformat(),
                    )
                    continue

            expires_at: datetime | None = None
            # Expiry is only used for repeatable medals; one-time medals stay in history forever.
            if erem.ideiglenes and erem.ismetelheto and erem.ervenyes_napig:
                expires_at = now + timedelta(days=erem.ervenyes_napig)
            repo.grant_erem(user, erem_id, lejarat_at=expires_at)
            newly_earned.append(erem)
            logger.info(
                "medal_granted | user=%s medal=%s nev=%r session=%s expires=%s",
                user, erem_id, erem.nev, session_id,
                expires_at.isoformat() if expires_at else None,
            )

    logger.info(
        "check_new_medals done | user=%s session=%s granted=%d "
        "skipped_owned=%d skipped_cooldown=%d skipped_no_new_signal=%d "
        "skipped_no_rule=%d errors=%d",
        user, session_id, len(newly_earned),
        skipped_already_has, skipped_cooldown, skipped_no_new_signal,
        skipped_no_rule, len(rule_errors),
    )
    if rule_errors:
        logger.warning("rule_errors detail | user=%s medals=%s", user, rule_errors)

    return newly_earned


def get_all_medals_for_user(
    user: str,
    repo: FeladatRepository,
    include_expired: bool = False,
) -> list[tuple[Erem, FelhasznaloErem]]:
    """Return (catalog_entry, earned_record) pairs for a user.

    Catalog is loaded from DB so it reflects any runtime additions.
    """
    earned = repo.get_eremek(user, include_expired=include_expired)
    catalog = repo.get_erem_katalogus(user)
    result: list[tuple[Erem, FelhasznaloErem]] = []
    for fe in earned:
        erem = catalog.get(fe.erem_id)
        if erem is not None:
            result.append((erem, fe))
    return result


# ---------------------------------------------------------------------------
# Rule simulation (dry-run, no DB writes)
# ---------------------------------------------------------------------------


@_dataclass
class RuleSimResult:
    erem_id: str
    nev: str
    ikon: str
    result: bool
    already_earned: bool
    ismetelheto: bool
    error: str | None = None


def simulate_medal_rules(
    user: str,
    engine: Engine,
    earned_erem_ids: set[str],
) -> list[RuleSimResult]:
    """Evaluate every registered rule for *user* without awarding anything.

    Returns one RuleSimResult per registered rule (static) plus any dynamic
    medals in the catalog that have a condition but no registered rule.
    """
    results: list[RuleSimResult] = []

    # Static rules
    for erem_id, rule_fn in SZABALY_REGISTRY.items():
        erem = EREM_KATALOGUS.get(erem_id)
        nev = erem.nev if erem else erem_id
        ikon = erem.ikon if erem else "🏅"
        ismetelheto = erem.ismetelheto if erem else False
        try:
            rule_result = rule_fn(user, None, engine)
            error = None
        except Exception as exc:
            rule_result = False
            error = str(exc)
        results.append(RuleSimResult(
            erem_id=erem_id,
            nev=nev,
            ikon=ikon,
            result=bool(rule_result),
            already_earned=erem_id in earned_erem_ids,
            ismetelheto=ismetelheto,
            error=error,
        ))

    # Dynamic medals (not in static registry but have a condition)
    for erem_id, erem in EREM_KATALOGUS.items():
        if erem_id in SZABALY_REGISTRY:
            continue
        if not erem.condition:
            continue
        try:
            rule_result = _eval_dynamic_condition(user, erem.condition, engine)
            error = None
        except Exception as exc:
            rule_result = False
            error = str(exc)
        results.append(RuleSimResult(
            erem_id=erem_id,
            nev=erem.nev,
            ikon=erem.ikon,
            result=bool(rule_result),
            already_earned=erem_id in earned_erem_ids,
            ismetelheto=erem.ismetelheto,
            error=error,
        ))

    return results
