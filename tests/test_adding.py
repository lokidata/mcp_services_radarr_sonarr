"""Tests for adding movies and series to Radarr and Sonarr."""

import json
from unittest.mock import MagicMock, patch

import pytest

from radarr_sonarr_mcp.adding import (
    AddError,
    is_anime,
    movie_payload,
    resolve_profile,
    resolve_root_folder,
    series_payload,
)
from radarr_sonarr_mcp.config import Config
from radarr_sonarr_mcp.server import RadarrSonarrMCPServer
from radarr_sonarr_mcp.services.arr_http import ArrError
from radarr_sonarr_mcp.services.radarr_service import Movie, RadarrService
from radarr_sonarr_mcp.services.sonarr_service import Series, SonarrService

PROFILES = [{"id": 1, "name": "Any"}, {"id": 4, "name": "HD-1080p"}]
FOLDERS = [
    {"id": 13, "path": "/data/concerts", "freeSpace": 10},
    {"id": 14, "path": "/data/movies", "freeSpace": 10},
]


# --- configuration -----------------------------------------------------------

def test_defaults_and_read_only_from_env(monkeypatch):
    monkeypatch.setenv("RADARR_DEFAULT_QUALITY_PROFILE", "HD-1080p")
    monkeypatch.setenv("RADARR_DEFAULT_ROOT_FOLDER", "/data/movies")
    monkeypatch.setenv("SONARR_DEFAULT_QUALITY_PROFILE", "Any")
    monkeypatch.setenv("SONARR_DEFAULT_ROOT_FOLDER", "/data/tv")
    monkeypatch.setenv("MCP_READ_ONLY", "true")
    cfg = Config.from_env()
    assert cfg.radarr_config.default_quality_profile == "HD-1080p"
    assert cfg.radarr_config.default_root_folder == "/data/movies"
    assert cfg.sonarr_config.default_quality_profile == "Any"
    assert cfg.sonarr_config.default_root_folder == "/data/tv"
    assert cfg.server_config.read_only is True


def test_defaults_and_read_only_roundtrip_in_file():
    cfg = Config.from_dict({
        "radarrConfig": {"defaultQualityProfile": "HD-1080p", "defaultRootFolder": "/data/movies"},
        "server": {"readOnly": True},
    })
    again = Config.from_dict(cfg.to_dict())
    assert again.radarr_config.default_quality_profile == "HD-1080p"
    assert again.radarr_config.default_root_folder == "/data/movies"
    assert again.server_config.read_only is True


def test_writes_enabled_by_default():
    assert Config().server_config.read_only is False


# --- choosing a profile / folder ---------------------------------------------

def test_profile_by_name_ignores_case():
    assert resolve_profile(PROFILES, "hd-1080p", "")["id"] == 4


def test_profile_by_id():
    assert resolve_profile(PROFILES, "4", "")["name"] == "HD-1080p"


def test_profile_falls_back_to_configured_default():
    assert resolve_profile(PROFILES, None, "Any")["id"] == 1


def test_profile_single_choice_is_used():
    assert resolve_profile([PROFILES[0]], None, "")["id"] == 1


def test_profile_ambiguous_lists_the_options():
    with pytest.raises(AddError) as error:
        resolve_profile(PROFILES, None, "")
    assert "quality profile" in str(error.value)
    assert error.value.options == ["Any", "HD-1080p"]


def test_profile_unknown_lists_the_options():
    with pytest.raises(AddError) as error:
        resolve_profile(PROFILES, "4K", "")
    assert error.value.options == ["Any", "HD-1080p"]


def test_root_folder_by_path_tolerates_trailing_slash():
    assert resolve_root_folder(FOLDERS, "/data/movies/", "")["id"] == 14


def test_root_folder_default_and_ambiguity():
    assert resolve_root_folder(FOLDERS, None, "/data/concerts")["id"] == 13
    with pytest.raises(AddError) as error:
        resolve_root_folder(FOLDERS, None, "")
    assert error.value.options == ["/data/concerts", "/data/movies"]


def test_configured_default_that_does_not_exist_is_an_error():
    with pytest.raises(AddError):
        resolve_root_folder(FOLDERS, None, "/data/gone")


# --- payloads ----------------------------------------------------------------

LOOKUP_MOVIE = {"id": None, "title": "Matrix", "tmdbId": 603, "year": 1999,
                "monitored": False, "qualityProfileId": 0, "minimumAvailability": "tba"}


def test_movie_payload_sets_what_radarr_requires():
    payload = movie_payload(LOOKUP_MOVIE, PROFILES[1], FOLDERS[1], monitored=True, search_now=False)
    assert payload["tmdbId"] == 603 and payload["title"] == "Matrix"
    assert payload["qualityProfileId"] == 4
    assert payload["rootFolderPath"] == "/data/movies"
    assert payload["monitored"] is True
    assert payload["minimumAvailability"] == "released"
    assert payload["addOptions"]["searchForMovie"] is False
    assert "id" not in payload
    assert LOOKUP_MOVIE["qualityProfileId"] == 0  # the lookup resource is not mutated


def test_movie_payload_search_now():
    payload = movie_payload(LOOKUP_MOVIE, PROFILES[0], FOLDERS[0], monitored=True, search_now=True)
    assert payload["addOptions"]["searchForMovie"] is True


LOOKUP_SERIES = {"id": 0, "title": "Slow Horses", "tvdbId": 1, "seriesType": "standard",
                 "seasonFolder": True, "monitored": False, "seasons": [{"seasonNumber": 1}]}


def test_series_payload_sets_what_sonarr_requires():
    payload = series_payload(LOOKUP_SERIES, PROFILES[1], FOLDERS[1], monitor="all",
                             series_type=None, search_now=False)
    assert payload["tvdbId"] == 1 and payload["title"] == "Slow Horses"
    assert payload["qualityProfileId"] == 4
    assert payload["rootFolderPath"] == "/data/movies"
    assert payload["monitored"] is True
    assert payload["seriesType"] == "standard"
    assert payload["addOptions"]["monitor"] == "all"
    assert payload["addOptions"]["searchForMissingEpisodes"] is False
    assert "id" not in payload


def test_series_payload_options():
    payload = series_payload(LOOKUP_SERIES, PROFILES[0], FOLDERS[0], monitor="none",
                             series_type="anime", search_now=True)
    assert payload["monitored"] is False
    assert payload["seriesType"] == "anime"
    assert payload["addOptions"]["monitor"] == "none"
    assert payload["addOptions"]["searchForMissingEpisodes"] is True


@pytest.mark.parametrize("monitor", ["", "everything", "unknown", "skip"])
def test_series_payload_rejects_unknown_monitor(monitor):
    with pytest.raises(AddError) as error:
        series_payload(LOOKUP_SERIES, PROFILES[0], FOLDERS[0], monitor=monitor,
                       series_type=None, search_now=False)
    assert "all" in error.value.options


def test_series_payload_rejects_unknown_type():
    with pytest.raises(AddError):
        series_payload(LOOKUP_SERIES, PROFILES[0], FOLDERS[0], monitor="all",
                       series_type="cartoon", search_now=False)


# --- HTTP layer of the services ----------------------------------------------

def _response(status=200, body=None, text=""):
    response = MagicMock(status_code=status, text=text)
    response.ok = status < 400
    response.json.return_value = body
    return response


def _radarr():
    return RadarrService(Config.from_dict({"radarrConfig": {"apiKey": "key"}}).radarr_config)


def test_service_lists_root_folders_with_the_key_in_a_header():
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(body=FOLDERS)) as request:
        assert _radarr().get_root_folders() == FOLDERS
    args, kwargs = request.call_args
    assert args[0] == "GET" and args[1].endswith("/rootfolder")
    assert kwargs["headers"] == {"X-Api-Key": "key"}
    assert "apikey" not in (kwargs.get("params") or {})


def test_service_adds_a_movie_with_a_post():
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(201, {"id": 7, "title": "Matrix"})) as request:
        added = _radarr().add_movie({"tmdbId": 603})
    args, kwargs = request.call_args
    assert args[0] == "POST" and args[1].endswith("/movie")
    assert kwargs["json"] == {"tmdbId": 603}
    assert added["id"] == 7


def test_service_reports_radarr_validation_messages():
    errors = [{"propertyName": "RootFolderPath", "errorMessage": "Path does not exist"}]
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(400, errors, text=json.dumps(errors))):
        with pytest.raises(ArrError, match="RootFolderPath: Path does not exist"):
            _radarr().add_movie({})


def test_service_reports_unreachable_server():
    import requests
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               side_effect=requests.ConnectionError("refused")):
        with pytest.raises(ArrError, match="Cannot reach"):
            _radarr().get_quality_profiles()


def test_lookup_movie_by_tmdb_returns_the_raw_resource():
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(body=LOOKUP_MOVIE)) as request:
        assert _radarr().lookup_movie_by_tmdb(603) == LOOKUP_MOVIE
    assert request.call_args.args[1].endswith("/movie/lookup/tmdb")
    assert request.call_args.kwargs["params"] == {"tmdbId": 603}


def test_lookup_series_by_tvdb_uses_the_tvdb_term_and_checks_the_id():
    sonarr = SonarrService(Config.from_dict({"sonarrConfig": {"apiKey": "key"}}).sonarr_config)
    results = [{"tvdbId": 2, "title": "Other"}, LOOKUP_SERIES]
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(body=results)) as request:
        assert sonarr.lookup_series_by_tvdb(1) == LOOKUP_SERIES
        assert request.call_args.kwargs["params"] == {"term": "tvdb:1"}
    with patch("radarr_sonarr_mcp.services.arr_http.requests.request",
               return_value=_response(body=[])):
        assert sonarr.lookup_series_by_tvdb(1) is None


# --- MCP tools ---------------------------------------------------------------

def _movie(id=1, tmdb_id=603, title="Matrix"):
    return Movie(id=id, title=title, year=1999, overview="", has_file=False, status="",
                 tags=[], genres=[], data={}, tmdb_id=tmdb_id)


def _series(id=1, tvdb_id=1, title="Slow Horses"):
    return Series(id=id, title=title, year=2022, overview="", status="", network="", tags=[],
                  genres=[], statistics=None, data={}, tvdb_id=tvdb_id)


def _tools(config=None):
    config = config or Config.from_dict({"radarrConfig": {"defaultRootFolder": "/data/movies",
                                                          "defaultQualityProfile": "HD-1080p"},
                                         "sonarrConfig": {"defaultRootFolder": "/data/movies",
                                                          "defaultQualityProfile": "HD-1080p"}})
    with patch("radarr_sonarr_mcp.server.FastMCP") as fastmcp, \
            patch("radarr_sonarr_mcp.server.SonarrService") as sonarr, \
            patch("radarr_sonarr_mcp.server.RadarrService") as radarr:
        RadarrSonarrMCPServer(config)
    tools = {c.args[0].__name__: c.args[0]
             for c in fastmcp.return_value.tool.return_value.call_args_list}
    radarr, sonarr = radarr.return_value, sonarr.return_value
    radarr.get_root_folders.return_value = FOLDERS
    radarr.get_quality_profiles.return_value = PROFILES
    radarr.get_all_movies.return_value = [_movie(tmdb_id=1)]
    radarr.lookup_movie_by_tmdb.return_value = dict(LOOKUP_MOVIE)
    radarr.add_movie.return_value = {"id": 9, "title": "Matrix", "year": 1999}
    sonarr.get_root_folders.return_value = FOLDERS
    sonarr.get_quality_profiles.return_value = PROFILES
    sonarr.get_all_series.return_value = [_series(tvdb_id=99)]
    sonarr.lookup_series_by_tvdb.return_value = dict(LOOKUP_SERIES)
    sonarr.add_series.return_value = {"id": 5, "title": "Slow Horses", "year": 2022}
    return tools, radarr, sonarr


def test_get_add_options_lists_folders_and_profiles_of_both_services():
    tools, _, _ = _tools()
    result = json.loads(tools["get_add_options"]())
    assert result["radarr"]["rootFolders"][1] == {"path": "/data/movies", "freeSpace": 10}
    assert result["radarr"]["qualityProfiles"] == [{"id": 1, "name": "Any"}, {"id": 4, "name": "HD-1080p"}]
    assert result["sonarr"]["qualityProfiles"][0]["name"] == "Any"


def test_add_movie_uses_configured_defaults_and_does_not_search():
    tools, radarr, _ = _tools()
    result = json.loads(tools["add_movie"](603))
    payload = radarr.add_movie.call_args.args[0]
    assert payload["rootFolderPath"] == "/data/movies" and payload["qualityProfileId"] == 4
    assert payload["addOptions"]["searchForMovie"] is False
    assert result == {"added": {"id": 9, "title": "Matrix", "year": 1999},
                      "qualityProfile": "HD-1080p", "rootFolder": "/data/movies", "searching": False}


def test_add_movie_explicit_choices_and_search():
    tools, radarr, _ = _tools()
    json.loads(tools["add_movie"](603, quality_profile="Any", root_folder="/data/concerts",
                                   monitored=False, search_now=True))
    payload = radarr.add_movie.call_args.args[0]
    assert payload["qualityProfileId"] == 1 and payload["rootFolderPath"] == "/data/concerts"
    assert payload["monitored"] is False and payload["addOptions"]["searchForMovie"] is True


def test_add_movie_refuses_a_duplicate():
    tools, radarr, _ = _tools()
    radarr.get_all_movies.return_value = [_movie(id=3, tmdb_id=603)]
    result = json.loads(tools["add_movie"](603))
    assert result["error"] == "already in library"
    assert result["existing"] == {"id": 3, "title": "Matrix"}
    radarr.add_movie.assert_not_called()


def test_add_movie_unknown_tmdb_id():
    tools, radarr, _ = _tools()
    radarr.lookup_movie_by_tmdb.return_value = None
    assert json.loads(tools["add_movie"](1))["error"] == "movie not found"
    radarr.add_movie.assert_not_called()


def test_add_movie_ambiguous_choice_lists_options_and_adds_nothing():
    config = Config()
    tools, radarr, _ = _tools(config)
    result = json.loads(tools["add_movie"](603))
    assert "quality profile" in result["error"] and result["options"] == ["Any", "HD-1080p"]
    radarr.add_movie.assert_not_called()


def test_add_movie_surfaces_radarr_errors():
    tools, radarr, _ = _tools()
    radarr.add_movie.side_effect = ArrError("RootFolderPath: Path does not exist")
    assert json.loads(tools["add_movie"](603))["error"] == "RootFolderPath: Path does not exist"


def test_add_series_defaults_to_monitoring_everything():
    tools, _, sonarr = _tools()
    result = json.loads(tools["add_series"](1))
    payload = sonarr.add_series.call_args.args[0]
    assert payload["addOptions"]["monitor"] == "all"
    assert payload["addOptions"]["searchForMissingEpisodes"] is False
    assert result["added"]["title"] == "Slow Horses" and result["monitor"] == "all"
    assert result["searching"] is False


def test_add_series_options():
    tools, _, sonarr = _tools()
    json.loads(tools["add_series"](1, monitor="firstSeason", series_type="anime", search_now=True))
    payload = sonarr.add_series.call_args.args[0]
    assert payload["addOptions"]["monitor"] == "firstSeason"
    assert payload["seriesType"] == "anime"
    assert payload["addOptions"]["searchForMissingEpisodes"] is True


def test_add_series_refuses_a_duplicate_and_unknown_id():
    tools, _, sonarr = _tools()
    sonarr.get_all_series.return_value = [_series(id=8, tvdb_id=1)]
    result = json.loads(tools["add_series"](1))
    assert result["error"] == "already in library" and result["existing"]["id"] == 8
    sonarr.get_all_series.return_value = []
    sonarr.lookup_series_by_tvdb.return_value = None
    assert json.loads(tools["add_series"](1))["error"] == "series not found"
    sonarr.add_series.assert_not_called()


def test_add_series_invalid_monitor_adds_nothing():
    tools, _, sonarr = _tools()
    result = json.loads(tools["add_series"](1, monitor="everything"))
    assert "monitor" in result["error"] and "all" in result["options"]
    sonarr.add_series.assert_not_called()


def test_lookups_expose_ids_and_library_status():
    tools, radarr, sonarr = _tools()
    radarr.lookup_movie.return_value = [_movie(id=0, tmdb_id=603), _movie(id=4, tmdb_id=604)]
    movies = json.loads(tools["lookup_movie"]("matrix"))["movies"]
    assert [(m["tmdbId"], m["inLibrary"]) for m in movies] == [(603, False), (604, True)]
    sonarr.lookup_series.return_value = [_series(id=0, tvdb_id=1), _series(id=6, tvdb_id=2)]
    series = json.loads(tools["lookup_series"]("horses"))["series"]
    assert [(s["tvdbId"], s["inLibrary"]) for s in series] == [(1, False), (2, True)]


def test_read_only_mode_registers_no_write_tool():
    tools, _, _ = _tools(Config.from_dict({"server": {"readOnly": True}}))
    assert "add_movie" not in tools and "add_series" not in tools
    assert {"get_add_options", "lookup_movie", "get_episodes"} <= set(tools)


# --- lookup results of items that are not in the library have no id ----------

def test_movie_lookup_result_without_id():
    movie = Movie.from_dict({"title": "Matrix", "tmdbId": 603, "year": 1999})
    assert movie.id == 0 and movie.tmdb_id == 603


def test_series_lookup_result_without_id():
    series = Series.from_dict({"title": "Slow Horses", "tvdbId": 1})
    assert series.id == 0 and series.tvdb_id == 1


def test_series_payload_uses_season_folders_whatever_the_lookup_says():
    resource = dict(LOOKUP_SERIES, seasonFolder=False)  # an unset boolean in a lookup result
    payload = series_payload(resource, PROFILES[0], FOLDERS[0], monitor="all",
                             series_type=None, search_now=False)
    assert payload["seasonFolder"] is True


# --- anime defaults ----------------------------------------------------------

ANIME_RESOURCE = dict(LOOKUP_SERIES, genres=["Animation", "Anime"])
ANIME_CONFIG = {"sonarrConfig": {
    "defaultQualityProfile": "HD-1080p", "defaultRootFolder": "/data/movies",
    "animeDefaultQualityProfile": "Any", "animeDefaultRootFolder": "/data/concerts",
}}


def test_anime_defaults_from_env(monkeypatch):
    monkeypatch.setenv("SONARR_ANIME_DEFAULT_QUALITY_PROFILE", "HD-1080p")
    monkeypatch.setenv("SONARR_ANIME_DEFAULT_ROOT_FOLDER", "/data/anime")
    cfg = Config.from_env().sonarr_config
    assert cfg.anime_default_quality_profile == "HD-1080p"
    assert cfg.anime_default_root_folder == "/data/anime"


def test_anime_defaults_roundtrip_in_file():
    cfg = Config.from_dict(ANIME_CONFIG)
    again = Config.from_dict(cfg.to_dict()).sonarr_config
    assert again.anime_default_quality_profile == "Any"
    assert again.anime_default_root_folder == "/data/concerts"


def test_anime_defaults_are_empty_by_default():
    cfg = Config().sonarr_config
    assert cfg.anime_default_quality_profile == "" and cfg.anime_default_root_folder == ""


@pytest.mark.parametrize("resource, series_type, expected", [
    (LOOKUP_SERIES, None, False),
    (ANIME_RESOURCE, None, True),                                  # genre Anime
    (dict(LOOKUP_SERIES, genres=["anime"]), None, True),           # case insensitive
    (dict(LOOKUP_SERIES, seriesType="anime"), None, True),         # Sonarr already knows it
    (LOOKUP_SERIES, "anime", True),                                # explicit
    (ANIME_RESOURCE, "standard", False),                           # explicit choice wins over the genre
    (dict(LOOKUP_SERIES, seriesType="anime"), "daily", False),
    (dict(LOOKUP_SERIES, genres=None), None, False),
])
def test_is_anime(resource, series_type, expected):
    assert is_anime(resource, series_type) is expected


def test_series_payload_detects_anime_from_the_genre():
    payload = series_payload(ANIME_RESOURCE, PROFILES[0], FOLDERS[0], monitor="all",
                             series_type=None, search_now=False)
    assert payload["seriesType"] == "anime"


def test_series_payload_keeps_an_explicit_type_over_the_genre():
    payload = series_payload(ANIME_RESOURCE, PROFILES[0], FOLDERS[0], monitor="all",
                             series_type="standard", search_now=False)
    assert payload["seriesType"] == "standard"


def _anime_tools(resource=ANIME_RESOURCE, config=ANIME_CONFIG):
    tools, radarr, sonarr = _tools(Config.from_dict(config))
    sonarr.lookup_series_by_tvdb.return_value = dict(resource)
    return tools, sonarr


def test_anime_uses_the_anime_defaults():
    tools, sonarr = _anime_tools()
    result = json.loads(tools["add_series"](1))
    payload = sonarr.add_series.call_args.args[0]
    assert (payload["qualityProfileId"], payload["rootFolderPath"]) == (1, "/data/concerts")
    assert result["qualityProfile"] == "Any" and result["rootFolder"] == "/data/concerts"
    assert result["seriesType"] == "anime"


def test_a_standard_series_keeps_the_general_defaults():
    tools, sonarr = _anime_tools(resource=LOOKUP_SERIES)
    result = json.loads(tools["add_series"](1))
    payload = sonarr.add_series.call_args.args[0]
    assert (payload["qualityProfileId"], payload["rootFolderPath"]) == (4, "/data/movies")
    assert result["seriesType"] == "standard"


def test_explicit_arguments_win_over_the_anime_defaults():
    tools, sonarr = _anime_tools()
    json.loads(tools["add_series"](1, quality_profile="HD-1080p", root_folder="/data/movies"))
    payload = sonarr.add_series.call_args.args[0]
    assert (payload["qualityProfileId"], payload["rootFolderPath"]) == (4, "/data/movies")


def test_explicit_anime_type_triggers_the_anime_defaults():
    tools, sonarr = _anime_tools(resource=LOOKUP_SERIES)
    result = json.loads(tools["add_series"](1, series_type="anime"))
    assert result["qualityProfile"] == "Any" and result["rootFolder"] == "/data/concerts"
    assert sonarr.add_series.call_args.args[0]["seriesType"] == "anime"


def test_explicit_standard_type_on_an_anime_genre_uses_the_general_defaults():
    tools, sonarr = _anime_tools()
    result = json.loads(tools["add_series"](1, series_type="standard"))
    assert result["qualityProfile"] == "HD-1080p" and result["rootFolder"] == "/data/movies"
    assert result["seriesType"] == "standard"


def test_anime_without_anime_defaults_falls_back_to_the_general_ones():
    config = {"sonarrConfig": {"defaultQualityProfile": "HD-1080p", "defaultRootFolder": "/data/movies"}}
    tools, sonarr = _anime_tools(config=config)
    result = json.loads(tools["add_series"](1))
    assert result["qualityProfile"] == "HD-1080p" and result["rootFolder"] == "/data/movies"
    assert result["seriesType"] == "anime"


def test_anime_default_that_does_not_exist_is_an_error_listing_the_options():
    config = {"sonarrConfig": dict(ANIME_CONFIG["sonarrConfig"], animeDefaultRootFolder="/data/gone")}
    tools, sonarr = _anime_tools(config=config)
    result = json.loads(tools["add_series"](1))
    assert "root folder" in result["error"] and result["options"] == ["/data/concerts", "/data/movies"]
    sonarr.add_series.assert_not_called()


def test_get_add_options_shows_the_anime_defaults():
    tools, _, _ = _tools(Config.from_dict(ANIME_CONFIG))
    defaults = json.loads(tools["get_add_options"]())["sonarr"]["defaults"]
    assert defaults["anime"] == {"qualityProfile": "Any", "rootFolder": "/data/concerts"}
