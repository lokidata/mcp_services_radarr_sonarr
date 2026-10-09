"""Tests for Emby support."""

from unittest.mock import patch, MagicMock

from radarr_sonarr_mcp.config import Config
from radarr_sonarr_mcp.server import RadarrSonarrMCPServer
from radarr_sonarr_mcp.services.emby_service import EmbyService


def _config():
    return Config.from_dict({
        "embyConfig": {"baseUrl": "http://emby:8096", "apiKey": "k", "userId": "u"},
    })


def test_config_roundtrip():
    cfg = _config()
    assert cfg.emby_config.enabled
    assert Config.from_dict(cfg.to_dict()).emby_config.user_id == "u"


def test_env_config(monkeypatch):
    monkeypatch.setenv("EMBY_BASE_URL", "http://emby:8096")
    assert Config.from_env().emby_config.base_url == "http://emby:8096"


@patch("radarr_sonarr_mcp.server.FastMCP")
def test_emby_reports_watched(_):
    server = RadarrSonarrMCPServer(_config())
    assert isinstance(server.emby, EmbyService)
    movie = MagicMock(title="Movie")
    with patch.object(EmbyService, "is_movie_watched", return_value=True):
        assert server.is_watched_movie(movie)


@patch("radarr_sonarr_mcp.server.FastMCP")
def test_emby_disabled_by_default(_):
    assert RadarrSonarrMCPServer(Config()).emby is None
