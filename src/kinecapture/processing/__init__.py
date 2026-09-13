"""Versioned offline processing. Raw sources are opened read-only.

Imports neither Qt nor ``pyzed`` at module level: ``process_take`` reaches the
SDK through ``sources.py`` only when it actually runs, and ``ReviewDataset``
never does. That is what lets a screen open a finished version while a
recording is in progress.
"""

from .arrays import ArrayStore, write_arrays
from .depth import DepthReader
from .jobs import PROCESSING_SCHEMA_VERSION, ProcessingConfig, process_take, restart_job
from .review import ReviewDataset
from .summary import TimelineSummary, build_summary
from .thumbnails import ThumbnailIndex, build_thumbnails

__all__ = [
    "PROCESSING_SCHEMA_VERSION",
    "ArrayStore",
    "DepthReader",
    "ProcessingConfig",
    "ReviewDataset",
    "ThumbnailIndex",
    "TimelineSummary",
    "build_summary",
    "build_thumbnails",
    "process_take",
    "restart_job",
    "write_arrays",
]
