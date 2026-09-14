"""The athlete panel, against a recording that really has two people in it.

What matters here is that the screen offers a choice and never makes one. A
version with an open question must look unfinished, and the only way to close
it must be a person clicking one of three buttons.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.processing.subject_review import (  # noqa: E402
    Verdict,
    load_subject_review,
)
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.review import ReviewSession  # noqa: E402
from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.viewmodels.subject import SubjectViewModel  # noqa: E402
from kinecapture.studio.views.subject import CandidateCard, SubjectPanel  # noqa: E402

FRAMES = 30


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _record_two_people(workspace, session, *, anchor: bool) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(
        width=160, height=120, fps=30, seed=5, num_bodies=2, profile=profile
    )
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
    if anchor:
        source = SyntheticSource(paths, take, config.profile(take))
        packet = next(iter(source))
        points = packet.bodies[0].joint_positions_2d
        write_json(paths.raw_dir / "subject_anchors.json", [{
            "camera_timestamp_ns": packet.camera_timestamp_ns,
            "source_resolution": list(packet.resolution),
            "point_xy": np.nanmean(points, axis=0).tolist(),
            "bbox_xyxy": np.r_[
                np.nanmin(points, axis=0), np.nanmax(points, axis=0)
            ].tolist(),
        }])
        source.close()
    return process_take(paths.root, config)


@pytest.fixture
def crowded(workspace, session) -> Path:
    """Two people in frame, with the athlete marked at capture time."""
    return _record_two_people(workspace, session, anchor=True)


@pytest.fixture
def unanchored(workspace, session) -> Path:
    """Two people and nobody marked - the tracker never locked onto anyone."""
    return _record_two_people(workspace, session, anchor=False)


@pytest.fixture
def opened(crowded: Path):
    review = ReviewSession.open(crowded)
    yield review
    review.close()


@pytest.fixture
def viewmodel(opened) -> SubjectViewModel:
    model = SubjectViewModel()
    model.open(opened, annotator="koc")
    return model


def test_every_person_in_the_recording_is_offered(viewmodel) -> None:
    rows = viewmodel.candidates.value
    assert len(rows) >= 2, "iki kişilik kayıtta iki aday bekleniyor"
    # Numbered for the reader; the tracker id stays a technical detail.
    assert [r.title for r in rows[:2]] == ["Kişi 1", "Kişi 2"]
    assert all(r.seconds_visible > 0 for r in rows)


def test_no_athlete_is_chosen_for_the_user(viewmodel) -> None:
    assert viewmodel.chosen.value == -1
    assert not viewmodel.settled.value
    assert "seçilmedi" in viewmodel.progress.value.lower()
    assert not any(r.is_chosen for r in viewmodel.candidates.value)


def test_a_version_nobody_was_locked_onto_cannot_be_rescued_here(
    unanchored: Path,
) -> None:
    """Its arrays are entirely NaN; only reprocessing can fix that, and the
    screen has to say so instead of offering a choice that changes nothing."""
    review = ReviewSession.open(unanchored)
    try:
        assert not review.has_subject_data
        model = SubjectViewModel()
        model.open(review, annotator="koc")
        assert model.blocker.value
        assert "yeniden işleyin" in model.blocker.value
        # Choosing is still allowed - it records who it should have been -
        # but it does not make the version exportable.
        assert model.choose(model.candidates.value[0].tracker_id)
        assert not model.settled.value
    finally:
        review.close()


def test_choosing_marks_exactly_one_candidate(viewmodel) -> None:
    first = viewmodel.candidates.value[0]
    assert viewmodel.choose(first.tracker_id)
    rows = viewmodel.candidates.value
    assert sum(1 for r in rows if r.is_chosen) == 1
    assert viewmodel.chosen.value == first.tracker_id


def test_an_unanswered_question_keeps_the_version_unexportable(viewmodel) -> None:
    viewmodel.choose(viewmodel.candidates.value[0].tracker_id)
    if not viewmodel.questions.value:
        # Nothing was ambiguous, so there is nothing left to answer.
        assert viewmodel.settled.value
        return
    assert not viewmodel.settled.value
    for row in viewmodel.questions.value:
        assert row.verdict is Verdict.UNANSWERED


def test_answers_survive_save_and_reload(viewmodel, opened) -> None:
    chosen = viewmodel.candidates.value[0].tracker_id
    viewmodel.choose(chosen)
    for row in viewmodel.questions.value:
        viewmodel.answer(row.interval_id, Verdict.NO_ATHLETE)
    viewmodel.flush()

    document = load_subject_review(
        opened.take_dir, opened.run_id, opened.source_fingerprint
    )
    assert document.athlete_tracker_id == chosen
    assert document.is_settled
    for decision in document.decisions:
        assert decision.verdict is Verdict.NO_ATHLETE
        assert decision.decided_at and decision.annotator == "koc"


def test_the_panel_renders_a_card_per_person(qapp, viewmodel, opened) -> None:
    panel = SubjectPanel(load_tokens("dark"))
    panel.set_context(opened.frame, viewmodel.candidate_title, opened.fps)
    try:
        panel.show_candidates(viewmodel.candidates.value)
        cards = panel.findChildren(CandidateCard)
        assert len(cards) == len(viewmodel.candidates.value)
        assert cards[0].button.isEnabled()  # nothing chosen yet

        chosen = []
        cards[0].chosen.connect(chosen.append)
        cards[0].button.click()
        assert chosen == [cards[0].row.tracker_id]
    finally:
        panel.deleteLater()


def test_the_panel_says_the_version_cannot_be_exported_yet(qapp, viewmodel, opened) -> None:
    panel = SubjectPanel(load_tokens("dark"))
    panel.set_context(opened.frame, viewmodel.candidate_title, opened.fps)
    try:
        panel.set_status(viewmodel.progress.value, viewmodel.settled.value)
        assert panel.status.text()
        assert panel.status.property("kcStatus") == "warning"
    finally:
        panel.deleteLater()


def test_a_question_offers_three_answers_and_no_default(qapp, viewmodel, opened) -> None:
    if not viewmodel.questions.value:
        pytest.skip("bu kayıtta belirsiz aralık yok")
    panel = SubjectPanel(load_tokens("dark"))
    panel.set_context(opened.frame, viewmodel.candidate_title, opened.fps)
    try:
        panel.show_questions(viewmodel.questions.value)
        from kinecapture.studio.views.subject import QuestionRowWidget

        rows = panel.findChildren(QuestionRowWidget)
        assert rows
        buttons = [b.text() for b in rows[0].findChildren(type(rows[0].other))]
        assert any("Aynı sporcu" in t for t in buttons)
        assert any("Diğer kişi" in t for t in buttons)
        assert any("Sporcu yok" in t for t in buttons)
    finally:
        panel.deleteLater()


def test_bodies_the_tracker_never_saw_are_not_offered_as_answers(viewmodel) -> None:
    """"Diğer kişi" may only name someone actually visible in that stretch."""
    known = {c.tracker_id for c in viewmodel.candidates.value}
    for row in viewmodel.questions.value:
        assert set(row.visible) <= known
