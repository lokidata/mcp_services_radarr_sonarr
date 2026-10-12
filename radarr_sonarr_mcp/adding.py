"""Logic for adding movies and series: choosing a profile and folder, building the payload."""

from typing import Any, Dict, List, Optional

# Values accepted by Sonarr's addOptions.monitor, minus the internal "unknown" and "skip"
MONITOR_TYPES = [
    "all", "future", "missing", "existing", "firstSeason", "lastSeason",
    "latestSeason", "pilot", "recent", "monitorSpecials", "unmonitorSpecials", "none",
]
SERIES_TYPES = ["standard", "daily", "anime"]
MOVIE_MINIMUM_AVAILABILITY = "released"


class AddError(Exception):
    """An add request cannot be built; `options` lists the valid choices when there are any."""

    def __init__(self, message: str, options: Optional[List[str]] = None):
        super().__init__(message)
        self.options = options or []


def _choose(items: List[Dict[str, Any]], key: str, wanted: Optional[str], default: str,
            label: str, normalize=lambda value: str(value).strip().lower()) -> Dict[str, Any]:
    """Pick one item by `key` (or by id): the given value, else the configured default, else the only one."""
    names = [item[key] for item in items]
    choice = wanted or default
    if choice:
        for item in items:
            if normalize(item[key]) == normalize(choice) or str(item.get("id")) == str(choice).strip():
                return item
        raise AddError(f"unknown {label} {choice!r}", names)
    if len(items) == 1:
        return items[0]
    raise AddError(f"no {label} given and no default configured", names)


def resolve_profile(profiles: List[Dict[str, Any]], wanted: Optional[str], default: str) -> Dict[str, Any]:
    return _choose(profiles, "name", wanted, default, "quality profile")


def resolve_root_folder(folders: List[Dict[str, Any]], wanted: Optional[str], default: str) -> Dict[str, Any]:
    return _choose(folders, "path", wanted, default, "root folder",
                   normalize=lambda value: str(value).strip().rstrip("/").lower())


def _base_payload(resource: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(resource)
    payload.pop("id", None)  # a lookup result is not in the library yet
    return payload


def movie_payload(resource: Dict[str, Any], profile: Dict[str, Any], folder: Dict[str, Any],
                  monitored: bool, search_now: bool) -> Dict[str, Any]:
    payload = _base_payload(resource)
    payload.update({
        "qualityProfileId": profile["id"],
        "rootFolderPath": folder["path"],
        "monitored": monitored,
        "minimumAvailability": MOVIE_MINIMUM_AVAILABILITY,
        "addOptions": {"monitor": "movieOnly", "searchForMovie": search_now},
    })
    return payload


def series_payload(resource: Dict[str, Any], profile: Dict[str, Any], folder: Dict[str, Any],
                   monitor: str, series_type: Optional[str], search_now: bool) -> Dict[str, Any]:
    if monitor not in MONITOR_TYPES:
        raise AddError(f"unknown monitor value {monitor!r}", MONITOR_TYPES)
    if series_type is not None and series_type not in SERIES_TYPES:
        raise AddError(f"unknown series type {series_type!r}", SERIES_TYPES)
    payload = _base_payload(resource)
    payload.update({
        "qualityProfileId": profile["id"],
        "rootFolderPath": folder["path"],
        "monitored": monitor != "none",
        "seasonFolder": True,  # the lookup result carries an unset boolean; Sonarr defaults to season folders
        "seriesType": series_type or resource.get("seriesType", "standard"),
        "addOptions": {
            "monitor": monitor,
            "searchForMissingEpisodes": search_now,
            "searchForCutoffUnmetEpisodes": False,
            "ignoreEpisodesWithFiles": False,
            "ignoreEpisodesWithoutFiles": False,
        },
    })
    return payload
