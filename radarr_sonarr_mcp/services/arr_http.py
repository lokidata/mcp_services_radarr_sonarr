"""HTTP helpers shared by the Radarr and Sonarr services."""

from typing import Any, Dict, List, Optional

import requests


class ArrError(Exception):
    """A Radarr or Sonarr request failed; the message is meant to be shown to the user."""


def _error_message(response) -> str:
    """Extract the validation messages Radarr and Sonarr return on a 4xx."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, list):
        messages = [
            f"{item['propertyName']}: {item['errorMessage']}" if item.get("propertyName")
            else item.get("errorMessage", "")
            for item in body if isinstance(item, dict)
        ]
        messages = [m for m in messages if m]
        if messages:
            return "; ".join(messages)
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])
    return f"HTTP {response.status_code}: {(response.text or '')[:200]}"


class ArrHttp:
    """Mixin giving a service `_call`; the API key travels in a header, never in the URL."""

    config: Any
    service_name = "service"

    def _call(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
              json: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.config.base_url}/{path}",
                headers={"X-Api-Key": self.config.api_key},
                params=params,
                json=json,
                timeout=30,
            )
        except requests.RequestException as e:
            raise ArrError(f"Cannot reach {self.service_name}: {e}") from e
        if not response.ok:
            raise ArrError(_error_message(response))
        return response.json()

    def get_root_folders(self) -> List[Dict[str, Any]]:
        return self._call("GET", "rootfolder")

    def get_quality_profiles(self) -> List[Dict[str, Any]]:
        return self._call("GET", "qualityprofile")
