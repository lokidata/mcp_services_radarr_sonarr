"""Typed configuration for the Radarr/Sonarr MCP server."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

CONFIG_ENV_VAR = "RADARR_SONARR_MCP_CONFIG"
DEFAULT_CONFIG_PATH = "config.json"


class ConfigError(Exception):
    """Raised when the configuration cannot be loaded."""


@dataclass
class NasConfig:
    """Host shared by the services."""
    ip: str = "127.0.0.1"
    port: str = "7878"


@dataclass
class _ArrConfig:
    """Common settings of a Radarr/Sonarr instance."""
    api_key: str = ""
    base_path: str = "/api/v3"
    port: str = ""
    host: str = ""  # filled from NasConfig by Config

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}{self.base_path}"


@dataclass
class RadarrConfig(_ArrConfig):
    port: str = "7878"


@dataclass
class SonarrConfig(_ArrConfig):
    port: str = "8989"


@dataclass
class JellyfinConfig:
    base_url: str = ""
    api_key: str = ""
    user_id: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)


@dataclass
class EmbyConfig:
    base_url: str = ""
    api_key: str = ""
    user_id: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)


@dataclass
class PlexConfig:
    base_url: str = ""
    token: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)


@dataclass
class ServerConfig:
    port: int = 3000


@dataclass
class Config:
    """Complete server configuration."""
    nas_config: NasConfig = field(default_factory=NasConfig)
    radarr_config: RadarrConfig = field(default_factory=RadarrConfig)
    sonarr_config: SonarrConfig = field(default_factory=SonarrConfig)
    jellyfin_config: JellyfinConfig = field(default_factory=JellyfinConfig)
    emby_config: EmbyConfig = field(default_factory=EmbyConfig)
    plex_config: PlexConfig = field(default_factory=PlexConfig)
    server_config: ServerConfig = field(default_factory=ServerConfig)

    def __post_init__(self):
        for cfg in (self.radarr_config, self.sonarr_config):
            if not cfg.host:
                cfg.host = self.nas_config.ip
            if not cfg.port:
                cfg.port = self.nas_config.port

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the camelCase JSON layout used in config.json."""
        data: Dict[str, Any] = {
            "nasConfig": {"ip": self.nas_config.ip, "port": self.nas_config.port},
            "radarrConfig": {
                "apiKey": self.radarr_config.api_key,
                "basePath": self.radarr_config.base_path,
                "port": self.radarr_config.port,
            },
            "sonarrConfig": {
                "apiKey": self.sonarr_config.api_key,
                "basePath": self.sonarr_config.base_path,
                "port": self.sonarr_config.port,
            },
            "server": {"port": self.server_config.port},
        }
        if self.jellyfin_config.enabled:
            data["jellyfinConfig"] = {
                "baseUrl": self.jellyfin_config.base_url,
                "apiKey": self.jellyfin_config.api_key,
                "userId": self.jellyfin_config.user_id,
            }
        if self.emby_config.enabled:
            data["embyConfig"] = {
                "baseUrl": self.emby_config.base_url,
                "apiKey": self.emby_config.api_key,
                "userId": self.emby_config.user_id,
            }
        if self.plex_config.enabled:
            data["plexConfig"] = {
                "baseUrl": self.plex_config.base_url,
                "token": self.plex_config.token,
            }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        nas = data.get("nasConfig", {})
        radarr = data.get("radarrConfig", {})
        sonarr = data.get("sonarrConfig", {})
        jellyfin = data.get("jellyfinConfig", {})
        emby = data.get("embyConfig", {})
        plex = data.get("plexConfig", {})
        nas_cfg = NasConfig(ip=nas.get("ip", "127.0.0.1"), port=str(nas.get("port", "7878")))
        return cls(
            nas_config=nas_cfg,
            radarr_config=RadarrConfig(
                api_key=radarr.get("apiKey", ""),
                base_path=radarr.get("basePath", "/api/v3"),
                port=str(radarr.get("port", "7878")),
            ),
            sonarr_config=SonarrConfig(
                api_key=sonarr.get("apiKey", ""),
                base_path=sonarr.get("basePath", "/api/v3"),
                port=str(sonarr.get("port", "8989")),
            ),
            jellyfin_config=JellyfinConfig(
                base_url=jellyfin.get("baseUrl", ""),
                api_key=jellyfin.get("apiKey", ""),
                user_id=jellyfin.get("userId", ""),
            ),
            emby_config=EmbyConfig(
                base_url=emby.get("baseUrl", ""),
                api_key=emby.get("apiKey", ""),
                user_id=emby.get("userId", ""),
            ),
            plex_config=PlexConfig(
                base_url=plex.get("baseUrl", ""),
                token=plex.get("token", ""),
            ),
            server_config=ServerConfig(port=int(data.get("server", {}).get("port", 3000))),
        )

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get
        return cls(
            nas_config=NasConfig(ip=env("NAS_IP", "127.0.0.1"), port=env("RADARR_PORT", "7878")),
            radarr_config=RadarrConfig(
                api_key=env("RADARR_API_KEY", ""),
                base_path=env("RADARR_BASE_PATH", "/api/v3"),
                port=env("RADARR_PORT", "7878"),
            ),
            sonarr_config=SonarrConfig(
                api_key=env("SONARR_API_KEY", ""),
                base_path=env("SONARR_BASE_PATH", "/api/v3"),
                port=env("SONARR_PORT", "8989"),
            ),
            jellyfin_config=JellyfinConfig(
                base_url=env("JELLYFIN_BASE_URL", ""),
                api_key=env("JELLYFIN_API_KEY", ""),
                user_id=env("JELLYFIN_USER_ID", ""),
            ),
            emby_config=EmbyConfig(
                base_url=env("EMBY_BASE_URL", ""),
                api_key=env("EMBY_API_KEY", ""),
                user_id=env("EMBY_USER_ID", ""),
            ),
            plex_config=PlexConfig(
                base_url=env("PLEX_BASE_URL", ""),
                token=env("PLEX_TOKEN", ""),
            ),
            server_config=ServerConfig(port=int(env("MCP_SERVER_PORT", "3000"))),
        )


def _resolve_path(path: Optional[str]) -> str:
    return path or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH


def load_config(path: Optional[str] = None) -> Config:
    """Load the configuration.

    An explicit ``path`` (or the RADARR_SONARR_MCP_CONFIG variable) always wins.
    Otherwise environment variables are used when an API key is set there,
    falling back to ./config.json. Raises ConfigError if nothing usable is found.
    """
    explicit = path or os.environ.get(CONFIG_ENV_VAR)
    if not explicit and (os.environ.get("RADARR_API_KEY") or os.environ.get("SONARR_API_KEY")):
        return Config.from_env()

    config_path = _resolve_path(path)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return Config.from_dict(json.load(f))
    except (OSError, ValueError) as e:
        raise ConfigError(f"Cannot load configuration from {config_path}: {e}") from e


def save_config(config: Config, path: Optional[str] = None) -> str:
    """Write the configuration as JSON and return the path used."""
    config_path = _resolve_path(path)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
    return config_path
