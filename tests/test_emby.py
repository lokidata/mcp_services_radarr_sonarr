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


def test_normalize_url():
    from radarr_sonarr_mcp.config import normalize_url
    assert normalize_url("192.168.1.10", 8096) == "http://192.168.1.10:8096"
    assert normalize_url("emby.local:9000/", 8096) == "http://emby.local:9000"
    assert normalize_url("https://emby.example.com", 8096) == "https://emby.example.com:8096"
    assert normalize_url("", 8096) == ""


def test_emby_url_normalized_from_config():
    cfg = Config.from_dict({"embyConfig": {"baseUrl": "192.168.1.253", "apiKey": "k", "userId": "u"}})
    assert cfg.emby_config.base_url == "http://192.168.1.253:8096"


def test_episode_watched_uses_played_flag():
    service = EmbyService(_config().emby_config)
    episodes = [
        {"ParentIndexNumber": 1, "IndexNumber": 1, "UserData": {"Played": True, "PlayCount": 0}},
        {"ParentIndexNumber": 6, "IndexNumber": 2, "UserData": {"Played": False, "PlayCount": 0}},
    ]
    with patch.object(EmbyService, "search_series", return_value=[{"Id": "1"}]), \
            patch.object(EmbyService, "get_episodes_for_series", return_value=episodes):
        assert service.is_episode_watched("Slow Horses", 1, 1)
        assert not service.is_episode_watched("Slow Horses", 6, 2)
        assert not service.is_episode_watched("Slow Horses", 9, 9)


def _service():
    return EmbyService(_config().emby_config)


def test_find_series_by_tvdb_id_beats_title():
    index = {"12345": {"Id": "A", "Name": "Titre traduit"}}
    with patch.object(EmbyService, "_series_by_tvdb", return_value=index), \
            patch.object(EmbyService, "search_series") as search:
        assert _service().find_series("Original Title", 12345)["Id"] == "A"
        search.assert_not_called()


def test_find_series_falls_back_to_title():
    with patch.object(EmbyService, "_series_by_tvdb", return_value={}), \
            patch.object(EmbyService, "search_series", return_value=[{"Id": "B"}]):
        assert _service().find_series("Title", 999)["Id"] == "B"
        assert _service().find_series("Title")["Id"] == "B"


def test_tvdb_index_is_cached():
    payload = {"Items": [{"Id": "1", "ProviderIds": {"Tvdb": "42"}}, {"Id": "2", "ProviderIds": {}}]}
    service = _service()
    with patch("radarr_sonarr_mcp.services.jellyfin_service.requests.get") as get:
        get.return_value.json.return_value = payload
        assert list(service._series_by_tvdb()) == ["42"]
        service._series_by_tvdb()
        assert get.call_count == 1


def test_configure_keeps_media_servers(tmp_path, monkeypatch):
    from radarr_sonarr_mcp import cli
    from radarr_sonarr_mcp.config import save_config, load_config
    path = str(tmp_path / "config.json")
    save_config(_config(), path)
    monkeypatch.setenv("RADARR_SONARR_MCP_CONFIG", path)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    cli.configure()
    assert load_config(path).emby_config.api_key == "k"
