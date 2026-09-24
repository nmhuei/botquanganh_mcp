"""Pure-Python cryptographic hash identification and digest calculation for CTF.

Zero external dependencies; uses standard hashlib, binascii, and zlib.
"""

from __future__ import annotations

import binascii
import hashlib
import re
import string
from typing import Any
import zlib


_HEX_CHARS = frozenset(string.hexdigits)

_HASH_SIGNATURES: list[dict[str, Any]] = [
    {
        "pattern": re.compile(r"^\$2[aby]?\$\d{2}\$[./A-Za-z0-9]{53}$"),
        "name": "bcrypt",
        "category": "Password Hash",
        "description": "OpenBSD Blowfish-based password hashing algorithm",
        "hashcat_mode": 3200,
        "john_format": "bcrypt",
    },
    {
        "pattern": re.compile(r"^\$6\$(?:rounds=\d+\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}$"),
        "name": "SHA-512 Crypt (Unix)",
        "category": "Password Hash",
        "description": "Linux /etc/shadow standard SHA-512 crypt",
        "hashcat_mode": 1800,
        "john_format": "sha512crypt",
    },
    {
        "pattern": re.compile(r"^\$5\$(?:rounds=\d+\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{43}$"),
        "name": "SHA-256 Crypt (Unix)",
        "category": "Password Hash",
        "description": "Linux /etc/shadow standard SHA-256 crypt",
        "hashcat_mode": 7400,
        "john_format": "sha256crypt",
    },
    {
        "pattern": re.compile(r"^\$1\$[./A-Za-z0-9]{1,8}\$[./A-Za-z0-9]{22}$"),
        "name": "MD5 Crypt (Unix)",
        "category": "Password Hash",
        "description": "FreeBSD/Linux MD5 crypt password hash",
        "hashcat_mode": 500,
        "john_format": "md5crypt",
    },
    {
        "pattern": re.compile(r"^\$apr1\$[./A-Za-z0-9]{1,8}\$[./A-Za-z0-9]{22}$"),
        "name": "Apache MD5 (apr1)",
        "category": "Password Hash",
        "description": "Apache htpasswd APR1-MD5 password hash",
        "hashcat_mode": 1600,
        "john_format": "md5apr1",
    },
    {
        "pattern": re.compile(r"^\$argon2(?:id|i|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$[./A-Za-z0-9+]+(?:\$[./A-Za-z0-9+]+)?$"),
        "name": "Argon2",
        "category": "Password Hash",
        "description": "Password Hashing Competition winner Argon2id / Argon2i",
        "hashcat_mode": 13400,
        "john_format": "argon2",
    },
]

_LENGTH_CANDIDATES: dict[int, list[dict[str, Any]]] = {
    8: [
        {"name": "CRC-32", "bit_length": 32, "category": "Checksum", "description": "Cyclic redundancy check (32-bit)", "hashcat_mode": 11500, "john_format": "crc32"},
        {"name": "Adler-32", "bit_length": 32, "category": "Checksum", "description": "Adler-32 checksum", "hashcat_mode": None, "john_format": None},
    ],
    32: [
        {"name": "MD5", "bit_length": 128, "category": "Cryptographic Hash", "description": "Standard MD5 message digest", "hashcat_mode": 0, "john_format": "raw-md5"},
        {"name": "NTLM", "bit_length": 128, "category": "Windows Hash", "description": "Windows NT LAN Manager password hash (MD4(UTF-16LE))", "hashcat_mode": 1000, "john_format": "nt"},
        {"name": "MD4", "bit_length": 128, "category": "Cryptographic Hash", "description": "MD4 message digest", "hashcat_mode": 900, "john_format": "raw-md4"},
        {"name": "LM", "bit_length": 64, "category": "Windows Hash", "description": "Windows LanManager hash (half or single block)", "hashcat_mode": 3000, "john_format": "lm"},
    ],
    40: [
        {"name": "SHA-1", "bit_length": 160, "category": "Cryptographic Hash", "description": "Secure Hash Algorithm 1", "hashcat_mode": 100, "john_format": "raw-sha1"},
        {"name": "RIPEMD-160", "bit_length": 160, "category": "Cryptographic Hash", "description": "RACE Integrity Primitives Evaluation Message Digest 160", "hashcat_mode": 6000, "john_format": "ripemd-160"},
    ],
    56: [
        {"name": "SHA-224", "bit_length": 224, "category": "Cryptographic Hash", "description": "SHA-2 truncated to 224 bits", "hashcat_mode": 1300, "john_format": "raw-sha224"},
        {"name": "SHA3-224", "bit_length": 224, "category": "Cryptographic Hash", "description": "Keccak SHA-3 (224-bit)", "hashcat_mode": 17300, "john_format": "raw-sha3-224"},
    ],
    64: [
        {"name": "SHA-256", "bit_length": 256, "category": "Cryptographic Hash", "description": "Secure Hash Algorithm 2 (256-bit)", "hashcat_mode": 1400, "john_format": "raw-sha256"},
        {"name": "Keccak-256", "bit_length": 256, "category": "Cryptographic Hash", "description": "Ethereum / Keccak-256 hash", "hashcat_mode": 17800, "john_format": "keccak-256"},
        {"name": "SHA3-256", "bit_length": 256, "category": "Cryptographic Hash", "description": "NIST FIPS 202 SHA-3 (256-bit)", "hashcat_mode": 17400, "john_format": "raw-sha3-256"},
        {"name": "BLAKE2s-256", "bit_length": 256, "category": "Cryptographic Hash", "description": "BLAKE2s optimized for 8 to 32-bit platforms", "hashcat_mode": None, "john_format": None},
    ],
    96: [
        {"name": "SHA-384", "bit_length": 384, "category": "Cryptographic Hash", "description": "Secure Hash Algorithm 2 (384-bit)", "hashcat_mode": 10800, "john_format": "raw-sha384"},
        {"name": "SHA3-384", "bit_length": 384, "category": "Cryptographic Hash", "description": "NIST FIPS 202 SHA-3 (384-bit)", "hashcat_mode": 17500, "john_format": "raw-sha3-384"},
    ],
    128: [
        {"name": "SHA-512", "bit_length": 512, "category": "Cryptographic Hash", "description": "Secure Hash Algorithm 2 (512-bit)", "hashcat_mode": 1700, "john_format": "raw-sha512"},
        {"name": "Whirlpool", "bit_length": 512, "category": "Cryptographic Hash", "description": "Whirlpool 512-bit cryptographic hash function", "hashcat_mode": 6100, "john_format": "whirlpool"},
        {"name": "SHA3-512", "bit_length": 512, "category": "Cryptographic Hash", "description": "NIST FIPS 202 SHA-3 (512-bit)", "hashcat_mode": 17600, "john_format": "raw-sha3-512"},
        {"name": "BLAKE2b-512", "bit_length": 512, "category": "Cryptographic Hash", "description": "BLAKE2b optimized for 64-bit platforms", "hashcat_mode": 600, "john_format": "raw-blake2b-512"},
    ],
}


def identify_hash(value: str) -> list[dict[str, Any]]:
    """Analyze a hash string and return ranked candidate hash types and metadata."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty hash string.")

    cleaned = value.strip()

    # 1. Regex signature matching (passwords, salts, crypt)
    candidates: list[dict[str, Any]] = []
    for sig in _HASH_SIGNATURES:
        if sig["pattern"].match(cleaned):
            candidates.append({
                "name": sig["name"],
                "category": sig["category"],
                "description": sig["description"],
                "hashcat_mode": sig["hashcat_mode"],
                "john_format": sig["john_format"],
                "confidence": "high",
            })

    if candidates:
        return candidates

    # 2. Hexadecimal character checks
    is_hex = all(c in _HEX_CHARS for c in cleaned)
    length = len(cleaned)

    if is_hex and length in _LENGTH_CANDIDATES:
        for entry in _LENGTH_CANDIDATES[length]:
            candidates.append({
                **entry,
                "confidence": "high" if entry["name"] in {"MD5", "SHA-1", "SHA-256", "SHA-512"} else "medium",
            })
        return candidates

    # 3. Base64 length checks
    base64_candidates: list[dict[str, Any]] = []
    if length == 24 and cleaned.endswith("="):
        base64_candidates.append({
            "name": "MD5 (Base64)",
            "bit_length": 128,
            "category": "Base64 Digest",
            "description": "128-bit hash encoded in standard Base64",
            "confidence": "medium",
        })
    elif length == 28 and cleaned.endswith("="):
        base64_candidates.append({
            "name": "SHA-1 (Base64)",
            "bit_length": 160,
            "category": "Base64 Digest",
            "description": "160-bit hash encoded in standard Base64",
            "confidence": "medium",
        })
    elif length == 44 and cleaned.endswith("="):
        base64_candidates.append({
            "name": "SHA-256 (Base64)",
            "bit_length": 256,
            "category": "Base64 Digest",
            "description": "256-bit hash encoded in standard Base64",
            "confidence": "medium",
        })

    if base64_candidates:
        return base64_candidates

    return [{
        "name": "Unknown / Unrecognized Hash Format",
        "length": length,
        "is_hex": is_hex,
        "description": "Hash does not match standard hexadecimal, crypt, or base64 lengths.",
        "confidence": "low",
    }]


def compute_hashes(data: str | bytes) -> dict[str, str]:
    """Compute standard cryptographic digests for given text or bytes."""
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, bytes):
        raw = data
    else:
        raise ValueError("data must be string or bytes.")

    md5_val = hashlib.md5(raw).hexdigest()
    sha1_val = hashlib.sha1(raw).hexdigest()
    sha256_val = hashlib.sha256(raw).hexdigest()
    sha512_val = hashlib.sha512(raw).hexdigest()
    crc32_val = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"

    # NTLM: MD4 of UTF-16LE
    ntlm_val = ""
    try:
        if isinstance(data, str):
            ntlm_bytes = data.encode("utf-16le")
        else:
            ntlm_bytes = raw.decode("utf-8", errors="ignore").encode("utf-16le")
        ntlm_val = hashlib.new("md4", ntlm_bytes).hexdigest()
    except Exception:
        ntlm_val = "unavailable"

    return {
        "md5": md5_val,
        "sha1": sha1_val,
        "sha256": sha256_val,
        "sha512": sha512_val,
        "ntlm": ntlm_val,
        "crc32": crc32_val,
    }
