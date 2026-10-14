from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from felvi_games.ai import coach_writing_chat, review_writing_submission
from felvi_games.writing_review import ReviewCriterion, ReviewGuide


def _guide() -> ReviewGuide:
    return ReviewGuide(
        guide_id="adapter-test-v1",
        name="Adapter test rubric",
        criteria=(ReviewCriterion("content", "Content", 3, "Assess relevant ideas."),),
    )


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_review_writing_submission_uses_configured_model_json_mode() -> None:
    response_json = (
        '{"criteria":[{"criterion_id":"content","score":2,"feedback":"Relevant idea.",'
        '"evidence_quote":"A draft phrase.","uncertain":false}]}'
    )
    mock_create = Mock(return_value=_completion(response_json))

    with (
        patch("felvi_games.ai.MODEL", "test-writing-model"),
        patch("felvi_games.ai._client.chat.completions.create", mock_create),
    ):
        result = review_writing_submission("Write about games.", "A draft phrase.", _guide())

    assert result.total_score == 2
    assert result.assessable_max_score == 3
    request = mock_create.call_args.kwargs
    assert request["model"] == "test-writing-model"
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}
    assert "A draft phrase." in request["messages"][1]["content"]


def test_review_writing_submission_surfaces_provider_errors() -> None:
    mock_create = Mock(side_effect=RuntimeError("provider unavailable"))

    with (
        patch("felvi_games.ai.MODEL", "test-writing-model"),
        patch("felvi_games.ai._client.chat.completions.create", mock_create),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        review_writing_submission("Prompt", "Draft", _guide())

    mock_create.assert_called_once()


def test_review_writing_submission_applies_short_text_rule_without_provider_call() -> None:
    mock_create = Mock()

    with patch("felvi_games.ai._client.chat.completions.create", mock_create):
        result = review_writing_submission(
            "Prompt",
            "Draft",
            _guide(),
            sentence_count=3,
            min_sentences_for_any_points=4,
        )

    assert result.total_score == 0
    mock_create.assert_not_called()


def test_coach_writing_chat_uses_cheap_model_and_only_recent_history() -> None:
    history = [
        {"role": "user", "content": f"Earlier question {index}"}
        if index % 2 == 0
        else {"role": "assistant", "content": f"Earlier answer {index}"}
        for index in range(12)
    ]
    mock_create = Mock(return_value=_completion("Jó kezdet. Melyik érvedet fejted ki először?"))

    with (
        patch("felvi_games.ai._CHEAP_MODEL", "test-coach-model"),
        patch("felvi_games.ai._client.chat.completions.create", mock_create),
    ):
        reply = coach_writing_chat(
            "Write about games.",
            "I prefer online games because I can play with friends.",
            _guide(),
            history,
            "Mivel folytassam?",
        )

    assert reply.startswith("Jó kezdet.")
    request = mock_create.call_args.kwargs
    assert request["model"] == "test-coach-model"
    assert request["temperature"] == 0.3
    assert request["max_tokens"] == 220
    assert len(request["messages"]) == 10
    assert request["messages"][1] == history[-8]
    assert request["messages"][-1]["role"] == "user"
    assert "I prefer online games" in request["messages"][-1]["content"]
    assert "Mivel folytassam?" in request["messages"][-1]["content"]


def test_coach_writing_chat_validates_input_and_surfaces_provider_errors() -> None:
    history = [{"role": "user", "content": "First turn"}]
    with pytest.raises(ValueError, match="empty"):
        coach_writing_chat("Prompt", "Draft", _guide(), history, " ")
    with pytest.raises(ValueError, match="history"):
        coach_writing_chat(
            "Prompt",
            "Draft",
            _guide(),
            [{"role": "system", "content": "not allowed"}],
            "Continue",
        )

    mock_create = Mock(side_effect=RuntimeError("provider unavailable"))
    with (
        patch("felvi_games.ai._CHEAP_MODEL", "test-coach-model"),
        patch("felvi_games.ai._client.chat.completions.create", mock_create),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        coach_writing_chat("Prompt", "Draft", _guide(), [], "Continue")
