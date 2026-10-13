from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from felvi_games.ai import review_writing_submission
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
