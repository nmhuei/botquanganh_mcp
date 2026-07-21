import json

from app.cli.output import emit_json, human_duration, redact_data


def test_redaction_hides_nested_secrets(capsys):
    payload = {
        "GATEWAY_TOKEN": "secret",  # pragma: allowlist secret
        "nested": {"api_key": "value", "safe": "ok"},  # pragma: allowlist secret
    }
    emit_json(payload)
    result = json.loads(capsys.readouterr().out)
    assert result["GATEWAY_TOKEN"] == "********"
    assert result["nested"]["api_key"] == "********"
    assert result["nested"]["safe"] == "ok"


def test_human_duration():
    assert human_duration(0) == "0s"
    assert human_duration(61) == "1m 1s"
    assert human_duration(90061) == "1d 1h 1m 1s"


def test_redact_data_preserves_empty_secret():
    assert redact_data({"token": ""}) == {"token": ""}
