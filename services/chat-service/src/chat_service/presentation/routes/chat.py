"""Chat/RAG API routes — standard and streaming SSE responses."""

from __future__ import annotations

import json
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from chat_service.application.rag import AgentResponse, ChatMessage, RagUseCase
from chat_service.presentation.dependencies import get_current_user, get_rag_use_case

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / response models ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] | None = None
    document_ids: list[str] | None = None
    stream: bool = False


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    text: str
    score: float
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    tools_used: list[str]
    suggestions: list[str]
    model: str
    intent: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "/",
    summary="Ask the CFO document assistant a question",
    description=(
        "Agentic RAG: the model decides to call tools (vector search + structured DB) "
        "before composing a grounded answer. Returns citations, follow-up suggestions, "
        "and the list of tools used. Pass stream=true for Server-Sent Events."
    ),
)
async def chat(
    body: ChatRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rag: Annotated[Any, Depends(get_rag_use_case)],
) -> ChatResponse | StreamingResponse:
    if body.stream:
        return await _stream_response(body, current_user, rag)

    result: AgentResponse = await rag.answer(
        question=body.question,
        tenant_id=str(current_user.tenant_id),
        history=body.history,
        document_ids=body.document_ids,
    )
    return ChatResponse(
        answer=result.answer,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                text=c.text,
                score=round(c.score, 4),
                page=c.page,
            )
            for c in result.citations
        ],
        tools_used=result.tools_used,
        suggestions=result.suggestions,
        model=result.model,
        intent=result.intent,
    )


async def _stream_response(
    body: ChatRequest,
    current_user: AuthenticatedUser,
    rag: Any,
) -> StreamingResponse:
    """SSE stream: first emit metadata (citations, tools_used, suggestions),
    then stream answer tokens, then emit [DONE]."""

    meta, token_gen = await rag.answer_stream(
        question=body.question,
        tenant_id=str(current_user.tenant_id),
        history=body.history,
        document_ids=body.document_ids,
    )

    async def _generate() -> AsyncIterator[str]:
        # Emit metadata event first so the client can show citations while text streams
        metadata_payload = {
            "type": "metadata",
            "citations": [
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "filename": c.filename,
                    "text": c.text[:300],
                    "score": round(c.score, 4),
                    "page": c.page,
                }
                for c in meta.citations
            ],
            "tools_used": meta.tools_used,
            "intent": meta.intent,
        }
        yield f"data: {json.dumps(metadata_payload)}\n\n"

        # Stream answer tokens
        full_answer = ""
        async for token in token_gen:
            full_answer += token
            yield f"data: {json.dumps({'type': 'token', 'delta': token})}\n\n"

        # Parse suggestions from the completed answer and emit
        _, suggestions = rag._parse_suggestions(full_answer)  # noqa: SLF001
        yield f"data: {json.dumps({'type': 'suggestions', 'suggestions': suggestions})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")
