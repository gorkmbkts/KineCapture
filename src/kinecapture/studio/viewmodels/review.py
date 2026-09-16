"""The labelling screen's state.

Everything the annotator does passes through here, and two rules govern all of
it.

**A label is never invented.** No class is guessed, no interval is nudged onto
a nearby frame, no verdict is inferred from silence. Where something is
missing, the screen says which thing and which movement, and the export stays
shut until a person supplies it.

**Everything is one frame.** Video, overlay and timeline are driven from a
single position, and that position is the version's own frame index - the
thing the source map and the arrays are both indexed by. There is no second
clock to drift against.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.domain.labels import LabelSchema
from kinecapture.processing.annotations import (
    Correctness,
    ErrorInterval,
    JointStatus,
    MovementSample,
    Readiness,
)
from kinecapture.studio.services.annotation_store import AnnotationStore
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.review import ReviewSession
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

logger = logging.getLogger(__name__)

READINESS_TEXT = {
    Readiness.READY: "hazır",
    Readiness.UNREVIEWED: "onay bekliyor",
    Readiness.NO_EXERCISE: "hareket sınıfı yok",
    Readiness.UNCLASSIFIED_ERROR: "sınıfsız hata aralığı",
    Readiness.INVALID_INTERVAL: "geçersiz aralık",
}

READINESS_STATUS = {
    Readiness.READY: "ready",
    Readiness.UNREVIEWED: "warning",
    Readiness.NO_EXERCISE: "warning",
    Readiness.UNCLASSIFIED_ERROR: "error",
    Readiness.INVALID_INTERVAL: "error",
}


@dataclass(frozen=True)
class MovementRow:
    """One movement, formatted for the list and the timeline."""

    sample_id: str
    start: int
    end: int
    exercise: str
    exercise_label: str
    readiness: Readiness
    correctness: Correctness
    error_count: int
    unclassified_errors: int
    excluded: bool
    #: The class's position in the project vocabulary, which is what gives it
    #: a colour. ``-1`` when no class has been chosen. Stable across sessions
    #: because the vocabulary order is stored with the project.
    colour_index: int = -1

    @property
    def code(self) -> str:
        """A short form for a box too narrow for the full class name."""
        return self.exercise.upper()[:4]

    @property
    def status(self) -> str:
        return "neutral" if self.excluded else READINESS_STATUS[self.readiness]

    @property
    def text(self) -> str:
        if self.excluded:
            return f"{self.exercise_label or 'hareket'} · dışlandı"
        if not self.exercise_label:
            return "sınıf yok"
        if self.correctness is Correctness.INCORRECT:
            return f"{self.exercise_label} · hatalı"
        if self.correctness is Correctness.CORRECT:
            return f"{self.exercise_label} · doğru"
        return self.exercise_label


@dataclass(frozen=True)
class ErrorRow:
    interval_id: str
    sample_id: str
    start: int
    end: int
    error_class: str
    error_label: str
    joint_status: JointStatus
    roles: tuple[str, ...]
    colour_index: int = -1

    @property
    def code(self) -> str:
        return self.error_class.upper()[:4]

    @property
    def status(self) -> str:
        return "warning" if self.error_class else "error"

    @property
    def text(self) -> str:
        return self.error_label or "sınıf seçin"


class ReviewViewModel:
    """Opens one processing version and lets a person label it."""

    def __init__(
        self,
        session: SessionService,
        runner: Optional[TaskRunner] = None,
    ) -> None:
        self._session = session
        self._runner: TaskRunner = runner or InlineRunner()
        self.review: Optional[ReviewSession] = None
        self.store: Optional[AnnotationStore] = None
        self._schema: LabelSchema = LabelSchema.default()

        self.position: Observable[int] = Observable(0, name="position")
        self.frames: Observable[int] = Observable(0, name="frames")
        self.fps: Observable[float] = Observable(30.0, name="fps")
        self.movements: Observable[tuple[MovementRow, ...]] = Observable((), name="movements")
        self.errors: Observable[tuple[ErrorRow, ...]] = Observable((), name="errors")
        self.selected_movement: Observable[str] = Observable("", name="selected_movement")
        self.selected_error: Observable[str] = Observable("", name="selected_error")
        self.playing: Observable[bool] = Observable(False, name="playing")
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.title: Observable[str] = Observable("", name="title")
        self.progress: Observable[str] = Observable("", name="progress")
        self.can_undo: Observable[bool] = Observable(False, name="can_undo")
        self.can_redo: Observable[bool] = Observable(False, name="can_redo")
        #: True while a decision is in memory but not yet on disk.
        self.dirty: Observable[bool] = Observable(False, name="dirty")
        self.exercise_options: Observable[tuple[tuple[str, str], ...]] = Observable(
            (), name="exercises"
        )
        self.error_options: Observable[tuple[tuple[str, str], ...]] = Observable(
            (), name="error_classes"
        )
        self.message: Event[Message] = Event()
        self.frame_changed: Event[int] = Event()
        #: Fired once the version is really loaded, carrying its directory.
        #: Everything a screen has to prepare hangs off this, never off a
        #: timer: the load runs on a worker thread and a ``singleShot(0)``
        #: fires long before it has finished.
        self.opened: Event[str] = Event()
        #: Fired when the load failed, carrying the directory that failed, so
        #: the screen can offer to try again instead of looking empty.
        self.open_failed: Event[str] = Event()
        self.open_error: Observable[str] = Observable("", name="open_error")

        #: Which version this viewmodel is showing (or trying to).
        self._directory = ""
        #: Bumped on every open and on close. A result carrying an old token
        #: belongs to a version the user has already navigated away from and is
        #: dropped rather than allowed to overwrite the current one.
        self._open_token = 0

    @property
    def directory(self) -> str:
        """The version currently open, or being opened. Empty when none."""
        return self._directory

    @property
    def is_open(self) -> bool:
        return self.review is not None

    # ------------------------------------------------------------------ open
    def open_version(self, directory: str) -> None:
        """Load a version and its labels. Anything already open is flushed first."""
        self.close()
        self._open_token += 1
        token = self._open_token
        self._directory = str(directory)
        self.open_error.set("")
        self.busy.set(True)

        def work() -> ReviewSession:
            return ReviewSession.open(directory)

        def done(review: ReviewSession) -> None:
            if token != self._open_token:
                # A later open (or a close) won the race. Release what this one
                # produced instead of showing B's screen filled with A's data.
                try:
                    review.close()
                except Exception:  # noqa: BLE001 - discarding, never reported
                    logger.debug("Geçersiz açılış sonucu kapatılamadı", exc_info=True)
                return
            self.busy.set(False)
            self._attach(review)
            self.opened.emit(self._directory)

        def failed(exc: BaseException) -> None:
            if token != self._open_token:
                return
            self.busy.set(False)
            self.open_error.set(str(exc) or "Sürüm açılamadı.")
            self.message.emit(from_error(exc, headline="Sürüm açılamadı."))
            self.open_failed.emit(self._directory)

        self._runner.run(work, done, failed)

    def retry_open(self) -> bool:
        """Try the last requested version again. Used by the error state."""
        if not self._directory:
            return False
        self.open_version(self._directory)
        return True

    def _attach(self, review: ReviewSession) -> None:
        self.review = review
        workspace = self._session.workspace
        self._schema = workspace.label_schema if workspace is not None else LabelSchema.default()
        try:
            document = review.dataset.load_annotations()
        except KineCaptureError as exc:
            # A sidecar that belongs to another source is refused, not merged.
            self.message.emit(from_error(exc, headline="Etiketler açılamadı."))
            document = review.empty_document()

        self.store = AnnotationStore(
            take_dir=review.take_dir,
            document=document,
            annotator=self._session.user.display_name if self._session.user else "",
            resolve=review.dataset.position_of_anchor,
            anchor_at=review.dataset.anchor_at,
            frames=review.frames,
            known_exercises=self._schema.exercise_codes(),
            known_error_classes=self._schema.error_type_codes(),
        )
        self.store.subscribe(self._refresh)
        self.frames.set(review.frames)
        self.fps.set(review.fps)
        self.title.set(f"{review.run_id} · {review.frames} kare")
        self._refresh_options()
        self.position.set(0)
        self.frame_changed.emit(0)
        self._refresh()

    def close(self) -> None:
        """Flush labels and release the version. Called before every switch."""
        if self.store is not None:
            try:
                self.store.flush()
            except (KineCaptureError, OSError) as exc:
                self.message.emit(from_error(exc, headline="Etiketler kaydedilemedi."))
        if self.review is not None:
            self.review.close()
        # Any open still in flight belongs to the version being left behind.
        self._open_token += 1
        self.review = None
        self.store = None
        self.movements.force(())
        self.errors.force(())
        self.selected_movement.set("")
        self.selected_error.set("")
        self.playing.set(False)
        self.busy.set(False)
        # The frame count is what every screen uses to decide whether there is
        # anything to edit, so it has to go back to zero with the data.
        self.frames.set(0)
        self.position.set(0)
        self.title.set("")
        self.progress.set("")
        self.can_undo.set(False)
        self.can_redo.set(False)
        self.dirty.set(False)

    # ------------------------------------------------------------- transport
    def seek(self, position: int) -> None:
        if self.review is None:
            return
        clamped = max(0, min(self.frames.value - 1, int(position)))
        if self.position.set(clamped):
            self.frame_changed.emit(clamped)

    def step(self, delta: int) -> None:
        self.seek(self.position.value + delta)

    def toggle_play(self) -> bool:
        self.playing.set(not self.playing.value)
        return self.playing.value

    def advance(self) -> None:
        """One playback tick. Stops at the end rather than wrapping."""
        if not self.playing.value:
            return
        nxt = self.position.value + 1
        if nxt >= self.frames.value:
            self.playing.set(False)
            return
        self.seek(nxt)

    # -------------------------------------------------------------- frame data
    def frame_image(self, position: Optional[int] = None):  # noqa: ANN201
        if self.review is None:
            return None
        return self.review.frame(position if position is not None else self.position.value)

    def frame_joints_2d(self, position: Optional[int] = None):  # noqa: ANN201
        if self.review is None:
            return None
        return self.review.joints_2d(
            position if position is not None else self.position.value
        )

    # ------------------------------------------------------------- movements
    def add_movement(self, start: int, end: int) -> Optional[str]:
        if self.store is None:
            return None
        try:
            sample = self.store.add_movement(start, end)
        except (ValidationError, KeyError) as exc:
            self.message.emit(from_error(exc, headline="Hareket eklenemedi."))
            return None
        self.select_movement(sample.sample_id)
        return sample.sample_id

    def set_movement_bounds(self, sample_id: str, start: int, end: int) -> None:
        self._guarded(lambda: self.store.set_movement_bounds(sample_id, start, end),
                      "Hareket sınırı değiştirilemedi.")

    def label_movement(self, sample_id: str, exercise: str, *, note: str = "") -> bool:
        if self.store is None or not exercise:
            return False
        return self._guarded(
            lambda: self.store.label_movement(sample_id, exercise, note=note),
            "Hareket etiketlenemedi.",
        )

    def remove_movement(self, sample_id: str) -> None:
        self._guarded(lambda: self.store.remove_movement(sample_id),
                      "Hareket silinemedi.")

    def set_excluded(self, sample_id: str, excluded: bool) -> None:
        self._guarded(lambda: self.store.set_excluded(sample_id, excluded),
                      "Hareket durumu değiştirilemedi.")

    def apply_exercise_to_unlabelled(self, exercise: str) -> int:
        """Give every unclassified movement the same exercise.

        A session is usually one exercise repeated, so labelling each of thirty
        repetitions by hand is thirty chances to misclick. Only movements with
        no class are touched, so it can never overwrite a decision.
        """
        if self.store is None or not exercise:
            return 0
        targets = [s.sample_id for s in self.store.document.samples if not s.exercise]
        changed = 0
        for sample_id in targets:
            if self.label_movement(sample_id, exercise):
                changed += 1
        if changed:
            self.message.emit(
                Message(
                    headline=f"{changed} sınıfsız harekete '{self._exercise_label(exercise)}' atandı.",
                    severity=Severity.INFO,
                    detail="Zaten sınıfı olan hareketler değiştirilmedi.",
                )
            )
        return changed

    # ----------------------------------------------------------------- errors
    def add_error(self, start: int, end: int, sample_id: str = "") -> Optional[str]:
        if self.store is None:
            return None
        target = sample_id or self.selected_movement.value
        if not target:
            # An error interval only means something inside a movement, and
            # guessing which movement was meant is how the wrong repetition
            # gets marked faulty.
            self.message.emit(
                Message(
                    headline="Önce bir hareket seçin.",
                    severity=Severity.WARNING,
                    detail="Hata aralığı her zaman bir hareketin içindedir.",
                )
            )
            return None
        try:
            interval = self.store.add_error(target, start, end)
        except (ValidationError, KeyError) as exc:
            self.message.emit(from_error(exc, headline="Hata aralığı eklenemedi."))
            return None
        self.selected_error.set(interval.interval_id)
        return interval.interval_id

    def set_error_bounds(self, interval_id: str, start: int, end: int) -> None:
        sample_id = self._owner_of(interval_id)
        if sample_id:
            self._guarded(
                lambda: self.store.set_error_bounds(sample_id, interval_id, start, end),
                "Hata aralığı değiştirilemedi.",
            )

    def label_error(
        self,
        interval_id: str,
        *,
        error_class: str,
        roles: Sequence[str] = (),
        joint_status: JointStatus = JointStatus.UNREVIEWED,
        note: str = "",
    ) -> bool:
        sample_id = self._owner_of(interval_id)
        if not sample_id or self.store is None:
            return False
        return self._guarded(
            lambda: self.store.label_error(
                sample_id,
                interval_id,
                error_class=error_class,
                affected_roles=roles,
                joint_status=joint_status,
                note=note,
            ),
            "Hata aralığı etiketlenemedi.",
        )

    def remove_error(self, interval_id: str) -> None:
        sample_id = self._owner_of(interval_id)
        if sample_id:
            self._guarded(lambda: self.store.remove_error(sample_id, interval_id),
                          "Hata aralığı silinemedi.")

    # -------------------------------------------------------------- selection
    def select_movement(self, sample_id: str) -> None:
        self.selected_movement.set(sample_id)
        if sample_id and self.store is not None:
            current = self.selected_error.value
            if current and self._owner_of(current) != sample_id:
                self.selected_error.set("")
        self._refresh()

    def select_error(self, interval_id: str) -> None:
        self.selected_error.set(interval_id)
        owner = self._owner_of(interval_id)
        if owner:
            self.selected_movement.set(owner)
        self._refresh()

    def select_at(self, position: int) -> None:
        if self.store is None:
            return
        sample = self.store.sample_at(position)
        self.select_movement(sample.sample_id if sample else "")

    def go_to_next_unfinished(self) -> bool:
        """Jump to the next movement that still needs something."""
        if self.store is None:
            return False
        sample = self.store.next_unfinished(self.selected_movement.value or None)
        if sample is None:
            self.message.emit(
                Message(
                    headline="Eksik hareket kalmadı.",
                    severity=Severity.INFO,
                    detail="Bu sürümdeki bütün hareketler etiketlenmiş görünüyor.",
                )
            )
            return False
        start, _end = self.store.sample_bounds(sample.sample_id)
        self.select_movement(sample.sample_id)
        self.seek(start)
        return True

    # --------------------------------------------------------------- history
    def undo(self) -> None:
        if self.store is not None and self.store.undo():
            self._refresh()

    def redo(self) -> None:
        if self.store is not None and self.store.redo():
            self._refresh()

    def flush(self) -> bool:
        """Write the labels. Keeps them in memory if the write fails.

        A failed save must not also lose the work: the store stays dirty, so
        the next autosave tries again and leaving the screen tries once more.
        """
        if self.store is None:
            return True
        try:
            self.store.flush()
        except (KineCaptureError, OSError) as exc:
            self.message.emit(
                from_error(exc, headline="Etiketler kaydedilemedi.")
            )
            self.dirty.set(self.store.is_dirty)
            return False
        self.dirty.set(self.store.is_dirty)
        return True

    # ------------------------------------------------------------- vocabulary
    def create_exercise(self, name: str) -> Optional[str]:
        """Create-or-reuse an exercise class, written to the project at once.

        A class is a *project* edit, so it survives cancelling the dialog that
        created it: it may already be in use on another take, and closing a
        window cannot un-define it.
        """
        return self._create_class(name, exercise=True)

    def create_error_class(self, name: str) -> Optional[str]:
        return self._create_class(name, exercise=False)

    def _create_class(self, name: str, *, exercise: bool) -> Optional[str]:
        workspace = self._session.workspace
        if workspace is None or not name.strip():
            return None
        schema = workspace.label_schema
        try:
            option = (
                schema.ensure_exercise(name)
                if exercise
                else schema.ensure_error_type(name)
            )
            workspace.save_label_schema(schema)
        except (KineCaptureError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Sınıf oluşturulamadı."))
            return None
        self._schema = schema
        if self.store is not None:
            self.store.known_exercises = schema.exercise_codes()
            self.store.known_error_classes = schema.error_type_codes()
        self._refresh_options()
        return option.code

    def _refresh_options(self) -> None:
        self.exercise_options.force(
            tuple((o.code, o.label) for o in self._schema.exercises)
        )
        self.error_options.force(
            tuple((o.code, o.label) for o in self._schema.error_types)
        )

    # ------------------------------------------------------------- internals
    def _guarded(self, action, headline: str) -> bool:  # noqa: ANN001
        if self.store is None:
            return False
        try:
            action()
        except (ValidationError, KeyError, KineCaptureError) as exc:
            self.message.emit(from_error(exc, headline=headline))
            return False
        return True

    def _owner_of(self, interval_id: str) -> str:
        if self.store is None or not interval_id:
            return ""
        for sample in self.store.document.samples:
            if any(i.interval_id == interval_id for i in sample.errors):
                return sample.sample_id
        return ""

    def _exercise_label(self, code: str) -> str:
        return self._schema.label_for_exercise(code)

    def class_index(self, code: str, *, fault: bool = False) -> int:
        """Where a class sits in the project vocabulary, or ``-1``.

        The position is what the timeline turns into a colour, so it has to
        come from something stored with the project: a class must look the
        same today and next week, on this take and the next one.
        """
        if not code:
            return -1
        options = self._schema.error_types if fault else self._schema.exercises
        for index, option in enumerate(options):
            if option.code == code:
                return index
        return -1

    def _refresh(self) -> None:
        store = self.store
        if store is None:
            return
        movements: list[MovementRow] = []
        errors: list[ErrorRow] = []
        for sample in store.document.samples:
            try:
                start, end = store.sample_bounds(sample.sample_id)
            except (ValueError, KeyError):
                # An unresolvable anchor is reported by validation; it must not
                # take the whole screen down.
                logger.warning("Hareket sınırı çözülemedi: %s", sample.sample_id)
                continue
            readiness = sample.readiness(self._schema.exercise_codes())
            movements.append(
                MovementRow(
                    sample_id=sample.sample_id,
                    start=start,
                    end=end,
                    exercise=sample.exercise,
                    exercise_label=self._exercise_label(sample.exercise) if sample.exercise else "",
                    readiness=readiness,
                    correctness=sample.correctness,
                    error_count=len(sample.errors),
                    unclassified_errors=sum(
                        1 for i in sample.errors if not i.is_classified
                    ),
                    excluded=sample.excluded,
                    colour_index=self.class_index(sample.exercise),
                )
            )
            for interval in sample.errors:
                try:
                    first, last = store.error_bounds(sample.sample_id, interval.interval_id)
                except (ValueError, KeyError):
                    continue
                errors.append(
                    ErrorRow(
                        interval_id=interval.interval_id,
                        sample_id=sample.sample_id,
                        start=first,
                        end=last,
                        error_class=interval.error_class,
                        error_label=(
                            self._schema.label_for_error(interval.error_class)
                            if interval.error_class
                            else ""
                        ),
                        joint_status=interval.joint_status,
                        roles=interval.affected_roles,
                        colour_index=self.class_index(
                            interval.error_class, fault=True
                        ),
                    )
                )
        movements.sort(key=lambda row: row.start)
        errors.sort(key=lambda row: row.start)
        self.movements.force(tuple(movements))
        self.errors.force(tuple(errors))
        ready, total = store.progress()
        self.progress.set(f"{ready}/{total} hareket hazır" if total else "Henüz hareket yok")
        self.can_undo.set(store.can_undo)
        self.can_redo.set(store.can_redo)
        self.dirty.set(store.is_dirty)

    def movement_row(self, sample_id: str) -> Optional[MovementRow]:
        return next((r for r in self.movements.value if r.sample_id == sample_id), None)

    def error_row(self, interval_id: str) -> Optional[ErrorRow]:
        return next((r for r in self.errors.value if r.interval_id == interval_id), None)


__all__ = ["ErrorRow", "MovementRow", "READINESS_STATUS", "READINESS_TEXT", "ReviewViewModel"]
