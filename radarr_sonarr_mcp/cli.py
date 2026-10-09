"""Command-line interface for the Radarr/Sonarr MCP server."""

import argparse
import logging

from .config import Config, NasConfig, RadarrConfig, SonarrConfig, ServerConfig, load_config, save_config
from .server import create_server

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def configure():
    """Run the configuration wizard."""
    logging.info("==== Radarr/Sonarr MCP Server Configuration Wizard ====")
    
    # Try to load existing config
    config = None
    try:
        config = load_config()
        logging.info("Loaded existing configuration. Press Enter to keep current values.")
    except Exception:
        # No existing config or error loading
        pass
    
    # NAS configuration
    nas_ip = input(f"NAS/Server IP address [{config.nas_config.ip if config else '10.0.0.23'}]: ")
    nas_ip = nas_ip or (config.nas_config.ip if config else '10.0.0.23')
    
    nas_port = input(f"Default port [{config.nas_config.port if config else '7878'}]: ")
    nas_port = nas_port or (config.nas_config.port if config else '7878')
    
    # Radarr configuration
    radarr_api_key = input(f"Radarr API key [{config.radarr_config.api_key if config else ''}]: ")
    radarr_api_key = radarr_api_key or (config.radarr_config.api_key if config else '')
    if not radarr_api_key:
        logging.warning("Warning: Radarr API key is required for movie functionality!")
    
    radarr_port = input(f"Radarr port [{config.radarr_config.port if config else '7878'}]: ")
    radarr_port = radarr_port or (config.radarr_config.port if config else '7878')
    
    radarr_base_path = input(f"Radarr API base path [{config.radarr_config.base_path if config else '/api/v3'}]: ")
    radarr_base_path = radarr_base_path or (config.radarr_config.base_path if config else '/api/v3')
    
    # Sonarr configuration
    sonarr_api_key = input(f"Sonarr API key [{config.sonarr_config.api_key if config else ''}]: ")
    sonarr_api_key = sonarr_api_key or (config.sonarr_config.api_key if config else '')
    if not sonarr_api_key:
        logging.warning("Warning: Sonarr API key is required for TV show functionality!")
    
    sonarr_port = input(f"Sonarr port [{config.sonarr_config.port if config else '8989'}]: ")
    sonarr_port = sonarr_port or (config.sonarr_config.port if config else '8989')
    
    sonarr_base_path = input(f"Sonarr API base path [{config.sonarr_config.base_path if config else '/api/v3'}]: ")
    sonarr_base_path = sonarr_base_path or (config.sonarr_config.base_path if config else '/api/v3')
    
    # Server configuration
    server_port = input(f"MCP server port [{config.server_config.port if config else '3000'}]: ")
    if server_port:
        try:
            server_port = int(server_port)
        except ValueError:
            logging.warning("Invalid port number, using default.")
            server_port = config.server_config.port if config else 3000
    else:
        server_port = config.server_config.port if config else 3000
    
    # Create new config
    new_config = Config(
        nas_config=NasConfig(
            ip=nas_ip,
            port=nas_port
        ),
        radarr_config=RadarrConfig(
            api_key=radarr_api_key,
            base_path=radarr_base_path,
            port=radarr_port
        ),
        sonarr_config=SonarrConfig(
            api_key=sonarr_api_key,
            base_path=sonarr_base_path,
            port=sonarr_port
        ),
        server_config=ServerConfig(
            port=server_port
        )
    )
    
    # Save config
    save_config(new_config)
    logging.info("Configuration saved successfully!")
    logging.info(f"To start the server, run: radarr-sonarr-mcp start")
    
    return new_config


def start(config_path=None, transport="stdio"):
    """Start the MCP server."""
    server = create_server(config_path)
    server.start(transport=transport)


def show_status():
    """Show the current status of the server."""
    try:
        config = load_config()
        logging.info("==== Radarr/Sonarr MCP Server Status ====")
        logging.info(f"NAS IP: {config.nas_config.ip}")
        logging.info(f"Radarr Port: {config.radarr_config.port or config.nas_config.port}")
        logging.info(f"Sonarr Port: {config.sonarr_config.port or config.nas_config.port}")
        logging.info(f"MCP Server Port: {config.server_config.port}")
        logging.info(f"MCP Endpoint URL: http://localhost:{config.server_config.port}")
        logging.info(f"Server is configured. Use 'radarr-sonarr-mcp start' to run the server.")
    except Exception as e:
        logging.error(f"Server is not configured: {e}")
        logging.info("Run 'radarr-sonarr-mcp configure' to set up the server.")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Radarr/Sonarr MCP Server")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Configure command
    configure_parser = subparsers.add_parser("configure", help="Configure the MCP server")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start the MCP server")
    start_parser.add_argument("--config", help="Path to config.json file")
    start_parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                              help="stdio (Claude Desktop, default) or http (listens on the configured port)")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show the server status")
    
    args = parser.parse_args()
    
    if args.command == "configure":
        configure()
    elif args.command == "start":
        start(args.config, args.transport)
    elif args.command == "status":
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
