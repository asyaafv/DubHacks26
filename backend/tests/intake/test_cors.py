"""CORS: the extension and local dashboards must pass preflight.

Starlette matches ``allow_origins`` entries literally (no ``*`` globbing), so
origins with variable parts (extension ids, localhost ports) must be covered
by ``allow_origin_regex``. These tests pin that behavior.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


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
