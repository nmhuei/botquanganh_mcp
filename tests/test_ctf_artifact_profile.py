import hashlib
import importlib
import io
import tarfile
import zipfile

import pytest

from app.chat_workspace import WorkspaceManager
from app.ctf import case_scope


def _profile_module():
    """Import lazily so the initial TDD run is a meaningful RED."""
    try:
        return importlib.import_module("app.ctf.artifact_profile")
    except ModuleNotFoundError as exc:
        pytest.fail(f"artifact profiler service is missing: {exc}")


@pytest.fixture()
def workspace_manager(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces", bind_wait_seconds=0.01)
    manager.create_or_bind("case001")
    case_scope.create_case(
        manager,
        "case001",
        label="forensics",
        authorized_origins=["http://127.0.0.1:8000"],
        network_mode="local_instance",
    )
    return manager


def _artifact_dir(manager):
    return case_scope.case_paths(manager, "case001").artifact_dir


def _write_artifact(manager, name, content):
    artifact = _artifact_dir(manager) / name
    artifact.write_bytes(content)
    return artifact


def test_profiles_a_regular_artifact_with_workspace_relative_evidence(workspace_manager):
    content = b"\x7fELF" + b"A" * 32
    _write_artifact(workspace_manager, "challenge.bin", content)

    result = _profile_module().profile_artifact(
        workspace_manager, "case001", "challenge.bin"
    )

    assert result["relative_path"] == "ctf/artifacts/challenge.bin"
    assert result["size_bytes"] == len(content)
    assert result["magic"]["format"] == "ELF"
    assert result["sha256"] == {
        "mode": "full",
        "bytes_hashed": len(content),
        "value": hashlib.sha256(content).hexdigest(),
    }
    assert result["entropy"]["bytes_sampled"] == len(content)
    assert result["evidence"]
    assert result["next_safe_actions"]


@pytest.mark.parametrize("name", ["../outside.bin", "/tmp/outside.bin", "nested/file.bin"])
def test_rejects_artifact_paths_that_can_escape_the_artifact_directory(
    workspace_manager, name
):
    _write_artifact(workspace_manager, "safe.bin", b"safe")

    with pytest.raises(ValueError, match="artifact"):
        _profile_module().profile_artifact(workspace_manager, "case001", name)


def test_rejects_artifact_symlink_and_non_regular_file(workspace_manager, tmp_path):
    artifact_dir = _artifact_dir(workspace_manager)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (artifact_dir / "link.bin").symlink_to(outside)
    (artifact_dir / "directory").mkdir()

    profiler = _profile_module()
    with pytest.raises(ValueError, match="symlink"):
        profiler.profile_artifact(workspace_manager, "case001", "link.bin")
    with pytest.raises(ValueError, match="regular"):
        profiler.profile_artifact(workspace_manager, "case001", "directory")


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("sample.elf", b"\x7fELF", "ELF"),
        ("sample.exe", b"MZ\x00\x00", "PE"),
        ("sample.macho", b"\xfe\xed\xfa\xcf", "Mach-O"),
        ("sample.zip", b"PK\x03\x04", "ZIP"),
        ("sample.apk", b"PK\x03\x04", "APK"),
        ("sample.gz", b"\x1f\x8b\x08\x00", "GZIP"),
        ("sample.pdf", b"%PDF-1.7", "PDF"),
        ("sample.png", b"\x89PNG\r\n\x1a\n", "PNG"),
        ("sample.jpg", b"\xff\xd8\xff\xe0", "JPEG"),
        ("sample.pcap", b"\xd4\xc3\xb2\xa1", "PCAP"),
        ("sample.pcapng", b"\x0a\x0d\x0d\x0a", "PCAPNG"),
        ("sample.wav", b"RIFF\x00\x00\x00\x00WAVE", "WAV"),
        ("sample.db", b"SQLite format 3\x00", "SQLite"),
        ("sample.wasm", b"\x00asm\x01\x00\x00\x00", "WASM"),
    ],
)
def test_detects_known_file_signatures(workspace_manager, name, content, expected):
    _write_artifact(workspace_manager, name, content)

    result = _profile_module().profile_artifact(workspace_manager, "case001", name)

    assert result["magic"]["format"] == expected


def test_caps_hash_and_entropy_sampling_for_large_artifacts(workspace_manager, monkeypatch):
    profiler = _profile_module()
    monkeypatch.setattr(profiler.config, "CTF_ARTIFACT_HASH_MAX_BYTES", 4)
    monkeypatch.setattr(profiler.config, "CTF_ARTIFACT_ENTROPY_MAX_BYTES", 3)
    content = b"0123456789"
    _write_artifact(workspace_manager, "large.bin", content)

    result = profiler.profile_artifact(workspace_manager, "case001", "large.bin")

    assert result["sha256"] == {
        "mode": "sampled_prefix_suffix",
        "bytes_hashed": 4,
        "value": hashlib.sha256(b"01" + b"89").hexdigest(),
    }
    assert result["entropy"]["bytes_sampled"] == 3
    assert result["entropy"]["sampled"] is True


def test_lists_a_bounded_zip_manifest_without_extracting_members(
    workspace_manager, monkeypatch
):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as created:
        created.writestr("first.txt", b"first")
        created.writestr("second.txt", b"second")
    _write_artifact(workspace_manager, "bundle.zip", archive.getvalue())
    profiler = _profile_module()
    monkeypatch.setattr(profiler.config, "CTF_ARTIFACT_MAX_MANIFEST_MEMBERS", 1)

    result = profiler.profile_artifact(workspace_manager, "case001", "bundle.zip")

    manifest = result["archive_manifest"]
    assert manifest["format"] == "ZIP"
    assert manifest["inspection"] == "metadata_only"
    assert manifest["member_count"] == 2
    assert manifest["member_count_complete"] is True
    assert manifest["members"] == ["first.txt"]
    assert manifest["members_truncated"] is True


def test_lists_a_bounded_tar_manifest_without_extracting_members(
    workspace_manager, monkeypatch
):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as created:
        for name, content in (("first.txt", b"first"), ("second.txt", b"second")):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            created.addfile(info, io.BytesIO(content))
    _write_artifact(workspace_manager, "bundle.tar", archive.getvalue())
    profiler = _profile_module()
    monkeypatch.setattr(profiler.config, "CTF_ARTIFACT_MAX_MANIFEST_MEMBERS", 1)

    result = profiler.profile_artifact(workspace_manager, "case001", "bundle.tar")

    manifest = result["archive_manifest"]
    assert manifest["format"] == "TAR"
    assert manifest["inspection"] == "metadata_only"
    assert manifest["member_count"] == 2
    assert manifest["member_count_complete"] is True
    assert manifest["members"] == ["first.txt"]
    assert manifest["members_truncated"] is True


def test_rejects_same_size_artifact_mutated_while_being_profiled(
    workspace_manager, monkeypatch
):
    artifact = _write_artifact(workspace_manager, "same-size.bin", b"original")
    profiler = _profile_module()
    original_profile = profiler._profile_open_artifact

    def profile_then_mutate(fd, size, artifact_name):
        result = original_profile(fd, size, artifact_name)
        artifact.write_bytes(b"modified")
        return result

    monkeypatch.setattr(profiler, "_profile_open_artifact", profile_then_mutate)

    with pytest.raises(ValueError, match="changed"):
        profiler.profile_artifact(workspace_manager, "case001", "same-size.bin")


def test_rejects_artifact_entry_replaced_after_safe_open(workspace_manager, monkeypatch):
    artifact_dir = _artifact_dir(workspace_manager)
    _write_artifact(workspace_manager, "replaced.bin", b"original")
    replacement = artifact_dir / "replacement.bin"
    replacement.write_bytes(b"modified")
    profiler = _profile_module()
    original_profile = profiler._profile_open_artifact

    def profile_then_replace(fd, size, artifact_name):
        result = original_profile(fd, size, artifact_name)
        replacement.replace(artifact_dir / artifact_name)
        return result

    monkeypatch.setattr(profiler, "_profile_open_artifact", profile_then_replace)

    with pytest.raises(ValueError, match="changed"):
        profiler.profile_artifact(workspace_manager, "case001", "replaced.bin")


def test_gzip_keeps_magic_and_safe_action_without_an_archive_manifest(workspace_manager):
    _write_artifact(workspace_manager, "payload.gz", b"\x1f\x8b\x08\x00")

    result = _profile_module().profile_artifact(workspace_manager, "case001", "payload.gz")

    assert result["magic"]["format"] == "GZIP"
    assert "archive_manifest" not in result
    assert any("do not decompress" in action for action in result["next_safe_actions"])


def test_tar_with_only_one_terminal_zero_block_is_not_complete(workspace_manager):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as created:
        info = tarfile.TarInfo("one.txt")
        info.size = 3
        created.addfile(info, io.BytesIO(b"one"))
    # One member header + padded payload + exactly one all-zero TAR block.
    _write_artifact(workspace_manager, "one-zero.tar", archive.getvalue()[:1536])

    result = _profile_module().profile_artifact(workspace_manager, "case001", "one-zero.tar")

    assert result["archive_manifest"]["inspection"] == "unavailable"
