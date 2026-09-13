"""Atomic, overwrite-aware JSON and JSONL helpers.

Data-integrity rules enforced here (MEMORY.md sections 4 and 10):

* a document is written to a temporary file in the *same* directory and then
  moved into place with ``os.replace``, so a crash never leaves a half-written
  JSON file where a valid one used to be;
* ``write_json`` refuses to clobber an existing file unless the caller passes
  ``overwrite=True``. Silent overwrites of user data are a bug, not a feature;
* JSONL streams are flushed on every record, so a recording interrupted by a
  power cut still yields every frame written before it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, TextIO

from kinecapture.core.errors import OverwriteRefusedError, StorageError
from kinecapture.core.paths import ensure_dir, long_path, path_exists


def _default(obj: Any) -> Any:
    """Serialise the few non-JSON types the domain layer uses."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


def dumps(payload: Any, *, indent: Optional[int] = 2) -> str:
    """Serialise to a deterministic JSON string (sorted keys, UTF-8 preserved)."""
    return json.dumps(
        payload,
        indent=indent,
        ensure_ascii=False,
        sort_keys=True,
        default=_default,
        separators=(",", ": ") if indent else (",", ":"),
    )


def write_text_atomic(path: Path, text: str, *, overwrite: bool = False) -> Path:
    """Write ``text`` to ``path`` atomically.

    Raises:
        OverwriteRefusedError: if ``path`` exists and ``overwrite`` is False.
        StorageError: if the directory cannot be created or the write fails.
    """
    path = Path(path)
    if path_exists(path) and not overwrite:
        raise OverwriteRefusedError(
            f"Dosya zaten var ve üzerine yazılmadı: {path.name}",
            remedy="Farklı bir hedef seçin veya mevcut kaydı açıkça güncelleyin.",
            details={"path": str(path)},
        )
    try:
        ensure_dir(path.parent)
        # A short fixed prefix on purpose: a long temporary name would push an
        # otherwise-legal path over the Windows limit only while it exists.
        handle, tmp_name = tempfile.mkstemp(
            prefix="~kc", suffix=".tmp", dir=long_path(path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, long_path(path))
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise StorageError(
            f"Dosya yazılamadı: {path.name}",
            remedy="Disk alanını ve klasör yazma iznini kontrol edin.",
            details={"path": str(path), "os_error": str(exc)},
        ) from exc
    return path


def write_json(
    path: Path, payload: Any, *, overwrite: bool = False, indent: Optional[int] = 2
) -> Path:
    """Atomically write ``payload`` as JSON. See :func:`write_text_atomic`."""
    return write_text_atomic(
        path, dumps(payload, indent=indent) + "\n", overwrite=overwrite
    )


def read_json(path: Path) -> Any:
    """Read a JSON document, reporting the file name on failure."""
    path = Path(path)
    try:
        with open(long_path(path), "r", encoding="utf-8") as stream:
            return json.loads(stream.read())
    except FileNotFoundError as exc:
        raise StorageError(
            f"Dosya bulunamadı: {path.name}",
            code="file_missing",
            remedy="Proje klasörünün taşınmış olup olmadığını kontrol edin.",
            details={"path": str(path)},
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise StorageError(
            f"Dosya okunamadı veya bozuk: {path.name}",
            code="file_corrupt",
            remedy="Dosyayı yedekten geri yükleyin.",
            details={"path": str(path), "error": str(exc)},
        ) from exc


def read_json_mapping(path: Path) -> dict[str, Any]:
    """Read a JSON document that must be an object."""
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise StorageError(
            f"Dosya beklenen biçimde değil: {path.name}",
            code="file_shape_invalid",
            remedy="Bu dosya bir JSON nesnesi olmalıdır.",
            details={"path": str(path)},
        )
    return dict(payload)


class JsonlWriter:
    """Append-safe line-delimited JSON stream.

    One record per line, flushed on every write. A process killed mid-stream
    leaves at most one truncated trailing line, which :func:`read_jsonl`
    tolerates rather than turning into a total loss.
    """

    def __init__(self, path: Path, *, append: bool = False) -> None:
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self._stream: Optional[TextIO] = open(
            long_path(self.path), "a" if append else "w", encoding="utf-8", newline="\n"
        )
        self._records = 0

    @property
    def records_written(self) -> int:
        return self._records

    @property
    def closed(self) -> bool:
        return self._stream is None

    def write(self, record: Any) -> None:
        if self._stream is None:
            raise StorageError(
                f"Kapatılmış akışa yazılamaz: {self.path.name}",
                code="stream_closed",
            )
        self._stream.write(dumps(record, indent=None))
        self._stream.write("\n")
        self._records += 1

    def flush(self, *, fsync: bool = False) -> None:
        if self._stream is None:
            return
        self._stream.flush()
        if fsync:
            os.fsync(self._stream.fileno())

    def close(self) -> None:
        """Flush, fsync and close. Idempotent, and safe during shutdown."""
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            stream.close()

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def read_jsonl(path: Path, *, strict: bool = False) -> Iterator[dict[str, Any]]:
    """Yield records from a JSONL file.

    A truncated final line (an interrupted recording) is skipped when
    ``strict`` is False, which is what recovery needs. With ``strict=True`` it
    raises instead, which is what validation needs.
    """
    path = Path(path)
    try:
        stream = open(long_path(path), "r", encoding="utf-8")
    except FileNotFoundError as exc:
        raise StorageError(
            f"Akış dosyası bulunamadı: {path.name}",
            code="file_missing",
            details={"path": str(path)},
        ) from exc
    with stream:
        for line_number, line in enumerate(stream, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if strict:
                    raise StorageError(
                        f"{path.name} dosyasında bozuk satır: {line_number}",
                        code="jsonl_corrupt_line",
                        details={"path": str(path), "line": line_number},
                    ) from exc
                continue
            if isinstance(record, dict):
                yield record


def count_jsonl_records(path: Path) -> int:
    """Number of parsable records, used by recovery and validation."""
    return sum(1 for _ in read_jsonl(path))


__all__ = [
    "JsonlWriter",
    "count_jsonl_records",
    "dumps",
    "read_json",
    "read_json_mapping",
    "read_jsonl",
    "write_json",
    "write_text_atomic",
]
