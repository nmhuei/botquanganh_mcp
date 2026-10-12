import pytest
from uri_core.parser import parse_url

def test_basic_url():
    u = parse_url("https://example.com:8443/api/v1?user=alice")
    assert u["scheme"] == "https"
    assert u["hostname"] == "example.com"
    assert u["port"] == 8443
    assert u["query"] == {"user": "alice"}

def test_multiple_params():
    u = parse_url("http://localhost/path?a=1&b=2")
    assert u["query"] == {"a": "1", "b": "2"}
