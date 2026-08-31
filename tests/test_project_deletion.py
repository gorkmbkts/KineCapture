"""Permanently deleting a project - the one destructive path in the app.

Every test here builds its own project under ``tmp_path`` and deletes that.
Nothing in this file can reach a real dataset: the identity database is
redirected by the ``isolated_user_state`` fixture and every path is a pytest
temporary directory.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from kinecapture.core.errors import StorageError, ValidationError
from kinecapture.core.jsonio import read_json_mapping, write_json
from kinecapture.dataset.deletion import (
    TOMBSTONE_FILE,
    ProjectDeletionService,
    inspect_target,
    measure_tree,
    recover_tombstones,
    remove_tree,
    tombstone_root,
)
from kinecapture.dataset.workspace import PROJECT_FILE, ProjectWorkspace
from kinecapture.identity.database import IdentityDatabase
from kinecapture.identity.service import AuthorizationError, IdentityService


@pytest.fixture
def identity(tmp_path):
    return IdentityService(IdentityDatabase(tmp_path / "identity.sqlite3"))


@pytest.fixture
def owner(identity):
    return identity.create_initial_owner(
        first_name="Sys",
        last_name="Owner",
        title="",
        username="owner",
        password="owner-password",
    )


@pytest.fixture
def normal_user(identity, owner):
    return identity.create_user(
        owner,
        first_name="Normal",
        last_name="User",
        title="",
        username="normal",
        password="normal-password",
    )


@pytest.fixture
def dataset_root(tmp_path):
    root = tmp_path / "datasets"
    root.mkdir()
    return root


def make_project(identity, user, dataset_root, name="Silinecek Proje"):
    """A registered project with real files in every subtree that matters."""
    workspace = identity.create_project(user, dataset_root, name)
    participant = workspace.create_participant()
    session = workspace.create_session(
        participant.participant_id, operator="pytest"
    )
    take_dir = (
        workspace.root
        / "participants"
        / participant.participant_id
        / "sessions"
        / session.session_id
        / "takes"
        / "take_test"
    )
    for relative, payload in (
        ("raw/rgbd_000000.bin", b"\x00" * 4096),
        ("derived/skeleton.jsonl", b'{"frame_index": 0}\n'),
        ("derived/proxy.mp4", b"\x00" * 2048),
        ("annotations/segments.json", b'{"samples": []}'),
    ):
        path = take_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    release = workspace.root / "releases" / "dataset_v001"
    release.mkdir(parents=True, exist_ok=True)
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    return workspace


@pytest.fixture
def service(identity, dataset_root):
    return ProjectDeletionService(identity, dataset_root)


# ------------------------------------------------------------ authorisation


def test_a_normal_user_is_refused_by_the_service_not_the_button(
    identity, owner, normal_user, dataset_root, service
) -> None:
    """The security boundary has to survive somebody bypassing the GUI."""
    workspace = make_project(identity, normal_user, dataset_root)
    project_id = workspace.project.project_id

    with pytest.raises(AuthorizationError):
        service.preflight(normal_user, project_id)
    with pytest.raises(AuthorizationError):
        service.delete(normal_user, project_id)
    with pytest.raises(AuthorizationError):
        identity.forget_project(normal_user, project_id)

    # Nothing moved.
    assert workspace.project_file.is_file()
    assert identity.repository.get_project(project_id) is not None


def test_the_owner_is_allowed(identity, owner, dataset_root, service) -> None:
    workspace = make_project(identity, owner, dataset_root)
    report = service.preflight(owner, workspace.project.project_id)
    assert report.ok, report.reason


def test_an_unregistered_project_cannot_be_deleted(
    identity, owner, dataset_root, service
) -> None:
    with pytest.raises(ValidationError) as info:
        service.preflight(owner, "prj_does_not_exist")
    assert info.value.code == "project_not_registered"


# ------------------------------------------------------------- path guards


def test_the_guard_refuses_a_moved_or_reused_directory(
    identity, owner, dataset_root
) -> None:
    """The database row is a claim about the disk; it is checked, not trusted."""
    workspace = make_project(identity, owner, dataset_root)
    other = make_project(identity, owner, dataset_root, name="Başka Proje")

    # The right folder for the wrong project id.
    report = inspect_target(
        recorded_path=workspace.root,
        project_id=other.project.project_id,
        dataset_root=dataset_root,
    )
    assert not report.ok
    assert report.code == "delete_identity_mismatch"


def test_the_guard_refuses_roots_and_non_projects(tmp_path, dataset_root) -> None:
    plain = tmp_path / "not-a-project"
    plain.mkdir()
    assert (
        inspect_target(
            recorded_path=plain, project_id="prj_x", dataset_root=dataset_root
        ).code
        == "delete_target_not_a_project"
    )

    assert (
        inspect_target(
            recorded_path=dataset_root, project_id="prj_x", dataset_root=dataset_root
        ).code
        == "delete_target_is_dataset_root"
    )

    anchor = Path(tmp_path.anchor)
    assert (
        inspect_target(
            recorded_path=anchor, project_id="prj_x", dataset_root=dataset_root
        ).code
        in ("delete_target_too_shallow", "delete_target_not_a_project")
    )

    missing = tmp_path / "gone"
    assert (
        inspect_target(
            recorded_path=missing, project_id="prj_x", dataset_root=dataset_root
        ).code
        == "delete_target_missing"
    )


def test_the_guard_refuses_the_home_directory(dataset_root) -> None:
    assert (
        inspect_target(
            recorded_path=Path.home(),
            project_id="prj_x",
            dataset_root=dataset_root,
        ).code
        in ("delete_target_is_home", "delete_target_not_a_project")
    )


def test_the_guard_refuses_a_link(identity, owner, dataset_root, tmp_path) -> None:
    """A junction would turn "delete this project" into "delete its target"."""
    workspace = make_project(identity, owner, dataset_root)
    link = tmp_path / "link-to-project"
    try:
        link.symlink_to(workspace.root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this environment cannot create a directory symlink")

    report = inspect_target(
        recorded_path=link,
        project_id=workspace.project.project_id,
        dataset_root=dataset_root,
    )
    assert not report.ok
    assert report.code == "delete_target_is_link"
    assert workspace.project_file.is_file()


def test_a_link_inside_a_project_is_not_followed_out_of_it(
    identity, owner, dataset_root, tmp_path
) -> None:
    workspace = make_project(identity, owner, dataset_root)
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("do not delete me", encoding="utf-8")
    try:
        (workspace.root / "shortcut").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this environment cannot create a directory symlink")

    assert remove_tree(workspace.root) == []
    assert not workspace.root.exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "do not delete me"


# ------------------------------------------------------------- the happy path


def test_deleting_removes_every_file_and_every_row(
    identity, owner, dataset_root, service
) -> None:
    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id
    root = workspace.root
    nested = list(root.rglob("*.bin"))
    assert nested, "the fixture must create a raw archive file"

    result = service.delete(owner, project_id)

    assert result.complete, result.summary()
    assert not root.exists()
    for path in nested:
        assert not path.exists()
    assert identity.repository.get_project(project_id) is None
    assert not identity.repository.assigned_project_ids(owner.user_id) & {project_id}
    assert project_id not in {p.project_id for p in identity.list_projects(owner)}
    # No hidden trash folder is left holding the bytes.
    assert not tombstone_root(dataset_root).exists()
    assert result.freed_bytes and result.freed_bytes > 4096


def test_the_audit_history_survives_the_foreign_key(
    identity, owner, dataset_root, service
) -> None:
    """Deleting a folder must not delete the record that somebody did it."""
    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id

    service.delete(owner, project_id)

    with identity.database.connection() as connection:
        rows = connection.execute(
            "SELECT event_type, actor_user_id, project_id, metadata_json "
            "FROM audit_log ORDER BY audit_id"
        ).fetchall()

    events = [row["event_type"] for row in rows]
    assert "project_created" in events or "project_registered" in events
    assert "project_deleted" in events
    assert "project_files_removed" in events

    # Every surviving row has had its dangling pointer cleared but kept the
    # identity of what it was about.
    assert all(row["project_id"] is None for row in rows)
    deleted = next(row for row in rows if row["event_type"] == "project_deleted")
    assert project_id in deleted["metadata_json"]
    assert deleted["actor_user_id"] == owner.user_id
    historic = next(
        row
        for row in rows
        if row["event_type"] in ("project_created", "project_registered")
    )
    assert project_id in historic["metadata_json"], (
        "an older event must keep the project identity it referred to"
    )


def test_progress_is_reported_in_order(identity, owner, dataset_root, service) -> None:
    workspace = make_project(identity, owner, dataset_root)
    steps: list[str] = []
    service.delete(owner, workspace.project.project_id, progress=steps.append)
    assert steps == [
        "Hedef doğrulanıyor…",
        "Boyut hesaplanıyor…",
        "Proje ayrılıyor…",
        "Kayıtlar temizleniyor…",
        "Dosyalar siliniyor…",
    ]


def test_measuring_can_be_skipped(identity, owner, dataset_root, service) -> None:
    workspace = make_project(identity, owner, dataset_root)
    result = service.delete(owner, workspace.project.project_id, measure=False)
    assert result.complete
    assert result.freed_bytes is None
    assert "ölçülemedi" in result.summary()


# --------------------------------------------------------------- resilience


def test_read_only_files_are_removed_not_reported_as_failures(
    identity, owner, dataset_root, service
) -> None:
    """The usual Windows refusal, which used to abort a delete half way."""
    workspace = make_project(identity, owner, dataset_root)
    target = next(workspace.root.rglob("*.bin"))
    os.chmod(target, stat.S_IREAD)
    try:
        result = service.delete(owner, workspace.project.project_id)
    finally:
        if target.exists():  # pragma: no cover - only on failure
            os.chmod(target, stat.S_IWRITE)
    assert result.complete, result.summary()
    assert not workspace.root.exists()


def test_a_database_failure_puts_the_project_back(
    identity, owner, dataset_root, service, monkeypatch
) -> None:
    """No silent half-state: either it is gone or it is exactly where it was."""
    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id
    before = sorted(p.name for p in workspace.root.iterdir())

    def explode(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(identity, "forget_project", explode)

    with pytest.raises(StorageError) as info:
        service.delete(owner, project_id)
    assert info.value.code == "delete_db_failed"

    assert workspace.root.is_dir()
    assert sorted(p.name for p in workspace.root.iterdir()) == before
    assert identity.repository.get_project(project_id) is not None
    assert not (workspace.root / TOMBSTONE_FILE).exists()


def test_files_left_behind_are_never_reported_as_success(
    identity, owner, dataset_root, service, monkeypatch
) -> None:
    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id

    monkeypatch.setattr(
        "kinecapture.dataset.deletion.remove_tree",
        lambda root: ["C:/somewhere/locked.bin (in use)"],
    )
    result = service.delete(owner, project_id)

    assert not result.complete
    assert not result.files_removed
    assert result.remaining
    assert "TAMAMEN silinemedi" in result.summary()
    # The database side did finish, so the tombstone marker says so and the
    # startup recovery will finish the physical delete rather than restore.
    marker = read_json_mapping(result.tombstone / TOMBSTONE_FILE)
    assert marker["database_cleared"] is True

    with identity.database.connection() as connection:
        events = [
            row["event_type"]
            for row in connection.execute("SELECT event_type FROM audit_log")
        ]
    assert "project_files_remaining" in events


# ----------------------------------------------------------------- recovery


def test_recovery_finishes_a_delete_whose_database_side_completed(
    dataset_root,
) -> None:
    tomb = tombstone_root(dataset_root) / "prj_x__20260830"
    (tomb / "raw").mkdir(parents=True)
    (tomb / "raw" / "chunk.bin").write_bytes(b"\x00" * 128)
    write_json(
        tomb / TOMBSTONE_FILE,
        {
            "project_id": "prj_x",
            "original_path": str(dataset_root / "projects" / "prj_x"),
            "database_cleared": True,
        },
        overwrite=True,
    )

    notes = recover_tombstones(dataset_root, known_project_ids=set())
    assert not tomb.exists()
    assert any("tamamlandı" in note for note in notes)


def test_recovery_restores_a_delete_whose_database_side_did_not(
    dataset_root,
) -> None:
    original = dataset_root / "projects" / "prj_y"
    tomb = tombstone_root(dataset_root) / "prj_y__20260830"
    (tomb / "raw").mkdir(parents=True)
    (tomb / "raw" / "chunk.bin").write_bytes(b"\x00" * 128)
    write_json(
        tomb / TOMBSTONE_FILE,
        {
            "project_id": "prj_y",
            "original_path": str(original),
            "database_cleared": False,
        },
        overwrite=True,
    )

    notes = recover_tombstones(dataset_root, known_project_ids={"prj_y"})
    assert original.is_dir()
    assert (original / "raw" / "chunk.bin").is_file()
    assert not (original / TOMBSTONE_FILE).exists()
    assert any("geri alındı" in note for note in notes)


def test_recovery_leaves_an_unreadable_tombstone_alone(dataset_root) -> None:
    """Ambiguity resolves towards keeping data, never towards erasing it."""
    tomb = tombstone_root(dataset_root) / "mystery"
    tomb.mkdir(parents=True)
    (tomb / "data.bin").write_bytes(b"\x00" * 32)

    notes = recover_tombstones(dataset_root, known_project_ids=set())
    assert tomb.is_dir()
    assert (tomb / "data.bin").is_file()
    assert any("dokunulmadı" in note for note in notes)


# ------------------------------------------------------------------ sizing


def test_measure_tree_reports_bytes_and_unreadable_entries(tmp_path) -> None:
    root = tmp_path / "tree"
    (root / "a").mkdir(parents=True)
    (root / "a" / "one.bin").write_bytes(b"\x00" * 1000)
    (root / "two.bin").write_bytes(b"\x00" * 24)

    total, unreadable = measure_tree(root)
    assert total == 1024
    assert unreadable == 0

    empty = tmp_path / "empty"
    empty.mkdir()
    assert measure_tree(empty) == (None, 0)


# ------------------------------------------------- orphaned project records


def test_an_orphan_record_can_be_removed_without_touching_the_disk(
    identity, owner, dataset_root, service
) -> None:
    """The folder is gone; the row was previously impossible to get rid of."""
    import shutil as _shutil

    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id
    _shutil.rmtree(workspace.root)
    assert not workspace.root.exists()

    # The normal delete correctly refuses: there is nothing it can verify.
    assert service.preflight(owner, project_id).code == "delete_target_missing"

    result = service.forget_orphan(owner, project_id)

    assert result.database_cleared
    assert result.freed_bytes == 0, "nothing was on disk to free"
    assert identity.repository.get_project(project_id) is None
    assert project_id not in {p.project_id for p in identity.list_projects(owner)}
    assert not tombstone_root(dataset_root).exists(), "no filesystem work happened"


def test_removing_an_orphan_keeps_a_distinguishable_audit_trail(
    identity, owner, dataset_root, service
) -> None:
    """"Files destroyed" and "stale row removed" must not read the same."""
    import shutil as _shutil

    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id
    name = workspace.project.name
    path = str(workspace.root)
    _shutil.rmtree(workspace.root)

    service.forget_orphan(owner, project_id)

    with identity.database.connection() as connection:
        rows = connection.execute(
            "SELECT event_type, actor_user_id, metadata_json FROM audit_log"
        ).fetchall()
    events = [row["event_type"] for row in rows]
    assert "project_record_removed" in events
    assert "project_deleted" not in events, (
        "an orphan removal must not look like a destruction"
    )
    entry = next(r for r in rows if r["event_type"] == "project_record_removed")
    assert entry["actor_user_id"] == owner.user_id
    # Parsed rather than substring-matched: a Windows path is JSON-escaped in
    # the stored text, and the point is what a reader gets back, not the bytes.
    metadata = json.loads(entry["metadata_json"])
    assert metadata["project_id"] == project_id
    assert metadata["project_name"] == name
    assert metadata["project_path"] == path
    assert metadata["files_deleted"] is False
    assert "bulunamadı" in metadata["reason"]


def test_a_normal_user_cannot_remove_an_orphan_record(
    identity, owner, normal_user, dataset_root, service
) -> None:
    import shutil as _shutil

    workspace = make_project(identity, normal_user, dataset_root)
    project_id = workspace.project.project_id
    _shutil.rmtree(workspace.root)

    with pytest.raises(AuthorizationError):
        service.forget_orphan(normal_user, project_id)
    assert identity.repository.get_project(project_id) is not None


def test_a_project_that_still_exists_is_not_an_orphan(
    identity, owner, dataset_root, service
) -> None:
    """The narrow door stays narrow: a present folder goes through delete."""
    workspace = make_project(identity, owner, dataset_root)

    with pytest.raises(ValidationError) as info:
        service.forget_orphan(owner, workspace.project.project_id)
    assert info.value.code == "not_an_orphan_record"
    assert workspace.project_file.is_file()
    assert identity.repository.get_project(workspace.project.project_id) is not None


def test_a_target_that_fails_a_security_guard_is_not_an_orphan(
    identity, owner, dataset_root, service, tmp_path
) -> None:
    """A folder we cannot verify is not the same as a folder that is gone.

    Manifest mismatch, symlink and permission failure all mean *something* is
    there that this application does not understand, which is exactly when
    quietly dropping the record would be the wrong answer.
    """
    workspace = make_project(identity, owner, dataset_root)
    project_id = workspace.project.project_id

    # Present, but its manifest claims a different project.
    manifest = read_json_mapping(workspace.project_file)
    manifest["project_id"] = "prj_somebody_else"
    write_json(workspace.project_file, manifest, overwrite=True)

    report = service.preflight(owner, project_id)
    assert report.code == "delete_identity_mismatch"
    with pytest.raises(ValidationError) as info:
        service.forget_orphan(owner, project_id)
    assert info.value.code == "not_an_orphan_record"
    assert identity.repository.get_project(project_id) is not None

    # And a folder that exists but is not a project at all.
    other = make_project(identity, owner, dataset_root, name="İkinci Proje")
    other_id = other.project.project_id
    (other.root / PROJECT_FILE).unlink()
    assert service.preflight(owner, other_id).code == "delete_target_not_a_project"
    with pytest.raises(ValidationError):
        service.forget_orphan(owner, other_id)
    assert identity.repository.get_project(other_id) is not None
