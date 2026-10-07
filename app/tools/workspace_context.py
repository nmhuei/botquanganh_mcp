"""Unified workspace context tool: session lifecycle, state persistence, hypotheses matrix, and resume briefings.

Consolidates workspace binding, workspace discovery, note taking, and persistent context management
into an evolved super-tool. Provides the authoritative memory gateway for AI agents to persist
working state (CURRENT.json / STATE.md), record negative knowledge (Hypotheses Matrix),
and generate instant Resume Briefings to rehydrate context without re-work.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import app.config
from app.chat_identity import InvalidChatId, validate_chat_id
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools_common import (
    _guard_chat_id,
    _record_tool_call,
    enforce_bridge_payload_limit,
)


def _chat_root() -> Path:
    return Path(getattr(app.config, "HOST_CHAT_ROOT", "/home/light/Downloads/bqa-workspaces")).expanduser().resolve()


def _get_workspace_manager():
    from app.chat_workspace import WorkspaceManager
    return WorkspaceManager(_chat_root())


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


@mcp.tool(
    name="workspace_context",
    description=(
        "Unified workspace context super-tool. Manages session binding, state persistence "
        "(CURRENT.json, STATE.md), operational notes, the Hypotheses Matrix (do-not-retry negative knowledge), "
        "and Resume Briefings for immediate agent rehydration. Call this before workspace exploration, "
        "Actions bind and list are permitted prior to binding for session initialization and discovery."
    ),
)
def workspace_context(
    action: str = "bind",
    chat_id: Optional[str] = None,
    resume_id: Optional[str] = None,
    label: Optional[str] = None,
    note: Optional[str] = None,
    state_update: Optional[dict[str, Any]] = None,
    hypothesis: Optional[str] = None,
    hypothesis_result: Optional[str] = None,
    do_not_retry: bool = False,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Manage the persistent lifecycle, memory, and cognitive state of the workspace."""
    valid_actions = {"bind", "list", "note", "state", "hypotheses", "resume"}
    normalized_action = (action or "bind").strip().lower()
    if normalized_action not in valid_actions:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_ACTION",
                "message": f"Unknown workspace_context action: {action}. Expected bind, list, note, state, hypotheses, or resume.",
            },
        }

    validated_id, rejection = _guard_chat_id("workspace_context", chat_id, action=normalized_action)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "workspace_context")

    try:
        mgr = _get_workspace_manager()

        if normalized_action == "bind":
            target = resume_id or chat_id
            if target and target not in {"latest", "@latest"} and not target.startswith("latest:"):
                validate_chat_id(target)

            bound = mgr.create_or_bind(
                target,
                label=label,
                require_token=False,
            )
            ws_dir = bound.path
            assigned_chat_id = bound.chat_id

            # Ensure baseline persistent context files exist
            current_file = ws_dir / "CURRENT.json"
            if not current_file.exists():
                _write_json_file(
                    current_file,
                    {
                        "chat_id": assigned_chat_id,
                        "label": label or "default",
                        "status": "active",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "objective": "",
                        "current_task": "Initialized workspace",
                    },
                )

            hypo_file = ws_dir / "hypotheses.json"
            if not hypo_file.exists():
                _write_json_file(hypo_file, [])

            state_file = ws_dir / "STATE.md"
            if not state_file.exists():
                state_file.write_text(
                    f"# Workspace State: {assigned_chat_id}\n\nStatus: Initialized\n",
                    encoding="utf-8",
                )

            from app.workspace_binding import register_workspace_binding

            meta_file = ws_dir / "meta.json"
            meta_created = None
            if meta_file.is_file():
                try:
                    meta_created = json.loads(meta_file.read_text(encoding="utf-8")).get("created_at")
                except Exception:
                    pass
            register_workspace_binding(_chat_root(), assigned_chat_id, meta_created)

            _record_tool_call("workspace_context", assigned_chat_id)
            return {
                "ok": True,
                "action": "bind",
                "chat_id": assigned_chat_id,
                "workspace_path": str(ws_dir),
                "created": bound.created,
                "resumed_hint": getattr(bound, "resumed_hint", None),
                "message": f"Bound to workspace {assigned_chat_id} at {ws_dir}",
            }

        elif normalized_action == "list":
            workspaces = []
            root = _chat_root()
            if root.is_dir():
                for item in sorted(root.iterdir()):
                    if item.is_dir() and not item.name.startswith("."):
                        meta_file = item / "meta.json"
                        meta = _read_json_file(meta_file, {})
                        workspaces.append(
                            {
                                "chat_id": item.name,
                                "created_at": meta.get("created_at"),
                                "label": meta.get("label"),
                            }
                        )

            _record_tool_call("workspace_context", None)
            return {
                "ok": True,
                "action": "list",
                "total": len(workspaces),
                "workspaces": workspaces,
            }

        target_chat_id = validated_id or chat_id
        ws_dir = mgr.workspace_path(target_chat_id)
        if not ws_dir.is_dir():
            return {
                "ok": False,
                "error": {
                    "code": "WORKSPACE_NOT_FOUND",
                    "message": f"Workspace directory for {target_chat_id} does not exist.",
                },
            }

        if normalized_action == "note":
            if not note:
                return {
                    "ok": False,
                    "error": {
                        "code": "MISSING_NOTE",
                        "message": "Action 'note' requires 'note' content.",
                    },
                }

            notes_dir = ws_dir / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            log_file = notes_dir / "log.txt"
            now_iso = datetime.now(timezone.utc).isoformat()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now_iso}] {note.strip()}\n")

            _record_tool_call("workspace_context", target_chat_id)
            return {"ok": True, "action": "note", "saved": True, "chat_id": target_chat_id}

        elif normalized_action == "state":
            current_file = ws_dir / "CURRENT.json"
            state_file = ws_dir / "STATE.md"

            if state_update:
                current_data = _read_json_file(current_file, {})
                current_data.update(state_update)
                current_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_json_file(current_file, current_data)

            current = _read_json_file(current_file, {})
            state_text = state_file.read_text(encoding="utf-8", errors="replace") if state_file.is_file() else ""

            _record_tool_call("workspace_context", target_chat_id)
            return {
                "ok": True,
                "action": "state",
                "current": current,
                "state_md": state_text,
            }

        elif normalized_action == "hypotheses":
            hypo_file = ws_dir / "hypotheses.json"
            hypotheses = _read_json_file(hypo_file, [])

            if hypothesis:
                new_entry = {
                    "hypothesis": hypothesis,
                    "result": hypothesis_result or "failed",
                    "do_not_retry": do_not_retry,
                    "reason": reason or "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                hypotheses.append(new_entry)
                _write_json_file(hypo_file, hypotheses)

            _record_tool_call("workspace_context", target_chat_id)
            return {
                "ok": True,
                "action": "hypotheses",
                "total": len(hypotheses),
                "hypotheses": hypotheses,
                "avoid_approaches": [h for h in hypotheses if h.get("do_not_retry")],
            }

        elif normalized_action == "resume":
            current = _read_json_file(ws_dir / "CURRENT.json", {})
            state_file = ws_dir / "STATE.md"
            state_md = state_file.read_text(encoding="utf-8", errors="replace") if state_file.is_file() else ""
            hypotheses = _read_json_file(ws_dir / "hypotheses.json", [])
            notes_file = ws_dir / "notes" / "log.txt"
            recent_notes = ""
            if notes_file.is_file():
                recent_notes = "\n".join(notes_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:])

            avoid_list = [h for h in hypotheses if h.get("do_not_retry")]

            briefing = (
                f"# Resume Briefing: {target_chat_id}\n\n"
                f"- **Objective**: {current.get('objective', 'General task execution')}\n"
                f"- **Current Task**: {current.get('current_task', 'Pending next command')}\n"
                f"- **Status**: {current.get('status', 'active')}\n"
                f"- **Known Anti-Patterns (Do NOT retry)**: {len(avoid_list)} recorded\n"
            )
            for av in avoid_list[:5]:
                briefing += f"  - [AVOID] {av.get('hypothesis')}: {av.get('reason')}\n"

            if recent_notes:
                briefing += f"\n### Recent Notes:\n{recent_notes}\n"

            _record_tool_call("workspace_context", target_chat_id)
            return {
                "ok": True,
                "action": "resume",
                "chat_id": target_chat_id,
                "resume_briefing_md": briefing,
                "current": current,
                "avoid_approaches": avoid_list,
            }

        else:
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_ACTION",
                    "message": f"Unknown workspace_context action: {action}. Expected bind, list, note, state, hypotheses, or resume.",
                },
            }
    except Exception as exc:
        return enforce_bridge_payload_limit(format_error_response(exc), "workspace_context")
