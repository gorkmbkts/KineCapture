"""Identity, access-control and automatic capture-context regressions."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.core.errors import ValidationError
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.project import CaptureProtocol, ProtocolTask
from kinecapture.gui.state import AppState
from kinecapture.identity import IdentityDatabase, IdentityService, UserRole
from kinecapture.identity.service import AuthenticationError, AuthorizationError


@pytest.fixture
def identity(tmp_path: Path) -> IdentityService:
    return IdentityService(IdentityDatabase(tmp_path / "identity.sqlite3"))


def owner(identity: IdentityService, *, username: str = "admin"):
    return identity.create_initial_owner(
        first_name="Sistem",
        last_name="Sahibi",
        title="Koordinatör",
        username=username,
        password="owner-password",
    )


def user_fields(username: str = "coach") -> dict[str, str]:
    return {
        "first_name": "Ayşe",
        "last_name": "Koç",
        "title": "Antrenör",
        "username": username,
        "password": "coach-password",
    }


def test_empty_database_bootstraps_exactly_one_owner(identity: IdentityService) -> None:
    assert identity.needs_initial_setup
    first = owner(identity)
    assert first.role is UserRole.OWNER
    assert not identity.needs_initial_setup
    with pytest.raises(ValidationError) as info:
        identity.create_initial_owner(**user_fields("second"))
    assert info.value.code == "setup_already_complete"


def test_database_partial_index_blocks_a_second_owner(identity: IdentityService) -> None:
    first = owner(identity)
    row = identity.repository.password_row("admin")
    assert row is not None
    with pytest.raises(sqlite3.IntegrityError):
        with identity.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO users(user_id, username, username_normalized,
                    password_hash, password_salt, password_algorithm,
                    password_parameters, first_name, last_name, title, role,
                    is_active, must_change_password, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'owner', 1, 0, ?, ?)
                """,
                (
                    "usr_second",
                    "second",
                    "second",
                    row["password_hash"],
                    row["password_salt"],
                    row["password_algorithm"],
                    row["password_parameters"],
                    "Second",
                    "Owner",
                    "",
                    first.created_at,
                    first.updated_at,
                ),
            )


def test_concurrent_first_setup_still_creates_one_owner(tmp_path: Path) -> None:
    service = IdentityService(IdentityDatabase(tmp_path / "identity.sqlite3"))
    barrier = threading.Barrier(2)

    def attempt(number: int) -> str:
        barrier.wait()
        try:
            created = service.create_initial_owner(
                first_name="Owner",
                last_name=str(number),
                title="",
                username=f"owner{number}",
                password="owner-password",
            )
            return created.user_id
        except ValidationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (1, 2)))
    assert sum(result.startswith("usr_") for result in results) == 1
    assert service.repository.user_count() == 1


def test_self_registration_is_always_a_normal_user(identity: IdentityService) -> None:
    owner(identity)
    created = identity.self_register(**user_fields())
    assert created.role is UserRole.USER
    assert created.is_active


def test_usernames_are_case_insensitively_unique(identity: IdentityService) -> None:
    owner(identity)
    identity.self_register(**user_fields("Coach.One"))
    with pytest.raises(ValidationError) as info:
        identity.self_register(**user_fields("coach.one"))
    assert info.value.code == "username_duplicate"


def test_password_is_hashed_and_authentication_is_generic(
    identity: IdentityService,
) -> None:
    owner(identity)
    raw = identity.database.path.read_bytes()
    assert b"owner-password" not in raw
    assert identity.authenticate("ADMIN", "owner-password").username == "admin"
    for username, password in (("admin", "wrong-value"), ("missing", "wrong-value")):
        with pytest.raises(AuthenticationError) as info:
            identity.authenticate(username, password)
        assert info.value.code == "authentication_failed"
        assert "Kullanıcı adı veya parola" in info.value.message


def test_inactive_user_cannot_login_or_use_protected_operations(
    identity: IdentityService, tmp_path: Path
) -> None:
    admin = owner(identity)
    coach = identity.self_register(**user_fields())
    identity.set_user_active(admin, coach.user_id, False)
    with pytest.raises(AuthenticationError) as info:
        identity.authenticate("coach", "coach-password")
    assert info.value.code == "account_inactive"
    with pytest.raises(AuthorizationError):
        identity.list_projects(coach)


def test_login_time_and_password_reset_flow(identity: IdentityService) -> None:
    admin = owner(identity)
    coach = identity.create_user(admin, **user_fields())
    assert coach.last_login_at is None
    logged_in = identity.authenticate("coach", "coach-password")
    assert logged_in.last_login_at is not None
    reset = identity.reset_password(admin, coach.user_id, "temporary-password")
    assert reset.must_change_password
    with pytest.raises(AuthenticationError):
        identity.authenticate("coach", "coach-password")
    forced = identity.authenticate("coach", "temporary-password")
    changed = identity.change_password(
        forced,
        current_password="temporary-password",
        new_password="new-coach-password",
    )
    assert not changed.must_change_password
    assert identity.authenticate("coach", "new-coach-password").user_id == coach.user_id


def test_owner_cannot_be_deactivated(identity: IdentityService) -> None:
    admin = owner(identity)
    with pytest.raises(AuthorizationError) as info:
        identity.set_user_active(admin, admin.user_id, False)
    assert info.value.code == "owner_cannot_be_deactivated"
    with pytest.raises(AuthorizationError) as deletion:
        identity.delete_user(admin, admin.user_id)
    assert deletion.value.code == "user_deletion_forbidden"
    with pytest.raises(AuthorizationError) as role_change:
        identity.set_user_role(admin, admin.user_id, UserRole.USER)
    assert role_change.value.code == "user_role_immutable"


def test_schema_installation_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "identity.sqlite3"
    first = IdentityService(IdentityDatabase(path))
    created = owner(first)
    second = IdentityService(IdentityDatabase(path))
    assert second.repository.user_count() == 1
    assert second.repository.get_user(created.user_id) == created


def test_project_access_and_removal_do_not_delete_files(
    identity: IdentityService, tmp_path: Path
) -> None:
    admin = owner(identity)
    coach = identity.self_register(**user_fields())
    workspace = ProjectWorkspace.create(tmp_path / "datasets", "Owner Project")
    record = identity.register_project(admin, workspace)
    assert identity.list_projects(coach) == []
    identity.assign_project(admin, coach.user_id, record.project_id)
    assert [p.project_id for p in identity.list_projects(coach)] == [record.project_id]
    assert identity.authorize_project_path(coach, workspace.root).project_id == record.project_id
    identity.remove_project_access(admin, coach.user_id, record.project_id)
    assert identity.list_projects(coach) == []
    assert workspace.project_file.is_file()


def test_normal_user_owns_and_can_open_the_project_they_create(
    identity: IdentityService, tmp_path: Path
) -> None:
    admin = owner(identity)
    coach = identity.self_register(**user_fields())
    workspace = identity.create_project(coach, tmp_path / "data", "Coach Project")
    record = identity.authorize_project(coach, workspace.project.project_id)
    assert record.owner_user_id == coach.user_id
    assert {p.project_id for p in identity.list_projects(admin)} == {record.project_id}


def test_project_creation_compensates_if_sql_registration_fails(
    identity: IdentityService, tmp_path: Path, monkeypatch
) -> None:
    admin = owner(identity)

    def fail(*_args, **_kwargs):
        raise ValidationError("forced", code="forced_registration_failure")

    monkeypatch.setattr(identity, "register_project", fail)
    with pytest.raises(ValidationError):
        identity.create_project(admin, tmp_path / "data", "Rollback")
    projects = tmp_path / "data" / "projects"
    assert not projects.exists() or list(projects.iterdir()) == []


def test_unauthorized_project_path_and_conflicting_project_id_are_rejected(
    identity: IdentityService, tmp_path: Path
) -> None:
    admin = owner(identity)
    coach = identity.self_register(**user_fields())
    first = ProjectWorkspace.create(tmp_path / "data", "First")
    identity.register_project(admin, first)
    with pytest.raises(AuthorizationError):
        identity.authorize_project_path(coach, first.root)
    with pytest.raises(AuthorizationError):
        identity.authorize_project_path(admin, tmp_path / ".." / "not-a-project")

    duplicate_root = tmp_path / "copied-project"
    duplicate_root.mkdir()
    (duplicate_root / "participants").mkdir()
    (duplicate_root / "project.json").write_bytes(first.project_file.read_bytes())
    with pytest.raises(ValidationError) as info:
        identity.register_project(admin, ProjectWorkspace.open(duplicate_root))
    assert info.value.code == "project_id_path_conflict"


def test_sql_metacharacters_in_profile_data_do_not_change_queries(
    identity: IdentityService,
) -> None:
    owner(identity)
    fields = user_fields("safe-user")
    fields["first_name"] = "Robert'); DROP TABLE users;--"
    identity.self_register(**fields)
    assert identity.repository.user_count() == 2
    assert identity.authenticate("safe-user", "coach-password").first_name.startswith("Robert")


def test_participant_codes_are_unique_under_concurrent_allocation(tmp_path: Path) -> None:
    workspace = ProjectWorkspace.create(tmp_path / "data", "Concurrent")

    def allocate(index: int) -> str:
        # Separate workspace objects simulate separate callers/process views.
        opened = ProjectWorkspace.open(workspace.root)
        return opened.create_participant(created_by_user_id=f"usr_{index}").code

    with ThreadPoolExecutor(max_workers=6) as executor:
        codes = list(executor.map(allocate, range(12)))
    assert sorted(codes) == [f"P{index:04d}" for index in range(1, 13)]
    assert len({p.participant_id for p in workspace.list_participants()}) == 12


def test_automatic_capture_context_binds_operator_and_closes_on_change(
    tmp_path: Path,
) -> None:
    config = AppConfig(
        dataset_root=tmp_path / "data",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    state = AppState(config)
    admin = state.identity.create_initial_owner(
        first_name="Ada",
        last_name="Admin",
        title="",
        username="ada",
        password="owner-password",
    )
    state.activate_user(admin)
    workspace = state.create_project("Capture")
    first = state.create_participant()
    second = state.create_participant()
    orphan = workspace.create_session(
        first.participant_id,
        operator="Eski",
        operator_user_id=admin.user_id,
        attributes={"automatic": True, "managed_run_id": "old-run"},
    )
    session = state.prepare_capture(first)
    assert workspace.load_session(first.participant_id, orphan.session_id).ended_at
    assert session.operator_user_id == admin.user_id
    assert session.operator == admin.display_name
    assert session.attributes["automatic"] is True
    same = state.prepare_capture(first)
    assert same.session_id == session.session_id

    next_session = state.prepare_capture(second)
    closed = workspace.load_session(first.participant_id, session.session_id)
    assert closed.ended_at is not None
    assert next_session.session_id != session.session_id
    state.logout()
    assert workspace.load_session(second.participant_id, next_session.session_id).ended_at


def test_single_recording_plan_is_selected_automatically(tmp_path: Path) -> None:
    config = AppConfig(
        dataset_root=tmp_path / "data",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    state = AppState(config)
    admin = state.identity.create_initial_owner(
        first_name="A", last_name="B", title="", username="admin", password="password1"
    )
    state.activate_user(admin)
    workspace = state.create_project("Plan")
    plan = CaptureProtocol.create("Diz Planı")
    plan.tasks.append(ProtocolTask.create("Squat"))
    workspace.project.protocols.append(plan)
    state.save_project()
    participant = state.create_participant()
    session = state.prepare_capture(participant)
    assert session.protocol_id == plan.protocol_id


def test_multiple_recording_plans_require_an_explicit_choice(tmp_path: Path) -> None:
    config = AppConfig(
        dataset_root=tmp_path / "data",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    state = AppState(config)
    admin = state.identity.create_initial_owner(
        first_name="A", last_name="B", title="", username="admin", password="password1"
    )
    state.activate_user(admin)
    workspace = state.create_project("Plan")
    workspace.project.protocols.extend(
        [CaptureProtocol.create("Plan 1"), CaptureProtocol.create("Plan 2")]
    )
    state.save_project()
    participant = state.create_participant()
    with pytest.raises(ValidationError) as info:
        state.prepare_capture(participant)
    assert info.value.code == "recording_plan_required"
    selected = state.prepare_capture(
        participant, protocol_id=workspace.project.protocols[1].protocol_id
    )
    assert selected.protocol_id == workspace.project.protocols[1].protocol_id
