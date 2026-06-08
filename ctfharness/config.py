from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .constants import (
    AUTHORIZED_REMOTE_DOMAINS_DEFAULT,
    FLAG_REGEX_DEFAULT,
    REJECT_DECOY_WORDS_DEFAULT,
    WORKSPACE_ROOT,
)

try:
    import yaml
except Exception as exc:  # pragma: no cover
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


DEFAULT_CONFIG = "ctf.yaml"


def load_config(path: str | os.PathLike[str] = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Missing config: {cfg_path}. Copy ctf.example.yaml to ctf.yaml or run ctfh init."
        )
    if yaml is None:
        raise RuntimeError(f"PyYAML is required: {YAML_IMPORT_ERROR}")
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    normalize_config(data)
    return data


def normalize_config(cfg: dict[str, Any]) -> None:
    cfg.setdefault("challenge", {})
    cfg.setdefault("policy", {})
    cfg.setdefault("local", {})
    cfg.setdefault("solver", {})
    cfg.setdefault("remote", {})
    cfg.setdefault("proof", {})

    ch = cfg["challenge"]
    ch.setdefault("name", "unnamed-challenge")
    ch.setdefault("category", "misc")
    ch.setdefault("workspace", WORKSPACE_ROOT)
    ch.setdefault("flag_regex", FLAG_REGEX_DEFAULT)

    pol = cfg["policy"]
    pol.setdefault("local_first", True)
    pol.setdefault("require_remote_evidence", True)
    pol.setdefault("reject_decoy_words", list(REJECT_DECOY_WORDS_DEFAULT))
    pol.setdefault("authorized_remote_domains", list(AUTHORIZED_REMOTE_DOMAINS_DEFAULT))

    for section in ("build", "start", "smoke", "stop"):
        cfg["local"].setdefault(section, [])
        if isinstance(cfg["local"][section], str):
            cfg["local"][section] = [cfg["local"][section]]


def challenge_dir(cfg: dict[str, Any]) -> Path:
    return Path(cfg["challenge"]["workspace"]) / safe_name(cfg["challenge"]["name"])


def safe_name(s: str) -> str:
    keep = []
    for c in str(s):
        if c.isalnum() or c in ("-", "_", "."):
            keep.append(c)
        else:
            keep.append("-")
    return "".join(keep).strip("-") or "challenge"
