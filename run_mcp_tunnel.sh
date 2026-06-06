#!/bin/bash
# Convenience launcher for ChatGPT web MCP connector setup.

cd "$(dirname "$0")"
exec ./scripts/start_tunnel_server.sh
