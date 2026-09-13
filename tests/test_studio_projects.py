"""Projects, participants and settings, driven through the real viewmodels.

No Qt here: everything below is the layer a WinUI front end would keep, so it
is tested the way that layer is meant to be testable - synchronously, with an
:class:`InlineRunner` standing in for the thread pool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.studio.services.projects import ProjectService
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.settings import (
    FIELDS_BY_KEY,
    GROUP_ORDER,
    SettingsService,
    all_fields,
)
from kinecapture.studio.viewmodels.auth import AuthMode, AuthViewModel
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from kinecapture.studio.viewmodels.settings import SettingsViewModel
from kinecapture.studio.viewmodels.tasks import InlineRunner


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    settings = AppConfig()
    settings.dataset_root = tmp_path / "datasets"
    settings.identity_db_path = tmp_path / "identity.sqlite3"
    settings.log_dir = tmp_path / "logs"
    settings.dataset_root.mkdir(parents=True)
    return settings


@pytest.fixture
def session(config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> SessionService:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    return SessionService.open(config)


@pytest.fixture
def signed_in(session: SessionService) -> SessionService:
    auth = AuthViewModel(session)
    assert auth.mode is AuthMode.SETUP
    assert auth.create_owner(
        first_name="Ada",
        last_name="Lovelace",
        title="",
        username="ada",
        password="kinecapture1",
        password_confirm="kinecapture1",
    )
    return session


@pytest.fixture
def projects(signed_in: SessionService) -> ProjectsViewModel:
    return ProjectsViewModel(signed_in, InlineRunner())


# ----------------------------------------------------------------------- auth


def test_first_run_offers_only_setup(session: SessionService) -> None:
    """Nothing else can succeed before the first account exists."""
    auth = AuthViewModel(session)
    assert auth.mode is AuthMode.SETUP
    auth.set_mode(AuthMode.REGISTER)
    assert auth.mode is AuthMode.SETUP


def test_mismatched_passwords_are_caught_before_the_database(
    session: SessionService,
) -> None:
    auth = AuthViewModel(session)
    assert not auth.create_owner(
        first_name="A", last_name="B", title="", username="ab",
        password="kinecapture1", password_confirm="different1",
    )
    assert auth.state.value.problem_for("password_confirm")
    assert session.needs_initial_setup is True


def test_sign_in_emits_once_and_opens_the_gate(signed_in: SessionService) -> None:
    assert signed_in.is_authenticated
    assert signed_in.user is not None
    assert signed_in.user.is_owner


def test_a_wrong_password_reports_without_saying_which_half_was_wrong(
    signed_in: SessionService,
) -> None:
    signed_in.sign_out()
    auth = AuthViewModel(signed_in)
    seen = []
    auth.message.subscribe(seen.append)
    assert auth.sign_in("ada", "wrong-password") is False
    assert len(seen) == 1
    # The service's own wording survives: it is more useful than a generic
    # "could not sign in", and deliberately does not say which half was wrong.
    headline = seen[0].headline.casefold()
    assert "parola" in headline
    assert "kullanıcı adı veya parola" in headline
    assert signed_in.is_authenticated is False


def test_empty_fields_are_reported_per_field(signed_in: SessionService) -> None:
    signed_in.sign_out()
    auth = AuthViewModel(signed_in)
    assert auth.sign_in("", "") is False
    assert auth.state.value.problem_for("username")
    assert auth.state.value.problem_for("password")


# ------------------------------------------------------------------- projects


def test_no_projects_yet_says_so(projects: ProjectsViewModel) -> None:
    projects.reload_projects()
    assert projects.projects.value == ()
    assert "proje yok" in projects.summary.value.casefold()


def test_creating_a_project_opens_it(projects: ProjectsViewModel) -> None:
    projects.reload_projects()
    assert projects.create_project("Squat", "önden çekim")
    assert len(projects.projects.value) == 1
    assert projects.selected_project.value == projects.projects.value[0].project_id
    assert projects.projects.value[0].is_owner is True


def test_a_project_needs_a_name(projects: ProjectsViewModel) -> None:
    seen = []
    projects.message.subscribe(seen.append)
    assert projects.create_project("   ") is False
    assert seen and "ad" in seen[0].headline.casefold()


def test_participants_get_sequential_anonymous_codes(
    projects: ProjectsViewModel,
) -> None:
    projects.reload_projects()
    projects.create_project("Squat")
    for _ in range(3):
        assert projects.create_participant()
    codes = [row.code for row in projects.participants.value]
    assert codes == ["P0001", "P0002", "P0003"]


def test_participant_needs_an_open_project(projects: ProjectsViewModel) -> None:
    seen = []
    projects.message.subscribe(seen.append)
    assert projects.create_participant() is False
    assert seen and "proje" in seen[0].headline.casefold()


def test_summary_counts_what_is_waiting(projects: ProjectsViewModel) -> None:
    projects.reload_projects()
    projects.create_project("Squat")
    projects.create_participant()
    assert "1 katılımcı" in projects.summary.value
    assert "0 kayıt" in projects.summary.value


def test_a_missing_project_folder_is_reported_not_dropped(
    projects: ProjectsViewModel, signed_in: SessionService
) -> None:
    """A drive that is not plugged in is not the same as data that is gone."""
    import shutil

    projects.reload_projects()
    projects.create_project("Squat")
    row = projects.projects.value[0]
    shutil.rmtree(row.path)

    projects.reload_projects()
    assert len(projects.projects.value) == 1
    assert projects.projects.value[0].exists is False
    assert "bulunamadı" in projects.projects.value[0].status_text

    seen = []
    projects.message.subscribe(seen.append)
    projects.open_project(row.project_id)
    assert seen and seen[0].code == "project_folder_missing"


def test_index_refresh_runs_through_the_runner(
    signed_in: SessionService,
) -> None:
    """The viewmodel must not call the scan directly; it hands it to a runner."""
    calls: list[str] = []

    class RecordingRunner(InlineRunner):
        def run(self, work, on_done, on_error=None):  # noqa: ANN001
            calls.append("ran")
            super().run(work, on_done, on_error)

    viewmodel = ProjectsViewModel(signed_in, RecordingRunner())
    viewmodel.reload_projects()
    viewmodel.create_project("Squat")
    assert calls, "indeks yenileme runner üzerinden geçmedi"
    assert viewmodel.busy.value is False


def test_a_failing_scan_leaves_the_screen_usable(signed_in: SessionService) -> None:
    class FailingRunner:
        def run(self, work, on_done, on_error=None):  # noqa: ANN001
            on_error(RuntimeError("disk okunamadı"))

    viewmodel = ProjectsViewModel(signed_in, FailingRunner())
    viewmodel.reload_projects()
    viewmodel.create_project("Squat")
    seen = []
    viewmodel.message.subscribe(seen.append)
    viewmodel.refresh_index()
    assert viewmodel.busy.value is False
    assert seen and seen[0].severity.value == "error"


# ------------------------------------------------------------------- service


def test_take_counts_come_from_the_index(signed_in: SessionService) -> None:
    from kinecapture.dataset.summary_index import build_index

    service = ProjectService(signed_in.identity, signed_in.user)
    workspace = service.create_project(signed_in.config.dataset_root, "Squat")
    participant = service.create_participant(workspace)
    session = workspace.create_session(participant.participant_id, operator="ada")
    directory = workspace.take_dir(
        participant.participant_id, session.session_id, "take_x"
    )
    (directory / "derived" / "processing" / "run_a").mkdir(parents=True)
    (directory / "take.json").write_text(
        json.dumps(
            {
                "take_id": "take_x",
                "started_at": "2026-09-13T10:00:00+00:00",
                "state": "finalized",
                "processing_status": "awaiting_processing",
                "metrics": {"frames_written": 10, "duration_s": 1.0},
            }
        ),
        encoding="utf-8",
    )
    (directory / "derived" / "processing" / "run_a" / "job.json").write_text(
        json.dumps({"run_id": "run_a", "state": "complete", "frames_processed": 10}),
        encoding="utf-8",
    )

    index = build_index(workspace.root, force=True)
    rows = service.participants(workspace, index)
    assert rows[0].take_count == 1
    assert rows[0].processed_count == 1
    # A take with a finished version is not still waiting.
    assert rows[0].awaiting_count == 0


# ------------------------------------------------------------------ settings


@pytest.fixture
def settings(config: AppConfig) -> SettingsViewModel:
    return SettingsViewModel(SettingsService(config, save=lambda _c: None))


def test_every_setting_explains_itself() -> None:
    """The sentence is part of the setting, not an optional extra."""
    for field in all_fields():
        assert field.help_text.strip(), field.key
        assert field.help_text.strip().endswith("."), field.key
        assert field.label.strip(), field.key


def test_every_group_has_fields(settings: SettingsViewModel) -> None:
    groups = {key: fields for key, _t, _s, fields in settings.groups()}
    assert tuple(groups) == GROUP_ORDER
    for key, fields in groups.items():
        assert fields, key


def test_costly_options_say_what_they_cost() -> None:
    """Turning on a live product is a real cost; it is stated before, not after."""
    assert FIELDS_BY_KEY["capture.enable_body_tracking"].cost_note
    assert FIELDS_BY_KEY["capture.depth_archive"].cost_note
    lossless = next(
        c for c in FIELDS_BY_KEY["capture.native_compression"].choices
        if c.value == "H264_LOSSLESS"
    )
    assert "GB/dk" in lossless.cost


def test_an_edit_is_pending_until_saved(settings: SettingsViewModel) -> None:
    assert settings.dirty.value is False
    settings.edit("capture.fps", 30)
    assert settings.dirty.value is True
    assert settings.value_of("capture.fps") == 30
    assert settings.service.config.capture.fps != 30
    assert settings.save()
    assert settings.service.config.capture.fps == 30
    assert settings.dirty.value is False


def test_editing_back_to_the_original_clears_the_edit(
    settings: SettingsViewModel,
) -> None:
    original = settings.value_of("capture.fps")
    settings.edit("capture.fps", 30)
    settings.edit("capture.fps", original)
    assert settings.dirty.value is False
    assert settings.pending.value == {}


def test_an_invalid_value_is_reported_against_its_own_field(
    settings: SettingsViewModel,
) -> None:
    settings.edit("capture.preview_fps", 0.0)
    assert settings.problem_for("capture.preview_fps")
    assert settings.save() is False
    # The application keeps running on the old value.
    assert settings.service.config.capture.preview_fps > 0


def test_nothing_is_written_when_one_field_is_invalid(
    settings: SettingsViewModel,
) -> None:
    """All-or-nothing: a half-applied settings change is a state nobody chose."""
    before = settings.service.config.capture.fps
    settings.edit("capture.fps", 45)
    settings.edit("capture.preview_fps", -1.0)
    assert settings.save() is False
    assert settings.service.config.capture.fps == before


def test_discard_restores_the_shown_values(settings: SettingsViewModel) -> None:
    original = settings.value_of("processing.body_format")
    settings.edit("processing.body_format", "BODY_18")
    settings.discard()
    assert settings.value_of("processing.body_format") == original
    assert settings.problems.value == {}


def test_processing_defaults_are_editable(settings: SettingsViewModel) -> None:
    settings.edit("processing.body_format", "BODY_34")
    settings.edit("processing.depth_mode", "QUALITY")
    assert settings.save()
    assert settings.service.processing.body_format == "BODY_34"
    assert settings.service.processing.depth_mode == "QUALITY"


def test_an_unknown_choice_is_refused(settings: SettingsViewModel) -> None:
    settings.edit("processing.body_format", "BODY_99")
    assert settings.problem_for("processing.body_format")
    assert settings.save() is False


def test_a_read_only_setting_cannot_be_changed(settings: SettingsViewModel) -> None:
    settings.edit("language", "en")
    assert settings.problem_for("language")


def test_settings_are_written_through_the_injected_saver(config: AppConfig) -> None:
    """Saving goes through the atomic preference writer, not a bare open()."""
    written: list[AppConfig] = []
    viewmodel = SettingsViewModel(SettingsService(config, save=written.append))
    viewmodel.edit("theme", "light")
    assert viewmodel.save()
    assert written and written[0] is config
    assert config.theme == "light"


def test_a_failing_save_does_not_lose_the_change(config: AppConfig) -> None:
    """A preference file that cannot be written is not worth refusing the change."""

    def boom(_config):  # noqa: ANN001
        raise OSError("disk dolu")

    viewmodel = SettingsViewModel(SettingsService(config, save=boom))
    viewmodel.edit("theme", "light")
    assert viewmodel.save()
    assert config.theme == "light"
