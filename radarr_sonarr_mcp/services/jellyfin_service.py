import time

import requests
from typing import Any, Dict, List, Optional, Tuple

from ..config import JellyfinConfig

INDEX_TTL_SECONDS = 300


def _is_played(item: Dict[str, Any]) -> bool:
    """Emby/Jellyfin can report Played=true with PlayCount=0 (e.g. marked as watched)."""
    user_data = item.get("UserData", {})
    return bool(user_data.get("Played")) or user_data.get("PlayCount", 0) > 0


def _best_matches(items: List[Dict[str, Any]], title: str) -> List[Dict[str, Any]]:
    """Put exact (case-insensitive) title matches first; keep the search order otherwise."""
    wanted = title.strip().lower()
    return sorted(items, key=lambda i: i.get("Name", "").strip().lower() != wanted)


class JellyfinService:
    """
    Service for interacting with the Jellyfin API.
    This service searches for a series by title and retrieves its episodes to check the watch status.
    """
    def __init__(self, config: JellyfinConfig):
        self.base_url = config.base_url
        self.api_key = config.api_key
        self.user_id = config.user_id  # The user ID to check watch status for
        self._tvdb_index: Dict[str, Dict[str, Any]] = {}
        self._tvdb_index_at = 0.0

    def _series_by_tvdb(self) -> Dict[str, Dict[str, Any]]:
        """Index of the library's series by TVDB id (cached for a few minutes)."""
        if self._tvdb_index and time.monotonic() - self._tvdb_index_at < INDEX_TTL_SECONDS:
            return self._tvdb_index
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        params = {
            "IncludeItemTypes": "Series",
            "Recursive": "true",
            "Fields": "ProviderIds",
            "api_key": self.api_key
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        self._tvdb_index = {
            str(item["ProviderIds"]["Tvdb"]): item
            for item in response.json().get("Items", [])
            if (item.get("ProviderIds") or {}).get("Tvdb")
        }
        self._tvdb_index_at = time.monotonic()
        return self._tvdb_index

    def find_series(self, title: str, tvdb_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Find a series by TVDB id (reliable across translations), else by title."""
        if tvdb_id:
            item = self._series_by_tvdb().get(str(tvdb_id))
            if item:
                return item
        items = self.search_series(title)
        return items[0] if items else None

    def search_series(self, title: str) -> List[Dict[str, Any]]:
        """
        Search for a series in Jellyfin by title.
        """
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        params = {
            "IncludeItemTypes": "Series",
            "SearchTerm": title,
            "Recursive": "true",
            "api_key": self.api_key
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return _best_matches(response.json().get("Items", []), title)

    def get_episodes_for_series(self, series_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve episodes for a given series ID from Jellyfin.
        """
        url = f"{self.base_url}/Shows/{series_id}/Episodes"
        params = {
            "UserId": self.user_id,
            "Fields": "UserData",
            "api_key": self.api_key
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("Items", [])

    def get_watched_episodes(self, series_title: str, tvdb_id: Optional[int] = None) -> Dict[Tuple[int, int], bool]:
        """Map (season, episode) -> played for every episode of the series. Empty if not found."""
        series = self.find_series(series_title, tvdb_id)
        if not series:
            return {}
        return {
            (ep.get("ParentIndexNumber"), ep.get("IndexNumber")): _is_played(ep)
            for ep in self.get_episodes_for_series(series.get("Id"))
        }

    def is_episode_watched(self, series_title: str, season: int, episode: int,
                           tvdb_id: Optional[int] = None) -> bool:
        """Determine if a given episode (season/episode number) of a series is watched."""
        return self.get_watched_episodes(series_title, tvdb_id).get((season, episode), False)

    def is_series_watched(self, series_title: str, tvdb_id: Optional[int] = None) -> bool:
        """
        Determine if the series is watched.
        A series is considered watched if all episodes are played.
        """
        series_item = self.find_series(series_title, tvdb_id)
        if not series_item:
            return False
        episodes = self.get_episodes_for_series(series_item.get("Id"))
        if not episodes:
            return False
        # Consider the series watched if every episode is played
        return all(_is_played(ep) for ep in episodes)

    def is_movie_watched(self, movie_title: str) -> bool:
        """Determine if a movie is watched (first search match has been played)."""
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        params = {
            "IncludeItemTypes": "Movie",
            "SearchTerm": movie_title,
            "Recursive": "true",
            "api_key": self.api_key
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        items = _best_matches(response.json().get("Items", []), movie_title)
        if not items:
            return False
        return _is_played(items[0])
