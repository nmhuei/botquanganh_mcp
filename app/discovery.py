"""Dynamic MCP tool discovery engine.

Automatically imports all modules inside app.tools (and subpackages).
Each module registers its own tools through @mcp.tool().
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

from app.logging_audit import log_audit_event

logger = logging.getLogger(__name__)

_LOADED_MODULES: set[str] = set()

# MCP 2.0 exposes only the eight replacement super-tools from this package.
# Historical log readers remain compatible; retired MCP operations are not registered.
_DISCOVERABLE_TOOLS = frozenset(
    {
        "server_info",
        "task",
        "terminal_execute",
        "web_intelligence",
        "workspace_context",
        "workspace_edit",
        "workspace_explore",
        "workspace_search",
    }
)


def discover_and_register_tools(tools_package_path: str = "app.tools") -> list[str]:
    """Discover and import MCP tool modules automatically.

    Fault-tolerant: SyntaxError or ImportError in a single tool module will not crash
    the server, but will log an audit warning and continue importing others.
    """
    loaded: list[str] = []
    try:
        tools_package = importlib.import_module(tools_package_path)
    except Exception as exc:
        logger.exception("Cannot import tools package: %s", tools_package_path)
        log_audit_event("TOOL_DISCOVERY_ERROR", {"package": tools_package_path, "error": str(exc)})
        return loaded

    package_path = getattr(tools_package, "__path__", None)
    if package_path is None:
        logger.error("Package path invalid: %s", tools_package_path)
        return loaded

    discovered = pkgutil.walk_packages(
        package_path,
        prefix=f"{tools_package_path}.",
    )

    for module_info in discovered:
        module_name = module_info.name
        short_name = module_name.rsplit(".", 1)[-1]
        if short_name not in _DISCOVERABLE_TOOLS:
            continue
        if module_name in _LOADED_MODULES:
            continue

        try:
            importlib.import_module(module_name)
            _LOADED_MODULES.add(module_name)
            loaded.append(module_name)
            logger.info("Loaded MCP tool module: %s", module_name)
        except (SyntaxError, ImportError) as exc:
            logger.warning("Error in tool module %s: %s", module_name, exc)
            log_audit_event(
                "TOOL_MODULE_LOAD_FAIL",
                {"module": module_name, "error": str(exc), "type": type(exc).__name__},
            )
        except Exception as exc:
            logger.exception("Failed loading tool module: %s", module_name)
            log_audit_event(
                "TOOL_MODULE_LOAD_FAIL",
                {"module": module_name, "error": str(exc), "type": type(exc).__name__},
            )

    return loaded
