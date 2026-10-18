"""Tests for backend/extraction/gliner_extract.py.

Model-dependent tests skip gracefully when gliner2 isn't installed or the
model can't be downloaded. A tiny local .eml -> text helper is used here
(clean.py is owned by another agent and may not be merged yet).
"""
from __future__ import annotations

import time
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

import pytest

from backend.extraction import gliner_extract
from backend.extraction.gliner_extract import extract_fields
from backend.extraction.types import FieldCandidates, FieldValue

EMAILS_DIR = Path(__file__).resolve().parents[3] / "shared" / "seed" / "emails"


class _HTMLToText(HTMLParser):
    """Minimal HTML-to-text for tests only."""

    _SKIP = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def eml_to_text(path: Path) -> str:
    """Extract subject + plain text (or HTML converted to text) from an .eml file."""
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = msg.get_body(preferencelist=("plain",))
    if body is not None:
        text = body.get_content()
    else:
        html_body = msg.get_body(preferencelist=("html",))
        parser = _HTMLToText()
        parser.feed(html_body.get_content() if html_body else "")
        text = "\n".join(parser.parts)
    return f"{msg['Subject']}\n\n{text}"


def _model_or_skip():
    model = gliner_extract._get_model()
    if model is None:
        pytest.skip("gliner2 not installed or model could not be downloaded")
    return model


# ---------------------------------------------------------------------------
# Tests that never need the model
# ---------------------------------------------------------------------------


def test_empty_text_returns_empty_candidates():
    result = extract_fields("")
    assert result == FieldCandidates()


def test_returns_empty_candidates_when_model_unavailable(monkeypatch):
    monkeypatch.setattr(gliner_extract, "_get_model", lambda: None)
    result = extract_fields("Get 10% off with code SAVE10!")
    assert result == FieldCandidates()


def test_model_load_failure_never_raises(monkeypatch):
    monkeypatch.setattr(gliner_extract, "_model", None)
    monkeypatch.setattr(gliner_extract, "_model_load_failed", False)
    monkeypatch.setattr(gliner_extract, "MODEL_ID", "fastino/does-not-exist-xyz")
    result = extract_fields("Get 10% off with code SAVE10!")
    assert result == FieldCandidates()
    assert gliner_extract._model_load_failed is True


def test_chunking_long_text():
    words = ["word"] * 2000
    chunks = gliner_extract._chunk_text(" ".join(words))
    assert 1 < len(chunks) <= gliner_extract.MAX_CHUNKS
    assert all(len(c.split()) <= gliner_extract.CHUNK_WORDS for c in chunks)


def test_stackable_mapping():
    fv = gliner_extract._stackable_from_span(
        [("cannot be combined with other offers", 0.9)]
    )
    assert fv is not None and fv.value == "false"
    fv = gliner_extract._stackable_from_span(
        [("stackable with other offers", 0.8)]
    )
    assert fv is not None and fv.value == "true"
    assert gliner_extract._stackable_from_span([]) is None


# ---------------------------------------------------------------------------
# Model-dependent tests on seed emails (skip if model unavailable)
# ---------------------------------------------------------------------------


def test_extract_fields_hollister_seed_email():
    _model_or_skip()
    text = eml_to_text(EMAILS_DIR / "hollister_10_percent.eml")

    start = time.perf_counter()
    result = extract_fields(text)
    latency_ms = (time.perf_counter() - start) * 1000
    print(f"\nhollister_10_percent latency: {latency_ms:.0f}ms\nresult: {result}")

    assert isinstance(result, FieldCandidates)
    assert result.code is not None, "expected a promo code span"
    assert "HCOFALL10" in result.code.value
    assert result.discount_value is not None
    assert "10" in result.discount_value.value
    for fv in [
        result.merchant,
        result.discount_value,
        result.min_spend,
        result.expiry,
        result.code,
        result.stackable,
        *result.exclusions,
    ]:
        if fv is not None:
            assert isinstance(fv, FieldValue)
            assert fv.source == "gliner"
            assert 0.0 <= fv.confidence <= 1.0


def test_extract_fields_chipotle_seed_email():
    _model_or_skip()
    text = eml_to_text(EMAILS_DIR / "chipotle_plaintext.eml")

    start = time.perf_counter()
    result = extract_fields(text)
    latency_ms = (time.perf_counter() - start) * 1000
    print(f"\nchipotle_plaintext latency: {latency_ms:.0f}ms\nresult: {result}")

    assert result.code is not None
    assert "FREEGUAC" in result.code.value
    # "This reward is stackable with other offers!"
    assert result.stackable is not None
    assert result.stackable.value == "true"
