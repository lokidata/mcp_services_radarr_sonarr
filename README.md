# Radarr and Sonarr MCP Server

A Python [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that gives AI assistants such as Claude access to your Radarr (movies) and Sonarr (TV series) libraries, including what you have actually watched according to Emby or Jellyfin.

This is a fork of [BerryKuipers/mcp_services_radarr_sonarr](https://github.com/BerryKuipers/mcp_services_radarr_sonarr).

## Features

- **Radarr and Sonarr**: browse and search your movie and TV libraries
- **Watched status** from Emby and Jellyfin (a title counts as watched if any configured server says so)
- **Per-episode view** (`get_episodes`): download and watched status of every episode of a series
- **Reliable matching**: Sonarr series are linked to Emby/Jellyfin by TVDB id and Radarr movies by TMDB id, so translated or renamed titles still match (the title is only the fallback)
- **Two transports**: stdio (the client starts the server) or HTTP, protected by an API key
- **Docker image** published to GitHub Container Registry, with a ready-to-use Portainer stack

## Quick start

| I want to... | Go to |
|---|---|
| Run it in Docker (recommended) | [Docker](#docker) |
| Run it on a NAS with Portainer | [Prebuilt image and Portainer](#prebuilt-image-and-portainer) |
| Use it from Claude Desktop | [Claude Desktop](#claude-desktop) |
| Put it behind a reverse proxy | [Securing access](#securing-access) |

## Installation (without Docker)

Python 3.10 or newer is required.

```bash
git clone https://github.com/lokidata/mcp_services_radarr_sonarr.git
cd mcp_services_radarr_sonarr
pip install -e .        # or: uv sync
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
| `RADARR_API_KEY` / `SONARR_API_KEY` | | API keys, see [Finding keys and ids](#finding-keys-and-ids) |
| `RADARR_PORT` / `SONARR_PORT` | `7878` / `8989` | Ports |
| `RADARR_BASE_PATH` / `SONARR_BASE_PATH` | `/api/v3` | API base paths |
| `EMBY_BASE_URL`, `EMBY_API_KEY`, `EMBY_USER_ID` | | Optional Emby server |
| `JELLYFIN_BASE_URL`, `JELLYFIN_API_KEY`, `JELLYFIN_USER_ID` | | Optional Jellyfin server |
| `PLEX_BASE_URL`, `PLEX_TOKEN` | | Optional Plex server (experimental, see [Watched status](#watched-status)) |
| `MCP_SERVER_HOST` | `127.0.0.1` | Interface used by the HTTP transport (`0.0.0.0` to listen everywhere) |
| `MCP_SERVER_PORT` | `3000` | Port used by the HTTP transport |
| `MCP_API_KEY` | | **Required by the HTTP transport**, see [Securing access](#securing-access) |
| `MCP_ALLOWED_HOSTS` | | Comma separated domain names accepted in the `Host` header behind a reverse proxy (only if requests are rejected) |
| `MCP_ALLOW_NO_AUTH` | `false` | `true` lets the HTTP transport start without an API key (not recommended) |

Media server URLs may omit the scheme and port: `192.168.1.10` becomes `http://192.168.1.10:8096` for Emby and Jellyfin (`:32400` for Plex).

### Configuration file

[config.example.json](config.example.json) shows the layout of `config.json` (git-ignored). Only `radarrConfig` and `sonarrConfig` are needed; `embyConfig`, `jellyfinConfig` (same keys as Emby), `plexConfig` (`baseUrl`, `token`) are optional. The `server` section accepts `host`, `port`, `apiKey`, `allowedHosts` (a list) and `allowNoAuth`.

`radarr-sonarr-mcp configure` is an interactive wizard for the Radarr, Sonarr and server port settings. It keeps any media server section already present in the file; add those by hand.

## Running the server

```bash
radarr-sonarr-mcp status                                # show the current configuration
radarr-sonarr-mcp start                                 # stdio transport (default)
radarr-sonarr-mcp start --transport http                # HTTP on host:port, requires MCP_API_KEY
radarr-sonarr-mcp start --config /path/to/config.json
```

`python run.py` runs the same command line without installing the package.

- **stdio** is for clients that start the server themselves. No API key is needed.
- **HTTP** serves the streamable HTTP MCP endpoint on `/mcp` and refuses to start without an API key, see [Securing access](#securing-access).

## Docker

```bash
cp .env.example .env      # then fill in the addresses and API keys
openssl rand -hex 32      # generate the value of MCP_API_KEY in .env
docker compose up -d --build
```

The MCP endpoint is `http://localhost:3000/mcp` and every request must carry `MCP_API_KEY`. The compose file refuses to start without it and publishes the port on `127.0.0.1` only; `MCP_SERVER_PORT` in `.env` changes the published port (the container always listens on 3000).

Inside the container, `NAS_IP` must be reachable from Docker's network: use the LAN address of the machine running Radarr and Sonarr, not `127.0.0.1`.

Without compose:

```bash
docker build -t radarr-sonarr-mcp .
docker run -d --env-file .env -e MCP_SERVER_PORT=3000 -p 127.0.0.1:3000:3000 radarr-sonarr-mcp
```

### Prebuilt image and Portainer

A GitHub Action ([docker.yml](.github/workflows/docker.yml)) runs the tests, then builds a multi-architecture image (`linux/amd64`, `linux/arm64`) and publishes it to GitHub Container Registry on every commit to `main`. Nothing is published from `development` or from pull requests; pull requests only build the image and start it to check that it works.

| Tag | Content |
|---|---|
| `latest` | latest build of `main` |
| `0.1.0` | the `version` of `pyproject.toml` at that build (moves until the version is bumped) |
| `sha-<commit>` | one exact build, immutable: use it to pin a version |

To run it from Portainer (Stacks > Add stack > Web editor), paste [docker-compose.portainer.yml](docker-compose.portainer.yml) and fill in the variables of [.env.example](.env.example) in the "Environment variables" section (`MCP_API_KEY` is required). Optional variables: `IMAGE_TAG` (default `latest`, use a `sha-…` tag to pin a build), `MCP_SERVER_PORT` (published port) and `MCP_BIND` (published interface, default `127.0.0.1`).

- The image of a public repository can be pulled anonymously, so Portainer needs no registry credentials. If your fork's package is private (GitHub > Packages > the image > Package settings), make it public or add `ghcr.io` as a registry in Portainer with a personal access token that has the `read:packages` scope.
- To reach the server from another machine, set `MCP_BIND` to `0.0.0.0` or to the NAS LAN address. The traffic is then not encrypted: keep it on a trusted network or put a TLS reverse proxy in front, see [Securing access](#securing-access).
- Update with "Pull and redeploy" in Portainer.

## Securing access

The HTTP transport refuses to start without `MCP_API_KEY` (at least 16 characters). Generate one with `openssl rand -hex 32`. Clients must send it in one of these headers:

```
Authorization: Bearer <key>
X-API-Key: <key>
```

Requests without a valid key get `401`. The key is compared in constant time and is never accepted in the URL, so it does not end up in access logs. Treat it like a password: keep it in `.env` or the Portainer variables, never in git, and rotate it by changing the value and restarting the container.

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

Clients then use `https://mcp.example.com/mcp`. If proxied requests are rejected because of their `Host` header, add the domain to `MCP_ALLOWED_HOSTS`. The proxy is also the right place for rate limiting and IP allow-lists.

## Claude Desktop

The `claude_desktop_config.json` file only declares local (stdio) servers. Its location:

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

`mcpServers` is a top-level key of that file: add it next to the existing keys (do not paste a second JSON object after them, the file would become invalid). Then quit Claude Desktop completely and start it again.

### With the Docker container (recommended)

Start the container first, then bridge it to Claude Desktop with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) (needs Node.js). Your Radarr, Sonarr and Emby keys stay in the container's `.env`; only the access key `MCP_API_KEY` goes in the Claude Desktop configuration. The header reads the `${MCP_API_KEY}` variable from `env` and must have no space after the colon:

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

Use the port you published with `MCP_SERVER_PORT` if you changed it. The container must be running before Claude Desktop starts (it restarts with Docker thanks to `restart: unless-stopped`).

**Container on another machine** (a NAS for instance): use its address. With a plain `http://` URL that is not `localhost`, `mcp-remote` refuses to start unless you add `--allow-http`, and the server shows up as disconnected in Claude Desktop (the error is in `mcp-server-radarr_sonarr.log`). The key then travels in clear text, so keep it on a trusted network. Through an HTTPS reverse proxy (see [Securing access](#securing-access)) `--allow-http` is not needed.

```json
"args": ["-y", "mcp-remote@0.14.3", "http://192.168.1.10:3000/mcp", "--allow-http", "--header", "X-API-Key:${MCP_API_KEY}"]
```

### Without Docker

Claude Desktop starts the server itself over stdio, so no `MCP_API_KEY` is needed. The Radarr, Sonarr and media server keys are then part of the Claude Desktop configuration, see [claude_desktop_config.example.json](claude_desktop_config.example.json):

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
| `get_available_movies` | Movies from Radarr. Filters: `year`, `downloaded`, `watched` |
| `lookup_movie` | Search movies by title (Radarr lookup) |
| `get_available_series` | Series from Sonarr. Filters: `year`, `downloaded`, `watched` |
| `lookup_series` | Search series by title (Sonarr lookup) |
| `get_episodes` | Episodes of a series with download and watched status. Arguments: `series`, `season`, `watched`, `downloaded` |

`get_episodes` finds the series in Sonarr by title (exact match preferred) and returns an error with candidates if the title is unknown or ambiguous. Each episode has `season`, `episode`, `title`, `airDate`, `downloaded`, `monitored` and `watched`. `watched` is `null` when no Emby/Jellyfin server is configured or the series is not in its library.

Both listing tools also accept an `actors` argument, but Radarr and Sonarr do not return cast information, so it never matches anything at the moment.

Resources: `radarr-sonarr://movies` and `radarr-sonarr://series`.

Example questions for Claude:

- "Which episodes of Slow Horses have I downloaded but not watched?"
- "Do I have any unwatched movies from 2023?"
- "What is missing from season 6 of Slow Horses?"

## Watched status

- **Emby and Jellyfin**: the `Played` flag of the configured user. A series is watched when all its episodes are played. Emby can report `PlayCount: 0` for items marked as watched, so the play count alone is not used.
- **Matching**: Sonarr series and Radarr movies are linked to Emby/Jellyfin by TVDB / TMDB id, which requires those ids in the media server's metadata. Without a match the title is used (exact match first) and may pick the wrong item when titles are ambiguous.
- **No media server configured**: movies are reported as not watched, and series fall back to a Sonarr heuristic (all episodes downloaded), which is not a real watched status.
- **Plex** (experimental): series and movies are matched by title only, and the client does not request JSON from Plex, so the result is not reliable. Plex is not used by `get_episodes`.

## Finding keys and ids

- **Radarr, Sonarr**: Settings > General > API Key.
- **Emby**: Dashboard > Advanced > API Keys. **Jellyfin**: Dashboard > API Keys.
- **Emby / Jellyfin user id**: `*_USER_ID` is the user's **id** (a hex string), not the user name. The watched status is the one of that user. List the ids with:

  ```bash
  curl "http://<host>:8096/Users?api_key=<api key>"
  ```

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Work happens on branches merged into `development` through pull requests. `main` only receives releases and is protected: changes go through a pull request whose `test` check must pass, with no direct push or force push, even for administrators.

### Releasing

1. In a pull request to `development`, bump `version` in `pyproject.toml` and merge it.
2. Open a pull request from `development` to `main` (for example titled "Release 0.2.0") and merge it with **Create a merge commit**, not squash: a squash would make `main` and `development` diverge and the next release pull request would conflict.
3. The commit on `main` builds and publishes the Docker image, tagged `latest`, the version and `sha-<commit>` (see [Prebuilt image and Portainer](#prebuilt-image-and-portainer)). Wait for the "Docker image" workflow to succeed.
4. Tag and publish the release on that commit:

   ```bash
   gh release create 0.2.0 --target main --title 0.2.0 --generate-notes
   ```

5. Update the deployment: "Pull and redeploy" in Portainer, or set `IMAGE_TAG` to the `sha-…` tag to pin an exact build.

Do not delete the "untagged" versions of the package on GitHub: they are the per-platform images and attestations of the multi-architecture tags, and removing them leaves tags that cannot be pulled.

GitHub Actions runs on every pull request to `development`:

- the tests, and a build of the Docker image followed by a start-up check of the API key, without publishing anything ([ci.yml](.github/workflows/ci.yml))
- a [CodeQL](.github/workflows/codeql.yml) analysis of the Python code and of the workflows
- a [`pip-audit`](.github/workflows/dependency-audit.yml) scan of the dependencies

CodeQL and `pip-audit` also run every Monday. [Dependabot](.github/dependabot.yml) opens weekly update pull requests (Python, GitHub Actions, Docker base image) and security alerts, and secret scanning with push protection is enabled. The results are in the repository's *Security* tab.

## Security notes

- Use the HTTP transport only with an API key, and over HTTPS as soon as it leaves a trusted network, see [Securing access](#securing-access).
- The server talks to Radarr, Sonarr and the media servers over plain HTTP, so run it on the same trusted network.
- Keep `config.json` and `.env` out of version control (they are git-ignored).
