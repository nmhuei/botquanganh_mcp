"""Unit tests for CTF cyclic pattern generator and offset finder."""

import pytest
from app.ctf.pattern import cyclic_create, cyclic_offset


def test_cyclic_create_basic():
    p = cyclic_create(16)
    assert len(p) == 16
    assert p == "aaaabaaacaaadaaa"


def test_cyclic_create_length_limit():
    with pytest.raises(ValueError, match="positive integer"):
        cyclic_create(0)
    with pytest.raises(ValueError, match="positive integer"):
        cyclic_create(-10)


def test_cyclic_offset_string():
    assert cyclic_offset("aaaa") == 0
    assert cyclic_offset("baaa") == 4
    assert cyclic_offset("caaa") == 8
    assert cyclic_offset("daaa") == 12


def test_cyclic_offset_hex_string():
    # 0x61616163 in little endian is 'caaa'
    assert cyclic_offset("0x61616163") == 8
    assert cyclic_offset("0x61616162") == 4


def test_cyclic_offset_int():
    # 0x61616163 is 'caaa'
    assert cyclic_offset(0x61616163) == 8


def test_cyclic_offset_width_8():
    p = cyclic_create(32, width=8)
    assert len(p) == 32
    assert cyclic_offset("aaaaaaaa", width=8) == 0
    assert cyclic_offset("baaaaaaa", width=8) == 8


def test_cyclic_offset_not_found():
    assert cyclic_offset("ZZZZ") == -1
