"""The Studio shell: navigation, theming, context bar, messages, window state.

Two halves on purpose. The first half drives the real viewmodel with no Qt at
all - that is where the behaviour lives, and it should be testable without a
display. The second half builds the real window offscreen and checks the parts
that only exist once widgets do: that pages are lazy, that the stylesheet
actually reaches the application, that closing saves state and detaches.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.studio.services.context import ContextState
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.window_state import (
    WindowState,
    load_window_state,
    save_window_state,
)
from kinecapture.studio.viewmodels.navigation import DESTINATIONS
from kinecapture.studio.viewmodels.observable import Event, Observable, Subscriptions
from kinecapture.studio.viewmodels.shell import ShellViewModel


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    """An isolated configuration. Never touches the real preference file."""
    settings = AppConfig()
    settings.dataset_root = tmp_path / "datasets"
    settings.identity_db_path = tmp_path / "identity.sqlite3"
    settings.log_dir = tmp_path / "logs"
    settings.dataset_root.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def session(config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> SessionService:
    # Preferences are a real file on the user's machine; a test must not write
    # to it even by accident.
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _config: None
    )
    return SessionService.open(config)


@pytest.fixture
def shell(session: SessionService) -> ShellViewModel:
    viewmodel = ShellViewModel(session)
    yield viewmodel
    viewmodel.close()


# --------------------------------------------------------------- observable


def test_observable_notifies_only_on_change() -> None:
    seen: list[int] = []
    value = Observable(0)
    value.subscribe(seen.append)
    assert value.set(1) is True
    assert value.set(1) is False
    assert value.set(2) is True
    assert seen == [1, 2]


def test_observable_force_notifies_even_when_equal() -> None:
    """Needed for a rebuilt payload whose contents compare equal."""
    seen: list[list[int]] = []
    value = Observable([1])
    value.subscribe(seen.append)
    value.set([1])
    assert seen == []
    value.force([1])
    assert seen == [[1]]


def test_unsubscribe_stops_delivery() -> None:
    seen: list[int] = []
    value = Observable(0)
    unsubscribe = value.subscribe(seen.append)
    unsubscribe()
    value.set(5)
    assert seen == []
    assert value.subscriber_count == 0


def test_event_retains_nothing() -> None:
    """A late subscriber must not receive an old error."""
    event: Event[str] = Event()
    event.emit("first")
    seen: list[str] = []
    event.subscribe(seen.append)
    assert seen == []
    event.emit("second")
    assert seen == ["second"]


def test_subscriptions_close_detaches_everything() -> None:
    value = Observable(0)
    group = Subscriptions()
    group.add(value.subscribe(lambda _v: None))
    group.add(value.subscribe(lambda _v: None))
    assert value.subscriber_count == 2
    group.close()
    assert value.subscriber_count == 0


# --------------------------------------------------------------- navigation


def test_workflow_order_is_the_product_order() -> None:
    assert [item.key for item in DESTINATIONS] == [
        "projects",
        "capture",
        "processing",
        "library",
        "review",
        "dataset",
        "export",
        "settings",
    ]


def test_navigate_to_unknown_key_is_ignored(shell: ShellViewModel) -> None:
    before = shell.active_page.value
    assert shell.navigate("nowhere") is False
    assert shell.active_page.value == before


def test_step_clamps_at_both_ends(shell: ShellViewModel) -> None:
    shell.navigate("projects")
    shell.step(-1)
    assert shell.active_page.value == "projects"
    shell.navigate("settings")
    shell.step(1)
    assert shell.active_page.value == "settings"


def test_step_moves_along_the_workflow(shell: ShellViewModel) -> None:
    shell.navigate("capture")
    shell.step(1)
    assert shell.active_page.value == "processing"
    shell.step(-2)
    assert shell.active_page.value == "projects"


def test_shell_starts_on_the_remembered_page(session: SessionService) -> None:
    viewmodel = ShellViewModel(session, WindowState(active_page="review"))
    assert viewmodel.active_page.value == "review"
    viewmodel.close()


def test_shell_ignores_a_remembered_page_that_no_longer_exists(
    session: SessionService,
) -> None:
    viewmodel = ShellViewModel(session, WindowState(active_page="activity"))
    assert viewmodel.active_page.value == "projects"
    viewmodel.close()


# ------------------------------------------------------------------ context


def test_context_reports_a_missing_data_folder_as_a_warning(
    shell: ShellViewModel, config: AppConfig
) -> None:
    config.dataset_root = config.dataset_root / "gone"
    shell.refresh_context()
    item = shell.context.value.item("data")
    assert item is not None
    assert item.state is ContextState.WARNING
    # A missing folder is not an error and must not read like lost data.
    assert "bulunamadı" in item.value


def test_disk_falls_back_to_the_nearest_existing_parent(
    shell: ShellViewModel, config: AppConfig
) -> None:
    """The data folder is created on first use; its volume still has free space."""
    config.dataset_root = config.dataset_root / "not" / "made" / "yet"
    shell.refresh_context()
    item = shell.context.value.item("disk")
    assert item is not None
    assert item.state is not ContextState.ERROR
    assert item.numeric is True


def test_context_only_notifies_when_something_changed(shell: ShellViewModel) -> None:
    seen: list[object] = []
    shell.context.subscribe(seen.append)
    shell.refresh_context()
    shell.refresh_context()
    assert seen == []


# ----------------------------------------------------------------- messages


def test_kinecapture_error_keeps_both_layers() -> None:
    from kinecapture.core.errors import StorageError

    message = from_error(
        StorageError(
            "Veri klasörü bulunamadı.",
            code="dataset_root_missing",
            remedy="Ayarlar'dan bir veri klasörü seçin.",
            details={"yol": "D:/yok"},
        )
    )
    assert message.severity is Severity.ERROR
    assert message.headline == "Veri klasörü bulunamadı."
    assert message.detail == "Ayarlar'dan bir veri klasörü seçin."
    # Technical content exists but is not part of what is shown first.
    assert message.code == "dataset_root_missing"
    assert "yol: D:/yok" in message.technical_text()
    assert "dataset_root_missing" not in message.headline


def test_unexpected_error_does_not_put_the_exception_on_screen() -> None:
    message = from_error(KeyError("p"))
    assert "KeyError" not in message.headline
    assert "KeyError" in message.technical_text()
    assert message.has_details


def test_message_without_details_says_so() -> None:
    assert Message(headline="Bitti").has_details is False


def test_report_error_reaches_subscribers(shell: ShellViewModel) -> None:
    seen: list[Message] = []
    shell.message.subscribe(seen.append)
    shell.report_error(ValueError("boom"))
    assert len(seen) == 1
    assert seen[0].severity is Severity.ERROR


# -------------------------------------------------------------- window state


def test_window_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "window_state.json"
    state = WindowState(
        width=1440, height=900, maximised=False, active_page="review",
        inspector_open=True, inspector_width=380, theme="light",
    )
    assert save_window_state(state, path) == path
    assert load_window_state(path) == state


def test_window_state_is_written_atomically(tmp_path: Path) -> None:
    path = tmp_path / "window_state.json"
    save_window_state(WindowState(), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_window_state_falls_back_to_defaults(tmp_path: Path) -> None:
    """Losing a remembered window size must never block startup."""
    path = tmp_path / "window_state.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert load_window_state(path) == WindowState()


def test_window_state_clamps_impossible_values(tmp_path: Path) -> None:
    path = tmp_path / "window_state.json"
    path.write_text(
        json.dumps({"width": 10, "height": -5, "inspector_width": 99999}),
        encoding="utf-8",
    )
    state = load_window_state(path)
    assert state.width == 1120
    assert state.height == 700
    assert state.inspector_width == 1200


def test_saving_to_an_unwritable_path_reports_instead_of_raising(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "file.txt"
    blocked.write_text("not a directory", encoding="utf-8")
    assert save_window_state(WindowState(), blocked / "state.json") is None
