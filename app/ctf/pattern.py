"""Pure-Python De Bruijn cyclic pattern generator and offset locator for CTF/PWN.

Compatible with standard pwntools cyclic() and cyclic_find().
Does not require external dependencies or spawning processes.
"""

from __future__ import annotations

import string
from typing import Generator


DEFAULT_ALPHABET = string.ascii_lowercase
MAX_PATTERN_LENGTH = 500_000


def de_bruijn(alphabet: str = DEFAULT_ALPHABET, n: int = 4) -> Generator[str, None, None]:
    """Generate a De Bruijn sequence over *alphabet* with subsequence length *n*."""
    if not alphabet:
        raise ValueError("alphabet must be non-empty.")
    if n <= 0:
        raise ValueError("n must be a positive integer.")

    k = len(alphabet)
    a = [0] * (k * n)

    def db(t: int, p: int) -> Generator[str, None, None]:
        if t > n:
            if n % p == 0:
                for j in range(1, p + 1):
                    yield alphabet[a[j]]
        else:
            a[t] = a[t - p]
            yield from db(t + 1, p)
            for j in range(a[t - p] + 1, k):
                a[t] = j
                yield from db(t + 1, t)

    return db(1, 1)


def cyclic_create(
    length: int = 128,
    width: int = 4,
    alphabet: str = DEFAULT_ALPHABET,
) -> str:
    """Generate a cyclic pattern of length *length* with unique subsequences of length *width*."""
    if not isinstance(length, int) or length <= 0:
        raise ValueError("length must be a positive integer.")
    if not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer.")
    if length > MAX_PATTERN_LENGTH:
        raise ValueError(f"length {length} exceeds maximum allowed length of {MAX_PATTERN_LENGTH}.")

    max_possible = len(alphabet) ** width
    if length > max_possible:
        raise ValueError(
            f"length {length} exceeds maximum unique pattern length {max_possible} "
            f"for alphabet size {len(alphabet)} and width {width}."
        )

    gen = de_bruijn(alphabet, width)
    out: list[str] = []
    for _ in range(length):
        try:
            out.append(next(gen))
        except StopIteration:
            break
    return "".join(out)


def cyclic_offset(
    value: str | int,
    width: int = 4,
    alphabet: str = DEFAULT_ALPHABET,
) -> int:
    """Locate the 0-indexed byte offset of *value* in the De Bruijn cyclic sequence.

    *value* can be:
    - An ASCII string (e.g. 'caaa')
    - A hexadecimal string (e.g. '0x61616163' or '61616163')
    - An integer address (e.g. 0x61616163)

    Integers and hex strings are decoded in little-endian byte order by default.
    Returns -1 if not found.
    """
    if not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer.")

    subseq: str
    if isinstance(value, int):
        subseq = "".join(chr((value >> (8 * i)) & 0xFF) for i in range(width))
    elif isinstance(value, str):
        v = value.strip()
        if v.startswith(("0x", "0X")):
            try:
                int_val = int(v, 16)
                subseq = "".join(chr((int_val >> (8 * i)) & 0xFF) for i in range(width))
            except ValueError as exc:
                raise ValueError(f"Invalid hex integer string: {value}") from exc
        else:
            # Check if entire string is hex representation of width bytes
            if len(v) == width * 2 and all(c in string.hexdigits for c in v):
                try:
                    int_val = int(v, 16)
                    # Test if packing as little-endian matches or raw string matches
                    subseq = "".join(chr((int_val >> (8 * i)) & 0xFF) for i in range(width))
                except ValueError:
                    subseq = v[:width]
            else:
                subseq = v[:width]
    else:
        raise ValueError("value must be a string or integer.")

    # Generate sequence up to max unique length or 200,000 bytes
    max_gen = min(200_000, len(alphabet) ** width)
    pattern = cyclic_create(max_gen, width, alphabet)
    return pattern.find(subseq)
