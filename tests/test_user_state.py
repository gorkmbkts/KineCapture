"""The application must never write to a user's settings behind their back.

Preferences are saved on purpose (theme change, project opened). What must not
happen is a *test run* - or any code path that only meant to read - rewriting
the real ``~/.kinecapture/user_state.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from kinecapture.core.config import AppConfig, load_config, save_user_state
from kinecapture.domain.enums import BackendKind


def test_saving_preferences_targets_the_redirected_path(
    isolated_user_state: Path, tmp_path: Path
) -> None:
    """The autouse isolation fixture really is in effect for the whole suite."""
    config = AppConfig(dataset_root=tmp_path / "d", theme="light")
    written = save_user_state(config)
    assert written == isolated_user_state
    assert isolated_user_state.is_file()
    assert Path.home() / ".kinecapture" not in written.parents


def test_saved_state_round_trips(isolated_user_state: Path, tmp_path: Path) -> None:
    config = AppConfig(
        dataset_root=tmp_path / "roundtrip",
        theme="light",
        backend=BackendKind.ZED,
        preview_fps=24.0,
        last_username="ayse",
    )
    save_user_state(config)
    payload = yaml.safe_load(isolated_user_state.read_text(encoding="utf-8"))
    assert payload["theme"] == "light"
    assert payload["backend"] == "zed"
    assert payload["preview_fps"] == 24.0
    assert payload["dataset_root"] == str(tmp_path / "roundtrip")
    assert payload["last_username"] == "ayse"
    assert "password" not in " ".join(payload).casefold()
    assert "identity_db_path" not in payload


def test_loading_config_does_not_write(isolated_user_state: Path) -> None:
    """Reading configuration must have no side effect on disk."""
    assert not isolated_user_state.exists()
    load_config(include_user_state=True)
    assert not isolated_user_state.exists()


def test_user_state_overlays_shipped_defaults(
    isolated_user_state: Path, tmp_path: Path
) -> None:
    isolated_user_state.write_text(
        yaml.safe_dump({"theme": "light", "preview_fps": 15}), encoding="utf-8"
    )
    config = load_config(include_user_state=True)
    assert config.theme == "light"
    assert config.preview_fps == 15
    # Values the overlay did not mention keep the shipped default.
    assert config.capture.body_format == "BODY_34"


def test_capture_profile_is_not_a_global_preference(
    isolated_user_state: Path, tmp_path: Path
) -> None:
    """Capture settings are copied into each take; changing them later must
    not retroactively alter what an existing take says about itself."""
    from kinecapture.dataset.workspace import ProjectWorkspace

    workspace = ProjectWorkspace.create(tmp_path / "ds", "Profil Testi")
    participant = workspace.create_participant()
    session = workspace.create_session(participant.participant_id)
    take, _paths = workspace.prepare_take(session)
    recorded_format = take.capture_profile.body_format

    config = AppConfig(dataset_root=tmp_path / "ds")
    config.capture.body_format = "BODY_38"
    save_user_state(config)

    reloaded = workspace.load_take(
        take.participant_id, take.session_id, take.take_id
    )
    assert reloaded.capture_profile.body_format == recorded_format
