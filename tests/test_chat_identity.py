import pytest

from app import chat_identity
from app.chat_identity import (
    DEFAULT_ATTRIBUTION_MODE,
    REGISTRY_CAPACITY,
    InvalidChatId,
    annotate,
    attribution_mode,
    bind_chat,
    bound_chat,
    get_chat_id,
    registered_chats,
    touch_chat,
    validate_chat_id,
)


@pytest.fixture(autouse=True)
def _isolated_state():
    chat_identity._REGISTRY.clear()
    chat_identity._CHAT_ID.set(None)
    yield
    chat_identity._REGISTRY.clear()
    chat_identity._CHAT_ID.set(None)


@pytest.mark.parametrize(
    "chat_id",
    [
        "abcdef",  # length 6, the minimum
        "a" * 63,
        "a" * 64,  # length 64, the maximum
        "Ops.Chat-01_x",
        "A1.b2-c3_d4",
        "123456",
    ],
)
def test_valid_chat_ids_pass_unchanged(chat_id):
    assert validate_chat_id(chat_id) == chat_id


@pytest.mark.parametrize(
    "chat_id",
    [
        "abcde",  # length 5, one below the minimum
        "a" * 65,  # length 65, one above the maximum
        "-abcde",  # leading hyphen
        ".abcde",  # leading dot
        "_abcde",  # leading underscore
        "ábcdef",  # unicode letter
        "chat id",  # whitespace
        "chat\tid",  # tab
        "",  # empty
        "a@bcde",  # disallowed punctuation
    ],
)
def test_invalid_chat_ids_are_rejected(chat_id):
    with pytest.raises(InvalidChatId):
        validate_chat_id(chat_id)


def test_non_string_ids_are_rejected():
    with pytest.raises(InvalidChatId):
        validate_chat_id(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidChatId):
        validate_chat_id(123456)  # type: ignore[arg-type]


def test_binding_preserves_the_id_verbatim():
    chat_id = "Ops.Chat-01_x"
    token = bind_chat(chat_id)
    try:
        assert get_chat_id() == chat_id
    finally:
        chat_identity._CHAT_ID.reset(token)


def test_bind_rejects_invalid_ids_without_changing_binding():
    bind_chat("valid1")
    with pytest.raises(InvalidChatId):
        bind_chat("bad id")
    assert get_chat_id() == "valid1"


def test_get_chat_id_defaults_to_none():
    assert get_chat_id() is None


def test_bound_chat_sets_and_restores():
    assert get_chat_id() is None
    with bound_chat("outer1"):
        assert get_chat_id() == "outer1"
        with bound_chat("inner1"):
            assert get_chat_id() == "inner1"
        assert get_chat_id() == "outer1"
    assert get_chat_id() is None


def test_bound_chat_restores_prior_binding_from_bind():
    bind_chat("base01")
    with bound_chat("temp01"):
        assert get_chat_id() == "temp01"
    assert get_chat_id() == "base01"


def test_bound_chat_restores_on_exception():
    with pytest.raises(RuntimeError):
        with bound_chat("doomed1"):
            raise RuntimeError("boom")
    assert get_chat_id() is None


def test_touch_chat_creates_entry_with_timestamps():
    entry = touch_chat("chat01", now=1000)
    assert entry == {"first_seen": 1000, "last_seen": 1000}
    refreshed = touch_chat("chat01", now=1500)
    assert refreshed == {"first_seen": 1000, "last_seen": 1500}
    assert registered_chats()["chat01"] == {"first_seen": 1000, "last_seen": 1500}


def test_touch_chat_rejects_invalid_ids():
    with pytest.raises(InvalidChatId):
        touch_chat("_nope_")
    assert registered_chats() == {}


def test_registry_evicts_least_recently_touched_at_capacity():
    for index in range(REGISTRY_CAPACITY):
        touch_chat(f"c{index:05d}", now=index)
    # Touching c00000 makes it most-recently-used again.
    touch_chat("c00000", now=999)
    touch_chat("c99999", now=1000)  # pushes the registry one over capacity

    chats = registered_chats()
    assert len(chats) == REGISTRY_CAPACITY
    assert "c00000" in chats  # recently touched, survives
    assert "c00001" not in chats  # least recently touched, evicted
    assert "c00002" in chats
    assert chats["c99999"] == {"first_seen": 1000, "last_seen": 1000}


def test_attribution_mode_absent_falls_back_to_off(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: None)
    assert attribution_mode() == DEFAULT_ATTRIBUTION_MODE


@pytest.mark.parametrize("raw", ["off", "OFF", " off ", "", None])
def test_attribution_mode_off_variants_normalize_to_off(monkeypatch, raw):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: raw)
    assert attribution_mode() == "off"


def test_unknown_attribution_mode_falls_back_to_off(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: "banana")
    assert attribution_mode() == "off"


def test_enabled_mode_is_recognized(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: "ON")
    assert attribution_mode() == "on"


def test_annotate_is_strict_noop_when_off(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: "off")
    record = {"event": "host_run_command", "exit_code": 0}
    with bound_chat("chat01"):
        result = annotate(record)
    assert result is record
    assert result == {"event": "host_run_command", "exit_code": 0}


def test_annotate_is_noop_when_config_attribute_entirely_absent(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: None)
    record = {"event": "x"}
    assert annotate(record) is record
    assert set(record) == {"event"}


def test_annotate_stamps_bound_chat_when_enabled(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: "on")
    record = {"event": "x"}
    with bound_chat("ops.chat-01_x"):
        annotated = annotate(record)
    assert annotated["chat_id"] == "ops.chat-01_x"


def test_annotate_skips_stamp_when_nothing_is_bound(monkeypatch):
    monkeypatch.setattr(chat_identity, "_raw_attribution_mode", lambda: "on")
    record = {"event": "x"}
    assert annotate(record) is record
    assert set(record) == {"event"}


def test_real_config_module_reads_defensively():
    # Whatever state the concurrent config change is in, the accessor must
    # return a usable mode string without raising.
    assert isinstance(attribution_mode(), str)


# ---------------------------------------------------------------------------
# B1: "enforce" attribution mode.
# ---------------------------------------------------------------------------


def test_known_modes_cover_every_config_value_plus_legacy_on():
    import app.config as config_module

    assert {"off", "tag", "strict", "enforce"} <= chat_identity.KNOWN_ATTRIBUTION_MODES
    assert "on" in chat_identity.KNOWN_ATTRIBUTION_MODES  # legacy alias survives
    # Whatever the ambient environment selected, the validated config value
    # must always resolve inside the identity layer's known set.
    assert config_module.ATTRIBUTION_MODE in chat_identity.KNOWN_ATTRIBUTION_MODES


def test_enforce_mode_resolves_through_the_real_config_module(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module, "ATTRIBUTION_MODE", "enforce")
    assert chat_identity.attribution_mode() == "enforce"
    assert chat_identity.is_enforcing() is True

    monkeypatch.setattr(config_module, "ATTRIBUTION_MODE", "tag")
    assert chat_identity.attribution_mode() == "tag"
    assert chat_identity.is_enforcing() is False


def test_is_enforcing_is_false_for_off_and_unknown(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module, "ATTRIBUTION_MODE", "off")
    assert chat_identity.is_enforcing() is False
    monkeypatch.setattr(config_module, "ATTRIBUTION_MODE", "banana")
    assert chat_identity.is_enforcing() is False
