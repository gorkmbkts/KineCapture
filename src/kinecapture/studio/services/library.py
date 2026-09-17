"""The library of finished processing versions.

Everything a list row needs comes from the derived index and from each run's
own ``job.json`` - never from opening the version itself. Opening one costs a
checksum verification over every file it contains, which is the right price to
pay before annotating and the wrong one to pay per row while scrolling.

Preview images were written at processing time (F3). This module hands out
paths; nothing here decodes video.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kinecapture.core.jsonio import read_json
from kinecapture.core.paths import path_exists
from kinecapture.dataset.summary_index import (
    ProcessingRunSummary,
    TakeIndex,
    TakeSummary,
    build_index,
)
from kinecapture.processing.thumbnails import ThumbnailIndex

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VersionRow:
    """One finished ``run_<id>``, as the library lists it."""

    take_id: str
    run_id: str
    participant_id: str
    session_id: str
    started_at: str
    duration_s: float
    directory: str
    take_directory: str
    frames: int = 0
    body_format: str = ""
    schema_version: str = ""
    subject_status: str = ""
    issues: tuple[str, ...] = ()
    #: Recorded frames, and how many were found again in the replayed source.
    capture_frames: int = 0
    matched_frames: int = 0
    #: When this version was produced. Versions of one take all carry the
    #: take's start time, so sorting on that alone left them in the order of
    #: the random hex in their folder names.
    created_at: str = ""
    job_mtime_ns: int = 0
    has_thumbnails: bool = False
    has_summary: bool = False
    has_depth: bool = False
    #: How many finished versions this take has. >1 means there is something
    #: to compare.
    sibling_versions: int = 1
    #: Whether a canonical annotation sidecar already exists for this version.
    annotated: bool = False

    @property
    def coverage_verified(self) -> bool:
        """False when a check did not pass. Never rounded up to "complete"."""
        return not self.issues

    @property
    def subject_chosen(self) -> bool:
        return self.subject_status == "associated"

    @property
    def coverage_text(self) -> str:
        """How much of the recording was found again, as a count.

        "kapsam doğrulanamadı" was the only thing the screen said about a
        version that had matched 521 of its 524 frames. A number lets the
        operator decide; a verdict decides for them, and decided wrongly.
        """
        if not self.capture_frames:
            return ""
        missing = self.capture_frames - self.matched_frames
        if missing <= 0:
            return f"{self.capture_frames} kare eşleşti"
        return f"{self.matched_frames}/{self.capture_frames} kare eşleşti"

    @property
    def quality_text(self) -> str:
        if not self.subject_chosen:
            return "kişi seçilmedi"
        if not self.coverage_verified:
            return self.coverage_text or "kapsam notları var"
        return "hazır"

    @property
    def quality_status(self) -> str:
        if not self.coverage_verified:
            return "warning"
        if not self.subject_chosen:
            return "warning"
        return "live"

    @property
    def model_text(self) -> str:
        return self.body_format or "—"

    def thumbnail(self) -> Optional[Path]:
        """The cover image, or ``None``. Read from disk; nothing is generated."""
        if not self.has_thumbnails:
            return None
        try:
            return ThumbnailIndex(Path(self.directory)).cover()
        except Exception as exc:  # noqa: BLE001 - a missing preview is cosmetic
            logger.debug("Önizleme okunamadı (%s): %s", self.run_id, exc)
            return None


class LibraryService:
    """Lists finished versions. Never opens one."""

    #: Filters the screen offers, as (key, label, predicate name).
    FILTERS = (
        ("all", "Tümü"),
        ("ready", "Etiketlemeye hazır"),
        ("needs_subject", "Kişi seçilmemiş"),
        ("unverified", "Kapsam notu olan"),
        ("annotated", "Etiketlenmiş"),
        ("multi", "Birden fazla sürüm"),
    )

    def versions(self, index: Optional[TakeIndex]) -> list[VersionRow]:
        if index is None:
            return []
        rows: list[VersionRow] = []
        for take in index:
            finished = take.published_runs
            for run in finished:
                rows.append(self._row(take, run, len(finished)))
        rows.sort(
            key=lambda row: (
                row.started_at,
                row.created_at,
                row.job_mtime_ns,
                row.run_id,
            ),
            reverse=True,
        )
        return rows

    def _row(
        self, take: TakeSummary, run: ProcessingRunSummary, siblings: int
    ) -> VersionRow:
        # The folder the run really sits in, not one rebuilt from its id.
        directory = (
            Path(take.directory) / "derived" / "processing" / (run.folder or run.run_id)
        )
        sidecar = (
            Path(take.directory) / "annotations" / "processing" / f"{run.run_id}.json"
        )
        return VersionRow(
            take_id=take.take_id,
            run_id=run.run_id,
            participant_id=take.participant_id,
            session_id=take.session_id,
            started_at=take.started_at,
            duration_s=take.duration_s,
            directory=str(directory),
            take_directory=take.directory,
            frames=run.frames,
            body_format=run.body_format,
            schema_version=run.schema_version,
            subject_status=run.subject_status,
            issues=run.issues,
            capture_frames=run.capture_frames,
            matched_frames=run.matched_frames,
            created_at=run.created_at,
            job_mtime_ns=run.job_mtime_ns,
            has_thumbnails=run.has_thumbnails,
            has_summary=run.has_summary,
            has_depth=run.has_depth,
            sibling_versions=siblings,
            annotated=path_exists(sidecar),
        )

    @staticmethod
    def matches(row: VersionRow, key: str) -> bool:
        if key == "ready":
            # A listed version is one that can be annotated correctly - that
            # is what publishing it decided. What is left to ask is whether
            # anybody is in it. A coverage note is a note, not a blocker; the
            # "Kapsam notu olan" filter is there for reading those.
            return row.subject_chosen
        if key == "needs_subject":
            return not row.subject_chosen
        if key == "unverified":
            return not row.coverage_verified
        if key == "annotated":
            return row.annotated
        if key == "multi":
            return row.sibling_versions > 1
        return True

    def versions_of(self, rows: list[VersionRow], take_id: str) -> list[VersionRow]:
        """Every finished version of one take, for a side-by-side comparison."""
        return [row for row in rows if row.take_id == take_id]

    @staticmethod
    def parameters_of(row: VersionRow) -> dict:
        """The settings that produced a version, read from its own job file."""
        path = Path(row.directory) / "job.json"
        if not path_exists(path):
            return {}
        try:
            job = dict(read_json(path))
        except Exception as exc:  # noqa: BLE001
            logger.debug("İş dosyası okunamadı (%s): %s", row.run_id, exc)
            return {}
        parameters = dict(job.get("parameters") or {})
        parameters["schema_version"] = job.get("schema_version", "")
        parameters["timestamp_qc"] = job.get("timestamp_qc", {})
        return parameters

    def refresh_index(self, project_root: Path, *, force: bool = False) -> TakeIndex:
        return build_index(project_root, force=force)


__all__ = ["LibraryService", "VersionRow"]
