"""Chainlit app for teacher-focused student analytics chat."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import chainlit as cl
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_teacher_scope",
            "description": "Get current student/scope summary for the teacher chat.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_attempts",
            "description": "List attempts for the selected student and subject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "correct", "partial", "wrong", "flagged", "slow"],
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                    "slow_threshold_sec": {
                        "type": "number",
                        "default": 180,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attempt_detail",
            "description": "Get full detail for one attempt by attempt ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "attempt_id": {"type": "integer"},
                },
                "required": ["attempt_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_related_tasks",
            "description": "List related tasks by weak/strong/frequent/unreliable grouping.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "weak", "strong", "frequent", "unreliable"],
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                    "min_attempts": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 1,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_strengths_weaknesses",
            "description": "Summarize the student's strengths and weaknesses in the selected scope.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_personalized_training",
            "description": "Create a personalized training recommendation list based on weak areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_recommendations": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 8,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_exam_assignment_order",
            "description": "Recommend assignment ordering strategy to maximize expected score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "enum": ["maximize_score", "confidence_first", "time_efficient"],
                        "default": "maximize_score",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 15,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reload_teacher_context",
            "description": "Switch active student/subject scope and reload the chat context from DB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user": {"type": "string"},
                    "targy": {
                        "type": "string",
                        "enum": ["matek", "magyar"],
                    },
                    "szint": {"type": "string", "default": "mind"},
                    "attempts_limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 200,
                    },
                },
                "required": ["user", "targy"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_students",
            "description": "List students available in the DB (optional name filter).",
            "parameters": {
                "type": "object",
                "properties": {
                    "contains": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                        "default": 25,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


def _load_context() -> dict:
    ctx_path = os.getenv("FELVI_TEACHER_CHAT_CONTEXT", "").strip()
    if not ctx_path:
        raise RuntimeError("FELVI_TEACHER_CHAT_CONTEXT env var is missing.")
    path = Path(ctx_path)
    if not path.exists():
        raise RuntimeError(f"Context file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _make_client() -> OpenAI:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def _tool_handlers(context: dict[str, Any]) -> dict[str, Any]:
    from felvi_games.teacher_agent_tools import (
        get_attempt_detail,
        get_teacher_scope,
        list_available_students,
        list_recent_attempts,
        list_related_tasks,
        recommend_exam_assignment_order,
        recommend_personalized_training,
        reload_teacher_context,
        summarize_strengths_weaknesses,
    )

    return {
        "get_teacher_scope": lambda **kwargs: get_teacher_scope(context),
        "list_recent_attempts": lambda **kwargs: list_recent_attempts(context, **kwargs),
        "get_attempt_detail": lambda **kwargs: get_attempt_detail(context, **kwargs),
        "list_related_tasks": lambda **kwargs: list_related_tasks(context, **kwargs),
        "summarize_strengths_weaknesses": lambda **kwargs: summarize_strengths_weaknesses(context, **kwargs),
        "recommend_personalized_training": lambda **kwargs: recommend_personalized_training(context, **kwargs),
        "recommend_exam_assignment_order": lambda **kwargs: recommend_exam_assignment_order(context, **kwargs),
        "reload_teacher_context": lambda **kwargs: reload_teacher_context(context, **kwargs),
        "list_available_students": lambda **kwargs: list_available_students(context, **kwargs),
    }


def _system_prompt(context: dict[str, Any]) -> str:
    summary = {
        "student": context.get("student", {}),
        "scope": context.get("scope", {}),
        "summary": context.get("summary", {}),
    }
    scope = context.get("scope", {})
    szint = str(scope.get("szint", "") or "").strip()
    scope_note = (
        "A scope az adott tantárgy minden szintjét tartalmazza."
        if szint in {"", "mind"}
        else f"A scope szintszűrt: {szint}."
    )
    return (
        "Felvételi tanári elemző asszisztens vagy. "
        "A cél: egy kiválasztott tanuló és tantárgy teljesítményének tárgyszerű elemzése, "
        "erősségek/gyengeségek azonosítása, személyre szabott gyakorlási javaslat, "
        "és feladatsorrend-ajánlás vizsgahelyzetre. "
        "Légy konkrét, adat-alapú, és hivatkozz a tool adatokra. "
        "Ha kevés az adat, mondd ki egyértelműen. "
        "A válasz nyelve magyar.\n"
        f"{scope_note}\n\n"
        "### KEZDŐ TANÁRI KONTEXTUS\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


@cl.on_chat_start
async def on_chat_start() -> None:
    context = _load_context()
    cl.user_session.set("context", context)
    cl.user_session.set("history", [])

    student = context.get("student", {})
    scope = context.get("scope", {})
    summary = context.get("summary", {})
    scope_szint = str(scope.get("szint", "") or "").strip()
    scope_label = (
        f"{scope.get('targy', '-')} / minden szint"
        if scope_szint in {"", "mind"}
        else f"{scope.get('targy', '-')} / {scope_szint}"
    )

    intro = (
        f"## Teacher analytics chat: {student.get('name', '-') }\n"
        f"- Tárgy/szint: {scope_label}\n"
        f"- Próbálkozások: {summary.get('attempts_total', 0)}\n"
        f"- Pontosság: {summary.get('accuracy_pct', 0)}% "
        f"(+részleges: {summary.get('partial_or_better_pct', 0)}%)\n"
        f"- Pontarány: {summary.get('points', 0)}/{summary.get('points_possible', 0)} "
        f"({summary.get('points_ratio_pct', 0)}%)\n\n"
        "Kérj elemzést például ezekre: erősség/gyengeség profil, személyre szabott tréning, "
        "vagy vizsga-feladatsorrend maximalizált pontszámhoz."
    )
    await cl.Message(content=intro).send()


def _tool_response_content(name: str, args: dict[str, Any], context: dict[str, Any]) -> str:
    handlers = _tool_handlers(context)
    handler = handlers.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    try:
        result = handler(**args)
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"Tool failed: {exc}"}
    return json.dumps(result, ensure_ascii=False, indent=2)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    context = cl.user_session.get("context") or {}
    history = cl.user_session.get("history") or []

    history.append({"role": "user", "content": message.content})

    client = _make_client()
    model = os.getenv("LLM_MODEL", "gpt-4o")

    messages = [{"role": "system", "content": _system_prompt(context)}] + history[-12:]

    try:
        for _ in range(6):
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            if msg.tool_calls:
                messages.append(msg.model_dump(exclude_none=True))
                for tool_call in msg.tool_calls:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    tool_content = _tool_response_content(tool_call.function.name, arguments, context)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_content,
                        }
                    )
                continue

            answer = (msg.content or "").strip() or "Nem érkezett válasz."
            break
        else:
            answer = "A modell túl sok tool-hívást végzett válasz nélkül."
    except Exception as exc:  # noqa: BLE001
        answer = f"Hiba történt a modellhívás közben: {exc}"

    history.append({"role": "assistant", "content": answer})
    cl.user_session.set("history", history)

    await cl.Message(content=answer).send()
