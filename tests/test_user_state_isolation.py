"""A test run must not be able to change what the application is configured to do.

On 20 September the user's real ``~/.kinecapture/user_state.yaml`` came back
from a measurement run with ``dataset_root`` pointing at a Claude scratchpad
directory. Nothing was broken in the code that *wrote* it: ``save_user_state``
faithfully wrote the configuration it was handed, to the module-level path it
had always used. The hole was that the four locations a configuration carries
could be moved apart - datasets, identity and logs into a sandbox, preferences
left global - and a script that moved three of them was one line away from
rewriting the user's settings.

So the preference path is part of the configuration now, and a configuration
whose data lives in a temporary tree is refused the real file outright. These
tests hold that shut. They deliberately exercise the real ``save_user_state``
rather than a stub, because a stubbed writer proves nothing about the writer.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from kinecapture.core import config as config_module
from kinecapture.core.config import AppConfig, ConfigError, load_config, save_user_state


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def test_sandboxed_config_saves_inside_its_own_sandbox(tmp_path: Path) -> None:
    config = AppConfig.sandboxed(tmp_path / "run")
    written = save_user_state(config)

    assert written == tmp_path / "run" / "user_state.yaml"
    assert written.is_file()
    # And every other location moved with it, which is the point.
    assert config.dataset_root == tmp_path / "run" / "datasets"
    assert config.identity_db_path == tmp_path / "run" / "identity.sqlite3"
    assert config.log_dir == tmp_path / "run" / "logs"


def test_a_temporary_dataset_root_cannot_reach_the_real_settings_file(
    tmp_path: Path, monkeypatch
) -> None:
    """The exact shape of the 20 September leak, refused."""
    real = tmp_path / "pretend_home" / "user_state.yaml"
    real.parent.mkdir(parents=True)
    real.write_text("dataset_root: C:\\\\kc15\\\\datasets\n", encoding="utf-8")
    before = _digest(real)
    monkeypatch.setattr(config_module, "USER_STATE_PATH", real)
    # `tmp_path` is itself under the system temp directory, so say plainly
    # which of the two sides this test treats as the user's permanent one.
    monkeypatch.setattr(
        config_module,
        "_is_sandbox_location",
        lambda path: path is not None and "scratchpad" in str(path).lower(),
    )

    # What the measurement script did: three locations moved, the fourth left
    # at its default - which is now `real`.
    leaky = AppConfig()
    leaky.dataset_root = tmp_path / "scratchpad" / "waste_home" / "datasets"

    with pytest.raises(ConfigError) as caught:
        save_user_state(leaky)

    assert "Geçici" in str(caught.value)
    assert _digest(real) == before, "the real preference file was written to"


def test_a_real_configuration_still_saves_normally(tmp_path: Path, monkeypatch) -> None:
    """The guard must not make the ordinary case impossible."""
    real = tmp_path / "pretend_home" / "user_state.yaml"
    monkeypatch.setattr(config_module, "USER_STATE_PATH", real)

    config = AppConfig()
    config.dataset_root = tmp_path / "pretend_data" / "datasets"
    # `tmp_path` is itself temporary, so state the case the guard is about:
    # a root the user chose, outside any sandbox marker.
    monkeypatch.setattr(config_module, "_is_sandbox_location", lambda _p: False)

    assert save_user_state(config) == real
    assert real.is_file()


def test_a_settings_file_cannot_redirect_where_settings_are_written(
    tmp_path: Path,
) -> None:
    """`user_state_path` is set by code, never read from a file."""
    state = tmp_path / "state.yaml"
    state.write_text(
        "user_state_path: C:\\\\somewhere\\\\else.yaml\ntheme: light\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path / "missing.yaml", user_state_path=state)

    assert config.theme == "light", "the rest of the file is still honoured"
    assert config.user_state_path == state


def test_the_gui_harness_never_touches_the_real_settings(tmp_path: Path) -> None:
    """The harness every GUI measurement uses is sandboxed by construction."""
    from kinecapture.core.config import USER_STATE_PATH

    config = AppConfig.sandboxed(tmp_path / "harness")
    assert config.is_sandboxed
    assert config.user_state_path != Path(USER_STATE_PATH)
