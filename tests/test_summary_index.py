"""The project take index: cheap listing, and never the authority.

The rule this file protects is that the cache can be deleted, corrupted or
simply absent and nothing is lost. Every answer it gives is recomputed from
``take.json`` and ``job.json``, which are the real records.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from kinecapture.dataset.summary_index import (
    TAKE_INDEX_SCHEMA_VERSION,
    TakeIndex,
    build_index,
)


def _take(
    root: Path,
    participant: str,
    session: str,
    take_id: str,
    *,
    processing_status: str = "awaiting_processing",
    runs: tuple[tuple[str, str], ...] = (),
) -> Path:
    directory = root / "participants" / participant / "sessions" / session / "takes" / take_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "take.json").write_text(
        json.dumps(
            {
                "take_id": take_id,
                "started_at": f"2026-09-13T10:00:00+00:00",
                "state": "finalized",
                "processing_status": processing_status,
                "origin": "synthetic",
                "quality": "good",
                "metrics": {"frames_written": 300, "duration_s": 10.0},
            }
        ),
        encoding="utf-8",
    )
    for run_id, state in runs:
        run_dir = directory / "derived" / "processing" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "job.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "state": state,
                    "frames_processed": 300,
                    "issues": [] if state == "complete" else ["source_frame_count_mismatch"],
                    "subject_status": "associated",
                    "skeleton_format": "zed_body_38",
                    "schema_version": "1.1.0",
                }
            ),
            encoding="utf-8",
        )
    return directory


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "prj_demo"
    (root / "participants").mkdir(parents=True)
    _take(root, "P0001", "ses_a", "take_001", runs=(("run_a", "complete"),))
    _take(root, "P0001", "ses_a", "take_002")
    _take(root, "P0002", "ses_b", "take_003", processing_status="live")
    _take(
        root,
        "P0002",
        "ses_b",
        "take_004",
        runs=(("run_b", "partial"), ("run_c", "complete")),
    )
    return root


def test_index_finds_every_take(project: Path) -> None:
    index = build_index(project, force=True)
    assert len(index) == 4
    assert {take.take_id for take in index} == {
        "take_001",
        "take_002",
        "take_003",
        "take_004",
    }


def test_index_reads_participant_and_session_from_the_path(project: Path) -> None:
    index = build_index(project, force=True)
    take = index.by_id("take_003")
    assert take is not None
    assert take.participant_id == "P0002"
    assert take.session_id == "ses_b"


def test_partial_runs_are_listed_but_not_counted_as_results(project: Path) -> None:
    index = build_index(project, force=True)
    take = index.by_id("take_004")
    assert take is not None
    assert len(take.runs) == 2
    assert [run.run_id for run in take.complete_runs] == ["run_c"]
    assert take.latest_complete_run.run_id == "run_c"


def test_takes_awaiting_processing_are_the_ones_with_no_result(project: Path) -> None:
    index = build_index(project, force=True)
    waiting = {take.take_id for take in index.awaiting_processing()}
    assert waiting == {"take_002"}


def test_pre_policy_takes_are_marked_not_hidden(project: Path) -> None:
    """Old recordings stay listed and stay on disk; they are simply labelled."""
    index = build_index(project, force=True)
    legacy = index.legacy_takes()
    assert [take.take_id for take in legacy] == ["take_003"]
    assert index.by_id("take_003") is not None


def test_complete_runs_lists_every_finished_version(project: Path) -> None:
    index = build_index(project, force=True)
    pairs = index.complete_runs()
    assert [(take.take_id, run.run_id) for take, run in pairs] == [
        ("take_001", "run_a"),
        ("take_004", "run_c"),
    ]


# ------------------------------------------------------------------- caching


def test_second_refresh_rereads_nothing(project: Path) -> None:
    build_index(project, force=True)
    again = build_index(project)
    assert len(again) == 4
    assert again.rescanned == 0
    assert again.scanned_directories == 4


def test_a_changed_take_is_rereard_and_the_rest_are_not(project: Path) -> None:
    build_index(project, force=True)
    run_dir = project / "participants/P0001/sessions/ses_a/takes/take_002/derived/processing/run_new"
    run_dir.mkdir(parents=True)
    (run_dir / "job.json").write_text(
        json.dumps({"run_id": "run_new", "state": "complete", "frames_processed": 12}),
        encoding="utf-8",
    )
    # Directory mtimes have coarse resolution on some file systems; make the
    # change unambiguous rather than depending on the clock.
    os.utime(run_dir.parent, (time.time() + 5, time.time() + 5))

    refreshed = build_index(project)
    assert refreshed.rescanned == 1
    assert refreshed.by_id("take_002").latest_complete_run.run_id == "run_new"


def test_a_missing_cache_is_not_an_error(project: Path) -> None:
    index = build_index(project, force=True)
    index.cache_file.unlink()
    rebuilt = build_index(project)
    assert len(rebuilt) == 4
    assert rebuilt.rescanned == 4


def test_a_corrupt_cache_is_rebuilt_silently(project: Path) -> None:
    """A cache that cannot be parsed must never stop the project from opening."""
    index = build_index(project, force=True)
    index.cache_file.write_text("{ not json", encoding="utf-8")
    rebuilt = build_index(project)
    assert len(rebuilt) == 4


def test_a_cache_from_another_schema_version_is_ignored(project: Path) -> None:
    index = build_index(project, force=True)
    payload = json.loads(index.cache_file.read_text(encoding="utf-8"))
    payload["schema_version"] = "0.9.0"
    index.cache_file.write_text(json.dumps(payload), encoding="utf-8")
    rebuilt = build_index(project)
    assert len(rebuilt) == 4
    assert rebuilt.rescanned == 4


def test_cache_is_written_atomically_and_declares_itself_derived(project: Path) -> None:
    index = build_index(project, force=True)
    payload = json.loads(index.cache_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == TAKE_INDEX_SCHEMA_VERSION
    assert "Türetilmiş" in payload["note"]
    assert not list(index.cache_file.parent.glob("*.tmp"))


def test_an_unreadable_take_does_not_hide_the_others(project: Path) -> None:
    broken = project / "participants/P0001/sessions/ses_a/takes/take_002/take.json"
    broken.write_text("{ truncated", encoding="utf-8")
    index = build_index(project, force=True)
    assert len(index) == 3
    assert index.by_id("take_002") is None


def test_an_unreadable_job_does_not_hide_its_take(project: Path) -> None:
    job = project / "participants/P0001/sessions/ses_a/takes/take_001/derived/processing/run_a/job.json"
    job.write_text("{ truncated", encoding="utf-8")
    index = build_index(project, force=True)
    take = index.by_id("take_001")
    assert take is not None
    assert take.runs == ()


def test_an_empty_project_produces_an_empty_index(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    (root / "participants").mkdir(parents=True)
    index = build_index(root, force=True)
    assert len(index) == 0
    assert index.sorted_takes() == []


def test_index_can_be_built_without_writing_a_cache(project: Path) -> None:
    index = build_index(project, force=True, save=False)
    assert len(index) == 4
    assert not index.cache_file.exists()


def test_load_of_a_project_that_was_never_indexed_is_empty(project: Path) -> None:
    assert len(TakeIndex.load(project)) == 0
