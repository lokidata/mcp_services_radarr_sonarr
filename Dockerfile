FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY radarr_sonarr_mcp ./radarr_sonarr_mcp
RUN pip install .

# Run as an unprivileged user
RUN useradd --create-home mcp
USER mcp

# Configuration comes from environment variables (see README)
ENV MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=3000
EXPOSE 3000

CMD ["radarr-sonarr-mcp", "start", "--transport", "http"]
