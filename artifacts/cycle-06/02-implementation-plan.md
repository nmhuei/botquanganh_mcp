# Implementation Plan — Official Cycle 06

## Goal
Create one shared error contract for MCP, REST, middleware, OpenAPI, and CLI-visible HTTP behavior.

## Tasks
1. Add a central exception/code/status/suggestion taxonomy.
2. Delegate MCP error envelopes and REST status mapping to the taxonomy.
3. Redact known workspace/repository/home paths from public messages.
4. Mask unexpected internal exception details.
5. Return JSON contract errors for authentication and rate limiting.
6. Publish the same code enum and response schema in OpenAPI.
7. Add exception matrix, REST integration, auth, rate-limit, and schema tests.
8. Reload only the bridge and verify public 404/400/OpenAPI behavior.
