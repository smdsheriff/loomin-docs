"""Tests for the shared RAG prompt builder.

These lock down the exact prompt text so the legacy pipeline and the LangGraph
pipeline — which both call ``build_rag_prompt`` — cannot silently diverge.
"""

from app.rag.prompting import build_rag_prompt


def test_no_files_and_no_document():
    prompt = build_rag_prompt("What is the capital?", [], available_files=[], document_content=None)
    assert "has not uploaded any files" in prompt
    assert "Do NOT answer from your own knowledge" in prompt
    assert prompt.endswith("Question: What is the capital?")


def test_files_present_but_no_relevant_chunks():
    files = [{"name": "notes.txt", "type": ".txt", "chunks": 3}]
    prompt = build_rag_prompt("Unrelated question?", [], available_files=files, document_content=None)
    assert "No relevant content was found" in prompt
    assert "Uploaded files available:" in prompt
    assert "notes.txt (.txt, 3 chunks)" in prompt


def test_chunks_are_numbered_and_cited():
    chunks = [
        {"chunk_text": "Paris is the capital of France.", "source_file": "geo.txt", "chunk_index": 0, "score": 0.9},
        {"chunk_text": "France is in Europe.", "source_file": "geo.txt", "chunk_index": 1, "score": 0.7},
    ]
    prompt = build_rag_prompt("Where is the capital?", chunks, available_files=None, document_content=None)
    assert "[Source 1: geo.txt (chunk 0)]" in prompt
    assert "[Source 2: geo.txt (chunk 1)]" in prompt
    assert "Cite sources using [Source N] notation" in prompt
    assert "Question: Where is the capital?" in prompt


def test_document_content_is_html_stripped_and_truncated():
    html = "<h1>Title</h1><p>" + ("word " * 1000) + "</p>"
    prompt = build_rag_prompt("Summarize", [], available_files=None, document_content=html)
    assert "--- CURRENT DOCUMENT ---" in prompt
    assert "<h1>" not in prompt and "<p>" not in prompt
    assert "... [truncated]" in prompt


def test_document_content_short_is_not_truncated():
    prompt = build_rag_prompt("Q", [], available_files=None, document_content="<p>hello world</p>")
    assert "hello world" in prompt
    assert "[truncated]" not in prompt
