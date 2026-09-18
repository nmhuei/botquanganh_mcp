"""LLM Honeypot, Canary, and Trap In-Place Sanitization Engine.

Automatically detects and sanitizes LLM honeypots, canary tokens, agent identifiers,
and anti-AI trap directives from both input (commands, file writes) and output (stdout,
stderr, file reads, search results).

Crucially, it redacts the honeypot/trap/agent tokens in-place without dropping the entire line
so that critical business data, flags, and surrounding code remain 100% intact.
"""

from __future__ import annotations

import re
from typing import Final

# Fast-path keyword check to avoid regex evaluation on benign texts
_FAST_TRIGGER_KEYWORDS: Final[tuple[str, ...]] = (
    "x-llm",
    "x_llm",
    "x-ai",
    "x_ai",
    "x-agent",
    "x_agent",
    "x-model",
    "x_model",
    "honeypot",
    "honey-port",
    "honey_port",
    "honey-token",
    "honey_token",
    "canary",
    "prompt-canary",
    "prompt_canary",
    "anti-llm",
    "anti_llm",
    "anti-ai",
    "anti_ai",
    "llm-trap",
    "llm_trap",
    "ai-trap",
    "ai_trap",
    "trap-llm",
    "trap_llm",
    "trap-ai",
    "trap_ai",
    "ignore-if-ai",
    "bot-honeypot",
    "agent-name",
    "agent_name",
    "agent:",
    "agent=",
    "model:",
    "model=",
    "llm:",
    "llm=",
    "llm-name",
    "llm_name",
    "llm-model",
    "llm_model",
    "target-model",
    "target_model",
    "target-agent",
    "target_agent",
    "antigravity",
    "claude",
    "openai",
    "muse",
    "gemini",
    "deepseek",
)

def _is_inside_quotes(s: str, pos: int) -> bool:
    """Return True if character at index pos in s is inside single or double quotes."""
    in_single = False
    in_double = False
    escaped = False
    for ch in s[:pos]:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
    return in_single or in_double


# Entire line is solely a honeypot/canary directive with no other code or data
_FULL_LINE_HONEYPOT_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^\s*
    (?:(?://|\#|--|/\*|<!--|;|%|\"|\*)\s*)?
    (?:
        x[\-_]llm[\-_][a-zA-Z0-9_\-\.]+
        |
        x[\-_]ai[\-_][a-zA-Z0-9_\-\.]+
        |
        x[\-_]agent[\-_][a-zA-Z0-9_\-\.]+
        |
        (?:llm|ai|bot|agent)[\-_]?(?:honeypot|honey[\-_]?(?:port|token)|canary(?:[\-_]?token)?|trap)
        |
        (?:anti|trap|block|deny|ignore|guard)[\-_]?(?:if[\-_]?)?(?:llm|ai|agent|bot|model)(?:[\-_]?(?:llm|ai|agent|bot|model))?
        |
        (?:honey[\-_]?(?:port|token)|canary[\-_]?token)
        |
        prompt[\-_]canary
    )
    (?:\s*[:=]|\s+is\b|\s+block\b|\s+deny\b|\s+guard\b).*?
    (?:\*/|-->)?\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Inline block comments: /* x-llm-trap: ... */
_BLOCK_COMMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*/\*.*?(?:x[\-_]llm|x[\-_]ai|x[\-_]agent|llm[\-_]honeypot|prompt[\-_]canary|canary|anti[\-_]ai|anti[\-_]llm).*?\*/",
    re.IGNORECASE,
)

# Inline HTML comments: <!-- x-llm-guard: ... -->
_HTML_COMMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*<!--.*?(?:x[\-_]llm|x[\-_]ai|x[\-_]agent|llm[\-_]honeypot|prompt[\-_]canary|canary|anti[\-_]ai|anti[\-_]llm).*?-->",
    re.IGNORECASE,
)

# Inline trailing line comments: // x-llm-... or # x-llm-...
# Must be a real comment delimiter, e.g. preceded by whitespace, quote/paren boundary, or start of line,
# NEVER part of a URL scheme like https:// or file://.
_LINE_COMMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:\s+|^|(?<=["'\)]))(?:(?<!:)//|#|--|;|%)\s*.*?(?:x[\-_]llm|x[\-_]ai|x[\-_]agent|x[\-_]model|llm[\-_]honeypot|canary|prompt[\-_]canary|honey[\-_]port|anti[\-_]ai|anti[\-_]llm|anti[\-_]agent|bot[\-_]honeypot|(?:agent|llm|model)\s*[:=]\s*(?:antigravity|agy|claude|openai|muse|gemini|deepseek|llama|qwen|mistral|chatgpt|gpt[\-_]?[0-9a-z\.]+|sonnet|opus|haiku)).*?$""",
    re.IGNORECASE,
)

# Inline directive/header: x-llm-anti: ... (optionally preceded by comment symbol)
_DIRECTIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:(?://|\#|--|;|%)\s*)?(?:x[\-_]llm[\-_][a-zA-Z0-9_\-\.]+|x[\-_]ai[\-_][a-zA-Z0-9_\-\.]+|prompt[\-_]canary|llm[\-_]honeypot)\s*[:=]\s*[^;\r\n"']*(?=(?:[;\r\n"']|\s*,\s*[a-zA-Z0-9_\-]+[:=]|$))""",
    re.IGNORECASE,
)

# Agent and LLM name tags: agent_name: "antigravity", x-model: claude, model: gpt-4o, agent=claude
_AGENT_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:x[\-_]agent[\-_][a-zA-Z0-9_\-\.]+|x[\-_]model[\-_][a-zA-Z0-9_\-\.]+|\b(?:x[\-_])?(?:agent|llm|model)(?:[\-_](?:name|id|type|target))?|target[\-_](?:model|agent))\s*[:=]\s*["']?(?:antigravity|agy|claude|openai|muse|gemini|deepseek|llama|qwen|mistral|chatgpt|gpt[\-_]?[0-9a-z\.]+|sonnet|opus|haiku)[^"',;\r\n\)]*["']?""",
    re.IGNORECASE,
)

# Bracketed agent/model identifiers: [agent: claude, model: opus], (agent: antigravity)
_BRACKET_AGENT_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:\[|\()\s*(?:agent|llm|model)\s*[:=]\s*[^\]\)]*(?:\]|\))""",
    re.IGNORECASE,
)

# Standalone bracketed agent name tags: [antigravity] or [claude]
_STANDALONE_BRACKET_AGENT_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:\[|\()\s*(?:antigravity|agy|claude|openai|muse|gemini|deepseek|llama|qwen|mistral|chatgpt)\s*(?:\]|\))""",
    re.IGNORECASE,
)

# JSON key-value pairs matching honeypot / canary fields
_JSON_HONEYPOT_RE: Final[re.Pattern[str]] = re.compile(
    r',?\s*\"(?:x[\-_]llm[^\"]*|x[\-_]ai[^\"]*|x[\-_]agent[^\"]*|llm[\-_]honeypot|prompt[\-_]canary)\"\s*:\s*\"[^\"]*\"',
    re.IGNORECASE,
)


def is_llm_honeypot_line(line: str) -> bool:
    """Return True if the entire line is purely an LLM honeypot/canary directive."""
    line_lower = line.lower()
    if not any(kw in line_lower for kw in _FAST_TRIGGER_KEYWORDS):
        return False
    return bool(_FULL_LINE_HONEYPOT_RE.match(line.rstrip("\r\n")))


def sanitize_llm_honeypots(text: str) -> tuple[str, list[str]]:
    """Sanitize text by removing honeypots, canaries, and agent/model tags in-place.

    Preserves all surrounding code, variables, tokens, and data.

    Args:
        text: Source code, document content, shell command string, or stdout/stderr.

    Returns:
        A tuple of (cleaned_text, stripped_entries).
    """
    if not text:
        return text, []

    text_lower = text.lower()
    if not any(kw in text_lower for kw in _FAST_TRIGGER_KEYWORDS):
        return text, []

    stripped: list[str] = []

    # 1. In-place JSON key-value scrub if text has JSON honeypot markers
    if '"x-llm' in text_lower or '"x_llm' in text_lower or '"llm' in text_lower or '"prompt-canary' in text_lower:
        def json_repl(m: re.Match[str]) -> str:
            chunk = m.group(0).strip()
            stripped.append(chunk)
            return ""
        text = _JSON_HONEYPOT_RE.sub(json_repl, text)

    lines = text.splitlines(keepends=True)
    cleaned_lines: list[str] = []

    for line in lines:
        stripped_line = line.rstrip("\r\n")

        # Fast-path per line
        if not any(kw in stripped_line.lower() for kw in _FAST_TRIGGER_KEYWORDS):
            cleaned_lines.append(line)
            continue

        # Case A: Entire line is purely a honeypot directive with no other code/data
        if is_llm_honeypot_line(stripped_line):
            stripped.append(stripped_line.strip())
            continue

        # Case B: Line contains important data/code AND inline honeypot/canary/agent tokens
        # Scrub ONLY the honeypot tokens in-place to protect surrounding data!
        new_line = stripped_line

        # Block comments: /* x-llm-trap: ... */
        for m in _BLOCK_COMMENT_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _BLOCK_COMMENT_RE.sub("", new_line)

        # HTML comments: <!-- x-llm-guard: ... -->
        for m in _HTML_COMMENT_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _HTML_COMMENT_RE.sub("", new_line)

        # Trailing line comments: // x-llm-... or # x-llm-...
        # Only strip as trailing comment if delimiter is OUTSIDE quotes
        for m in _LINE_COMMENT_RE.finditer(new_line):
            if not _is_inside_quotes(new_line, m.start()):
                stripped.append(m.group(0).strip())
                new_line = new_line[:m.start()]
                break

        # Standalone bracketed agent name tags: [antigravity]
        for m in _STANDALONE_BRACKET_AGENT_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _STANDALONE_BRACKET_AGENT_RE.sub("", new_line)

        # Bracketed agent tags: [agent: claude, model: opus]
        for m in _BRACKET_AGENT_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _BRACKET_AGENT_RE.sub("", new_line)

        # Standalone directives: x-llm-anti: ...
        for m in _DIRECTIVE_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _DIRECTIVE_RE.sub("", new_line)

        # Agent & model tags: agent_name: "antigravity"
        for m in _AGENT_TAG_RE.finditer(new_line):
            stripped.append(m.group(0).strip())
        new_line = _AGENT_TAG_RE.sub("", new_line)

        # If line originally had content and now is solely whitespace, only omit it if it was a honeypot
        if stripped_line.strip() and not new_line.strip():
            continue

        # Normalize redundant commas or extra spaces left by in-place deletion
        new_line = re.sub(r",(?:\s*,)+", ",", new_line)
        new_line = re.sub(r",\s*", ", ", new_line)
        new_line = re.sub(r"([\(\[])\s*,+\s*", r"\1", new_line)
        new_line = re.sub(r"\s*,+\s*([\)\]])", r"\1", new_line)
        new_line = re.sub(r"\(\s*\)", "", new_line)
        new_line = re.sub(r"\[\s*\]", "", new_line)
        new_line = re.sub(r"^\s*,+\s*", "", new_line)
        new_line = re.sub(r"\s*,+\s*$", "", new_line)

        # Preserve original indentation while collapsing extra interior spaces
        original_indent = len(stripped_line) - len(stripped_line.lstrip(" \t"))
        original_indent_str = stripped_line[:original_indent]
        body = new_line.strip()
        body = re.sub(r"[ \t]{2,}", " ", body)
        new_line = original_indent_str + body

        # Preserve original line break
        if line.endswith("\r\n"):
            new_line += "\r\n"
        elif line.endswith("\n"):
            new_line += "\n"

        cleaned_lines.append(new_line)

    cleaned_text = "".join(cleaned_lines)
    return cleaned_text, stripped


def sanitize_command(command: str) -> tuple[str, list[str]]:
    """Sanitize a shell command string, scrubbing honeypot/canary/agent tokens in-place."""
    return sanitize_llm_honeypots(command)


def sanitize_file_content(content: str) -> tuple[str, list[str]]:
    """Sanitize file content, scrubbing honeypot/canary/agent tokens in-place."""
    return sanitize_llm_honeypots(content)


def sanitize_output(output: str) -> tuple[str, list[str]]:
    """Sanitize command output (stdout/stderr), scrubbing honeypot/canary/agent tokens in-place."""
    return sanitize_llm_honeypots(output)
