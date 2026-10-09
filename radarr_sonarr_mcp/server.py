#!/usr/bin/env python
"""Main MCP server implementation for Radarr/Sonarr."""

import json
import logging
from typing import Optional

from fastmcp import FastMCP

from .config import Config, load_config
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
        self._register_resources()

    # ------------------------------------------------------------------
    # Watched status
    # ------------------------------------------------------------------

    def _watched(self, check_name: str, title: str, fallback) -> bool:
        """True if any configured media service reports the title as watched.

        Without Plex/Jellyfin/Emby, falls back to the Radarr/Sonarr heuristic.
        """
        statuses = []
        for name, client in (("Jellyfin", self.jellyfin), ("Emby", self.emby), ("Plex", self.plex)):
            if client is None:
                continue
            try:
                statuses.append(getattr(client, check_name)(title))
            except Exception as e:
                logger.error(f"{name} check failed for {title}: {e}")
        return any(statuses) if statuses else bool(fallback())

    def is_watched_series(self, series) -> bool:
        return self._watched(
            "is_series_watched", series.title, lambda: self.sonarr_service.is_series_watched(series)
        )

    def is_watched_movie(self, movie) -> bool:
        return self._watched(
            "is_movie_watched", movie.title, lambda: self.radarr_service.is_movie_watched(movie)
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
                    {"id": s.id, "title": s.title, "year": s.year, "overview": s.overview}
                    for s in results
                ],
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
                    {"id": m.id, "title": m.title, "year": m.year, "overview": m.overview}
                    for m in results
                ],
            })

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

    def start(self, transport: str = "stdio"):
        """Run the server. 'stdio' for Claude Desktop, 'http' to listen on server.port."""
        if transport == "http":
            port = self.config.server_config.port
            logger.info(f"Starting Radarr-Sonarr MCP Server over HTTP on port {port}")
            self.server.run(transport="http", port=port)
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
