from concurrent.futures import ThreadPoolExecutor

import pytest

import app.config
from app.host.files import (
    append_text_file,
    list_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)


@pytest.fixture
def secure_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", workspace)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "MAX_SINGLE_FILE_BYTES", 128)
    return workspace


def test_directory_listing_does_not_follow_or_expose_symlink_target(secure_workspace):
    outside = secure_workspace.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = secure_workspace / "escape"
    link.symlink_to(outside)

    result = list_directory(".")
    item = next(entry for entry in result["items"] if entry["name"] == "escape")
    assert item["path"] == "escape"
    assert item["is_symlink"] is True
    assert item["is_directory"] is False
    assert str(outside) not in item["path"]

    with pytest.raises(PermissionError):
        read_text_file("escape")


def test_search_does_not_traverse_symlink_directory(secure_workspace):
    outside = secure_workspace.parent / "outside-dir"
    outside.mkdir()
    (outside / "secret.txt").write_text("needle", encoding="utf-8")
    (secure_workspace / "linked-dir").symlink_to(outside, target_is_directory=True)

    result = search_text("needle", path=".")
    assert result["results"] == []


def test_append_enforces_final_file_size(secure_workspace):
    write_text_file("note.txt", "x" * 120)
    with pytest.raises(ValueError, match="Append would exceed"):
        append_text_file("note.txt", "y" * 9)
    assert read_text_file("note.txt")["content"] == "x" * 120


def test_replace_rejects_oversized_existing_file(secure_workspace):
    path = secure_workspace / "large.txt"
    path.write_text("a" * 129, encoding="utf-8")
    with pytest.raises(ValueError, match="File exceeds"):
        replace_text_in_file("large.txt", "a", "b", expected_count=-1)
    assert path.read_text(encoding="utf-8") == "a" * 129


def test_atomic_no_overwrite_allows_only_one_concurrent_creator(secure_workspace):
    def create(value: str):
        try:
            return write_text_file("race.txt", value, overwrite=False)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ["first", "second"]))

    assert sum(result is not None for result in results) == 1
    assert read_text_file("race.txt")["content"] in {"first", "second"}
    assert not list(secure_workspace.glob(".*.bqa-tmp-*"))


def test_atomic_overwrite_preserves_existing_mode(secure_workspace):
    path = secure_workspace / "mode.txt"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o640)
    write_text_file("mode.txt", "new", overwrite=True)
    assert path.read_text(encoding="utf-8") == "new"
    assert path.stat().st_mode & 0o777 == 0o640


def test_concurrent_append_is_serialized(secure_workspace, monkeypatch):
    monkeypatch.setattr(app.config, "MAX_SINGLE_FILE_BYTES", 10_000)
    write_text_file("append.txt", "")

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda number: append_text_file("append.txt", f"{number:03d}\n"), range(100)))

    lines = read_text_file("append.txt")["content"].splitlines()
    assert len(lines) == 100
    assert set(lines) == {f"{number:03d}" for number in range(100)}
