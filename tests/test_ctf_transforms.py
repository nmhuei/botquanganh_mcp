"""Behavioral tests for the bounded, offline CTF transform service."""

import base64
import gzip
import importlib
import zlib

import pytest


def _transforms_module():
    """Import lazily so the initial TDD run proves the service is absent."""
    try:
        return importlib.import_module("app.ctf.transforms")
    except ModuleNotFoundError as exc:
        pytest.fail(f"CTF transform service is missing: {exc}")


def _result_bytes(result):
    return base64.b64decode(result["output_base64"], validate=True)


class _OversizedString(str):
    """A caller-controlled string that makes accidental encoding observable."""

    def encode(self, *args, **kwargs):
        raise AssertionError("the oversized value was encoded before its cap check")


@pytest.mark.parametrize(
    ("operation", "input_text", "input_base64", "key_hex", "expected"),
    [
        ("base64_encode", None, "AGhlbGxv/w==", None, b"AGhlbGxv/w=="),
        ("base64_decode", "AGhlbGxv/w==", None, None, b"\x00hello\xff"),
        ("hex_encode", None, "AP8=", None, b"00ff"),
        ("hex_decode", "00ff", None, None, b"\x00\xff"),
        ("url_encode", "a b/?", None, None, b"a%20b%2F%3F"),
        ("url_decode", "a%20b%2F%3F", None, None, b"a b/?"),
        ("rot13", "Uryyb, Jbeyq!", None, None, b"Hello, World!"),
        ("xor_hex", None, "AAH/", "0f10", b"\x0f\x11\xf0"),
    ],
)
def test_transforms_each_non_compression_codec_family(
    operation, input_text, input_base64, key_hex, expected
):
    """A wrong dispatch branch or byte conversion changes this literal result."""
    result = _transforms_module().transform(
        operation,
        input_text=input_text,
        input_base64=input_base64,
        key_hex=key_hex,
    )

    assert _result_bytes(result) == expected


@pytest.mark.parametrize(
    ("operation", "compressed", "decoder"),
    [
        ("gzip_compress", None, gzip.decompress),
        ("zlib_compress", None, zlib.decompress),
    ],
)
def test_compression_operations_produce_a_standard_round_trippable_stream(
    operation, compressed, decoder
):
    """Using the standard decoder catches a wrong compression implementation."""
    result = _transforms_module().transform(operation, input_text="repeat me")

    assert decoder(_result_bytes(result)) == b"repeat me"


@pytest.mark.parametrize(
    ("operation", "compressed"),
    [
        ("gzip_decompress", gzip.compress(b"\x00plain\xff", mtime=0)),
        ("zlib_decompress", zlib.compress(b"\x00plain\xff")),
    ],
)
def test_decompression_operations_return_original_binary_bytes(operation, compressed):
    """A bad decompression path cannot replace non-UTF-8 bytes with text."""
    result = _transforms_module().transform(
        operation, input_base64=base64.b64encode(compressed).decode("ascii")
    )

    assert _result_bytes(result) == b"\x00plain\xff"
    assert "output_text" not in result


def test_result_includes_text_only_when_output_is_valid_utf8():
    """Binary output remains lossless without a lossy replacement-text field."""
    result = _transforms_module().transform("base64_decode", input_text="/wA=")

    assert result["output_base64"] == "/wA="
    assert "output_text" not in result


@pytest.mark.parametrize(
    ("operation", "kwargs", "message"),
    [
        ("unknown", {"input_text": "x"}, "operation"),
        ("hex_decode", {}, "exactly one"),
        ("hex_decode", {"input_text": "00", "input_base64": "AA=="}, "exactly one"),
        ("base64_decode", {"input_text": "not base64!"}, "base64"),
        ("hex_decode", {"input_text": "0g"}, "hex"),
        ("url_decode", {"input_text": "bad%2"}, "percent"),
        ("xor_hex", {"input_text": "x"}, "key_hex"),
        ("xor_hex", {"input_text": "x", "key_hex": ""}, "key_hex"),
        ("xor_hex", {"input_text": "x", "key_hex": "zz"}, "hex"),
        ("rot13", {"input_base64": "/w=="}, "UTF-8"),
        ("hex_encode", {"input_text": "x", "key_hex": "00"}, "key_hex"),
    ],
)
def test_rejects_invalid_operations_and_arguments(operation, kwargs, message):
    """Malformed codecs, stray keys, and unlisted operations must not execute."""
    with pytest.raises(ValueError, match=message):
        _transforms_module().transform(operation, **kwargs)


def test_rejects_oversized_raw_input_from_the_base64_carrier(monkeypatch):
    """A base64 carrier cannot bypass the declared input byte cap."""
    transforms = _transforms_module()
    monkeypatch.setattr(transforms, "MAX_INPUT_BYTES", 4)

    with pytest.raises(ValueError, match="input limit"):
        transforms.transform("hex_encode", input_base64="MTIzNDU=")


@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        ("hex_encode", {"input_text": _OversizedString("x" * 5)}),
        ("hex_encode", {"input_text": _OversizedString("é" * 4)}),
        ("hex_encode", {"input_base64": _OversizedString("A" * 9)}),
        ("xor_hex", {"input_text": "x", "key_hex": _OversizedString("00" * 5)}),
    ],
)
def test_preflights_oversized_caller_strings_before_encoding(monkeypatch, operation, kwargs):
    """Removing a string-length preflight would invoke the test value's encode."""
    transforms = _transforms_module()
    monkeypatch.setattr(transforms, "MAX_INPUT_BYTES", 4)

    with pytest.raises(ValueError, match="limit"):
        transforms.transform(operation, **kwargs)


def test_rejects_an_encoded_result_larger_than_the_output_cap(monkeypatch):
    """An expanding encoder cannot return bytes beyond the output cap."""
    transforms = _transforms_module()
    monkeypatch.setattr(transforms, "MAX_OUTPUT_BYTES", 4)

    with pytest.raises(ValueError, match="output limit"):
        transforms.transform("hex_encode", input_text="abc")


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("gzip_decompress", gzip.compress(b"A" * 17, mtime=0)),
        ("zlib_decompress", zlib.compress(b"A" * 17)),
    ],
)
def test_decompression_stops_at_the_output_limit_without_partial_success(
    monkeypatch, operation, payload
):
    """A decompression bomb must fail before any oversized result is returned."""
    transforms = _transforms_module()
    monkeypatch.setattr(transforms, "MAX_OUTPUT_BYTES", 16)

    with pytest.raises(ValueError, match="output limit"):
        transforms.transform(
            operation, input_base64=base64.b64encode(payload).decode("ascii")
        )


@pytest.mark.parametrize(
    ("operation", "payload", "message"),
    [
        ("gzip_decompress", b"not a gzip stream", "invalid"),
        ("zlib_decompress", b"not a zlib stream", "invalid"),
        ("gzip_decompress", gzip.compress(b"complete", mtime=0)[:-4], "truncated"),
        ("zlib_decompress", zlib.compress(b"complete")[:-1], "truncated"),
    ],
)
def test_decompression_rejects_corrupt_or_truncated_streams(operation, payload, message):
    """Malformed streams must not be reported as a transformed byte result."""
    with pytest.raises(ValueError, match=message):
        _transforms_module().transform(
            operation, input_base64=base64.b64encode(payload).decode("ascii")
        )


def test_zlib_decompression_rejects_trailing_bytes():
    """The zlib operation accepts exactly one complete stream, not a prefix."""
    payload = zlib.compress(b"complete") + b"unexpected"

    with pytest.raises(ValueError, match="trailing"):
        _transforms_module().transform(
            "zlib_decompress", input_base64=base64.b64encode(payload).decode("ascii")
        )


def test_gzip_decompression_accepts_complete_concatenated_members():
    """Valid chained gzip members are decoded as one bounded byte sequence."""
    payload = gzip.compress(b"first", mtime=0) + gzip.compress(b"second", mtime=0)

    result = _transforms_module().transform(
        "gzip_decompress", input_base64=base64.b64encode(payload).decode("ascii")
    )

    assert _result_bytes(result) == b"firstsecond"
