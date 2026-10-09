# Radarr and Sonarr MCP Server

A Python [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that gives AI assistants such as Claude access to your Radarr (movies) and Sonarr (TV series) libraries, including what you have actually watched according to Emby, Jellyfin and/or Plex.

## Features

- **Radarr and Sonarr**: browse and search your movie and TV libraries
- **Watched status** from Emby, Jellyfin and Plex (a title counts as watched if any configured service says so)
- **Per-episode view**: download and watched status for every episode of a series
- **Reliable matching**: series are linked between Sonarr and Emby/Jellyfin by TVDB id, and movies between Radarr and Emby/Jellyfin by TMDB id, so translated or renamed titles still match (title search is the fallback)
- **Two transports**: stdio (Claude Desktop) or HTTP
- Built with [FastMCP](https://gofastmcp.com)

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/lokidata/mcp_services_radarr_sonarr.git
cd mcp_services_radarr_sonarr
pip install -e .
```

## Configuration

The server reads its configuration from the first of these that applies:

1. the file given with `--config` (or the `RADARR_SONARR_MCP_CONFIG` environment variable)
2. environment variables, when `RADARR_API_KEY` or `SONARR_API_KEY` is set
3. `./config.json`

If none is usable, the server stops with an explicit error instead of silently using empty defaults.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `NAS_IP` | `127.0.0.1` | Host running Radarr and Sonarr |
| `RADARR_API_KEY` / `SONARR_API_KEY` | | API keys (Settings > General) |
| `RADARR_PORT` / `SONARR_PORT` | `7878` / `8989` | Ports |
| `RADARR_BASE_PATH` / `SONARR_BASE_PATH` | `/api/v3` | API base paths |
| `EMBY_BASE_URL`, `EMBY_API_KEY`, `EMBY_USER_ID` | | Optional Emby server |
| `JELLYFIN_BASE_URL`, `JELLYFIN_API_KEY`, `JELLYFIN_USER_ID` | | Optional Jellyfin server |
| `PLEX_BASE_URL`, `PLEX_TOKEN` | | Optional Plex server |
| `MCP_SERVER_PORT` | `3000` | Port used by the HTTP transport |
| `MCP_SERVER_HOST` | `127.0.0.1` | Interface used by the HTTP transport (`0.0.0.0` to listen everywhere) |

Media server URLs may omit the scheme and port: `192.168.1.10` becomes `http://192.168.1.10:8096` for Emby and Jellyfin, and `:32400` for Plex.

For Emby and Jellyfin, `*_USER_ID` is the user's **id** (a hex string), not the user name. The watched status is the one of that user. List the ids with:

```bash
curl "http://<host>:8096/Users?api_key=<api key>"
```

### Configuration file

`config.json` (ignored by git) uses this layout; the `embyConfig`, `jellyfinConfig` and `plexConfig` sections are optional:

```json
{
  "nasConfig": { "ip": "192.168.1.10", "port": "7878" },
  "radarrConfig": { "apiKey": "YOUR_RADARR_API_KEY", "basePath": "/api/v3", "port": "7878" },
  "sonarrConfig": { "apiKey": "YOUR_SONARR_API_KEY", "basePath": "/api/v3", "port": "8989" },
  "embyConfig": { "baseUrl": "http://192.168.1.10:8096", "apiKey": "...", "userId": "..." },
  "server": { "port": 3000 }
}
```

`radarr-sonarr-mcp configure` is an interactive wizard for the Radarr/Sonarr/server settings. It keeps any media server section already present in the file; add those sections by hand.

## Usage

```bash
radarr-sonarr-mcp status                   # show the current configuration
radarr-sonarr-mcp start                    # stdio transport (default)
radarr-sonarr-mcp start --transport http   # HTTP on the configured port
radarr-sonarr-mcp start --config /path/to/config.json
```

### Docker

```bash
cp .env.example .env      # then fill in your API keys and addresses
docker compose up -d --build
```

The MCP endpoint is then `http://localhost:3000/mcp` (streamable HTTP). The compose file publishes the port on `127.0.0.1` only, because the server has no authentication: do not expose it to an untrusted network. Change `MCP_SERVER_PORT` in `.env` to publish another host port.

Inside the container, `NAS_IP` must be reachable from Docker's network (use the LAN address of your NAS, not `127.0.0.1`). Without compose:

```bash
docker build -t radarr-sonarr-mcp .
docker run -d --env-file .env -e MCP_SERVER_PORT=3000 -p 127.0.0.1:3000:3000 radarr-sonarr-mcp
```

Clients that only speak stdio (such as Claude Desktop) need a bridge: see [Claude Desktop](#claude-desktop) below.

### Claude Desktop

Claude Desktop only speaks stdio. Add the server to its configuration file:

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

`mcpServers` is a top-level key of that file: add it next to the existing keys (do not paste a second JSON object after them, the file would become invalid). Then quit Claude Desktop completely and start it again.

#### With the Docker container (recommended)

Start the container first (see [Docker](#docker)), then bridge it to Claude Desktop with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote). This needs Node.js, and your API keys stay in the container's `.env` instead of the Claude Desktop configuration:

```json
{
  "mcpServers": {
    "radarr_sonarr": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.3", "http://127.0.0.1:3000/mcp"]
    }
  }
}
```

Use the port you published with `MCP_SERVER_PORT` if you changed it. The container must be running before Claude Desktop starts (it restarts automatically with Docker thanks to `restart: unless-stopped`).

#### Without Docker

Claude Desktop starts the server itself over stdio (see [config.json.example](config.json.example)). Here the keys are part of the Claude Desktop configuration:

```json
{
  "mcpServers": {
    "radarr_sonarr": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp_services_radarr_sonarr", "run", "radarr-sonarr-mcp", "start"],
      "env": {
        "NAS_IP": "192.168.1.10",
        "RADARR_API_KEY": "your_radarr_api_key",
        "SONARR_API_KEY": "your_sonarr_api_key",
        "EMBY_BASE_URL": "http://192.168.1.10:8096",
        "EMBY_API_KEY": "your_emby_api_key",
        "EMBY_USER_ID": "your_emby_user_id"
      }
    }
  }
}
```

## MCP tools

| Tool | Description |
|---|---|
| `get_available_movies` | Movies from Radarr. Filters: `year`, `downloaded`, `watched`, `actors` |
| `lookup_movie` | Search movies by title (Radarr lookup) |
| `get_available_series` | Series from Sonarr. Filters: `year`, `downloaded`, `watched`, `actors` |
| `lookup_series` | Search series by title (Sonarr lookup) |
| `get_episodes` | Episodes of a series with download and watched status. Arguments: `series`, `season`, `watched`, `downloaded` |

`get_episodes` finds the series in Sonarr by title (exact match preferred) and returns an error with candidates if the title is unknown or ambiguous. Each episode has `season`, `episode`, `title`, `airDate`, `downloaded`, `monitored` and `watched`. `watched` is `null` when no Emby/Jellyfin server is configured or the series is not in its library.

Resources: `radarr-sonarr://movies` and `radarr-sonarr://series`.

Example questions for Claude:

- "Which episodes of Slow Horses have I downloaded but not watched?"
- "Do I have any unwatched movies from 2023?"
- "What is missing from season 6 of Slow Horses?"

## Watched status: how it works

- **Emby and Jellyfin**: the `Played` flag of the configured user (Emby can report `PlayCount: 0` for items marked as watched, so the play count alone is not used). A series is watched when all its episodes are played.
- **Plex**: series and movie checks exist but are basic; Plex is **not** used by `get_episodes`.
- **No media server configured**: movies are reported as not watched, and series fall back to a Sonarr heuristic (all episodes downloaded), which is not a real watched status.
- Sonarr series and Radarr movies are linked to Emby/Jellyfin by TVDB / TMDB id (this requires the ids to be present in the media server's metadata). Without a match, or for Plex, the title is used and may pick the wrong item when titles are ambiguous.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

`python run.py` runs the command line interface without installing the package.

## Finding API keys

Radarr and Sonarr: Settings > General > API Key. Emby: Dashboard > Advanced > API Keys. Jellyfin: Dashboard > API Keys.

## Security

API keys are sent to your services over plain HTTP by default. Run the server only on a trusted local network and keep `config.json` out of version control (it is git-ignored).
