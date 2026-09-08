import logging
import time
from collections.abc import Iterator

from azure.identity import get_bearer_token_provider
from openai import APITimeoutError, OpenAI

from app.config import Settings, get_settings
from app.models.schemas import MessageRecord
from app.services.azure_auth import get_azure_credential
from app.services.search import RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful retail assistant. Answer using ONLY the provided context.
If the context is insufficient, say you don't know. Cite document titles. Be concise.

Rules for amounts, thresholds, and policies:
- Quote dollar amounts and thresholds exactly as written in the context. Never replace a policy threshold with the user's amount.
- When the user asks about a specific amount, find the matching rule in the context, state the documented threshold, then say whether the user's amount falls under that rule.
  Example: if the context says "greater than $2,500" and the user asks about $2,800, answer that refunds greater than $2,500 require X approval, and $2,800 meets that threshold.
- Do not merge approval roles from different documents or domains (e.g. customer claims vs vendor reimbursements vs refunds). Use the document that matches the question topic.
- For follow-up questions (e.g. "what about above 5k?"), use the conversation history to resolve the topic, then answer from the context."""


class ChatModelError(RuntimeError):
    pass


def _is_reasoning_model(deployment: str) -> bool:
    name = deployment.lower()
    return name.startswith("gpt-5") or name.startswith("o")


def _get_chat_client() -> OpenAI:
    settings = get_settings()
    timeout = settings.api_timeout_seconds
    if settings.azure_openai_api_key:
        return OpenAI(
            base_url=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            timeout=timeout,
            max_retries=0,
        )
    token_provider = get_bearer_token_provider(
        get_azure_credential(), "https://ai.azure.com/.default"
    )
    return OpenAI(
        base_url=settings.azure_openai_endpoint,
        api_key=token_provider,
        timeout=timeout,
        max_retries=0,
    )


def _format_context(chunks: list[RetrievedChunk], max_snippet_chars: int) -> str:
    if not chunks:
        return "No relevant documents found."

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.title or "Unknown"
        snippet = (chunk.snippet or "")[:max_snippet_chars]
        parts.append(f"[{i}] {title}: {snippet}")
    return "\n".join(parts)


def _format_history(history: list[MessageRecord]) -> str:
    lines: list[str] = []
    for msg in history[-4:]:
        if msg.role not in ("user", "assistant"):
            continue
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content}")
    if not lines:
        return ""
    return "Previous conversation:\n" + "\n".join(lines) + "\n\n"


def _build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[MessageRecord],
    settings: Settings,
) -> list[dict[str, str]]:
    llm_chunks = chunks[: settings.llm_top_k_chunks]
    context = _format_context(llm_chunks, settings.llm_snippet_chars)
    history_block = _format_history(history)

    if _is_reasoning_model(settings.azure_openai_chat_deployment):
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Context:\n{context}\n\n"
            f"{history_block}"
            f"Question: {question}\n\n"
            "Answer:"
        )
        return [{"role": "user", "content": prompt}]

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}"},
    ]
    for msg in history[-4:]:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": question})
    return messages


def _message_text(message) -> str:
    if not message:
        return ""

    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()

    refusal = getattr(message, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return refusal.strip()

    if hasattr(message, "model_dump"):
        data = message.model_dump(exclude_none=True)
        for key in ("content", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _chat_kwargs(settings: Settings, messages: list[dict[str, str]]) -> dict:
    kwargs: dict = {
        "model": settings.azure_openai_chat_deployment,
        "messages": messages,
    }
    if _is_reasoning_model(settings.azure_openai_chat_deployment):
        kwargs["max_completion_tokens"] = settings.chat_max_completion_tokens
        kwargs["reasoning_effort"] = "low"
    else:
        kwargs["max_tokens"] = 500
        kwargs["temperature"] = 0.2
    return kwargs


def _complete_chat(
    client: OpenAI,
    messages: list[dict[str, str]],
    settings: Settings,
    history: list[MessageRecord] | None = None,
) -> str:
    payload_chars = sum(len(m["content"]) for m in messages)
    logger.info(
        "Chat payload: %d messages, %d chars, %d history turn(s) → model %s",
        len(messages),
        payload_chars,
        len(history or []),
        settings.azure_openai_chat_deployment,
    )
    started = time.monotonic()
    completion = client.chat.completions.create(**_chat_kwargs(settings, messages))
    elapsed = time.monotonic() - started

    choice = completion.choices[0]
    answer = _message_text(choice.message)
    logger.info(
        "Chat model responded in %.1fs (%d chars, finish_reason=%s).",
        elapsed,
        len(answer),
        choice.finish_reason,
    )
    logger.info("Answer: %s", answer)

    if not answer:
        raw = choice.message.model_dump() if hasattr(choice.message, "model_dump") else str(choice.message)
        logger.warning("Empty answer payload: %s", raw)
        hint = (
            "Increase CHAT_MAX_COMPLETION_TOKENS in .env"
            if choice.finish_reason == "length"
            else "Check deployment in Foundry Playground"
        )
        raise ChatModelError(
            f"Chat model returned empty content from {settings.azure_openai_chat_deployment}. {hint}"
        )
    return answer


def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[MessageRecord],
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    client = _get_chat_client()
    messages = _build_messages(question, chunks, history, settings)

    try:
        return _complete_chat(client, messages, settings, history)
    except APITimeoutError as exc:
        raise ChatModelError(
            f"Chat model timed out after {settings.api_timeout_seconds}s. "
            "Try increasing API_TIMEOUT_SECONDS in .env."
        ) from exc
    except ChatModelError:
        raise
    except Exception as exc:
        logger.error("Chat model API error: %s", exc)
        raise ChatModelError(f"Chat model error: {exc}") from exc


def stream_answer(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[MessageRecord],
    settings: Settings | None = None,
) -> Iterator[str]:
    answer = generate_answer(question, chunks, history, settings)
    yield answer
