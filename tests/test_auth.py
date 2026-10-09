"""Tests for the HTTP API key authentication."""

from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from radarr_sonarr_mcp.auth import ApiKeyMiddleware
from radarr_sonarr_mcp.config import Config, ConfigError
from radarr_sonarr_mcp.server import RadarrSonarrMCPServer

KEY = "k" * 32


def _client():
    app = Starlette(
        routes=[Route("/mcp", lambda request: PlainTextResponse("ok"), methods=["GET", "POST"])],
        middleware=[Middleware(ApiKeyMiddleware, api_key=KEY)],
    )
    return TestClient(app)


def test_rejects_missing_key():
    with _client() as client:
        response = client.get("/mcp")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert "Bearer" in response.headers["www-authenticate"]


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer wrong"},
    {"Authorization": KEY},                    # no Bearer prefix
    {"Authorization": f"Basic {KEY}"},
    {"X-API-Key": "wrong"},
    {"X-API-Key": KEY + "x"},
    {"X-API-Key": ""},
])
def test_rejects_wrong_key(headers):
    with _client() as client:
        assert client.get("/mcp", headers=headers).status_code == 401


@pytest.mark.parametrize("headers", [
    {"Authorization": f"Bearer {KEY}"},
    {"Authorization": f"bearer {KEY}"},
    {"X-API-Key": KEY},
])
def test_accepts_correct_key(headers):
    with _client() as client:
        response = client.post("/mcp", headers=headers)
    assert response.status_code == 200 and response.text == "ok"


def test_key_is_not_accepted_in_query_string():
    with _client() as client:
        assert client.get(f"/mcp?api_key={KEY}").status_code == 401


def _server(**server):
    with patch("radarr_sonarr_mcp.server.FastMCP") as fastmcp:
        instance = RadarrSonarrMCPServer(Config.from_dict({"server": server}))
    return instance, fastmcp.return_value


def test_http_refuses_to_start_without_key():
    instance, mcp = _server()
    with pytest.raises(ConfigError, match="API key"):
        instance.start("http")
    mcp.run.assert_not_called()


def test_http_refuses_short_key():
    instance, mcp = _server(apiKey="short")
    with pytest.raises(ConfigError, match="at least"):
        instance.start("http")
    mcp.run.assert_not_called()


def test_http_starts_with_key_middleware_and_allowed_hosts():
    instance, mcp = _server(apiKey=KEY, allowedHosts=["mcp.example.com"])
    instance.start("http")
    kwargs = mcp.run.call_args.kwargs
    assert kwargs["allowed_hosts"] == ["mcp.example.com"]
    assert kwargs["middleware"][0].cls is ApiKeyMiddleware
    assert kwargs["middleware"][0].kwargs["api_key"] == KEY


def test_opt_out_requires_explicit_flag():
    instance, mcp = _server(allowNoAuth=True)
    instance.start("http")
    assert "middleware" not in mcp.run.call_args.kwargs


def test_stdio_needs_no_key():
    instance, mcp = _server()
    instance.start("stdio")
    mcp.run.assert_called_once_with()


def test_env_config(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", KEY)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "a.example.com, b.example.com")
    monkeypatch.setenv("MCP_ALLOW_NO_AUTH", "true")
    cfg = Config.from_env().server_config
    assert cfg.api_key == KEY and cfg.allow_no_auth
    assert cfg.allowed_hosts == ["a.example.com", "b.example.com"]
