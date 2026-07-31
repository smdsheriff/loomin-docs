"""Route-level tests for POST /api/chat.

These exercise the full HTTP surface — SSE framing, status codes, and the
flag-gated routing — with Ollama and retrieval mocked. They cover the seams the
graph-unit tests can't: the request handler, backward-compat error semantics,
and equivalence between the legacy and LangGraph paths.
"""

import httpx
import pytest
from httpx import ASGITransport


async def _fake_stream(messages, model):
    for tok in ["Hi", " there"]:
        yield tok


async def _no_chunks(query, session, top_k=5, min_score=None):
    return []


async def _boom_retrieve(query, session, top_k=5, min_score=None):
    raise RuntimeError("faiss index missing")


@pytest.fixture
async def client():
    from app.models.database import init_db

    await init_db()
    from app.main import app

    # raise_app_exceptions=False makes the transport translate an unhandled
    # endpoint exception into a real 500 response, as a production server does.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _patch_ollama_and_retrieval(monkeypatch, retrieve=_no_chunks, stream=_fake_stream):
    # Patch retrieval where each path references it, and the shared Ollama singleton.
    from app.api.routes import chat as chat_route
    from app.rag import graph as graph_mod
    from app.services.ollama import ollama_service

    monkeypatch.setattr(chat_route, "retrieve_relevant_chunks", retrieve)
    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", retrieve)
    monkeypatch.setattr(ollama_service, "chat_stream", stream)


def _set_flag(monkeypatch, value: bool):
    from app.core.config import settings
    monkeypatch.setattr(settings, "USE_LANGGRAPH", value)


@pytest.mark.parametrize("use_langgraph", [False, True])
async def test_chat_streams_tokens_and_done(client, monkeypatch, use_langgraph):
    """Both paths emit identical SSE framing: token frames then a done frame."""
    _set_flag(monkeypatch, use_langgraph)
    _patch_ollama_and_retrieval(monkeypatch)

    resp = await client.post("/api/chat", json={"message": "hello", "document_id": "d1"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert '"token": "Hi"' in body
    assert '"token": " there"' in body
    assert '"done": true' in body
    assert '"request_id"' in body  # metadata populated in the done frame


async def test_graph_prep_failure_returns_500_not_200(client, monkeypatch):
    """Backward-compat contract: a retrieval failure under the graph path must
    surface as HTTP 500 (as the legacy path does), not a 200 error-token stream."""
    _set_flag(monkeypatch, True)
    _patch_ollama_and_retrieval(monkeypatch, retrieve=_boom_retrieve)

    resp = await client.post("/api/chat", json={"message": "hello", "document_id": "d1"})

    assert resp.status_code == 500


async def test_legacy_retrieval_failure_also_500(client, monkeypatch):
    """The legacy path returns 500 on retrieval failure — the behavior the graph
    path is required to match."""
    _set_flag(monkeypatch, False)
    _patch_ollama_and_retrieval(monkeypatch, retrieve=_boom_retrieve)

    resp = await client.post("/api/chat", json={"message": "hello", "document_id": "d1"})

    assert resp.status_code == 500
