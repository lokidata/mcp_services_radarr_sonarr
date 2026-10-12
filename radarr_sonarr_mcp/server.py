#!/usr/bin/env python
"""Main MCP server implementation for Radarr/Sonarr."""

import json
import logging
from typing import Optional

from fastmcp import FastMCP

from starlette.middleware import Middleware

from .adding import AddError, is_anime, movie_payload, resolve_profile, resolve_root_folder, series_payload
from .auth import MIN_API_KEY_LENGTH, ApiKeyMiddleware
from .config import Config, ConfigError, load_config
from .services.arr_http import ArrError
from .services.emby_service import EmbyService
from .services.jellyfin_service import JellyfinService
from .services.plex_service import PlexService
from .services.radarr_service import RadarrService
from .services.sonarr_service import SonarrService

logger = logging.getLogger(__name__)


def _has_actor(data: dict, actor: str) -> bool:
    cast = (data.get("credits") or {}).get("cast", [])
    return any(actor.lower() in c.get("name", "").lower() for c in cast)


class RadarrSonarrMCPServer:
    """MCP Server for Radarr and Sonarr."""

    def __init__(self, config: Config):
        self.config = config
        self.server = FastMCP(
            name="radarr-sonarr-mcp-server",
            instructions="MCP Server for Radarr and Sonarr media management",
        )
        self.sonarr_service = SonarrService(config.sonarr_config)
        self.radarr_service = RadarrService(config.radarr_config)
        self.jellyfin = JellyfinService(config.jellyfin_config) if config.jellyfin_config.enabled else None
        self.emby = EmbyService(config.emby_config) if config.emby_config.enabled else None
        self.plex = PlexService(config.plex_config) if config.plex_config.enabled else None
        self._register_tools()
        if not config.server_config.read_only:
            self._register_write_tools()
        self._register_resources()

    # ------------------------------------------------------------------
    # Watched status
    # ------------------------------------------------------------------

    def _watched(self, check_name: str, title: str, fallback, **kwargs) -> bool:
        """True if any configured media service reports the title as watched.

        Without Plex/Jellyfin/Emby, falls back to the Radarr/Sonarr heuristic.
        """
        statuses = []
        for name, client in (("Jellyfin", self.jellyfin), ("Emby", self.emby), ("Plex", self.plex)):
            if client is None:
                continue
            try:
                statuses.append(getattr(client, check_name)(title, **kwargs))
            except Exception as e:
                logger.error(f"{name} check failed for {title}: {e}")
        return any(statuses) if statuses else bool(fallback())

    def _find_series(self, title: str) -> list:
        """Sonarr series matching a title: exact (case-insensitive) match, else substring."""
        wanted = title.strip().lower()
        library = self.sonarr_service.get_all_series()
        exact = [s for s in library if s.title.strip().lower() == wanted]
        return exact or [s for s in library if wanted in s.title.lower()]

    def _episode_watched_map(self, title: str, tvdb_id: Optional[int] = None):
        """((season, episode) -> watched, has_status). An episode is watched if any service says so."""
        merged, has_status = {}, False
        for name, client in (("Jellyfin", self.jellyfin), ("Emby", self.emby)):
            if client is None:
                continue
            try:
                per_service = client.get_watched_episodes(title, tvdb_id)
            except Exception as e:
                logger.error(f"{name} episode check failed for {title}: {e}")
                continue
            has_status = has_status or bool(per_service)
            for key, played in per_service.items():
                merged[key] = merged.get(key, False) or played
        return merged, has_status

    def is_watched_series(self, series) -> bool:
        return self._watched(
            "is_series_watched", series.title, lambda: self.sonarr_service.is_series_watched(series),
            tvdb_id=series.tvdb_id,
        )

    def is_watched_movie(self, movie) -> bool:
        return self._watched(
            "is_movie_watched", movie.title, lambda: self.radarr_service.is_movie_watched(movie),
            tmdb_id=movie.tmdb_id,
        )

    # ------------------------------------------------------------------
    # Tools and resources
    # ------------------------------------------------------------------

    def _register_tools(self):
        @self.server.tool()
        def get_available_series(year: Optional[int] = None,
                                 downloaded: Optional[bool] = None,
                                 watched: Optional[bool] = None,
                                 actors: Optional[str] = None) -> str:
            """
            Get a list of available TV series with optional filters.
            Watched status is determined using Plex, Jellyfin and/or Emby; if any reports watched, the series is considered watched.
            """
            result = self.sonarr_service.get_all_series()

            if year is not None:
                result = [s for s in result if s.year == year]
            if downloaded is not None:
                result = [
                    s for s in result
                    if bool(s.statistics and s.statistics.episode_file_count > 0) == downloaded
                ]
            if actors:
                result = [s for s in result if _has_actor(s.data, actors)]

            # Compute watched once per series (it may cost HTTP calls)
            watched_by_id = {s.id: self.is_watched_series(s) for s in result}
            if watched is not None:
                result = [s for s in result if watched_by_id[s.id] == watched]

            return json.dumps({
                "count": len(result),
                "series": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "year": s.year,
                        "overview": s.overview,
                        "status": s.status,
                        "network": s.network,
                        "genres": s.genres,
                        "watched": watched_by_id[s.id],
                    }
                    for s in result
                ],
            })

        @self.server.tool()
        def lookup_series(term: str) -> str:
            """Search for a TV series by title."""
            results = self.sonarr_service.lookup_series(term)
            return json.dumps({
                "count": len(results),
                "series": [
                    {
                        "tvdbId": s.tvdb_id,
                        "title": s.title,
                        "year": s.year,
                        "overview": s.overview,
                        "inLibrary": bool(s.id),
                    }
                    for s in results
                ],
            })

        @self.server.tool()
        def get_episodes(series: str,
                         season: Optional[int] = None,
                         watched: Optional[bool] = None,
                         downloaded: Optional[bool] = None) -> str:
            """
            List the episodes of a TV series with download and watched status.
            `series` is matched against the Sonarr library by title (exact match preferred).
            Watched status comes from Jellyfin/Emby (any reporting watched wins);
            it is null when none is configured or the series is not found there.
            """
            matches = self._find_series(series)
            if len(matches) != 1:
                return json.dumps({
                    "error": "series not found" if not matches else "ambiguous series title",
                    "candidates": [{"id": s.id, "title": s.title, "year": s.year} for s in matches[:10]],
                })
            found = matches[0]

            watched_map, has_status = self._episode_watched_map(found.title, found.tvdb_id)
            episodes = self.sonarr_service.get_episodes(found.id)
            if season is not None:
                episodes = [e for e in episodes if e.season_number == season]
            if downloaded is not None:
                episodes = [e for e in episodes if e.has_file == downloaded]

            rows = []
            for e in sorted(episodes, key=lambda e: (e.season_number, e.episode_number)):
                is_watched = watched_map.get((e.season_number, e.episode_number), False) if has_status else None
                if watched is not None and is_watched != watched:
                    continue
                rows.append({
                    "season": e.season_number,
                    "episode": e.episode_number,
                    "title": e.title,
                    "airDate": e.air_date,
                    "downloaded": e.has_file,
                    "monitored": e.monitored,
                    "watched": is_watched,
                })
            return json.dumps({
                "series": {"id": found.id, "title": found.title, "year": found.year},
                "count": len(rows),
                "episodes": rows,
            })

        @self.server.tool()
        def get_available_movies(year: Optional[int] = None,
                                 downloaded: Optional[bool] = None,
                                 watched: Optional[bool] = None,
                                 actors: Optional[str] = None) -> str:
            """
            Get a list of all available movies with optional filters.
            Watched status is determined using Plex, Jellyfin and/or Emby.
            """
            result = self.radarr_service.get_all_movies()

            if year is not None:
                result = [m for m in result if m.year == year]
            if downloaded is not None:
                result = [m for m in result if m.has_file == downloaded]
            if actors:
                result = [m for m in result if _has_actor(m.data or {}, actors)]

            watched_by_id = {m.id: self.is_watched_movie(m) for m in result}
            if watched is not None:
                result = [m for m in result if watched_by_id[m.id] == watched]

            return json.dumps({
                "count": len(result),
                "movies": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "year": m.year,
                        "overview": m.overview,
                        "hasFile": m.has_file,
                        "status": m.status,
                        "genres": m.genres or [],
                        "watched": watched_by_id[m.id],
                    }
                    for m in result
                ],
            })

        @self.server.tool()
        def lookup_movie(term: str) -> str:
            """Search for a movie by title."""
            results = self.radarr_service.lookup_movie(term)
            return json.dumps({
                "count": len(results),
                "movies": [
                    {
                        "tmdbId": m.tmdb_id,
                        "title": m.title,
                        "year": m.year,
                        "overview": m.overview,
                        "inLibrary": bool(m.id),
                    }
                    for m in results
                ],
            })

        @self.server.tool()
        def get_add_options() -> str:
            """
            List what add_movie and add_series can use: the root folders and quality profiles
            of Radarr and Sonarr, and the configured defaults.
            """
            options = {}
            for name, service, cfg in (("radarr", self.radarr_service, self.config.radarr_config),
                                       ("sonarr", self.sonarr_service, self.config.sonarr_config)):
                try:
                    options[name] = {
                        "rootFolders": [{"path": f["path"], "freeSpace": f.get("freeSpace")}
                                        for f in service.get_root_folders()],
                        "qualityProfiles": [{"id": p["id"], "name": p["name"]}
                                            for p in service.get_quality_profiles()],
                        "defaults": {"qualityProfile": cfg.default_quality_profile or None,
                                     "rootFolder": cfg.default_root_folder or None},
                    }
                    if name == "sonarr":
                        options[name]["defaults"]["anime"] = {
                            "qualityProfile": cfg.anime_default_quality_profile or None,
                            "rootFolder": cfg.anime_default_root_folder or None,
                        }
                except ArrError as e:
                    options[name] = {"error": str(e)}
            return json.dumps(options)

    def _register_write_tools(self):
        @self.server.tool()
        def add_movie(tmdb_id: int,
                      quality_profile: Optional[str] = None,
                      root_folder: Optional[str] = None,
                      monitored: bool = True,
                      search_now: bool = False) -> str:
            """
            Add a movie to Radarr. `tmdb_id` comes from lookup_movie.
            quality_profile (name or id) and root_folder (path) default to the configured values;
            see get_add_options. No release search is started unless search_now is true.
            """
            try:
                resource = self.radarr_service.lookup_movie_by_tmdb(tmdb_id)
                if resource is None:
                    return json.dumps({"error": "movie not found"})
                existing = next((m for m in self.radarr_service.get_all_movies() if m.tmdb_id == tmdb_id), None)
                if existing:
                    return json.dumps({"error": "already in library",
                                       "existing": {"id": existing.id, "title": existing.title}})
                cfg = self.config.radarr_config
                profile = resolve_profile(self.radarr_service.get_quality_profiles(), quality_profile,
                                          cfg.default_quality_profile)
                folder = resolve_root_folder(self.radarr_service.get_root_folders(), root_folder,
                                             cfg.default_root_folder)
                added = self.radarr_service.add_movie(
                    movie_payload(resource, profile, folder, monitored, search_now))
            except (AddError, ArrError) as e:
                return self._add_error(e)
            return json.dumps({
                "added": {"id": added.get("id"), "title": added.get("title"), "year": added.get("year")},
                "qualityProfile": profile["name"],
                "rootFolder": folder["path"],
                "searching": search_now,
            })

        @self.server.tool()
        def add_series(tvdb_id: int,
                       quality_profile: Optional[str] = None,
                       root_folder: Optional[str] = None,
                       monitor: str = "all",
                       series_type: Optional[str] = None,
                       search_now: bool = False) -> str:
            """
            Add a TV series to Sonarr. `tvdb_id` comes from lookup_series.
            quality_profile (name or id) and root_folder (path) default to the configured values;
            see get_add_options. `monitor` is all, future, missing, existing, firstSeason, lastSeason,
            latestSeason, pilot, recent, monitorSpecials, unmonitorSpecials or none.
            series_type is standard, daily or anime. By default a series tagged with the Anime genre
            is added as an anime, using the anime defaults (profile and root folder) when configured.
            No search for missing episodes is started unless search_now is true.
            """
            try:
                resource = self.sonarr_service.lookup_series_by_tvdb(tvdb_id)
                if resource is None:
                    return json.dumps({"error": "series not found"})
                existing = next((s for s in self.sonarr_service.get_all_series() if s.tvdb_id == tvdb_id), None)
                if existing:
                    return json.dumps({"error": "already in library",
                                       "existing": {"id": existing.id, "title": existing.title}})
                cfg = self.config.sonarr_config
                anime = is_anime(resource, series_type)
                default_profile, default_folder = cfg.default_quality_profile, cfg.default_root_folder
                if anime:  # the anime defaults come first when they are configured
                    default_profile = cfg.anime_default_quality_profile or default_profile
                    default_folder = cfg.anime_default_root_folder or default_folder
                profile = resolve_profile(self.sonarr_service.get_quality_profiles(), quality_profile,
                                          default_profile)
                folder = resolve_root_folder(self.sonarr_service.get_root_folders(), root_folder,
                                             default_folder)
                payload = series_payload(resource, profile, folder, monitor, series_type, search_now)
                added = self.sonarr_service.add_series(payload)
            except (AddError, ArrError) as e:
                return self._add_error(e)
            return json.dumps({
                "added": {"id": added.get("id"), "title": added.get("title"), "year": added.get("year")},
                "qualityProfile": profile["name"],
                "rootFolder": folder["path"],
                "seriesType": payload["seriesType"],
                "monitor": monitor,
                "searching": search_now,
            })

    @staticmethod
    def _add_error(error: Exception) -> str:
        result = {"error": str(error)}
        if getattr(error, "options", None):
            result["options"] = error.options
        return json.dumps(result)

    def _register_resources(self):
        @self.server.resource("radarr-sonarr://series", description="TV series collection from Sonarr")
        def series() -> dict:
            series_list = self.sonarr_service.get_all_series()
            return {
                "count": len(series_list),
                "series": [{"id": s.id, "title": s.title, "year": s.year} for s in series_list],
            }

        @self.server.resource("radarr-sonarr://movies", description="Movie collection from Radarr")
        def movies() -> dict:
            movies_list = self.radarr_service.get_all_movies()
            return {
                "count": len(movies_list),
                "movies": [{"id": m.id, "title": m.title, "year": m.year} for m in movies_list],
            }

    # ------------------------------------------------------------------

    def start(self, transport: str = "stdio", host: Optional[str] = None):
        """Run the server. 'stdio' for Claude Desktop, 'http' to listen on server.host:server.port."""
        if transport == "http":
            server_config = self.config.server_config
            host = host or server_config.host
            port = server_config.port
            options = {}
            if server_config.api_key:
                if len(server_config.api_key) < MIN_API_KEY_LENGTH:
                    raise ConfigError(
                        f"MCP_API_KEY must be at least {MIN_API_KEY_LENGTH} characters "
                        "(generate one with: openssl rand -hex 32)"
                    )
                options["middleware"] = [Middleware(ApiKeyMiddleware, api_key=server_config.api_key)]
            elif server_config.allow_no_auth:
                logger.warning("HTTP transport started WITHOUT authentication (MCP_ALLOW_NO_AUTH)")
            else:
                raise ConfigError(
                    "The HTTP transport requires an API key: set MCP_API_KEY "
                    "(generate one with: openssl rand -hex 32), or MCP_ALLOW_NO_AUTH=true to disable the check"
                )
            if server_config.allowed_hosts:
                options["allowed_hosts"] = server_config.allowed_hosts
            logger.info(f"Starting Radarr-Sonarr MCP Server over HTTP on {host}:{port}")
            self.server.run(transport="http", host=host, port=port, **options)
        else:
            self.server.run()


def create_server(config_path: Optional[str] = None) -> RadarrSonarrMCPServer:
    """Create the server from a config file or environment variables."""
    return RadarrSonarrMCPServer(load_config(config_path))


def main():
    """Entry point: start the server over stdio."""
    logging.basicConfig(level=logging.INFO)
    create_server().start()


if __name__ == "__main__":
    main()
