"""İşlenen Videolar: the balance, the grouping, and the two sizes.

The size rules are the ones worth defending. A raw recording belongs to the
*take*; adding it to each version would treble a 2 GB SVO for a take processed
three ways, and a release built on that total would be planned against a
number nobody can reconcile. An unmeasured size is "—", never "0 B".
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.formatting import MISSING, file_size  # noqa: E402
from kinecapture.studio.services.library import LibraryService, VersionRow  # noqa: E402

from conftest import show_page_directly  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    window = build_window(config, state_path=tmp_path / "window.json")
    window.resize(1600, 900)
    window.show()
    assert window.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    # Shown directly: this file is about how the screen renders, not about
    # the project gate in front of it.
    show_page_directly(window, "library", app)
    yield window.page("library"), window, app
    window.close()


def version(
    take: str, run: str, *, ordinal: int = 1, siblings: int = 1, created: str = "a"
) -> VersionRow:
    return VersionRow(
        take_id=take,
        run_id=run,
        participant_id="P0001",
        session_id="ses_1",
        started_at="2026-09-18T10:00:00+00:00",
        duration_s=12.0,
        directory=f"/tmp/{take}/{run}",
        take_directory=f"/tmp/{take}",
        frames=720,
        body_format="zed_body_38",
        schema_version="1.1.0",
        subject_status="associated",
        created_at=created,
        sibling_versions=siblings,
        version_ordinal=ordinal,
    )


# ------------------------------------------------------------------- LIB-01


def test_the_starting_split_is_about_fifty_five_forty_five(page) -> None:
    view, _window, app = page
    app.processEvents()
    sizes = view.splitter.sizes()
    total = sum(sizes)
    assert total > 0
    assert 0.50 <= sizes[0] / total <= 0.60, sizes


def test_versions_of_one_take_are_kept_together(page) -> None:
    """Grouping is a reordering. Every version stays its own row."""
    rows = [
        version("take_a", "run_a1", created="1"),
        version("take_b", "run_b1", created="2"),
        version("take_a", "run_a2", created="3"),
        version("take_b", "run_b2", created="4"),
    ]
    grouped = LibraryService.grouped(rows)
    assert len(grouped) == 4
    takes = [row.take_id for row in grouped]
    # Each take appears as one contiguous run.
    assert takes == ["take_a", "take_a", "take_b", "take_b"]
    # Newest first inside the group.
    assert [r.run_id for r in grouped[:2]] == ["run_a2", "run_a1"]


def test_grouping_keeps_the_takes_in_the_order_they_arrived(page) -> None:
    rows = [version("take_z", "run_z"), version("take_a", "run_a")]
    assert [r.take_id for r in LibraryService.grouped(rows)] == ["take_z", "take_a"]


def test_a_version_says_which_of_how_many_it_is(page) -> None:
    view, _window, app = page
    rows = (
        version("take_a", "run_a2", ordinal=2, siblings=2),
        version("take_a", "run_a1", ordinal=1, siblings=2),
        version("take_b", "run_b1"),
    )
    view.model.set_rows(rows)
    app.processEvents()
    column = [c.key for c in view.model.columns].index("versions")
    texts = [
        view.model.data(view.model.index(row, column))
        for row in range(view.model.rowCount())
    ]
    assert texts == ["2 / 2", "1 / 2", "tek"]


def test_every_version_is_still_selectable_on_its_own(page) -> None:
    view, _window, app = page
    rows = (
        version("take_a", "run_a2", ordinal=2, siblings=2),
        version("take_a", "run_a1", ordinal=1, siblings=2),
    )
    view.model.set_rows(rows)
    app.processEvents()
    view.view.selectRow(1)
    app.processEvents()
    assert view.label_button.isEnabled()


# ------------------------------------------------------------------- LIB-02


def test_an_unknown_size_is_not_shown_as_zero() -> None:
    assert file_size(None) == MISSING
    assert file_size(0) == "0 B"


def test_sizes_read_in_the_unit_a_person_says_them_in() -> None:
    assert file_size(512) == "512 B"
    assert file_size(1_500) == "1.5 KB"
    assert file_size(2_700_000_000) == "2.7 GB"
    # Three digits of decimals is noise.
    assert file_size(847_300_000) == "847 MB"


def test_the_raw_recording_is_measured_once_per_take_not_per_version(
    tmp_path,
) -> None:
    """The bug this rules out: a 2 GB SVO counted three times."""
    take_dir = tmp_path / "take_a"
    raw = take_dir / "raw"
    raw.mkdir(parents=True)
    (raw / "capture.svo2").write_bytes(b"x" * 4000)
    rows = []
    for index in (1, 2, 3):
        directory = take_dir / "derived" / "processing" / f"run_{index}"
        directory.mkdir(parents=True)
        (directory / "arrays.npz").write_bytes(b"y" * 1000)
        rows.append(
            VersionRow(
                take_id="take_a",
                run_id=f"run_{index}",
                participant_id="P0001",
                session_id="ses",
                started_at="",
                duration_s=1.0,
                directory=str(directory),
                take_directory=str(take_dir),
            )
        )
    measured = [LibraryService.sizes_for(row) for row in rows]
    assert [derived for derived, _raw in measured] == [1000, 1000, 1000]
    assert [raw_bytes for _d, raw_bytes in measured] == [4000, 4000, 4000]
    # Derived total is three versions' worth; the raw file is one file.
    assert sum(d for d, _r in measured) == 3000


def test_an_unreadable_folder_measures_as_unknown(tmp_path) -> None:
    assert LibraryService.directory_size(tmp_path / "nope") is None


def test_the_panel_says_both_sizes_and_keeps_them_apart(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["library"]
    row = version("take_a", "run_a1")
    view.model.set_rows((row,))
    app.processEvents()
    viewmodel._size_cache[row.run_id] = (1_000_000, 2_000_000_000)
    viewmodel.select(row)
    app.processEvents()
    text = view.detail_lines.text()
    assert "sürüm boyutu" in text
    assert "ham kayıt" in text
    assert file_size(1_000_000) in text
    assert file_size(2_000_000_000) in text


def test_a_late_measurement_does_not_land_on_a_newer_selection(page) -> None:
    """A→B while A is still being walked. B's panel keeps B's numbers."""
    view, window, app = page
    viewmodel = window.viewmodel_for["library"]
    first = version("take_a", "run_a1")
    second = version("take_b", "run_b1")

    held: list = []

    class _HoldingRunner:
        def run(self, work, done, failed=None):  # noqa: ANN001
            held.append((work, done))

        def wait(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return True

    viewmodel._runner = _HoldingRunner()
    viewmodel.select(first)
    viewmodel.select(second)
    app.processEvents()
    # The first job now finishes, late.
    work, done = held[0]
    done((111, 222))
    app.processEvents()
    run_id, derived, raw = viewmodel.selected_sizes.value
    assert run_id == second.run_id
    assert (derived, raw) != (111, 222)
    # And the answer is not thrown away - it is there if A is chosen again.
    assert viewmodel._size_cache[first.run_id] == (111, 222)


def test_while_measuring_the_panel_says_so_rather_than_lying(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["library"]

    class _HoldingRunner:
        def run(self, work, done, failed=None):  # noqa: ANN001
            pass

        def wait(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return True

    viewmodel._runner = _HoldingRunner()
    row = version("take_a", "run_a1")
    view.model.set_rows((row,))
    app.processEvents()
    viewmodel.select(row)
    app.processEvents()
    # Nothing measured yet and nothing invented.
    assert "0 B" not in view.detail_lines.text()


def test_findings_are_a_summary_plus_a_fold(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["library"]
    row = version("take_a", "run_a1")
    row = VersionRow(**{**row.__dict__, "issues": (
        "capture_frames_unmatched", "source_timestamp_gap",
    )})
    view.model.set_rows((row,))
    app.processEvents()
    viewmodel.select(row)
    app.processEvents()
    assert view.issues_row_holder.isVisibleTo(view)
    assert "2 bulgu" in view.detail_issue_summary.text()
    assert not view.detail_issues.isVisibleTo(view)
    view.detail_issue_button.setChecked(True)
    app.processEvents()
    assert view.detail_issues.isVisibleTo(view)
    # Nothing is lost by folding: both findings are in the fold.
    assert len(view.detail_issues.text().splitlines()) == 2


def test_a_clean_version_shows_no_findings_row(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["library"]
    row = version("take_a", "run_a1")
    view.model.set_rows((row,))
    app.processEvents()
    viewmodel.select(row)
    app.processEvents()
    assert not view.issues_row_holder.isVisibleTo(view)


def test_nothing_on_this_screen_decodes_video(page) -> None:
    """LIB-02: static stills and cached metadata, never a player per row."""
    import inspect

    from kinecapture.studio.views.pages import library as module

    source = inspect.getsource(module)
    for banned in ("VideoCapture", "QMediaPlayer", "open_video", "read_at"):
        assert banned not in source, banned
