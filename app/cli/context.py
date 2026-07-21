from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.cli.config_view import load_env
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError


GLOBAL_FLAG_OPTIONS = {"--json", "--no-color", "--verbose", "--quiet", "--public", "--local"}
GLOBAL_VALUE_OPTIONS = {"--base-url", "--token", "--token-file", "--request-timeout"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    for suffix in ("/api/v1", "/mcp"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    if not value.startswith(("http://", "https://")):
        raise CLIError("Base URL must start with http:// or https://.", EXIT_USAGE)
    return value.rstrip("/")


def extract_global_options(argv: Sequence[str]) -> list[str]:
    """Allow global options before or after subcommands.

    Command payloads should be passed as one quoted positional argument. Tokens after
    an explicit ``--`` are preserved verbatim.
    """
    globals_found: list[str] = []
    remaining: list[str] = []
    index = 0
    passthrough = False
    while index < len(argv):
        token = argv[index]
        if passthrough:
            remaining.append(token)
            index += 1
            continue
        if token == "--":  # nosec B105
            passthrough = True
            remaining.append(token)
            index += 1
            continue
        if token in GLOBAL_FLAG_OPTIONS:
            globals_found.append(token)
            index += 1
            continue
        matched_value_option = next(
            (name for name in GLOBAL_VALUE_OPTIONS if token == name or token.startswith(name + "=")),
            None,
        )
        if matched_value_option:
            globals_found.append(token)
            if token == matched_value_option:
                if index + 1 >= len(argv):
                    globals_found.append("")
                else:
                    globals_found.append(argv[index + 1])
                    index += 1
            index += 1
            continue
        remaining.append(token)
        index += 1
    return [*globals_found, *remaining]


@dataclass(slots=True)
class CLIContext:
    repo_root: Path
    values: dict[str, str]
    base_url: str
    token: str
    request_timeout: float
    json_output: bool = False
    no_color: bool = False
    verbose: bool = False
    quiet: bool = False
    public: bool = False

    @classmethod
    def from_args(cls, args) -> "CLIContext":
        root = repo_root()
        values = load_env(root)

        selected = sum(
            bool(item)
            for item in (
                getattr(args, "public", False),
                getattr(args, "local", False),
                getattr(args, "base_url", None),
            )
        )
        if selected > 1:
            raise CLIError("Use only one of --public, --local, or --base-url.", EXIT_USAGE)

        public = bool(getattr(args, "public", False))
        explicit_base = getattr(args, "base_url", None) or os.getenv("BQA_BASE_URL", "")
        if explicit_base:
            base_url = normalize_base_url(explicit_base)
        elif public:
            url_file = root / "logs" / "tunnel_url.txt"
            if not url_file.is_file():
                raise NotFoundCLIError(f"Tunnel URL file not found: {url_file}")
            base_url = normalize_base_url(url_file.read_text(encoding="utf-8").splitlines()[0])
        else:
            connect_host = values.get("MCP_CONNECT_HOST", "127.0.0.1").strip() or "127.0.0.1"
            if connect_host in {"0.0.0.0", "::"}:  # nosec B104
                connect_host = "127.0.0.1"
            port = values.get("MCP_PORT", "8000").strip() or "8000"
            base_url = normalize_base_url(f"http://{connect_host}:{port}")

        token = getattr(args, "token", None) or ""
        token_file = getattr(args, "token_file", None)
        if token and token_file:
            raise CLIError("Use only one of --token or --token-file.", EXIT_USAGE)
        if token_file:
            path = Path(token_file).expanduser()
            if not path.is_file():
                raise NotFoundCLIError(f"Token file not found: {path}")
            token = path.read_text(encoding="utf-8").strip()
        if not token:
            token = os.getenv("BQA_TOKEN") or os.getenv("GATEWAY_TOKEN") or values.get("GATEWAY_TOKEN", "")

        try:
            request_timeout = float(getattr(args, "request_timeout", 15.0))
        except (TypeError, ValueError) as exc:
            raise CLIError("--request-timeout must be a number.", EXIT_USAGE) from exc
        if request_timeout <= 0:
            raise CLIError("--request-timeout must be greater than zero.", EXIT_USAGE)

        return cls(
            repo_root=root,
            values=values,
            base_url=base_url,
            token=token,
            request_timeout=request_timeout,
            json_output=bool(getattr(args, "json", False)),
            no_color=bool(getattr(args, "no_color", False)),
            verbose=bool(getattr(args, "verbose", False)),
            quiet=bool(getattr(args, "quiet", False)),
            public=public,
        )
