"""Bounded, deterministic offline byte and text transforms for CTF analysis.

This module deliberately has no MCP, workspace, filesystem, network, process,
or expression-evaluation dependency.  Callers supply exactly one input carrier
and receive a lossless base64 representation of the transformed bytes.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import gzip
import zlib
from urllib.parse import quote_from_bytes, unquote_to_bytes


MAX_INPUT_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 512 * 1024
_DECOMPRESS_CHUNK_BYTES = 16 * 1024
_OPERATIONS = frozenset(
    {
        "base64_encode",
        "base64_decode",
        "hex_encode",
        "hex_decode",
        "url_encode",
        "url_decode",
        "gzip_compress",
        "gzip_decompress",
        "zlib_compress",
        "zlib_decompress",
        "rot13",
        "xor_hex",
    }
)
_HEX_DIGITS = frozenset(b"0123456789abcdefABCDEF")


def _active_limit(name: str) -> int:
    value = globals()[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _check_input_size(value: bytes) -> bytes:
    if len(value) > _active_limit("MAX_INPUT_BYTES"):
        raise ValueError("input limit exceeded.")
    return value


def _utf8_exceeds_limit(value: str, limit: int) -> bool:
    """Count UTF-8 bytes without allocating an encoded copy of *value*."""
    size = 0
    for character in value:
        code_point = ord(character)
        if code_point <= 0x7F:
            size += 1
        elif code_point <= 0x7FF:
            size += 2
        elif code_point <= 0xFFFF:
            size += 3
        else:
            size += 4
        if size > limit:
            return True
    return False


def _input_bytes(input_text: str | None, input_base64: str | None) -> bytes:
    if (input_text is None) == (input_base64 is None):
        raise ValueError("provide exactly one of input_text or input_base64.")
    if input_text is not None:
        if not isinstance(input_text, str):
            raise ValueError("input_text must be a string.")
        input_limit = _active_limit("MAX_INPUT_BYTES")
        if len(input_text) > input_limit or _utf8_exceeds_limit(input_text, input_limit):
            raise ValueError("input limit exceeded.")
        return _check_input_size(input_text.encode("utf-8"))

    if not isinstance(input_base64, str):
        raise ValueError("input_base64 must be a string.")
    # Check character count before an ASCII conversion.  ASCII preserves this
    # length, and a valid carrier for a capped byte sequence cannot be longer.
    input_limit = _active_limit("MAX_INPUT_BYTES")
    carrier_limit = 4 * ((input_limit + 2) // 3)
    if len(input_base64) > carrier_limit:
        raise ValueError("input limit exceeded.")
    try:
        encoded = input_base64.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("input_base64 must use ASCII base64 characters.") from exc

    # A canonical base64 carrier for a capped byte sequence needs no more than
    # this many bytes.  Check it before decoding so the carrier itself is bounded.
    if len(encoded) > carrier_limit:
        raise ValueError("input limit exceeded.")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("input_base64 is not valid base64.") from exc
    return _check_input_size(decoded)


def _strict_hex(value: bytes | str, field: str) -> bytes:
    try:
        raw = value.encode("ascii") if isinstance(value, str) else value
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field} must be hexadecimal.") from exc
    try:
        return binascii.unhexlify(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field} must be hexadecimal.") from exc


def _strict_percent_encoding(value: bytes) -> None:
    position = 0
    while position < len(value):
        if value[position] == ord("%"):
            if position + 2 >= len(value) or (
                value[position + 1] not in _HEX_DIGITS
                or value[position + 2] not in _HEX_DIGITS
            ):
                raise ValueError("URL input contains an invalid percent escape.")
            position += 3
        else:
            position += 1


def _bounded_decompress(data: bytes, wbits: int, *, concatenated: bool) -> bytes:
    """Decompress complete stream members while enforcing the output cap.

    No bytes escape this helper until every member is complete.  Thus a
    truncated stream or an expansion past the limit has no partial success.
    """
    source = data
    parts: list[bytes] = []
    output_size = 0
    while source:
        decoder = zlib.decompressobj(wbits)
        position = 0
        while position < len(source) and not decoder.eof:
            chunk = source[position : position + _DECOMPRESS_CHUNK_BYTES]
            position += len(chunk)
            remaining = chunk
            while remaining:
                available = _active_limit("MAX_OUTPUT_BYTES") - output_size
                try:
                    output = decoder.decompress(remaining, available + 1)
                except zlib.error as exc:
                    raise ValueError("compressed input is invalid.") from exc
                if len(output) > available:
                    raise ValueError("output limit exceeded.")
                if output:
                    parts.append(output)
                    output_size += len(output)
                remaining = decoder.unconsumed_tail
                if not remaining:
                    break

        available = _active_limit("MAX_OUTPUT_BYTES") - output_size
        try:
            output = decoder.flush(available + 1)
        except zlib.error as exc:
            raise ValueError("compressed input is invalid.") from exc
        if len(output) > available:
            raise ValueError("output limit exceeded.")
        if output:
            parts.append(output)
            output_size += len(output)

        if not decoder.eof:
            raise ValueError("compressed input is truncated.")
        source = decoder.unused_data + source[position:]
        if source and not concatenated:
            raise ValueError("compressed input has trailing data.")

    if not parts and not data:
        raise ValueError("compressed input is truncated.")
    return b"".join(parts)


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(data))


def _result(operation: str, output: bytes) -> dict[str, str]:
    if len(output) > _active_limit("MAX_OUTPUT_BYTES"):
        raise ValueError("output limit exceeded.")
    result = {
        "operation": operation,
        "output_base64": base64.b64encode(output).decode("ascii"),
    }
    try:
        result["output_text"] = output.decode("utf-8")
    except UnicodeDecodeError:
        pass
    return result


def transform(
    operation: str,
    *,
    input_text: str | None = None,
    input_base64: str | None = None,
    key_hex: str | None = None,
) -> dict[str, str]:
    """Run one allowlisted transform on bounded text or base64-carried bytes."""
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise ValueError("operation is not supported.")
    if operation == "xor_hex":
        if not isinstance(key_hex, str) or not key_hex:
            raise ValueError("xor_hex requires a non-empty key_hex.")
        input_limit = _active_limit("MAX_INPUT_BYTES")
        if len(key_hex) > 2 * input_limit:
            raise ValueError("key_hex limit exceeded.")
        key = _strict_hex(key_hex, "key_hex")
        if not key or len(key) > input_limit:
            raise ValueError("xor_hex requires a non-empty key_hex.")
    elif key_hex is not None:
        raise ValueError("key_hex is only valid for xor_hex.")
    else:
        key = b""

    data = _input_bytes(input_text, input_base64)
    if operation == "base64_encode":
        output = base64.b64encode(data)
    elif operation == "base64_decode":
        try:
            output = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("base64 input is invalid.") from exc
    elif operation == "hex_encode":
        output = binascii.hexlify(data)
    elif operation == "hex_decode":
        output = _strict_hex(data, "hex input")
    elif operation == "url_encode":
        output = quote_from_bytes(data, safe="").encode("ascii")
    elif operation == "url_decode":
        _strict_percent_encoding(data)
        output = unquote_to_bytes(data)
    elif operation == "gzip_compress":
        output = gzip.compress(data, compresslevel=9, mtime=0)
    elif operation == "gzip_decompress":
        output = _bounded_decompress(data, zlib.MAX_WBITS | 16, concatenated=True)
    elif operation == "zlib_compress":
        output = zlib.compress(data, level=9)
    elif operation == "zlib_decompress":
        output = _bounded_decompress(data, zlib.MAX_WBITS, concatenated=False)
    elif operation == "rot13":
        try:
            output = codecs.decode(data.decode("utf-8"), "rot_13").encode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("rot13 requires valid UTF-8 input.") from exc
    else:  # xor_hex is included in the fixed allowlist above.
        output = _xor(data, key)
    return _result(operation, output)
