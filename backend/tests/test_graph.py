"""Integration tests for the LangGraph chat pipeline.

Ollama and FAISS retrieval are mocked, so these run offline and prove the graph
wiring itself: token streaming, finalization, citation assembly, trace metadata,
message-array construction, and error handling — independent of any model.
"""

import pytest

from app.core.tracing import RequestTrace
from app.models.schemas import RetrievedChunk
from app.rag import graph as graph_mod


# ── Fakes ────────────────────────────────────────────────────────────────────

class _FakeResult:
    def all(self):
        return []


class _FakeSession:
    """Minimal stand-in for AsyncSession used by the inventory node."""

    async def execute(self, stmt):
        return _FakeResult()


async def _fake_stream(messages, model):
    for tok in ["Hello", ", ", "world"]:
        yield tok


async def _boom_stream(messages, model):
    if False:  # make this an async generator
        yield ""
    raise RuntimeError("ollama down")


async def _no_chunks(query, session, top_k=5, min_score=None):
    return []


def _base_state(**overrides):
    trace = RequestTrace()
    trace.model = "test-model"
    state = {
        "user_message": "hi",
        "document_id": "doc1",
        "model": "test-model",
        "document_content": None,
        "history": [],
        "redactions": 0,
        "session": _FakeSession(),
        "trace": trace,
    }
    state.update(overrides)
    return state


async def _run(state):
    """Run the full flow: eager prep, then streamed generation."""
    prepared = await graph_mod.prepare_chat_state(state)
    tokens, final = [], None
    async for ev in graph_mod.stream_generation(prepared):
        if ev["type"] == "token":
            tokens.append(ev["token"])
        elif ev["type"] == "final":
            final = ev
    return tokens, final


# ── Tests ────────────────────────────────────────────────────────────────────

async def test_streams_tokens_and_finalizes(monkeypatch):
    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", _no_chunks)
    monkeypatch.setattr(graph_mod.ollama_service, "chat_stream", _fake_stream)

    tokens, final = await _run(_base_state(redactions=2))

    assert tokens == ["Hello", ", ", "world"]
    assert final is not None
    assert final["full_response"] == "Hello, world"
    assert final["metadata"]["tokens_generated"] == 3
    assert final["metadata"]["pii_redactions"] == 2
    assert final["metadata"]["citations"] == []
    assert final["metadata"]["model"] == "test-model"


async def test_citations_built_from_retrieved_chunks(monkeypatch):
    async def _chunks(query, session, top_k=5, min_score=None):
        return [
            RetrievedChunk(chunk_text="Paris is the capital.", source_file="geo.txt", chunk_index=0, score=0.91),
        ]

    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", _chunks)
    monkeypatch.setattr(graph_mod.ollama_service, "chat_stream", _fake_stream)

    _, final = await _run(_base_state())

    citations = final["metadata"]["citations"]
    assert final["metadata"]["chunks_retrieved"] == 1
    assert len(citations) == 1
    assert citations[0]["source_file"] == "geo.txt"
    assert citations[0]["chunk_index"] == 0
    assert citations[0]["score"] == pytest.approx(0.91)
    assert citations[0]["text"] == "Paris is the capital."


async def test_messages_array_has_system_history_and_user(monkeypatch):
    captured = {}

    async def _capture_stream(messages, model):
        captured["messages"] = messages
        for tok in ["ok"]:
            yield tok

    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", _no_chunks)
    monkeypatch.setattr(graph_mod.ollama_service, "chat_stream", _capture_stream)

    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    await _run(_base_state(history=history, user_message="new question"))

    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert "You are Loomin" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "earlier question"}
    assert msgs[2] == {"role": "assistant", "content": "earlier answer"}
    assert msgs[-1]["role"] == "user"
    assert "new question" in msgs[-1]["content"]


async def test_generation_error_still_finalizes(monkeypatch):
    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", _no_chunks)
    monkeypatch.setattr(graph_mod.ollama_service, "chat_stream", _boom_stream)

    tokens, final = await _run(_base_state())

    assert any(t.startswith("[Error:") for t in tokens)
    assert final is not None  # a final frame is always emitted
    assert "metadata" in final
    # Metadata is fully populated even on a generation error (matches legacy)
    assert "request_id" in final["metadata"]
    assert final["metadata"]["citations"] == []


async def test_prep_failure_propagates_not_swallowed(monkeypatch):
    """Backward-compat guard: a retrieval failure must raise (→ HTTP 500),
    not degrade into a 200 SSE stream with a blank persisted message."""

    async def _boom_retrieve(query, session, top_k=5, min_score=None):
        raise RuntimeError("faiss index missing")

    monkeypatch.setattr(graph_mod, "retrieve_relevant_chunks", _boom_retrieve)

    with pytest.raises(RuntimeError, match="faiss index missing"):
        await graph_mod.prepare_chat_state(_base_state())
