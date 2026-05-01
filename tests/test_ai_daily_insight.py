from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from felvi_games.ai import generate_daily_insight
from felvi_games.models import Erem
from felvi_games.progress_check import CloseMedal


def test_generate_daily_insight_prompt_includes_trends_patterns_and_events() -> None:
    stats = {
        "total_attempts": 86,
        "correct": 50,
        "accuracy_pct": 58.1,
        "completed_sessions": 9,
        "current_streak_days": 1,
        "recent_days_7d": 4,
        "best_correct_streak": 16,
        "subjects_used": ["magyar", "matek"],
        "levels_used": ["4 osztályos"],
        "trends": {
            "attempts_last_24h": 5,
            "activity_trend": "javul",
            "daily_attempts_7d": [
                {"date": "2026-04-25", "attempts": 5, "correct": 3, "accuracy_pct": 60.0},
            ],
        },
        "patterns": {"subject_session_counts": {"matek": 6}},
        "events": {"counts_last_24h": {"ujraertekeles": 1}},
    }
    close_medals = [
        CloseMedal(
            erem=Erem(
                id="szaz_feladat",
                nev="Centurion",
                leiras="100 feladatot oldottál meg.",
                ikon="💯",
                kategoria="merfoldko",
            ),
            progress=0.86,
            hint="86 / 100 feladat",
        )
    ]
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"greeting":"Szia","new_medal":null}'))]
    )
    mock_create = Mock(return_value=fake_response)

    with patch("felvi_games.ai._client.chat.completions.create", mock_create):
        result = generate_daily_insight("Lóri", stats, close_medals, 11, window_hours=18)

    assert result == {"greeting": "Szia", "new_medal": None}
    prompt = mock_create.call_args.kwargs["messages"][1]["content"]
    # New simplified prompt structure
    assert "Utolsó 7 nap" in prompt
    assert "2026-04-25" in prompt          # daily summary line
    assert "Interakciók" in prompt
    assert "ujraertekeles: 1" in prompt    # event count line
    assert "most:" in prompt               # as_of timestamp