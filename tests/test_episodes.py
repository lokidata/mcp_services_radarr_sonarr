"""Tests for the get_episodes tool."""

import json
from unittest.mock import MagicMock, patch

from radarr_sonarr_mcp.config import Config
from radarr_sonarr_mcp.server import RadarrSonarrMCPServer
from radarr_sonarr_mcp.services.sonarr_service import Episode, Series


def _series(id, title):
    return Series(id=id, title=title, year=2022, overview="", status="", network="",
                  tags=[], genres=[], statistics=None, data={})


def _episode(season, number, has_file=True):
    return Episode(id=season * 100 + number, series_id=1, episode_file_id=None,
                   season_number=season, episode_number=number, title=f"E{number}",
                   air_date=None, has_file=has_file, monitored=True, overview="", data={})


def _build(emby_map=None):
    config = Config.from_dict({"embyConfig": {"baseUrl": "emby", "apiKey": "k", "userId": "u"}}) \
        if emby_map is not None else Config()
    with patch("radarr_sonarr_mcp.server.FastMCP") as fastmcp, \
            patch("radarr_sonarr_mcp.server.SonarrService") as sonarr, \
            patch("radarr_sonarr_mcp.server.RadarrService"), \
            patch("radarr_sonarr_mcp.server.EmbyService") as emby:
        server = RadarrSonarrMCPServer(config)
    sonarr.return_value.get_all_series.return_value = [_series(1, "Slow Horses"), _series(2, "Slow Horses Extra")]
    sonarr.return_value.get_episodes.return_value = [_episode(1, 1), _episode(6, 2), _episode(6, 1, has_file=False)]
    if emby_map is not None:
        emby.return_value.get_watched_episodes.return_value = emby_map
    tool = next(c.args[0] for c in fastmcp.return_value.tool.return_value.call_args_list
                if c.args[0].__name__ == "get_episodes")
    return tool


WATCHED = {(1, 1): True, (6, 2): False, (6, 1): False}


def test_episodes_with_watched_status():
    result = json.loads(_build(WATCHED)("Slow Horses"))
    assert [(e["season"], e["episode"], e["watched"]) for e in result["episodes"]] == [
        (1, 1, True), (6, 1, False), (6, 2, False)]


def test_filters():
    tool = _build(WATCHED)
    assert [e["episode"] for e in json.loads(tool("Slow Horses", season=6))["episodes"]] == [1, 2]
    assert json.loads(tool("Slow Horses", watched=True))["count"] == 1
    assert [e["episode"] for e in json.loads(tool("Slow Horses", season=6, downloaded=True))["episodes"]] == [2]


def test_watched_is_null_without_media_service():
    result = json.loads(_build()("Slow Horses"))
    assert all(e["watched"] is None for e in result["episodes"])


def test_unknown_and_ambiguous_series():
    tool = _build(WATCHED)
    assert json.loads(tool("Nope"))["error"] == "series not found"
    assert json.loads(tool("slow"))["error"] == "ambiguous series title"
