"""Chainlit app for interactive Feladat review discussion."""

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
            "name": "get_task_overview",
            "description": "Get the task metadata, accepted answer, and current review stats.",
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
            "name": "get_source_excerpt",
            "description": "Get a concise excerpt from the task sheet, guide, or both.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["task", "guide", "both"],
                        "default": "both",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_attempts",
            "description": "List recent attempts, optionally filtered by good, bad, or flagged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "good", "bad", "flagged"],
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
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
            "description": "Return one attempt by numeric attempt ID.",
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
            "name": "summarize_answer_patterns",
            "description": "Summarize common wrong-answer patterns from the loaded attempts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_review_risk",
            "description": "Return a compact risk summary for the current task review.",
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
            "name": "get_markdown_origin",
            "description": "Load original group context and source markdown/text extracts for this task.",
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
            "name": "list_wrong_tasks",
            "description": "List wrong tasks from DB using wrong/flagged/keyword/any strategy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["wrong", "flagged", "keyword", "any"],
                        "default": "any",
                    },
                    "user": {"type": "string"},
                    "contains": {"type": "string", "default": "hibás"},
                    "min_hibas": {"type": "integer", "minimum": 1, "default": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    "include_wrong_answers": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_task_update_confirmation",
            "description": "Prepare a versioned task+guide update and generate a required confirmation code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": (
                            "Task fields to update (kerdes, helyes_valasz, "
                            "elfogadott_valaszok, magyarazat, reszpontozas, "
                            "ertekeles_megjegyzes, etc.)"
                        ),
                    },
                    "review_note": {"type": "string"},
                },
                "required": ["updates"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_task_update_with_confirmation",
            "description": "Apply the pending task update only when the exact confirmation code is provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_code": {"type": "string"},
                },
                "required": ["confirmation_code"],
                "additionalProperties": False,
            },
        },
    },
]


def _load_context() -> dict:
    ctx_path = os.getenv("FELVI_REVIEW_CHAT_CONTEXT", "").strip()
    if not ctx_path:
        raise RuntimeError("FELVI_REVIEW_CHAT_CONTEXT env var is missing.")
    path = Path(ctx_path)
    if not path.exists():
        raise RuntimeError(f"Context file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _make_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    )


def _tool_handlers(context: dict[str, Any]) -> dict[str, Any]:
    from felvi_games.review_agent_tools import (
        apply_task_update_with_confirmation,
        get_attempt_detail,
        get_markdown_origin,
        get_source_excerpt,
        get_task_overview,
        list_attempts,
        list_wrong_tasks,
        request_task_update_confirmation,
        summarize_answer_patterns,
        summarize_review_risk,
    )

    return {
        "get_task_overview": lambda **kwargs: get_task_overview(context),
        "get_source_excerpt": lambda **kwargs: get_source_excerpt(context, **kwargs),
        "list_attempts": lambda **kwargs: list_attempts(context, **kwargs),
        "get_attempt_detail": lambda **kwargs: get_attempt_detail(context, **kwargs),
        "summarize_answer_patterns": lambda **kwargs: summarize_answer_patterns(context, **kwargs),
        "summarize_review_risk": lambda **kwargs: summarize_review_risk(context),
        "get_markdown_origin": lambda **kwargs: get_markdown_origin(context),
        "list_wrong_tasks": lambda **kwargs: list_wrong_tasks(context, **kwargs),
        "request_task_update_confirmation": lambda **kwargs: request_task_update_confirmation(context, **kwargs),
        "apply_task_update_with_confirmation": lambda **kwargs: apply_task_update_with_confirmation(context, **kwargs),
    }


def _system_prompt(context: dict) -> str:
    summary = {
        "feladat": context.get("feladat", {}),
        "attempts": context.get("attempts", {}),
        "ai_assessment": context.get("ai_assessment", ""),
    }
    return (
        "Felvételi feladat-review moderátor vagy. "
        "A cél: a potenciális hibák tárgyszerű feltárása és javítási javaslat. "
        "Légy konkrét, bizonyíték-alapú, hivatkozz a kontextus elemeire. "
        "Ha részletesebb adatra van szükség, használd az elérhető tools-t. "
        "Ha nem biztos valami, mondd ki. "
        "A válasz nyelve magyar.\n\n"
        "### KEZDŐ ÖSSZEFOGLALÓ\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


@cl.on_chat_start
async def on_chat_start() -> None:
    context = _load_context()
    cl.user_session.set("context", context)
    cl.user_session.set("history", [])

    feladat = context.get("feladat", {})
    attempts = context.get("attempts", {})
    ai_assessment = context.get("ai_assessment", "")

    intro = (
        f"## Review chat: {feladat.get('id', '-') }\n"
        f"- Tárgy/szint: {feladat.get('targy', '-')} / {feladat.get('szint', '-')}\n"
        f"- Típus/max pont: {feladat.get('feladat_tipus', '-')} / {feladat.get('max_pont', '-')}\n"
        "- Korábbi próbák: "
        f"összes={attempts.get('total', 0)}, "
        f"jó={attempts.get('good_count', 0)}, "
        f"rossz={attempts.get('bad_count', 0)}\n\n"
        f"### AI előértékelés\n{ai_assessment or 'Nincs AI előértékelés.'}\n\n"
        "Kérdezz bátran: meg tudjuk vitatni, jogos volt-e a hibajelölés, "
        "és mit érdemes javítani a feladaton vagy az útmutatón."
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
