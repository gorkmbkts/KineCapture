"""Content hashing for checksums and dataset fingerprints.

Two distinct jobs live here:

* **File checksums** prove a stored file has not changed since it was written.
  They go into ``checksums.json`` next to each take.
* **Dataset fingerprints** prove that two dataset releases contain the same
  logical content. A fingerprint is computed over a canonical JSON projection
  of the release, not over file bytes, so it stays stable across compression
  settings, file ordering and timestamps.

Neither hash is a security mechanism; both are integrity and reproducibility
mechanisms.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from kinecapture.core.errors import StorageError
from kinecapture.core.jsonio import dumps
from kinecapture.core.paths import long_path, path_exists

#: Read size for streaming file hashes. Large files are never fully buffered.
_CHUNK_BYTES = 1024 * 1024


def hash_file(path: Path, *, algorithm: str = "sha256") -> str:
    """Stream ``path`` through a hash and return ``"sha256:<hex>"``."""
    path = Path(path)
    digest = hashlib.new(algorithm)
    try:
        with open(long_path(path), "rb") as stream:
            while chunk := stream.read(_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise StorageError(
            f"Sağlama toplamı hesaplanamadı: {path.name}",
            code="checksum_failed",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    return f"{algorithm}:{digest.hexdigest()}"


def hash_payload(payload: Any, *, algorithm: str = "sha256") -> str:
    """Hash a canonical JSON projection of ``payload``.

    Keys are sorted and separators are fixed by :func:`kinecapture.core.jsonio.dumps`,
    so the same logical content always produces the same digest regardless of
    the order in which it was assembled.
    """
    digest = hashlib.new(algorithm)
    digest.update(dumps(payload, indent=None).encode("utf-8"))
    return f"{algorithm}:{digest.hexdigest()}"


def checksum_manifest(
    files: Mapping[str, Path], *, algorithm: str = "sha256"
) -> dict[str, Any]:
    """Build a ``{relative_name: {size, checksum}}`` manifest.

    Missing files are recorded as such rather than skipped: a validation report
    that silently omits a lost file is worse than useless.
    """
    entries: dict[str, Any] = {}
    for name, path in sorted(files.items()):
        path = Path(path)
        if not path_exists(path):
            entries[name] = {"present": False, "size_bytes": None, "checksum": None}
            continue
        entries[name] = {
            "present": True,
            "size_bytes": os.stat(long_path(path)).st_size,
            "checksum": hash_file(path, algorithm=algorithm),
        }
    return {"algorithm": algorithm, "files": entries}


def verify_checksum_manifest(
    manifest: Mapping[str, Any], base_dir: Path
) -> list[dict[str, Any]]:
    """Re-hash every file in ``manifest`` and return the mismatches.

    An empty list means everything matched. Each problem entry carries a
    machine-readable ``issue`` so the dataset QA screen can group them.
    """
    algorithm = str(manifest.get("algorithm", "sha256"))
    problems: list[dict[str, Any]] = []
    files = manifest.get("files") or {}
    if not isinstance(files, Mapping):
        return [{"file": "-", "issue": "manifest_shape_invalid"}]
    for name, entry in sorted(files.items()):
        if not isinstance(entry, Mapping):
            problems.append({"file": name, "issue": "entry_shape_invalid"})
            continue
        path = Path(base_dir) / name
        expected = entry.get("checksum")
        if not entry.get("present", True):
            continue
        if not path_exists(path):
            problems.append({"file": name, "issue": "missing"})
            continue
        if expected is None:
            continue
        actual = hash_file(path, algorithm=algorithm)
        if actual != expected:
            problems.append(
                {
                    "file": name,
                    "issue": "checksum_mismatch",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return problems


def dataset_fingerprint(
    sample_keys: Iterable[Mapping[str, Any]],
    *,
    export_config: Mapping[str, Any],
    skeleton_spec: Mapping[str, Any],
    label_schema: Mapping[str, Any],
    features: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Compute the fingerprint of a dataset release.

    The fingerprint has independent components so a difference between two
    releases can be attributed instead of merely detected: samples, export
    configuration, skeleton definition, label schema and - when a release
    carries derived features - the feature definitions each get their own
    digest, plus a combined digest over all of them.

    ``sample_keys`` must be small per-sample dictionaries (identifiers, frame
    counts, label values, and the **checksum of the written array file**) -
    never the pose arrays themselves. Including that checksum is what ties the
    fingerprint to the bytes actually published: without it two releases whose
    metadata matched but whose arrays differed would fingerprint identically.
    """
    samples = sorted(
        (dict(entry) for entry in sample_keys),
        key=lambda item: str(item.get("sample_id", "")),
    )
    components = {
        "samples": hash_payload(samples),
        "export_config": hash_payload(dict(export_config)),
        "skeleton_spec": hash_payload(dict(skeleton_spec)),
        "label_schema": hash_payload(dict(label_schema)),
    }
    if features is not None:
        components["features"] = hash_payload(dict(features))
    return {
        "algorithm": "sha256",
        "num_samples": len(samples),
        "components": components,
        "fingerprint": hash_payload(components),
    }


__all__ = [
    "checksum_manifest",
    "dataset_fingerprint",
    "hash_file",
    "hash_payload",
    "verify_checksum_manifest",
]
