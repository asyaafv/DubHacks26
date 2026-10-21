"""CORS: the extension and local dashboards must pass preflight.

Starlette matches ``allow_origins`` entries literally (no ``*`` globbing), so
origins with variable parts (extension ids, localhost ports) must be covered
by ``allow_origin_regex``. These tests pin that behavior.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.app.main import BASE_CORS_ORIGIN_REGEX, app, build_cors_config


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/inbound",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )


@pytest.mark.parametrize(
    "origin",
    [
        "chrome-extension://abcdefghijklmnop",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost",
    ],
)
def test_allowed_origins_pass_preflight(client: TestClient, origin: str) -> None:
    resp = _preflight(client, origin)
    assert resp.status_code == 200, resp.text
    assert resp.headers["access-control-allow-origin"] == origin


def test_unknown_origin_rejected(client: TestClient) -> None:
    resp = _preflight(client, "https://evil.example.com")
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


def test_simple_get_carries_cors_header(client: TestClient) -> None:
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


# ---------------------------------------------------------------------------
# CORS_EXTRA_ORIGINS / CORS_EXTRA_ORIGIN_REGEX (deploy-specific origins)
# ---------------------------------------------------------------------------


def test_build_cors_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_EXTRA_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_EXTRA_ORIGIN_REGEX", raising=False)
    origins, regex = build_cors_config()
    assert origins == []
    assert regex == BASE_CORS_ORIGIN_REGEX


def test_build_cors_config_parses_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_EXTRA_ORIGINS",
        " https://dash.example.com, https://other.example.com ,",
    )
    monkeypatch.setenv("CORS_EXTRA_ORIGIN_REGEX", r"https://.*\.sslip\.io")
    origins, regex = build_cors_config()
    assert origins == ["https://dash.example.com", "https://other.example.com"]
    assert regex == BASE_CORS_ORIGIN_REGEX + r"|https://.*\.sslip\.io"


def _app_from_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    """Build a fresh app with the middleware configured from the given env."""
    monkeypatch.delenv("CORS_EXTRA_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_EXTRA_ORIGIN_REGEX", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    origins, regex = build_cors_config()

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return TestClient(test_app)


def test_extra_exact_origin_passes_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app_from_env(
        monkeypatch,
        CORS_EXTRA_ORIGINS="https://dash.172-234-249-8.sslip.io",
    )
    resp = _preflight(client, "https://dash.172-234-249-8.sslip.io")
    assert resp.status_code == 200, resp.text
    assert (
        resp.headers["access-control-allow-origin"]
        == "https://dash.172-234-249-8.sslip.io"
    )
    # Defaults are still honored alongside the extras.
    resp = _preflight(client, "http://localhost:5173")
    assert resp.status_code == 200
    # Other origins remain rejected.
    resp = _preflight(client, "https://evil.example.com")
    assert resp.status_code == 400


def test_extra_origin_regex_passes_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app_from_env(
        monkeypatch,
        CORS_EXTRA_ORIGIN_REGEX=r"https://([a-z0-9-]+\.)*172-234-249-8\.sslip\.io",
    )
    for origin in (
        "https://dash.172-234-249-8.sslip.io",
        "https://172-234-249-8.sslip.io",
    ):
        resp = _preflight(client, origin)
        assert resp.status_code == 200, (origin, resp.text)
        assert resp.headers["access-control-allow-origin"] == origin
    resp = _preflight(client, "https://evil.example.com")
    assert resp.status_code == 400


def test_both_extras_combine(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app_from_env(
        monkeypatch,
        CORS_EXTRA_ORIGINS="https://dash.example.com",
        CORS_EXTRA_ORIGIN_REGEX=r"https://.*\.preview\.example\.com",
    )
    for origin in (
        "https://dash.example.com",
        "https://pr-42.preview.example.com",
        "chrome-extension://abcdefghijklmnop",
    ):
        resp = _preflight(client, origin)
        assert resp.status_code == 200, (origin, resp.text)
