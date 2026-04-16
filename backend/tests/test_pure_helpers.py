"""Unit tests for pure helpers added alongside the quality pass."""
from __future__ import annotations

from app.services.conversation_titler import _sanitize_title
from app.services.parsers.pdf_parser import clean_ocr_text
from app.services.query_processor import _is_enumeration_query
from app.services.rag import _format_source_header


def test_sanitize_title_strips_quotes_and_trailing_period():
    assert _sanitize_title('"My Chat."') == "My Chat"
    assert _sanitize_title("'thing'") == "thing"
    assert _sanitize_title("Title: Hello World") == "Hello World"


def test_sanitize_title_collapses_whitespace_and_clamps_length():
    raw = "A   very\nlong\ntitle" + "x" * 500
    result = _sanitize_title(raw)
    assert "\n" not in result
    assert "   " not in result
    assert len(result) <= 120


def test_sanitize_title_keeps_question_mark():
    assert _sanitize_title("Who wrote this?") == "Who wrote this?"


def test_clean_ocr_text_dehyphenates_line_breaks():
    assert clean_ocr_text("exam-\nple word") == "example word"


def test_clean_ocr_text_drops_noise_lines():
    raw = "Real content here\n===============\n|||||\nMore content"
    result = clean_ocr_text(raw)
    assert "Real content here" in result
    assert "More content" in result
    assert "===" not in result
    assert "|||" not in result


def test_clean_ocr_text_handles_empty():
    assert clean_ocr_text("") == ""
    assert clean_ocr_text(None) == ""  # type: ignore[arg-type]


def test_format_source_header_includes_available_metadata():
    chunk = {
        "doc_name": "Gulliver's Travels",
        "section_heading": "Part I, Chapter 2",
        "page_number": 14,
    }
    header = _format_source_header(3, chunk)
    assert header.startswith("[Source 3 — ")
    assert "Gulliver's Travels" in header
    assert "Part I, Chapter 2" in header
    assert "p. 14" in header


def test_format_source_header_ocr_tag():
    chunk = {"doc_name": "Scan.pdf", "source_type": "ocr_low_conf"}
    header = _format_source_header(1, chunk)
    assert "[ocr_low_conf]" in header


def test_format_source_header_minimal():
    # Should still work when only the index is known.
    assert _format_source_header(2, {}) == "[Source 2]"


def test_enumeration_query_detection_variants():
    assert _is_enumeration_query("Who are all the characters in this novel?")
    assert _is_enumeration_query("List the characters and their roles.")
    assert _is_enumeration_query("Name all people mentioned in this chapter.")


def test_non_enumeration_query_detection():
    assert not _is_enumeration_query("What is the main conflict in this story?")
