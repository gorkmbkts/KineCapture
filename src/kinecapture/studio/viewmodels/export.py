"""Dışa Aktarım: check first, then write.

The screen is built around one idea - **nothing is discovered during the
build**. Every version is inspected up front and shown as either "goes in" or
"stays out, for this reason", and the user sees that list before anything is
written. A build that silently skipped a take would be the single most
expensive kind of bug this project can have: the dataset would simply be
missing an athlete and nobody would know to look.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.labels import LabelSchema
from kinecapture.export.canonical import (
    REFUSAL_TEXT,
    CanonicalExportOptions,
    ExportReport,
    VersionReport,
    build_release,
    current_revisions,
    inspect_version,
)
from kinecapture.studio.services.library import VersionRow
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService

from enum import Enum

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreflightRow:
    """One version, as the check left it."""

    run_id: str
    take_id: str
    directory: str
    accepted: bool
    samples: int
    reasons: tuple[str, ...]
    detail: tuple[str, ...]

    @property
    def status(self) -> str:
        return "ready" if self.accepted else "warning"

    @property
    def text(self) -> str:
        if self.accepted:
            return f"{self.samples} hareket dışa aktarılacak"
        return " · ".join(self.reasons) or "nedeni belirtilmedi"


class CheckState(str, Enum):
    """What the screen actually knows about the versions in front of it.

    Six states rather than a boolean, because "not checked yet" and "checked
    and refused" are different answers to the same question and a screen that
    shows one for the other is lying. STALE is the one worth spelling out: the
    check passed, and then the labels underneath it changed. The package
    itself is never in danger - ``build_release`` re-inspects every version on
    the way in - but a green row that no longer describes the data on disk is
    an invitation to press a button believing something that is not true.
    """

    NOT_CHECKED = "not_checked"
    CHECKING = "checking"
    EMPTY = "empty"
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"
    STALE = "stale"


#: One line per state, in the words the screen uses.
CHECK_STATE_TEXT = {
    CheckState.NOT_CHECKED: "Henüz kontrol edilmedi.",
    CheckState.CHECKING: "Sürümler kontrol ediliyor…",
    CheckState.EMPTY: "Kontrol edilecek sürüm yok.",
    CheckState.READY: "Bütün sürümler hazır.",
    CheckState.WARNING: "Bazı sürümler dışarıda kalacak.",
    CheckState.BLOCKED: "Hiçbir sürüm dışa aktarılamıyor.",
    CheckState.STALE: (
        "Kontrolden sonra etiketler değişti. Yazmadan önce tekrar kontrol edin."
    ),
}


class ExportViewModel:
    """Preflight and build for the canonical dataset package."""

    def __init__(
        self, session: SessionService, runner: Optional[TaskRunner] = None
    ) -> None:
        self._session = session
        self._runner: TaskRunner = runner or InlineRunner()
        self._rows: tuple[VersionRow, ...] = ()

        self.rows: Observable[tuple[PreflightRow, ...]] = Observable((), name="rows")
        self.summary: Observable[str] = Observable("", name="summary")
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.can_build: Observable[bool] = Observable(False, name="can_build")
        self.last_release: Observable[str] = Observable("", name="last_release")
        self.state: Observable[CheckState] = Observable(
            CheckState.NOT_CHECKED, name="state"
        )
        #: The annotation and subject revisions each version had when it was
        #: checked. Read back from disk to decide whether the result still
        #: describes the data, rather than trusting a flag nobody updated.
        self._checked: dict[str, tuple[int, int]] = {}
        self._freshness_pending = False
        self.options: Observable[CanonicalExportOptions] = Observable(
            CanonicalExportOptions(), name="options"
        )
        self.message: Event[Message] = Event()
        self.finished: Event[ExportReport] = Event()

    # ------------------------------------------------------------- schema
    @property
    def schema(self) -> LabelSchema:
        workspace = self._session.workspace
        return workspace.label_schema if workspace else LabelSchema.default()

    @property
    def releases_dir(self) -> Optional[Path]:
        workspace = self._session.workspace
        return Path(workspace.root) / "releases" if workspace else None

    # ---------------------------------------------------------- preflight
    def check(self, versions: Sequence[VersionRow]) -> None:
        """Open every version and decide, off the GUI thread.

        This is the expensive, honest path: it verifies derived checksums and
        validates every annotation against the version it belongs to. It is
        what the build would do anyway, done while the user can still react.
        """
        self._rows = tuple(versions)
        if not versions:
            self.rows.force(())
            self.state.set(CheckState.EMPTY)
            self.summary.set(CHECK_STATE_TEXT[CheckState.EMPTY])
            self.can_build.set(False)
            return
        self.busy.set(True)
        self.state.set(CheckState.CHECKING)
        self.summary.set(CHECK_STATE_TEXT[CheckState.CHECKING])
        schema = self.schema

        progress = self._progress_reporter(CHECK_STATE_TEXT[CheckState.CHECKING])

        def work() -> list[VersionReport]:
            reports: list[VersionReport] = []
            for position, row in enumerate(versions, start=1):
                report, opened = inspect_version(Path(row.directory), schema)
                if opened is not None:
                    opened["dataset"].close()
                    report.samples_written = len(opened["ready"])
                reports.append(report)
                progress(position, len(versions))
            return reports

        def done(reports: list[VersionReport]) -> None:
            self.busy.set(False)
            self._show(reports)

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            # A failed check is not a refusal: nothing was learned about the
            # versions, so the screen goes back to saying so rather than
            # leaving the spinner's wording behind.
            self.state.set(CheckState.NOT_CHECKED)
            self.summary.set(CHECK_STATE_TEXT[CheckState.NOT_CHECKED])
            self.can_build.set(False)
            self.message.emit(from_error(exc, headline="Kontrol tamamlanamadı."))

        self._runner.run(work, done, failed)

    def _show(self, reports: Sequence[VersionReport]) -> None:
        rows = tuple(
            PreflightRow(
                run_id=report.run_id,
                take_id=report.take_id,
                directory=report.directory,
                accepted=report.accepted,
                samples=report.samples_written,
                reasons=tuple(REFUSAL_TEXT[r] for r in report.refusals),
                detail=report.detail,
            )
            for report in reports
        )
        self.rows.force(rows)
        ready = [r for r in rows if r.accepted]
        samples = sum(r.samples for r in ready)
        blocked = len(rows) - len(ready)
        parts = [f"{len(ready)}/{len(rows)} sürüm hazır", f"{samples} hareket"]
        if blocked:
            parts.append(f"{blocked} sürüm dışarıda")
        self.summary.set(" · ".join(parts))
        self.can_build.set(bool(ready))
        self._checked = {
            report.directory: (
                int(report.annotation_revision),
                int(report.subject_revision),
            )
            for report in reports
        }
        if not rows:
            self.state.set(CheckState.EMPTY)
        elif not ready:
            self.state.set(CheckState.BLOCKED)
        elif blocked:
            self.state.set(CheckState.WARNING)
        else:
            self.state.set(CheckState.READY)

    # ---------------------------------------------------------- staleness
    def recheck_freshness(self) -> bool:
        """Does the last result still describe what is on disk?

        EXPORT-02. The read is deliberately narrow - the revision counters
        from each version's own annotation and subject files - so it costs a
        few small JSON reads rather than another full verification. It answers
        "is this result still about the current data", never "is this data
        exportable"; that second question has one answer, and it is the check.

        Returns True when the result still stands.
        """
        if not self._checked or self.busy.value:
            return True
        if _any_changed(dict(self._checked)):
            self._mark_stale()
            return False
        return True

    def refresh_freshness(self) -> None:
        """:meth:`recheck_freshness`, off the GUI thread. What a visit calls.

        Three small reads per checked version is nothing for ten versions and
        a frozen window for thirty thousand: measured at 660 ms for 500
        versions, on the GUI thread, every time the screen was opened
        (release gate A3, 23 September 2026). The answer arrives a moment
        later; until it does the previous one stands, which is what it did
        before as well.
        """
        if not self._checked or self.busy.value or self._freshness_pending:
            return
        checked = dict(self._checked)
        self._freshness_pending = True

        def done(changed: bool) -> None:
            self._freshness_pending = False
            # Only if nothing was checked again meanwhile: a newer result
            # describes the disk better than this one does.
            if changed and self._checked == checked and not self.busy.value:
                self._mark_stale()

        def failed(_exc: BaseException) -> None:
            self._freshness_pending = False

        self._runner.run(lambda: _any_changed(checked), done, failed)

    def _mark_stale(self) -> None:
        self.state.set(CheckState.STALE)
        self.summary.set(CHECK_STATE_TEXT[CheckState.STALE])
        self.can_build.set(False)

    # -------------------------------------------------------------- build
    def build(self) -> None:
        """Write the package. Only versions that passed the check go in."""
        releases = self.releases_dir
        if releases is None:
            self.message.emit(
                Message(headline="Önce bir proje açın.", severity=Severity.WARNING)
            )
            return
        accepted = [r for r in self.rows.value if r.accepted]

        self.busy.set(True)
        schema = self.schema
        options = self.options.value
        operator = self._session.user.display_name if self._session.user else ""
        # Everything selected is re-inspected inside the build. The preflight
        # result is shown to the user, never trusted as a substitute for the
        # check that actually guards the write.
        directories = [Path(r.directory) for r in self.rows.value]
        checked = dict(self._checked)
        progress = self._progress_reporter("Paket yazılıyor…")

        def work() -> Optional[ExportReport]:
            # Whether the result on screen still describes the disk, asked
            # here on the worker rather than on the GUI thread first: for a
            # large project the question alone froze the window.
            if checked and _any_changed(checked):
                return None
            if not accepted:
                return _NOTHING_READY
            return build_release(
                directories,
                releases,
                schema,
                options=options,
                operator=operator,
                progress=progress,
            )

        def done(report: Optional[ExportReport]) -> None:
            self.busy.set(False)
            if report is _NOTHING_READY:
                # Asked after the freshness question on purpose: when the
                # labels changed, "nothing is ready" may no longer be true,
                # and re-checking is the more useful thing to say.
                self.message.emit(
                    Message(
                        headline="Dışa aktarılacak hazır sürüm yok.",
                        severity=Severity.WARNING,
                        detail="Listedeki nedenleri giderdikten sonra tekrar kontrol edin.",
                    )
                )
                return
            if report is None:
                self._mark_stale()
                self.message.emit(
                    Message(
                        headline="Kontrolden sonra etiketler değişti.",
                        severity=Severity.WARNING,
                        detail=(
                            "Paket her sürümü yeniden denetleyerek yazılır, ama "
                            "ekrandaki sonuç artık diskteki veriyi anlatmıyor. "
                            "Tekrar kontrol edin."
                        ),
                    )
                )
                return
            self._show(report.versions)
            self.last_release.set(str(report.release_dir or ""))
            self.finished.emit(report)
            refused = len(report.refused)
            self.message.emit(
                Message(
                    headline=(
                        f"{report.samples} hareket yazıldı"
                        f" · {report.release_dir.name if report.release_dir else ''}"
                    ),
                    severity=Severity.INFO,
                    detail=(
                        f"{refused} sürüm dışarıda kaldı; nedenleri pakete de yazıldı."
                        if refused
                        else "Seçilen bütün sürümler pakete girdi."
                    ),
                )
            )

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Dışa aktarım tamamlanamadı."))

        self._runner.run(work, done, failed)

    def _progress_reporter(self, text: str):  # noqa: ANN202 - Callable[[int, int], None]
        """``(done, total)`` into the summary line, at most four times a second.

        Called from the worker; the summary reaches the screen through the
        bridge's queued signal. Checking or writing ten thousand versions took
        minutes on the gate machine, and a line that only says "checking" for
        that long is indistinguishable from a hang.
        """
        import time

        last = [0.0]

        def report(done: int, total: int) -> None:
            now = time.monotonic()
            if done < total and now - last[0] < 0.25:
                return
            last[0] = now
            self.summary.set(f"{text} {done}/{total} sürüm")

        return report

    def set_option(self, **changes) -> None:  # noqa: ANN003
        from dataclasses import replace

        self.options.set(replace(self.options.value, **changes))


#: What the build's worker returns when the check left nothing to write.
_NOTHING_READY: Any = object()


def _any_changed(checked: dict[str, tuple[int, int]]) -> bool:
    """Whether any checked version's revisions moved on disk. Reads only."""
    return any(
        current_revisions(Path(directory)) != revisions
        for directory, revisions in checked.items()
    )


__all__ = [
    "CHECK_STATE_TEXT",
    "CheckState",
    "ExportViewModel",
    "PreflightRow",
    "current_revisions",
]
