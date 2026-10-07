import pytest
from app import config
from app.tools_common import enforce_payload


def test_task_config_defaults():
    assert hasattr(config, "HOST_TASK_MAX_PER_CHAT")
    assert config.HOST_TASK_MAX_PER_CHAT >= 1
    assert hasattr(config, "HOST_TASK_MAX_GLOBAL")
    assert config.HOST_TASK_MAX_GLOBAL >= config.HOST_TASK_MAX_PER_CHAT
    assert hasattr(config, "HOST_TASK_WAIT_BEFORE_ASYNC_MS")
    assert config.HOST_TASK_WAIT_BEFORE_ASYNC_MS >= 1000
    assert hasattr(config, "HOST_TASK_MAX_TAIL_BYTES")
    assert config.HOST_TASK_MAX_TAIL_BYTES <= 128 * 1024
    assert hasattr(config, "HOST_TASK_LOG_MAX_BYTES")
    assert config.HOST_TASK_LOG_MAX_BYTES >= 1024 * 1024
    assert hasattr(config, "HOST_TASK_KILL_GRACE_SECONDS")
    assert config.HOST_TASK_KILL_GRACE_SECONDS >= 1


def test_enforce_payload_within_limit():
    data = {"status": "ok", "message": "hello"}
    assert enforce_payload(data) == data


def test_enforce_payload_exceeding_limit():
    huge_data = {"data": "x" * 600000}
    with pytest.raises(ValueError, match="exceeds wire limit"):
        enforce_payload(huge_data, max_bytes=500000)
