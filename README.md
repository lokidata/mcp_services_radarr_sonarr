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
| `MCP_API_KEY` | | **Required by the HTTP transport**: key clients must present (see [Securing access](#securing-access)) |
| `MCP_ALLOWED_HOSTS` | | Comma separated domain names accepted in the `Host` header behind a reverse proxy (only needed if requests are rejected) |
| `MCP_ALLOW_NO_AUTH` | `false` | `true` lets the HTTP transport start without an API key (not recommended) |

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
openssl rand -hex 32      # generate the value of MCP_API_KEY in .env
docker compose up -d --build
```

The MCP endpoint is then `http://localhost:3000/mcp` (streamable HTTP), and every request must carry the `MCP_API_KEY` (see [Securing access](#securing-access)). The compose file refuses to start without it, and publishes the port on `127.0.0.1` only. Change `MCP_SERVER_PORT` in `.env` to publish another host port.

Inside the container, `NAS_IP` must be reachable from Docker's network (use the LAN address of your NAS, not `127.0.0.1`). Without compose:

```bash
docker build -t radarr-sonarr-mcp .
docker run -d --env-file .env -e MCP_SERVER_PORT=3000 -p 127.0.0.1:3000:3000 radarr-sonarr-mcp   # .env must contain MCP_API_KEY
```

#### Prebuilt image and Portainer

A GitHub Action ([docker.yml](.github/workflows/docker.yml)) runs the tests, then builds a multi-architecture image (`linux/amd64`, `linux/arm64`) and publishes it to GitHub Container Registry on every merge into `development` and on `v*` tags:

| Tag | When |
|---|---|
| `latest` | latest build of `development` |
| `development` | same build, by branch name |
| `sha-<commit>` | every published build, to pin an exact commit |
| `1.2.3`, `1.2` | when a `v1.2.3` git tag is pushed |

Pull requests only build the image to check it, they do not publish it.

To run it from Portainer (Stacks > Add stack > Web editor), paste [docker-compose.portainer.yml](docker-compose.portainer.yml) and fill in the variables of [.env.example](.env.example) in the "Environment variables" section. Optional variables: `IMAGE_TAG` (default `latest`, use a `sha-…` tag to pin a build), `MCP_SERVER_PORT` (published port) and `MCP_BIND` (default `127.0.0.1`).

- The image of a public repository can be pulled anonymously, so Portainer needs no registry credentials. If your fork's package is private (check GitHub > Packages > the image > Package settings), make it public or add `ghcr.io` as a registry in Portainer with a personal access token that has the `read:packages` scope.
- To reach the server from another machine (for example Claude Desktop on your PC through `mcp-remote`), set `MCP_BIND` to `0.0.0.0` or to the NAS LAN address, and use `http://<nas-ip>:3000/mcp` (with `--allow-http` in `mcp-remote`, see [Claude Desktop](#claude-desktop)). The traffic is then not encrypted: keep it on a trusted network, or put a TLS reverse proxy in front (see [Securing access](#securing-access)). `MCP_API_KEY` is required in the stack's variables.
- Update with "Pull and redeploy" in Portainer.

Clients that only speak stdio (such as Claude Desktop) need a bridge: see [Claude Desktop](#claude-desktop) below.

### Claude Desktop

Claude Desktop only speaks stdio. Add the server to its configuration file:

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

`mcpServers` is a top-level key of that file: add it next to the existing keys (do not paste a second JSON object after them, the file would become invalid). Then quit Claude Desktop completely and start it again.

#### With the Docker container (recommended)

Start the container first (see [Docker](#docker)), then bridge it to Claude Desktop with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote). This needs Node.js. Your Radarr/Sonarr/Emby keys stay in the container's `.env`; only the access key `MCP_API_KEY` goes in the Claude Desktop configuration (the header uses the `${MCP_API_KEY}` variable from `env`, without a space after the colon):

```json
{
  "mcpServers": {
    "radarr_sonarr": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.3", "http://127.0.0.1:3000/mcp", "--header", "X-API-Key:${MCP_API_KEY}"],
      "env": { "MCP_API_KEY": "the same value as MCP_API_KEY in the container's .env" }
    }
  }
}
```

Use the port you published with `MCP_SERVER_PORT` if you changed it. The container must be running before Claude Desktop starts (it restarts automatically with Docker thanks to `restart: unless-stopped`).

If the container runs on another machine (for example a NAS), use its address and add `--allow-http`. Without it `mcp-remote` refuses plain `http://` URLs that are not `localhost` and the server shows up as disconnected in Claude Desktop (the error is in `mcp-server-radarr_sonarr.log`). The traffic is then unencrypted (the key travels in clear text), so keep it on a trusted network, or use HTTPS through a reverse proxy instead (no `--allow-http` needed), and publish the container on the LAN (`MCP_BIND=0.0.0.0` in the Portainer stack):

```json
{
  "mcpServers": {
    "radarr_sonarr": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.3", "http://192.168.1.10:3000/mcp", "--allow-http", "--header", "X-API-Key:${MCP_API_KEY}"],
      "env": { "MCP_API_KEY": "the same value as MCP_API_KEY in the container's .env" }
    }
  }
}
```

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

## Securing access

The HTTP transport refuses to start without `MCP_API_KEY` (at least 16 characters). Generate one with `openssl rand -hex 32`. Clients must send it in one of these headers:

```
Authorization: Bearer <key>
X-API-Key: <key>
```

Requests without a valid key get `401`. The key is compared in constant time and is never accepted in the URL, so it does not end up in access logs. Treat it like a password: store it in `.env` or the Portainer variables, never in git, and rotate it by changing the value and restarting the container. The stdio transport (Claude Desktop starting the server itself) needs no key.

```bash
curl -X POST http://localhost:3000/mcp \
  -H "X-API-Key: $MCP_API_KEY" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
```

### Behind a reverse proxy

The key protects the server, but the key and the data travel in clear text unless the proxy terminates TLS. Expose the server only through an HTTPS reverse proxy, keep the container published on `127.0.0.1` (or on a private Docker network shared with the proxy), and consider restricting the proxy to the addresses that need it. The MCP endpoint streams responses, so disable response buffering. Illustrative nginx example:

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;
    # ssl_certificate ... ssl_certificate_key ...

    location /mcp {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 1h;
    }
}
```

Clients then use `https://mcp.example.com/mcp` (without `--allow-http`). If proxied requests are rejected because of their `Host` header, add the domain to `MCP_ALLOWED_HOSTS`. The proxy is also the right place for rate limiting and IP allow-lists.

## Security

Automated checks (all free on public repositories): CodeQL analysis of the Python code and of the workflows, a `pip-audit` scan of the dependencies, Dependabot alerts and update pull requests (Python, GitHub Actions, Docker base image), and secret scanning with push protection. They run on every pull request and every Monday; the results are in the repository's *Security* tab.

The server talks to Radarr, Sonarr and the media servers over plain HTTP by default, so run it on the same trusted network as they are. Keep `config.json` and `.env` out of version control (they are git-ignored). See [Securing access](#securing-access) before exposing the HTTP transport.
