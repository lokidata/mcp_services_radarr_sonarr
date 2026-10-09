from ..config import EmbyConfig
from .jellyfin_service import JellyfinService


class EmbyService(JellyfinService):
    """
    Service for interacting with the Emby API.

    Jellyfin is a fork of Emby and both expose the same /Users/{id}/Items
    endpoints with api_key authentication and UserData.PlayCount, so the
    watched-status logic is shared with JellyfinService.
    """
    def __init__(self, config: EmbyConfig):
        super().__init__(config)
