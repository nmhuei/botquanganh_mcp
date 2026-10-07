# Host Environment

## Runtime

- The MCP server uses the permissions of its process owner.
- `HOST_WORKSPACE_DIR` limits workspace file operations.
- Keep `HOST_RESTRICT_TO_WORKSPACE=true` unless an operator approves a wider scope.
- `HOST_COMMAND_POLICY=guarded` blocks explicit destructive or privileged commands.
- This service is not a sandbox. Allowed commands still use host-user permissions.

## Discovery

Call `server_info` for service health, active limits, sandbox location and the
eight-tool catalog. Use CLI or REST knowledge routes to inspect local guides
and the installed-command catalog.

## Workspace

Call `workspace_context(action="bind")` before workspace operations when
enforce mode is active. Reuse the returned `chat_id` for later tool calls.
