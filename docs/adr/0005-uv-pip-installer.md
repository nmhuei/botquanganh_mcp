---
adr: 0005
title: uv pip replaces pip in install.sh
status: Accepted
date: 2026-08-20
---

## Context

The one-line installer previously used `pip`, which was slow to resolve and
prone to polluting system site-packages on machines without venv discipline.

## Decision

`install.sh` creates/reuses `.venv` and installs through `uv pip`
(commit ca72210); dependencies stay pinned in `pyproject.toml`
(`fastmcp==3.4.0`, `pytest==9.1.1` under `[test]`).

## Consequences

- Faster cold installs; deterministic pinned resolution.
- Contributors need `uv` available (documented in install path) or can fall
  back to plain `pip` manually against `.venv`.
