"""İşlenen Videolar: listing finished versions without opening any of them.

The rule this screen has to keep is that a row costs nothing. Opening a version
verifies a checksum over every file in it - the right price before annotating,
the wrong one per row while scrolling - so the list is built entirely from the
derived index and each run's own job file.

The second rule is that a version whose coverage did not verify is never listed
as ready, and the annotator is told before they start rather than after.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kinecapture.dataset.summary_index import (
    ProcessingRunSummary,
    TakeIndex,
    TakeSummary,
    build_index,
)
from kinecapture.studio.services.library import LibraryService, VersionRow
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.tasks import InlineRunner


def _version(**overrides) -> VersionRow:
    payload = {
        "take_id": "take_1",
        "run_id": "run_a",
        "participant_id": "P0001",
        "session_id": "ses_1",
        "started_at": "2026-09-13T10:00:00+00:00",
        "duration_s": 12.0,
        "directory": "/x/run_a",
        "take_directory": "/x",
        "frames": 300,
        "body_format": "zed_body_38",
        "subject_status": "associated",
    }
    payload.update(overrides)
    return VersionRow(**payload)


# ------------------------------------------------------------------- rules


def test_a_version_with_issues_is_not_ready() -> None:
    row = _version(issues=("source_frame_count_mismatch",))
    assert row.coverage_verified is False
    assert row.quality_status == "warning"


def test_coverage_is_offered_as_a_count_not_a_verdict() -> None:
    """521 of 524 is something an operator can weigh. "Doğrulanamadı" is not.

    Both 16 September takes matched over 99% of their frames and the screen had
    one sentence for it, the same sentence it would use for a recording that
    matched none.
    """
    row = _version(
        issues=("capture_frames_unmatched",), capture_frames=524, matched_frames=521
    )
    assert row.coverage_text == "521/524 kare eşleşti"
    assert row.quality_text == "521/524 kare eşleşti"
    row = _version(capture_frames=524, matched_frames=524)
    assert row.coverage_text == "524 kare eşleşti"
    assert row.quality_text == "hazır"


def test_a_version_without_a_chosen_subject_is_not_ready() -> None:
    row = _version(subject_status="needs_subject_selection")
    assert row.subject_chosen is False
    assert row.quality_text == "kişi seçilmedi"


def test_a_clean_version_is_ready() -> None:
    row = _version()
    assert row.coverage_verified and row.subject_chosen
    assert row.quality_text == "hazır"
    assert row.quality_status == "live"


@pytest.mark.parametrize(
    ("key", "row", "expected"),
    [
        ("ready", _version(), True),
        # A coverage note is something to read before annotating, not a reason
        # the version cannot be annotated - publishing it already decided that.
        ("ready", _version(issues=("x",)), True),
        ("ready", _version(subject_status="needs_subject_selection"), False),
        ("needs_subject", _version(subject_status="needs_subject_selection"), True),
        ("needs_subject", _version(), False),
        ("unverified", _version(issues=("x",)), True),
        ("unverified", _version(), False),
        ("annotated", _version(annotated=True), True),
        ("annotated", _version(), False),
        ("multi", _version(sibling_versions=2), True),
        ("multi", _version(), False),
        ("all", _version(issues=("x",)), True),
    ],
)
def test_filters(key: str, row: VersionRow, expected: bool) -> None:
    assert LibraryService.matches(row, key) is expected


def test_every_offered_filter_has_a_label() -> None:
    keys = {key for key, _label in LibraryService.FILTERS}
    assert keys == {"all", "ready", "needs_subject", "unverified", "annotated", "multi"}
    for _key, caption in LibraryService.FILTERS:
        assert caption.strip()


# ------------------------------------------------------------------ listing


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project with one take carrying two finished versions, and one partial."""
    root = tmp_path / "prj"
    take_dir = root / "participants/P0001/sessions/ses_1/takes/take_1"
    take_dir.mkdir(parents=True)
    (take_dir / "take.json").write_text(
        json.dumps(
            {
                "take_id": "take_1",
                "started_at": "2026-09-13T10:00:00+00:00",
                "state": "finalized",
                "processing_status": "awaiting_processing",
                "metrics": {"frames_written": 300, "duration_s": 10.0},
            }
        ),
        encoding="utf-8",
    )
    runs = {
        "run_a": {"state": "complete", "skeleton_format": "zed_body_38", "issues": []},
        "run_b": {"state": "complete", "skeleton_format": "zed_body_34", "issues": []},
        "run_c": {
            "state": "partial",
            "skeleton_format": "zed_body_38",
            "issues": ["source_frame_count_mismatch"],
        },
    }
    # An attempt still in staging. This is what "not a result" means now: the
    # folder is dot-prefixed because nothing renamed it, so no screen may list
    # it. A promoted run with recorded caveats is a different thing entirely.
    runs[".run_d.partial"] = {
        "state": "running",
        "skeleton_format": "zed_body_38",
        "issues": [],
    }
    for run_id, extra in runs.items():
        directory = take_dir / "derived" / "processing" / run_id
        directory.mkdir(parents=True)
        (directory / "job.json").write_text(
            json.dumps(
                {
                    "run_id": run_id.lstrip(".").removesuffix(".partial"),
                    "frames_processed": 300,
                    "subject_status": "associated",
                    "schema_version": "1.1.0",
                    "parameters": {"depth_mode": "NEURAL_PLUS", "body_fitting": True},
                    **extra,
                }
            ),
            encoding="utf-8",
        )
    return root


def test_only_published_versions_are_listed(project: Path) -> None:
    """A staged attempt is not a result; a published one with notes is.

    ``run_c`` carries ``source_frame_count_mismatch`` and is listed, with the
    caveat on its row. ``run_d`` never left its staging folder, so it is not.
    """
    index = build_index(project, force=True)
    rows = LibraryService().versions(index)
    assert {row.run_id for row in rows} == {"run_a", "run_b", "run_c"}
    caveated = next(row for row in rows if row.run_id == "run_c")
    assert caveated.coverage_verified is False


def test_sibling_count_shows_there_is_something_to_compare(project: Path) -> None:
    index = build_index(project, force=True)
    rows = LibraryService().versions(index)
    assert all(row.sibling_versions == 3 for row in rows)


def test_parameters_come_from_the_version_itself(project: Path) -> None:
    index = build_index(project, force=True)
    rows = LibraryService().versions(index)
    parameters = LibraryService.parameters_of(rows[0])
    assert parameters["depth_mode"] == "NEURAL_PLUS"
    assert parameters["schema_version"] == "1.1.0"


def test_an_existing_sidecar_marks_a_version_as_annotated(project: Path) -> None:
    sidecar = project / "participants/P0001/sessions/ses_1/takes/take_1/annotations/processing"
    sidecar.mkdir(parents=True)
    (sidecar / "run_a.json").write_text("{}", encoding="utf-8")
    index = build_index(project, force=True)
    rows = {row.run_id: row for row in LibraryService().versions(index)}
    assert rows["run_a"].annotated is True
    assert rows["run_b"].annotated is False


def test_a_missing_thumbnail_is_not_an_error(project: Path) -> None:
    index = build_index(project, force=True)
    row = LibraryService().versions(index)[0]
    assert row.has_thumbnails is False
    assert row.thumbnail() is None


# ---------------------------------------------------------------- viewmodel


class _Session:
    """The smallest thing the library viewmodel needs from a session."""

    def __init__(self, root: Path) -> None:
        self.workspace = type("W", (), {"root": root})()


@pytest.fixture
def library(project: Path) -> LibraryViewModel:
    return LibraryViewModel(_Session(project), runner=InlineRunner())


def test_reload_lists_the_published_versions(library: LibraryViewModel) -> None:
    library.reload(force=True)
    assert len(library.rows.value) == 3
    assert "3 sürüm gösteriliyor" in library.summary.value


def test_the_summary_names_what_is_unresolved(library: LibraryViewModel) -> None:
    library.reload(force=True)
    # Every version here has a subject, so that phrase must be absent rather
    # than shown with a zero.
    assert "kişi seçilmemiş" not in library.summary.value
    assert "etiketlemeye hazır" in library.summary.value


def test_filtering_does_not_re_read_the_project(
    library: LibraryViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    library.reload(force=True)
    calls: list[int] = []
    monkeypatch.setattr(
        library._service, "refresh_index", lambda *_a, **_k: calls.append(1)
    )
    library.set_filter("multi")
    library.set_filter("all")
    assert calls == []
    assert len(library.rows.value) == 3


def test_selecting_shows_the_other_versions_of_the_same_take(
    library: LibraryViewModel,
) -> None:
    library.reload(force=True)
    library.select(library.rows.value[0])
    assert {row.run_id for row in library.comparison.value} == {
        "run_a",
        "run_b",
        "run_c",
    }


def test_clearing_the_selection_clears_the_comparison(library: LibraryViewModel) -> None:
    library.reload(force=True)
    library.select(library.rows.value[0])
    library.select(None)
    assert library.comparison.value == ()


def test_labelling_hands_the_version_on(library: LibraryViewModel) -> None:
    library.reload(force=True)
    opened: list[VersionRow] = []
    library.open_for_review.subscribe(opened.append)
    library.select(library.rows.value[0])
    assert library.label()
    assert opened and opened[0].run_id == library.rows.value[0].run_id


def test_labelling_an_unverified_version_warns_first(project: Path) -> None:
    """Allowed, but never silently: an hour of work deserves the warning."""
    job = project / "participants/P0001/sessions/ses_1/takes/take_1/derived/processing/run_a/job.json"
    payload = json.loads(job.read_text(encoding="utf-8"))
    payload["issues"] = ["capture_frames_unmatched"]
    job.write_text(json.dumps(payload), encoding="utf-8")

    library = LibraryViewModel(_Session(project), runner=InlineRunner())
    library.reload(force=True)
    row = next(r for r in library.rows.value if r.run_id == "run_a")
    seen = []
    library.message.subscribe(seen.append)
    library.select(row)
    assert library.label()
    assert seen and seen[0].code == "coverage_unverified"
    assert "eksiksiz sayılmaz" in seen[0].detail


def test_labelling_nothing_selected_does_nothing(library: LibraryViewModel) -> None:
    library.reload(force=True)
    assert library.label() is False


def test_without_a_project_the_screen_says_so() -> None:
    class _Empty:
        workspace = None

    library = LibraryViewModel(_Empty(), runner=InlineRunner())
    library.reload()
    assert library.rows.value == ()
    assert "proje" in library.summary.value.casefold()


def test_an_empty_project_says_there_is_nothing_yet(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    (root / "participants").mkdir(parents=True)
    library = LibraryViewModel(_Session(root), runner=InlineRunner())
    library.reload(force=True)
    assert library.rows.value == ()
    assert "henüz" in library.summary.value.casefold()


def test_a_failing_scan_leaves_the_screen_usable(project: Path) -> None:
    class FailingRunner:
        def run(self, work, on_done, on_error=None):  # noqa: ANN001
            on_error(OSError("disk okunamadı"))

    library = LibraryViewModel(_Session(project), runner=FailingRunner())
    seen = []
    library.message.subscribe(seen.append)
    library.reload()
    assert library.busy.value is False
    assert seen and seen[0].severity.value == "error"
