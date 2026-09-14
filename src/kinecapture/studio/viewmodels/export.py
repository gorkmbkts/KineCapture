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
from typing import Optional, Sequence

from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.labels import LabelSchema
from kinecapture.export.canonical import (
    REFUSAL_TEXT,
    CanonicalExportOptions,
    ExportReport,
    VersionReport,
    build_release,
    inspect_version,
)
from kinecapture.studio.services.library import VersionRow
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService

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
            self.summary.set("Kontrol edilecek sürüm seçilmedi.")
            self.can_build.set(False)
            return
        self.busy.set(True)
        schema = self.schema

        def work() -> list[VersionReport]:
            reports: list[VersionReport] = []
            for row in versions:
                report, opened = inspect_version(Path(row.directory), schema)
                if opened is not None:
                    opened["dataset"].close()
                    report.samples_written = len(opened["ready"])
                reports.append(report)
            return reports

        def done(reports: list[VersionReport]) -> None:
            self.busy.set(False)
            self._show(reports)

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
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
        if not accepted:
            self.message.emit(
                Message(
                    headline="Dışa aktarılacak hazır sürüm yok.",
                    severity=Severity.WARNING,
                    detail="Listedeki nedenleri giderdikten sonra tekrar kontrol edin.",
                )
            )
            return

        self.busy.set(True)
        schema = self.schema
        options = self.options.value
        operator = self._session.user.display_name if self._session.user else ""
        # Everything selected is re-inspected inside the build. The preflight
        # result is shown to the user, never trusted as a substitute for the
        # check that actually guards the write.
        directories = [Path(r.directory) for r in self.rows.value]

        def work() -> ExportReport:
            return build_release(
                directories,
                releases,
                schema,
                options=options,
                operator=operator,
            )

        def done(report: ExportReport) -> None:
            self.busy.set(False)
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

    def set_option(self, **changes) -> None:  # noqa: ANN003
        from dataclasses import replace

        self.options.set(replace(self.options.value, **changes))


__all__ = ["ExportViewModel", "PreflightRow"]
