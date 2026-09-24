"""Integration tests for CTF suite MCP tools (ctf_transform, ctf_pattern, ctf_hash_tool)."""

import pytest
from app.tools.ctf_suite import ctf_hash_tool, ctf_pattern, ctf_transform


def test_ctf_transform_tool_base64():
    res = ctf_transform("base64_encode", input_text="Hello CTF!")
    assert res["ok"] is True
    assert res["operation"] == "base64_encode"
    assert res["output_text"] == "SGVsbG8gQ1RGIQ=="

    dec = ctf_transform("base64_decode", input_text="SGVsbG8gQ1RGIQ==")
    assert dec["ok"] is True
    assert dec["output_text"] == "Hello CTF!"


def test_ctf_transform_tool_hex_and_xor():
    res = ctf_transform("hex_encode", input_text="ABCD")
    assert res["ok"] is True
    assert res["output_text"] == "41424344"

    xor_res = ctf_transform("xor_hex", input_text="ABCD", key_hex="20202020")
    assert xor_res["ok"] is True
    assert xor_res["output_text"] == "abcd"


def test_ctf_transform_tool_rot13():
    res = ctf_transform("rot13", input_text="cvpbPGS{grfg}")
    assert res["ok"] is True
    assert res["output_text"] == "picoCTF{test}"


def test_ctf_pattern_tool():
    # Create pattern
    create_res = ctf_pattern(action="create", length=32)
    assert create_res["ok"] is True
    assert create_res["pattern"] == "aaaabaaacaaadaaaeaaafaaagaaahaaa"

    # Find offset
    offset_res = ctf_pattern(action="offset", value="caaa")
    assert offset_res["ok"] is True
    assert offset_res["offset"] == 8

    # Find hex offset
    offset_hex = ctf_pattern(action="offset", value="0x61616164")
    assert offset_hex["ok"] is True
    assert offset_hex["offset"] == 12


def test_ctf_hash_tool_mcp():
    id_res = ctf_hash_tool(action="identify", value="5d41402abc4b2a76b9719d911017c592")
    assert id_res["ok"] is True
    names = [c["name"] for c in id_res["candidates"]]
    assert "MD5" in names

    comp_res = ctf_hash_tool(action="compute", value="admin")
    assert comp_res["ok"] is True
    assert comp_res["hashes"]["md5"] == "21232f297a57a5a743894a0e4a801fc3"
