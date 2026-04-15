"""
Unified provider adapter for Anthropic + Vertex AI with failover.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import anthropic
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.config import settings

logger = logging.getLogger(__name__)

_anthropic: anthropic.AsyncAnthropic | None = None
_vertex_initialized = False
_vertex_models: dict[str, GenerativeModel] = {}


def _provider_name(value: str, default: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in {"anthropic", "vertex"} else default


def provider_order() -> list[str]:
    primary = _provider_name(settings.llm_primary_provider, "anthropic")
    fallback = _provider_name(settings.llm_fallback_provider, "vertex")
    return [primary] if primary == fallback else [primary, fallback]


def _anthropic_model_for_task(task: str) -> str:
    mapping = {
        "chat": settings.anthropic_chat_model,
        "summary": settings.anthropic_summary_model,
        "rewrite": settings.anthropic_rewrite_model,
        "enrich": settings.anthropic_enrich_model,
        "rerank": settings.anthropic_rerank_model,
    }
    return mapping.get(task, settings.anthropic_chat_model)


def _vertex_model_for_task(task: str) -> str:
    mapping = {
        "chat": settings.vertex_chat_model,
        "summary": settings.vertex_summary_model,
        "rewrite": settings.vertex_rewrite_model,
        "enrich": settings.vertex_enrich_model,
        "rerank": settings.vertex_rerank_model,
    }
    return mapping.get(task, settings.vertex_chat_model)


def _ensure_vertex_initialized() -> None:
    global _vertex_initialized
    if _vertex_initialized:
        return
    project = settings.vertex_project_id or settings.firebase_project_id
    if not project:
        raise ValueError("vertex_project_id (or firebase_project_id fallback) must be set for Vertex AI")
    vertexai.init(project=project, location=settings.vertex_location)
    _vertex_initialized = True


def _get_vertex_model(task: str) -> GenerativeModel:
    _ensure_vertex_initialized()
    model_name = _vertex_model_for_task(task)
    if model_name not in _vertex_models:
        _vertex_models[model_name] = GenerativeModel(model_name)
    return _vertex_models[model_name]


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic


async def _complete_anthropic(
    task: str,
    prompt: str,
    *,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    client = get_anthropic_client()
    kwargs: dict = {
        "model": _anthropic_model_for_task(task),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = await client.messages.create(**kwargs)
    return response.content[0].text if response.content else ""


def _complete_vertex_sync(
    task: str,
    prompt: str,
    *,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    model = _get_vertex_model(task)
    request_prompt = f"System:\n{system}\n\nUser:\n{prompt}" if system else prompt
    response = model.generate_content(
        request_prompt,
        generation_config=GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        ),
    )
    return getattr(response, "text", "") or ""


async def _complete_vertex(
    task: str,
    prompt: str,
    *,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    return await asyncio.to_thread(
        _complete_vertex_sync,
        task,
        prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
    )


async def complete_text(
    task: str,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> tuple[str, str]:
    """Run completion with provider routing. Returns (text, provider_used)."""
    last_error: Exception | None = None
    for provider in provider_order():
        try:
            if provider == "anthropic":
                text = await _complete_anthropic(
                    task,
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                text = await _complete_vertex(
                    task,
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            return text, provider
        except Exception as exc:  # noqa: BLE001 - deliberate multi-provider fallback
            logger.warning("Provider %s failed for task %s: %s", provider, task, exc)
            last_error = exc

    raise RuntimeError(f"All LLM providers failed for task '{task}'") from last_error


def _messages_to_prompt(messages: list[dict]) -> str:
    return "\n\n".join(f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in messages)


async def stream_chat(
    messages: list[dict],
    *,
    system: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> AsyncIterator[str]:
    """Stream chat with provider routing. Vertex fallback yields chunked full text."""
    last_error: Exception | None = None
    for provider in provider_order():
        try:
            if provider == "anthropic":
                client = get_anthropic_client()
                async with client.messages.stream(
                    model=_anthropic_model_for_task("chat"),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=messages,
                ) as stream:
                    async for token in stream.text_stream:
                        yield token
                return

            prompt = _messages_to_prompt(messages)
            text = await _complete_vertex(
                "chat",
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            for i in range(0, len(text), 256):
                yield text[i:i + 256]
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat provider %s failed: %s", provider, exc)
            last_error = exc

    raise RuntimeError("All providers failed for chat streaming") from last_error
