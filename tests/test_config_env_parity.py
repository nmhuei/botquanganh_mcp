"""Differential safety net for the minimal .env loader in app.config.

Every case asserts that ``app.config._load_env_file`` mutates ``os.environ``
IDENTICALLY to ``dotenv.load_dotenv`` (which runs with its defaults:
``override=False``, ``interpolate=True``, ``encoding="utf-8"``). If this suite
fails, the minimal loader has drifted from python-dotenv and must not be used.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv as dotenv_load_dotenv

from app.config import _load_env_file

P = "BQA_PARITY_"

CASES = {
    "plain": f"{P}A=1\n",
    "empty_value": f"{P}EMPTY=\n",
    "spaces_around_eq": f"{P}SP = value \n",
    "quoted_hash_double": f'{P}QH="v # here"\n',
    "quoted_hash_single": f"{P}QHS='v # here'\n",
    "unquoted_inline_comment": f"{P}UC=val # comment\n",
    "hash_without_space_kept": f"{P}HNOS=v#x\n",
    "escaped_quotes_double": f'{P}EQ="say \\"hi\\" and \\\\ done"\n',
    "single_quote_escape": f"{P}SQE='it\\'s here'\n",
    "double_quoted_escapes": f'{P}DQE="tab\\tnewline\\nend"\n',
    "single_quoted_no_escapes": f"{P}SQN='a\\nb'\n",
    "export_prefix": f"export {P}EX=plain\nexport {P}EXQ=\"quoted v\"\n",
    "crlf_lines": (
        f"{P}C1=one\r\n{P}C2=\"two\"\r\n# comment\r\n{P}C3=three\r\n"
    ),
    "duplicate_keys_last_wins": f"{P}DUP=first\n{P}DUP=second\n",
    "duplicate_mixed_styles": f'{P}DUP2="quoted one"\n{P}DUP2=plain two\n',
    "comments_and_blanks": (
        f"# leading comment\n\n   # indented comment\n{P}CB=yes  # trailing\n"
    ),
    "bare_word_no_equals": f"{P}SETME=1\nJUSTAWORD\n",
    "equals_only_line": "=novalue\n",
    "unterminated_quote": f'{P}OK1=before\n{P}BROKEN="oops\n{P}OK2=after\n',
    "value_starts_with_hash": f"{P}HASHVAL= # tricky\n",
    "multiline_double_quoted": f'{P}ML="line1\nline2"\n',
    "interp_from_file_var": f"{P}BASE=/opt/x\n{P}USE=${{{P}BASE}}/bin\n",
    "interp_from_environ_var": f"{P}FROMENV=${{{P}PRESET}}/suffix\n",
    "interp_missing_default": f"{P}DEF=${{{P}NOT_SET_XYZ:-fallback}}\n",
    "interp_missing_empty": f"{P}NOVAR=${{{P}NOT_SET_XYZ}}\n",
    "interp_environ_wins_over_file": (
        f"{P}WIN=file_value\n{P}DERIVED=${{{P}WIN}}/sub\n"
    ),
    "interp_literal_dollar": f"{P}LIT=a$b c\n{P}ESC=\\${{{P}NOT_SET_XYZ}}\n",
}

INTERP_ENV_KEYS = {
    "interp_from_environ_var": f"{P}PRESET",
    "interp_environ_wins_over_file": f"{P}WIN",
}


def _capture(keys: set[str]) -> dict[str, str]:
    return {key: os.environ[key] for key in keys if key in os.environ}


def _restore(previous: dict[str, str], keys: set[str]) -> None:
    for key in keys:
        os.environ.pop(key, None)
    os.environ.update(previous)


def _case_keys(name: str) -> set[str]:
    return {
        line.split("=", 1)[0].replace("export ", "").strip()
        for line in CASES[name].splitlines()
        if "=" in line
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_env_loader_matches_dotenv(name, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(CASES[name], encoding="utf-8")
    keys = {key for key in _case_keys(name) if key.startswith(P)}
    preset_keys = {INTERP_ENV_KEYS.get(name)} - {None}

    for preset_key in preset_keys:
        os.environ[preset_key] = f"{preset_key}_value"
        keys.add(preset_key)

    try:
        baseline = _capture(keys)
        _load_env_file(env_path)
        mine = _capture(keys)
        _restore(baseline, keys)

        dotenv_load_dotenv(env_path)
        theirs = _capture(keys)
        _restore(theirs, keys)

        assert mine == theirs
    finally:
        for preset_key in preset_keys:
            os.environ.pop(preset_key, None)


def test_existing_environ_not_overridden(tmp_path):
    """load_dotenv() default is override=False: pre-set vars must survive."""
    key = f"{P}OVERRIDE_ME"
    env_path = tmp_path / ".env"
    env_path.write_text(f"{key}=from_file\n", encoding="utf-8")

    os.environ[key] = "from_environ"
    try:
        _load_env_file(env_path)
        assert os.environ[key] == "from_environ"

        del os.environ[key]
        dotenv_load_dotenv(env_path)
        assert os.environ[key] == "from_file"
    finally:
        os.environ.pop(key, None)
