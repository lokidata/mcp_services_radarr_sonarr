import requests
from typing import Any, Dict, List, Tuple

from ..config import JellyfinConfig

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

    def get_watched_episodes(self, series_title: str) -> Dict[Tuple[int, int], bool]:
        """Map (season, episode) -> played for every episode of the series. Empty if not found."""
        items = self.search_series(series_title)
        if not items:
            return {}
        return {
            (ep.get("ParentIndexNumber"), ep.get("IndexNumber")): _is_played(ep)
            for ep in self.get_episodes_for_series(items[0].get("Id"))
        }

    def is_episode_watched(self, series_title: str, season: int, episode: int) -> bool:
        """Determine if a given episode (season/episode number) of a series is watched."""
        items = self.search_series(series_title)
        if not items:
            return False
        for ep in self.get_episodes_for_series(items[0].get("Id")):
            if ep.get("ParentIndexNumber") == season and ep.get("IndexNumber") == episode:
                return _is_played(ep)
        return False

    def is_series_watched(self, series_title: str) -> bool:
        """
        Determine if the series is watched.
        A series is considered watched if all episodes are played.
        """
        items = self.search_series(series_title)
        if not items:
            return False
        series_item = items[0]  # take the first match
        series_id = series_item.get("Id")
        episodes = self.get_episodes_for_series(series_id)
        if not episodes:
            return False
        # Consider the series watched if every episode has a PlayCount > 0
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
