"""OpenAI wrapper: TTS, STT, and answer evaluation."""

from __future__ import annotations

import json
import os
import tempfile

from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from felvi_games.models import Ertekeles

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

_client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
)
MODEL = os.getenv("LLM_MODEL", "gpt-4o")
_CHEAP_MODEL = os.getenv("LLM_CHEAP_MODEL", "gpt-4o")

_TTS_PREP_SYSTEM = (
    "You are a TTS normalization assistant for Hungarian school exam content. "
    "Your ONLY task is to rewrite the provided markdown/math text into naturally speakable Hungarian. "
    "Do not solve, explain, evaluate, simplify, or add extra educational commentary. "
    "Preserve the original meaning exactly. "
    "Rules: "
    "1) Output language must be Hungarian. "
    "2) Remove markdown formatting (**, *, #, backticks, links), but keep all information content. "
    "3) Convert LaTeX/math/symbols into spoken Hungarian forms. "
    "4) Keep proper nouns, abbreviations, labels, and identifiers unless pronunciation needs tiny spacing. "
    "5) Rewrite bullet lists/tables into fluent sentences without losing items. "
    "6) Convert operators and symbols to words (>=, <=, !=, %, /, +, -, ^, sqrt, sum, etc.). "
    "7) If an expression is ambiguous, keep it faithful rather than guessing intent. "
    "8) Return ONLY the transformed read-aloud text. No prefixes like 'Output:' or notes. "
    "Example expectation: "
    "Input: 'Oldd meg: $\\frac{a}{b} \\ge 3$. **Válaszlehetőségek:** A) 1 B) 2 C) 3' "
    "Output: 'Oldd meg: a per b nagyobb vagy egyenlő három. Válaszlehetőségek: A, egyes. B, kettes. C, hármas.'"
)

_EVAL_SYSTEM = (
    "Magyar felvételi kvíz értékelő vagy. "
    "Röviden (max 2 mondat), buzdítóan értékeld a tanuló válaszát."
)

_EVAL_TEMPLATE = """\
Feladat: {kerdes}
Helyes válasz: {helyes}
{elfogadott_sor}
{tipus_sor}
Tanuló válasza: {adott}
Magyarázat: {magyarazat}
Max. pontszám: {max_pont}
{reszpontozas_sor}

Értékeld a választ, majd adj vissza CSAK egy JSON objektumot:
{{"visszajelzes": "...", "pont": 0-{max_pont}}}

Megjegyzés: ha az elfogadott válaszok listája nem üres, akkor az adott választ
azokhoz kell hasonlítani (szinonimákat és eltolódásokat is fogadj el).
Igaz/hamis feladatnál csak "igaz" vagy "hamis" szó elfogadható.
Párosítás- és halmaz-típusú feladatoknál (ahol a helyes válasz több elem
kombinációja) az elemek sorrendje ne számítson; részleges egyezésnél adj
részletes visszajelzést arról, mely elemek helyesek.
Ha van részpontozási szabály (lásd fent), alkalmazd pontosan: számítsd ki a
pontot a szabály szerint."""


def text_to_speech(szoveg: str) -> bytes:
    """TTS – visszatér nyers MP3 byte-okkal."""
    response = _client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=szoveg,
    )
    return response.content


def speech_to_text(audio_bytes: bytes) -> str:
    """Whisper STT – visszatér az átírt szöveggel."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            transcript = _client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="hu",
            )
        return transcript.text
    finally:
        os.unlink(tmp_path)


def kerdes_to_tts_szoveg(kerdes_markdown: str) -> str:
    """Convert a markdown question text into natural spoken Hungarian for TTS.

    Uses a cost-efficient model (_CHEAP_MODEL) since this is a simple
    text-transformation task.
    """
    response = _client.chat.completions.create(
        model=_CHEAP_MODEL,
        messages=[
            {"role": "system", "content": _TTS_PREP_SYSTEM},
            {"role": "user", "content": 
             f"""
---
Input:
{kerdes_markdown}
---
Output:
             """
             },
        ],
        temperature=0,
        max_tokens=512,
    )
    return (response.choices[0].message.content or "").strip()


def check_answer(
    kerdes: str,
    helyes: str,
    adott: str,
    magyarazat: str,
    *,
    elfogadott_valaszok: list[str] | None = None,
    feladat_tipus: str | None = None,
    max_pont: int = 1,
    reszpontozas: str | None = None,
) -> Ertekeles:
    """GPT értékeli a választ. Visszatér egy `Ertekeles` példánnyal."""
    elfogadott_sor = (
        f"Elfogadott válaszok: {', '.join(elfogadott_valaszok)}"
        if elfogadott_valaszok
        else ""
    )
    tipus_sor = f"Feladat típusa: {feladat_tipus}" if feladat_tipus else ""
    reszpontozas_sor = f"Részpontozási szabály: {reszpontozas}" if reszpontozas else ""
    prompt = _EVAL_TEMPLATE.format(
        kerdes=kerdes,
        helyes=helyes,
        elfogadott_sor=elfogadott_sor,
        tipus_sor=tipus_sor,
        reszpontozas_sor=reszpontozas_sor,
        adott=adott,
        magyarazat=magyarazat,
        max_pont=max_pont,
    )
    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _EVAL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        ert = Ertekeles.from_dict(json.loads(response.choices[0].message.content))
        # Clamp point to valid range; derive helyes from score (GPT no longer returns it)
        clamped = max(0, min(ert.pont, max_pont))
        return Ertekeles(helyes=(clamped == max_pont), visszajelzes=ert.visszajelzes, pont=clamped)
    except Exception:
        return Ertekeles.hiba()


# ---------------------------------------------------------------------------
# Medal asset generation
# ---------------------------------------------------------------------------

_MEDAL_IMAGE_PROMPT = (
    "A vibrant, highly detailed digital award medal for a children's educational game. "
    "The medal should look like a collectible achievement badge: circular, gold/silver metallic rim, "
    "colorful center, with the following theme: {tema}. "
    "Style: colorful flat vector illustration, bold outlines, celebratory feel. "
    "No text on the medal. Transparent or white background. Square canvas."
)

_MEDAL_HANG_TEMPLATE = (
    "Gratulálunk! Megszerezted a(z) {nev} érmet! {leiras}"
)


def generate_medal_image(nev: str, leiras: str, ikon: str) -> bytes:
    """Generate a PNG medal image with DALL-E 3.

    Returns raw PNG bytes (1024×1024).
    """
    tema = f"{nev} – {leiras} (symbol hint: {ikon})"
    prompt = _MEDAL_IMAGE_PROMPT.format(tema=tema)
    response = _client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        n=1,
        size="1024x1024",
        response_format="b64_json",
        quality="standard",
    )
    import base64
    b64 = response.data[0].b64_json
    return base64.b64decode(b64)


def generate_medal_hang(nev: str, leiras: str) -> bytes:
    """Generate an MP3 award announcement with TTS (Nova voice).

    Returns raw MP3 bytes.
    """
    szoveg = _MEDAL_HANG_TEMPLATE.format(nev=nev, leiras=leiras)
    return text_to_speech(szoveg)


# ---------------------------------------------------------------------------
# Daily insight (progress analysis + optional new medal suggestion)
# ---------------------------------------------------------------------------

_DAILY_INSIGHT_SYSTEM = (
    "Magyar felvételi kvíz coach vagy. "
    "A játékos napi belépésekor rövid, személyes motiváló üzenetet írsz, "
    "és esetleg javaslatot teszel egy egyedi időkorlátozott kihívás éremre. "
    "Mindig magyarul válaszolj. Légy lelkesítő, tömör (max 3 mondat az üzenetben)."
)

# Supported condition types for dynamic medals.
# IMPORTANT: n counts events AFTER the medal is created, not historical lookback.
_CONDITION_TYPES_DOC = """\
Feltétel típusok (gépileg kiértékelhető, n = esemény EZUTÁN az érem létrehozása után):
  feladat_count  – {"type":"feladat_count","n":5,"window_hours":12}
  helyes_count   – {"type":"helyes_count","n":3,"window_hours":8}
  pont_sum       – {"type":"pont_sum","n":20,"window_hours":18}
  session_count  – {"type":"session_count","n":2,"window_hours":6}
  tokeletes_session – {"type":"tokeletes_session","window_hours":18}
  feladat_subject – {"type":"feladat_subject","n":5,"subject":"matek","window_hours":12}
    before_hour    – {"type":"before_hour","hour":10,"n":5,"window_hours":12}
    after_hour     – {"type":"after_hour","hour":18,"n":5,"window_hours":12}

Szabályok:
- n és window_hours legyen reálisan elérhető a közelmúlt alapján.
- window_hours: 1–18 között (rövid kihívás).
- leiras: pl. "Oldj meg 5 feladatot 8 órán belül!"
- Ha a név/leírás reggeli jellegű (pl. "Reggeli"), használj `before_hour` típust.
- Ha a név/leírás esti jellegű (pl. "Esti"), használj `after_hour` típust.
- FONTOS: a feltétel az érem LÉTREHOZÁSA UTÁN teljesítendő, nem a múltban."""

_DAILY_INSIGHT_TEMPLATE = """\
Felhasználó: {user}  (most: {now_str})

Összesített statisztika:
  - Összes megoldott: {total_attempts}, helyes: {correct}, arány: {accuracy_pct}%
  - Lezárt menetek: {completed_sessions}, aktív napok (7d): {recent_days_7d}
  - Jelenlegi napi sorozat: {current_streak_days} nap
  - Legjobb helyes sorozat: {best_correct_streak}
  - Tárgyak: {subjects_used}
  - Megszerzett érmek: {earned_count}

Utolsó 7 nap (napi összesítő):
{daily_summary_text}

Interakciók (utolsó 24 óra):
{event_counts_24h_text}

Közel lévő érmek:
{close_medals_text}

{condition_types_doc}

Feladatod:
1. Írj egy rövid, személyre szabott motiváló üzenetet (greeting, max 2 mondat).
2. Javasolj egy privát kihívás érmet, amelyet a felhasználó a következő {window_hours} órán belül
   szerezhet meg HA az az elmúlt teljesítmény alapján reálisan elérhető.
   FONTOS: a feltételben lévő n az érem LÉTREHOZÁSA UTÁNI teljesítményből számít!
   Tehát pl. ha tegnap 8 feladatot csinált, ne adj n=8-at – az újból teljesítendő.
   Javasolj mérsékelten ambiciózus, de nem lehetetlen n értéket.
   Ha nincs jó ötlet, hagyj new_medal null-on.

Válaszolj CSAK JSON-ban:
{{
  "greeting": "...",
  "new_medal": {{
    "nev": "...",
    "leiras": "Rövid leírás a feltételről",
    "ikon": "emoji",
    "kategoria": "teljesitmeny|merfoldko|rendszeresseg|felfedezes|kitartas",
    "ervenyes_napig": 1,
    "condition": {{ ...egy condition objektum... }}
  }} | null
}}"""

_NOVELTY_GATE_SYSTEM = (
        "Magyar felvételi játék érmeihez tartozó minőségellenőr vagy. "
        "A feladatod eldönteni, hogy egy új kihívásérem szabálya érdemben különbözik-e "
        "a meglévő aktív kihívásoktól. Csak akkor mondd, hogy elég különböző, ha a játékos "
        "számára tényleg más viselkedést vagy időablakot jutalmaz."
)

_NOVELTY_GATE_TEMPLATE = """\
Vizsgáld meg, hogy az új érem elég újszerű-e a meglévőkhöz képest.

Új jelölt:
{candidate_json}

Ütköző meglévő érmek:
{existing_json}

Szabályok:
- "reasonably_different" csak akkor legyen true, ha a kihívás tényleg más viselkedést, más időzítést,
    más tárgyfókuszt vagy érdemben más célt kér.
- Pusztán névcsere vagy minimális n/window_hours eltérés önmagában nem elég.
- Válaszolj CSAK JSON-nal ebben a formában:
    {{"reasonably_different": true|false, "reason": "rövid indok"}}
"""

_REFINE_MEDAL_SYSTEM = (
        "Magyar felvételi kvíz coach vagy. "
        "Egy túl hasonló privát napi kihívásérmet kell átdolgoznod úgy, hogy továbbra is reálisan "
        "teljesíthető legyen, de világosan eltérjen a meglévő aktív kihívásoktól."
)

_REFINE_MEDAL_TEMPLATE = """\
Felhasználó: {user}
Mostani időablak: {window_hours} óra
Összes megszerzett érem: {earned_count}

Rövid statisztika:
{stats_json}

Közel lévő érmek:
{close_medals_json}

Elutasított jelölt:
{candidate_json}

Miért problémás:
{rejection_reason}

Meglévő ütköző aktív érmek:
{existing_json}

{condition_types_doc}

Feladat:
- Adj vissza egy ÉRDEMBEN eltérő új `new_medal` objektumot, vagy null-t, ha nincs jó ötlet.
- Az új feltétel ne csak minimális számbeli eltérés legyen.
- A feltétel továbbra is legyen rövid távon teljesíthető és gépileg kiértékelhető.

Válaszolj CSAK JSON-ban:
{{"new_medal": {{...}} | null}}
"""


def generate_daily_insight(
    user: str,
    stats: dict,
    close_medals: list,
    earned_count: int,
    *,
    window_hours: int = 18,
) -> dict:
    """Ask the LLM for a motivational greeting and an optional new medal suggestion.

    Args:
        user:         Player name.
        stats:        Dict from ``progress_check.get_user_stats()``.
        close_medals: List of ``CloseMedal`` objects.
        earned_count: How many medals the user has earned so far.
        window_hours: Validity window for the dynamic challenge medal (1–18h).

    Returns:
        Dict with ``greeting`` (str) and ``new_medal`` (dict | None).
        ``new_medal`` includes a ``condition`` dict for machine evaluation.
    """
    from datetime import datetime, timezone

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    close_text = "\n".join(
        f"  - {cm.erem.ikon} {cm.erem.nev}: {cm.hint} ({int(cm.progress * 100)}%)"
        for cm in close_medals
    ) or "  (nincs közel lévő érem)"

    # Build compact daily summary (last 7 days, one line each)
    daily_buckets = stats.get("trends", {}).get("daily_attempts_7d", [])
    if daily_buckets:
        daily_lines = [
            f"  {b['date']}: {b['attempts']} feladat, {b['correct']} helyes ({b['accuracy_pct']}%)"
            for b in daily_buckets
        ]
        daily_summary_text = "\n".join(daily_lines)
    else:
        daily_summary_text = "  (nincs adat)"

    # Build compact event counts (last 24h, only non-zero)
    event_24h = stats.get("events", {}).get("counts_last_24h", {})
    if event_24h:
        event_lines = [f"  {etype}: {cnt}" for etype, cnt in sorted(event_24h.items())]
        event_counts_24h_text = "\n".join(event_lines)
    else:
        event_counts_24h_text = "  (nincs esemény az elmúlt 24 órában)"

    prompt = _DAILY_INSIGHT_TEMPLATE.format(
        user=user,
        now_str=now_str,
        close_medals_text=close_text,
        earned_count=earned_count,
        condition_types_doc=_CONDITION_TYPES_DOC,
        daily_summary_text=daily_summary_text,
        event_counts_24h_text=event_counts_24h_text,
        window_hours=window_hours,
        correct=stats.get("correct", 0),
        **{k: stats[k] for k in (
            "total_attempts", "accuracy_pct", "completed_sessions",
            "current_streak_days", "recent_days_7d",
            "best_correct_streak", "subjects_used",
        )},
    )

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _DAILY_INSIGHT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_completion_tokens=500,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"greeting": f"Helló {user}! Üdv vissza! 🎉", "new_medal": None}


def judge_medal_novelty(candidate: dict, existing_medals: list[dict]) -> dict:
    """Return LLM judgement for whether candidate differs enough from conflicts."""
    if not candidate or not existing_medals:
        return {"reasonably_different": True, "reason": "no_conflicts"}

    prompt = _NOVELTY_GATE_TEMPLATE.format(
        candidate_json=json.dumps(candidate, ensure_ascii=False, indent=2),
        existing_json=json.dumps(existing_medals, ensure_ascii=False, indent=2),
    )
    response = _client.chat.completions.create(
        model=_CHEAP_MODEL,
        messages=[
            {"role": "system", "content": _NOVELTY_GATE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_completion_tokens=250,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"reasonably_different": False, "reason": "invalid_llm_review"}
    return {
        "reasonably_different": bool(parsed.get("reasonably_different")),
        "reason": str(parsed.get("reason", "")).strip(),
    }


def refine_daily_medal(
    user: str,
    stats: dict,
    close_medals: list,
    earned_count: int,
    *,
    window_hours: int,
    candidate: dict,
    conflicting_medals: list[dict],
    rejection_reason: str,
) -> dict | None:
    """Ask the LLM for one refined medal candidate after novelty rejection."""
    close_payload = [
        {
            "nev": cm.erem.nev,
            "kategoria": cm.erem.kategoria,
            "hint": cm.hint,
            "progress": round(cm.progress, 3),
        }
        for cm in close_medals[:5]
    ]
    stats_payload = {
        "total_attempts": stats.get("total_attempts", 0),
        "correct": stats.get("correct", 0),
        "accuracy_pct": stats.get("accuracy_pct", 0),
        "completed_sessions": stats.get("completed_sessions", 0),
        "recent_days_7d": stats.get("recent_days_7d", 0),
        "current_streak_days": stats.get("current_streak_days", 0),
        "best_correct_streak": stats.get("best_correct_streak", 0),
        "subjects_used": stats.get("subjects_used", []),
        "events": stats.get("events", {}).get("counts_last_24h", {}),
    }
    prompt = _REFINE_MEDAL_TEMPLATE.format(
        user=user,
        window_hours=window_hours,
        earned_count=earned_count,
        stats_json=json.dumps(stats_payload, ensure_ascii=False, indent=2),
        close_medals_json=json.dumps(close_payload, ensure_ascii=False, indent=2),
        candidate_json=json.dumps(candidate, ensure_ascii=False, indent=2),
        rejection_reason=rejection_reason,
        existing_json=json.dumps(conflicting_medals, ensure_ascii=False, indent=2),
        condition_types_doc=_CONDITION_TYPES_DOC,
    )
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _REFINE_MEDAL_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_completion_tokens=400,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    refined = parsed.get("new_medal")
    return refined if isinstance(refined, dict) else None

