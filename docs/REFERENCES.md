# References

These are the external references used when rewriting the operator and security
documentation. Local code remains the source of truth for exact tool names and
environment variables.

## MCP

- Model Context Protocol specification: Streamable HTTP transport
  - https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
  - Used for documenting the `/mcp` endpoint shape, HTTP transport assumptions,
    and security concerns around local binding and origin validation.

- Model Context Protocol specification: Authorization
  - https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
  - Used for the security note that long-lived public deployments should prefer
    a real authorization layer over a static shared URL.

## FastMCP

- FastMCP documentation
  - https://gofastmcp.com
  - Used for the `fastmcp run app/main.py --transport streamable-http --path
    /mcp` operating model.

- FastMCP server concepts
  - https://gofastmcp.com/servers/server
  - Used for documenting FastMCP server/tool registration at a high level.

## Cloudflare Tunnel

- Cloudflare Tunnel documentation
  - https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
  - Used for the public tunnel mental model.

- Cloudflare Quick Tunnels
  - https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/
  - Used for documenting that `trycloudflare.com` quick tunnel URLs are
    temporary/ephemeral and should not be treated as durable endpoints.

## Local Source Of Truth

The most important local files for behavior are:

```text
app/main.py
app/config.py
app/security.py
app/tools/*.py
scripts/start_tunnel_server.sh
scripts/restart_server_only.sh
.env
```

When docs and code disagree, inspect the code and update the docs.

## Agent Harness Design References

- OpenHands sandbox/runtime overview
  - https://docs.openhands.dev/openhands/usage/runtimes/overview
  - Used for the separation between planner, sandbox/runtime, and workspace.

- OpenHands remote agent server overview
  - https://docs.openhands.dev/sdk/guides/agent-server/overview
  - Used for the client/server/workspace/event-stream mental model.

- SWE-agent architecture
  - https://swe-agent.com/0.7/background/architecture/
  - Used for the environment, shell session, action/observation, and history
    compression patterns.

- SWE-agent environment reference
  - https://swe-agent.com/latest/reference/env/
  - Used for lifecycle hooks and environment management inspiration.

- LangGraph persistence
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - Used for checkpoint/resume/time-travel design ideas.

- OpenAI Agents SDK tracing
  - https://openai.github.io/openai-agents-python/tracing/
  - Used for tracing tool calls, guardrails, handoffs, and custom events.

- Claude Code hooks
  - https://code.claude.com/docs/en/hooks
  - Used for deterministic lifecycle hooks around tool use and stop/failure
    events.

- Google Agent Development Kit technical overview
  - https://google.github.io/adk-docs/get-started/about/
  - Used for session/event/artifact concepts.
