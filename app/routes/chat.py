import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionDetail,
)
from app.services.context import session_store
from app.services.llm import ChatModelError, generate_answer, stream_answer
from app.services.search import (
    SearchAuthError,
    chunks_to_citations,
    filter_citations_for_answer,
    search_chunks,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_chat_pipeline(request: ChatRequest):
    settings = get_settings()
    session = session_store.get_or_create(request.session_id, request.customer_id)
    history = session_store.get_history(session.session_id, settings.max_history_turns)
    if history:
        logger.info("Session %s: using %d prior message(s).", session.session_id, len(history))
    chunks = search_chunks(request.message, settings)
    return settings, session, history, chunks


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    logger.info("Chat request received.")

    try:
        settings, session, history, chunks = _run_chat_pipeline(request)
    except SearchAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        answer = generate_answer(request.message, chunks, history, settings)
    except ChatModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    all_citations = chunks_to_citations(chunks)
    citations = filter_citations_for_answer(all_citations, answer, chunks)

    session_store.add_message(session.session_id, "user", request.message)
    session_store.add_message(session.session_id, "assistant", answer)
    logger.info("Chat request complete.")

    return ChatResponse(
        session_id=session.session_id,
        answer=answer,
        citations=citations,
    )


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    logger.info("Chat stream request received.")

    def event_generator() -> Iterator[str]:
        try:
            settings, session, history, chunks = _run_chat_pipeline(request)
        except SearchAuthError as exc:
            yield _sse("error", {"message": str(exc)})
            return
        except Exception as exc:
            logger.exception("Search failed during stream.")
            yield _sse("error", {"message": str(exc)})
            return

        yield _sse("session", {"session_id": session.session_id})
        yield _sse("status", {"message": "generating answer"})

        answer_parts: list[str] = []
        try:
            for token in stream_answer(request.message, chunks, history, settings):
                answer_parts.append(token)
                yield _sse("token", {"content": token})
        except ChatModelError as exc:
            yield _sse("error", {"message": str(exc)})
            return

        answer = "".join(answer_parts)
        all_citations = chunks_to_citations(chunks)
        citations = filter_citations_for_answer(all_citations, answer, chunks)
        session_store.add_message(session.session_id, "user", request.message)
        session_store.add_message(session.session_id, "assistant", answer)
        logger.info("Answer (%d chars): %s", len(answer), answer)
        logger.info("Chat stream request complete.")

        yield _sse(
            "done",
            {
                "session_id": session.session_id,
                "answer": answer,
                "citations": [c.model_dump() for c in citations],
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    session_id = session_store.create_session(request.customer_id)
    return SessionCreateResponse(session_id=session_id)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str) -> SessionDetail:
    detail = session_store.to_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found.")
    return detail
