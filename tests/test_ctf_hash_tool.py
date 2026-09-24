"""Unit tests for hash identification and digest calculator."""

import pytest
from app.ctf.hash_tool import compute_hashes, identify_hash


def test_identify_hash_bcrypt():
    h = "$2a$12$e8n02nddIeF.T4jI7f7tEe08wP/gW42dG224fXw0rVn67h5n/U4k6"
    results = identify_hash(h)
    assert len(results) > 0
    assert results[0]["name"] == "bcrypt"
    assert results[0]["confidence"] == "high"


def test_identify_hash_sha512crypt():
    h = "$6$rounds=5000$usesomesillystri$D4Iuz6qKEU9AcULwVSVUETgUMbhVYnxJxFaVBgCcDCxrvUK6G58QBGs60gy9hkB5m20/k44/J/Z8Tsnk9p9qj0"
    results = identify_hash(h)
    assert len(results) > 0
    assert "SHA-512 Crypt" in results[0]["name"]


def test_identify_hash_md5():
    h = "5d41402abc4b2a76b9719d911017c592"
    results = identify_hash(h)
    names = [r["name"] for r in results]
    assert "MD5" in names
    assert "NTLM" in names


def test_identify_hash_sha1():
    h = "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"
    results = identify_hash(h)
    names = [r["name"] for r in results]
    assert "SHA-1" in names


def test_identify_hash_sha256():
    h = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    results = identify_hash(h)
    names = [r["name"] for r in results]
    assert "SHA-256" in names


def test_identify_hash_crc32():
    h = "3610a686"
    results = identify_hash(h)
    names = [r["name"] for r in results]
    assert "CRC-32" in names


def test_compute_hashes():
    data = "hello"
    res = compute_hashes(data)
    assert res["md5"] == "5d41402abc4b2a76b9719d911017c592"
    assert res["sha1"] == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"
    assert res["sha256"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert res["crc32"] == "3610a686"
    # NTLM of hello
    assert len(res["ntlm"]) == 32
