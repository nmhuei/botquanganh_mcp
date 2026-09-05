import importlib
import json
import os
import socket
from pathlib import Path

import pytest

from app.chat_workspace import WorkspaceManager


def _case_scope():
    """Import lazily so the first TDD run fails as a test, not collection error."""
    try:
        return importlib.import_module("app.ctf.case_scope")
    except ModuleNotFoundError as exc:
        pytest.fail(f"case authority service is missing: {exc}")


@pytest.fixture()
def workspace_manager(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces", bind_wait_seconds=0.01)
    manager.create_or_bind("case001")
    return manager


def _public_resolver(hostname, port, *, type):
    assert hostname == "challenge.example"
    assert port == 443
    assert type == socket.SOCK_STREAM
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0)),
    ]


def test_creates_public_case_with_canonical_exact_origin(workspace_manager):
    case_scope = _case_scope()

    record = case_scope.create_case(
        workspace_manager,
        "case001",
        label="  qualifier web  ",
        authorized_origins=["HTTPS://Challenge.Example:443/"],
        network_mode="public_https",
        resolver=_public_resolver,
    )

    assert record.label == "qualifier web"
    assert record.authorized_origins == ("https://challenge.example",)
    assert record.network_mode == "public_https"
    assert len(record.case_id) >= 16


@pytest.mark.parametrize(
    ("origin", "resolver"),
    [
        ("https://challenge.example/login", _public_resolver),
        ("https://user:password@challenge.example", _public_resolver),
        (
            "https://challenge.example",
            lambda *_args, **_kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))
            ],
        ),
    ],
)
def test_public_case_rejects_authority_broadening(workspace_manager, origin, resolver):
    case_scope = _case_scope()

    with pytest.raises(ValueError):
        case_scope.create_case(
            workspace_manager,
            "case001",
            label="web",
            authorized_origins=[origin],
            network_mode="public_https",
            resolver=resolver,
        )


@pytest.mark.parametrize("port", [0, 65536])
def test_public_case_rejects_invalid_explicit_port(workspace_manager, port):
    case_scope = _case_scope()

    with pytest.raises(ValueError):
        case_scope.create_case(
            workspace_manager,
            "case001",
            label="web",
            authorized_origins=[f"https://challenge.example:{port}"],
            network_mode="public_https",
            resolver=lambda *_args, **_kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
            ],
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:18427/",
        "https://[::1]:8443",
        "http://localhost:3000",
    ],
)
def test_local_case_accepts_only_canonical_literal_loopback_origins(workspace_manager, origin):
    case_scope = _case_scope()

    record = case_scope.create_case(
        workspace_manager,
        "case001",
        label="local pwn",
        authorized_origins=[origin],
        network_mode="local_instance",
    )

    assert record.authorized_origins == (origin.rstrip("/"),)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "https://127.0.0.1",
        "http://192.168.1.10:8080",
        "http://[::1]:8080/path",
        "http://[::1%25eth0]:8080",
        "http://loopback.example:8080",
    ],
)
def test_local_case_rejects_missing_port_lan_paths_and_dns_names(workspace_manager, origin):
    case_scope = _case_scope()

    with pytest.raises(ValueError):
        case_scope.create_case(
            workspace_manager,
            "case001",
            label="local",
            authorized_origins=[origin],
            network_mode="local_instance",
        )


def test_persists_active_case_with_restrictive_permissions(workspace_manager):
    case_scope = _case_scope()

    created = case_scope.create_case(
        workspace_manager,
        "case001",
        label="forensics",
        authorized_origins=["http://127.0.0.1:8080"],
        network_mode="local_instance",
    )
    paths = case_scope.case_paths(workspace_manager, "case001")
    stored = json.loads(paths.record_file.read_text(encoding="utf-8"))

    assert paths.artifact_dir.is_dir()
    assert paths.record_file.stat().st_mode & 0o077 == 0
    assert stored["schema"] == 1
    assert stored["case_id"] == created.case_id
    assert case_scope.load_active_case(workspace_manager, "case001") == created


def test_replacing_case_invalidates_prior_case_id(workspace_manager):
    case_scope = _case_scope()
    first = case_scope.create_case(
        workspace_manager,
        "case001",
        label="first",
        authorized_origins=["http://localhost:5000"],
        network_mode="local_instance",
    )
    second = case_scope.create_case(
        workspace_manager,
        "case001",
        label="second",
        authorized_origins=["http://localhost:5001"],
        network_mode="local_instance",
    )

    assert second.case_id != first.case_id
    with pytest.raises(ValueError):
        case_scope.load_active_case(workspace_manager, "case001", case_id=first.case_id)
    assert case_scope.load_active_case(
        workspace_manager, "case001", case_id=second.case_id
    ) == second


def test_rejects_persisted_case_without_an_authorized_origin(workspace_manager):
    case_scope = _case_scope()
    created = case_scope.create_case(
        workspace_manager,
        "case001",
        label="tamper check",
        authorized_origins=["http://localhost:5000"],
        network_mode="local_instance",
    )
    record_file = case_scope.case_paths(workspace_manager, "case001").record_file
    raw = created.to_json()
    raw["authorized_origins"] = []
    record_file.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="origins"):
        case_scope.load_active_case(workspace_manager, "case001")


def test_rejects_case_directory_symlink_that_escapes_chat_workspace(
    workspace_manager, tmp_path
):
    case_scope = _case_scope()
    workspace = workspace_manager.workspace_path("case001")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "ctf").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes"):
        case_scope.create_case(
            workspace_manager,
            "case001",
            label="escape",
            authorized_origins=["http://localhost:3000"],
            network_mode="local_instance",
        )


def test_post_validation_case_directory_substitution_cannot_write_outside_workspace(
    workspace_manager, tmp_path, monkeypatch
):
    case_scope = _case_scope()
    workspace = workspace_manager.workspace_path("case001")
    case_scope.case_paths(workspace_manager, "case001")
    case_directory = workspace / "ctf"
    outside = tmp_path / "outside"
    outside.mkdir()
    moved_directory = workspace / "ctf-held"
    real_open = case_scope.os.open
    swapped = False

    def swap_case_directory_before_temporary_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if (
            not swapped
            and flags & os.O_CREAT
            and Path(path).name.startswith(".case.json.")
        ):
            swapped = True
            case_directory.rename(moved_directory)
            case_directory.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(case_scope.os, "open", swap_case_directory_before_temporary_open)

    with pytest.raises(ValueError, match="changed"):
        case_scope.create_case(
            workspace_manager,
            "case001",
            label="race",
            authorized_origins=["http://localhost:3000"],
            network_mode="local_instance",
        )

    assert swapped is True
    assert not (outside / "case.json").exists()
