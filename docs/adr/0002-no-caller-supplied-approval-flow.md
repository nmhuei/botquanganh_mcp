---
adr: 0002
title: No caller-supplied approval flow
status: Accepted
date: 2026-08-24
---

## Context

Versions up to v0.3.x exposed an interactive approval flow: a caller could pass
an approval token to authorize a command, resolved through a registry decoupled
from SSE subscribers (race fixed in b583e1e). In practice the approval came from
the same party requesting execution, so it added a bypass-shaped surface without
adding security.

## Decision

Delete the approval flow. `inspect_host_command` documents this explicitly:
"There is deliberately no caller-supplied approval bypass"
(`app/host/policy.py`). Authorization is purely server-side policy:
`guarded` blocks an explicit destructive-pattern list; `allowlist` additionally
requires every chained command to be listed. `get_capabilities` asserts
`caller_approval_parameter: false`.

## Consequences

- No approval race class to test or defend (the old resolve_approval/SSE races
  are gone with the feature).
- Feature requests re-introducing caller-controlled approval are rejected by
  policy (see `.github/ISSUE_TEMPLATE/feature_request.md` scope guard).
