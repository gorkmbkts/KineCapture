"""KineCapture Studio - ZED 2i motion capture, review, labelling and dataset export.

This module is the single place where product identity and the versioned data
contracts are defined. Renaming the product means editing ``APP_NAME`` here (and,
optionally, ``app_name`` in ``configs/default.yaml``); nothing else in the code
base hard-codes the display name.

Schema versions are part of the on-disk contract. Every JSON document written by
the application carries the version of the schema it was written with, so a
future reader can tell what it is looking at instead of guessing.
"""

from __future__ import annotations

#: Human-readable product name (working title).
APP_NAME: str = "KineCapture Studio"

#: Importable Python package name. Kept separate from ``APP_NAME`` on purpose.
PACKAGE_NAME: str = "kinecapture"

#: Application version.
APP_VERSION: str = "0.5.0"

#: Schema version for ``project.json``.
PROJECT_SCHEMA_VERSION: str = "1.0.0"

#: Schema version for ``participant.json`` and ``session.json``.
SESSION_SCHEMA_VERSION: str = "1.0.0"

#: Schema version for ``take.json``.
TAKE_SCHEMA_VERSION: str = "1.0.0"

#: Schema version for the append-safe per-frame skeleton sidecar (JSONL).
#: 1.1 adds optional tracker fields (2D keypoints, per-joint covariances,
#: parent-relative joint positions, root orientation and velocity, action
#: state). Every one of them is optional, so a 1.0 stream stays readable
#: without migration and a 1.1 reader loses nothing from either version.
SKELETON_STREAM_SCHEMA_VERSION: str = "1.1.0"

#: Schema version for the label sidecar (``annotations/segments.json``).
#: 2.x introduces the two-level MovementSample / ErrorInterval hierarchy;
#: 1.x documents are read through a lossless compatibility path.
ANNOTATION_SCHEMA_VERSION: str = "2.0.0"

#: Schema version of the built-in label schema document.
LABEL_SCHEMA_VERSION: str = "2.0.0"

#: Schema version for an exported dataset release manifest.
#: 2.x adds the selectable feature layer: the canonical raw arrays are
#: unchanged, but a release may now carry additional named arrays described by
#: ``feature_spec.json``.
RELEASE_SCHEMA_VERSION: str = "2.0.0"

#: Schema version of ``feature_spec.json`` inside a release.
FEATURE_SPEC_SCHEMA_VERSION: str = "1.0.0"

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "ANNOTATION_SCHEMA_VERSION",
    "FEATURE_SPEC_SCHEMA_VERSION",
    "LABEL_SCHEMA_VERSION",
    "PACKAGE_NAME",
    "PROJECT_SCHEMA_VERSION",
    "RELEASE_SCHEMA_VERSION",
    "SESSION_SCHEMA_VERSION",
    "SKELETON_STREAM_SCHEMA_VERSION",
    "TAKE_SCHEMA_VERSION",
]
