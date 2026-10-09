#!/usr/bin/env python3
"""
Simple script to run the MCP server directly without installation.
Useful for development.
"""

import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from radarr_sonarr_mcp.cli import main

if __name__ == "__main__":
    main()
