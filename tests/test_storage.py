"""Workspace storage, recording, finalisation and partial recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import (
    OverwriteRefusedError,
    StorageError,
    ValidationError,
)
from kinecapture.core.fingerprint import (
    checksum_manifest,
    hash_payload,
    verify_checksum_manifest,
)
from kinecapture.core.jsonio import JsonlWriter, read_json, read_jsonl, write_json
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import TakeState
from kinecapture.playback.take_reader import load_take, recover_partial_take
from tests.conftest import paced_backend, record_take


# ------------------------------------------------------------- atomic JSON


def test_write_json_refuses_silent_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    write_json(target, {"v": 1})
    with pytest.raises(OverwriteRefusedError):
        write_json(target, {"v": 2})
    assert read_json(target) == {"v": 1}  # original intact
    write_json(target, {"v": 2}, overwrite=True)
    assert read_json(target) == {"v": 2}


def test_write_json_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "a.json"
    write_json(target, {"v": 1})
    # The staging file is created beside the target and must be gone after the
    # rename; a leftover would accumulate on every save.
    siblings = sorted(p.name for p in target.parent.iterdir())
    assert siblings == ["a.json"]


def test_read_json_reports_corruption(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError) as info:
        read_json(target)
    assert info.value.code == "file_corrupt"


def test_jsonl_survives_truncation(tmp_path: Path) -> None:
    """A recording killed mid-write keeps everything already flushed."""
    target = tmp_path / "stream.jsonl"
    with JsonlWriter(target) as writer:
        for index in range(5):
            writer.write({"i": index})
    # Simulate a power cut in the middle of the last line.
    content = target.read_text(encoding="utf-8")
    target.write_text(content[:-6], encoding="utf-8")

    records = list(read_jsonl(target))
    assert len(records) == 4
    assert [r["i"] for r in records] == [0, 1, 2, 3]

    with pytest.raises(StorageError):
        list(read_jsonl(target, strict=True))


# -------------------------------------------------------------- checksums


def test_checksum_manifest_detects_tampering(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    target.write_bytes(b"original")
    manifest = checksum_manifest({"data.bin": target})
    assert not verify_checksum_manifest(manifest, tmp_path)

    target.write_bytes(b"modified")
    problems = verify_checksum_manifest(manifest, tmp_path)
    assert problems and problems[0]["issue"] == "checksum_mismatch"

    target.unlink()
    problems = verify_checksum_manifest(manifest, tmp_path)
    assert problems[0]["issue"] == "missing"


def test_payload_hash_is_order_independent() -> None:
    assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})
    assert hash_payload({"a": 1}) != hash_payload({"a": 2})


# -------------------------------------------------------------- workspace


def test_create_and_open_project(dataset_root: Path) -> None:
    workspace = ProjectWorkspace.create(dataset_root, "Deneme")
    assert workspace.project_file.is_file()
    assert workspace.label_schema_file.is_file()
    reopened = ProjectWorkspace.open(workspace.root)
    assert reopened.project.name == "Deneme"
    assert ProjectWorkspace.discover(dataset_root) == [workspace.root]


def test_open_non_project_directory_fails(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        ProjectWorkspace.open(tmp_path)
    assert info.value.code == "project_not_found"
    assert info.value.remedy


def test_participant_codes_are_sequential(workspace: ProjectWorkspace) -> None:
    codes = [workspace.create_participant().code for _ in range(3)]
    assert codes == ["P0001", "P0002", "P0003"]


def test_participant_code_contains_no_pii(workspace: ProjectWorkspace) -> None:
    participant = workspace.create_participant()
    participant.notes = "arbitrary note"
    workspace.save_participant(participant)
    # The directory name is the pseudonymous code and nothing else.
    assert workspace.participant_dir(participant.participant_id).name == "P0001"


def test_workspace_rejects_path_traversal(workspace: ProjectWorkspace) -> None:
    with pytest.raises(ValidationError) as info:
        workspace.participant_dir("../../etc")
    assert info.value.code == "unsafe_identifier"


def test_session_and_take_roundtrip(workspace, participant, session) -> None:
    loaded_session = workspace.load_session(
        participant.participant_id, session.session_id
    )
    assert loaded_session.operator == "pytest"
    take, paths = workspace.prepare_take(session)
    assert paths.metadata.is_file()
    assert take.state is TakeState.RECORDING  # discoverable even if we crash now
    loaded = workspace.load_take(
        participant.participant_id, session.session_id, take.take_id
    )
    assert loaded.take_id == take.take_id


def test_prepare_take_never_reuses_a_directory(
    workspace, session, monkeypatch
) -> None:
    """Even a colliding identifier must refuse rather than overwrite a take."""
    first, first_paths = workspace.prepare_take(session)
    assert first_paths.metadata.is_file()

    # Force the next take to claim the identifier that is already on disk.
    monkeypatch.setattr(
        "kinecapture.domain.project.timestamped_id",
        lambda prefix, moment=None: first.take_id,
    )
    with pytest.raises(StorageError) as info:
        workspace.prepare_take(session)
    assert info.value.code == "take_exists"
    # The original take is untouched.
    assert workspace.load_take(
        first.participant_id, first.session_id, first.take_id
    ).take_id == first.take_id


def test_takes_get_distinct_directories(workspace, session) -> None:
    first, first_paths = workspace.prepare_take(session)
    second, second_paths = workspace.prepare_take(session)
    assert first.take_id != second.take_id
    assert first_paths.root != second_paths.root
    assert second.index_in_session == 2


# ---------------------------------------------------------- recording flow


def test_recording_produces_all_expected_files(workspace, session) -> None:
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=25, exercise="squat")
    service.shutdown()

    assert take is not None
    assert take.state is TakeState.FINALIZED
    paths = workspace.take_paths(take)
    assert paths.metadata.is_file()
    assert paths.skeleton_stream.is_file()
    assert paths.quality.is_file()
    assert paths.checksums.is_file()
    assert take.metrics.frames_written >= 25
    assert take.metrics.duration_s > 0
    assert take.metrics.tracking_coverage > 0
    assert "skeleton_stream" in take.files


def test_recorded_checksums_verify(workspace, session) -> None:
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=15)
    service.shutdown()
    paths = workspace.take_paths(take)
    manifest = read_json(paths.checksums)
    assert not verify_checksum_manifest(manifest, paths.root)


def test_skeleton_stream_has_a_self_describing_header(workspace, session) -> None:
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=12)
    service.shutdown()

    records = list(read_jsonl(workspace.take_paths(take).skeleton_stream))
    header = records[0]
    assert header["record"] == "header"
    # The stream must be readable without take.json.
    assert header["skeleton_format"] == "mock_16"
    assert header["origin"] == "synthetic"
    assert header["coordinate_system"]
    assert header["length_unit"]
    assert header["schema_version"]


def test_annotation_edits_never_touch_take_metadata(workspace, session) -> None:
    from kinecapture.annotations.repository import AnnotationRepository

    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=20)
    service.shutdown()

    paths = workspace.take_paths(take)
    before = paths.metadata.read_bytes()

    repository = AnnotationRepository(workspace, take, frame_count=20)
    sample = repository.create_sample(2, 15)
    repository.label_sample(sample.sample_id, exercise="squat")
    repository.save()

    assert paths.segments.is_file()
    assert paths.metadata.read_bytes() == before, (
        "labelling rewrote take.json - curation must stay in the sidecar"
    )


def test_marker_is_stored_in_both_stream_and_metadata(workspace, session) -> None:
    import time

    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    service.start_preview()
    service.start_recording(workspace, session)
    deadline = time.time() + 10.0
    while service.recorded_frame_count < 5 and time.time() < deadline:
        time.sleep(0.005)
    service.add_marker("rep")
    while service.recorded_frame_count < 15 and time.time() < deadline:
        time.sleep(0.005)
    take = service.stop_recording()
    service.shutdown()

    assert take.markers, "marker missing from take metadata"
    records = list(read_jsonl(workspace.take_paths(take).skeleton_stream))
    assert any(r.get("record") == "marker" for r in records)


# -------------------------------------------------------- partial recovery


def test_partial_take_is_discoverable_and_recoverable(workspace, session) -> None:
    """A recording interrupted by a crash keeps its frames and says it is partial."""
    from kinecapture.recording.take_writer import TakeWriter

    take, paths = workspace.prepare_take(session)
    take.skeleton_format = "mock_16"
    writer = TakeWriter(workspace, take, paths, write_proxy_video=False)

    backend = paced_backend(width=64, height=48)
    backend.connect()
    backend.start_preview()
    for _ in range(12):
        writer.write_frame(backend.grab_frame())
    backend.disconnect()
    # Simulate the process dying: streams are closed but finalize never runs.
    writer.close_streams()

    partials = workspace.find_partial_takes()
    assert [p.take_id for p in partials] == [take.take_id]

    recovered, frames = recover_partial_take(workspace, partials[0])
    assert frames == 12
    assert recovered.state is TakeState.PARTIAL
    assert recovered.metrics.frames_written == 12
    assert "Kurtarıldı" in recovered.notes


def test_aborted_recording_is_marked_partial(workspace, session) -> None:
    backend = paced_backend(width=64, height=48)
    service = CaptureService(backend)
    service.connect()
    service.start_preview()
    service.start_recording(workspace, session)
    import time

    deadline = time.time() + 10.0
    while service.recorded_frame_count < 8 and time.time() < deadline:
        time.sleep(0.005)
    take = service.stop_recording(abort_reason="test kesintisi")
    service.shutdown()

    assert take.state is TakeState.PARTIAL
    assert "test kesintisi" in take.notes
    # The frames written before the interruption are still readable.
    loaded = load_take(workspace, take, with_video=False)
    assert loaded.frame_count >= 8


def test_shutdown_during_recording_finalizes_safely(workspace, session) -> None:
    """Closing the app mid-recording must not lose what was already captured."""
    import time

    backend = paced_backend(width=64, height=48)
    service = CaptureService(backend)
    service.connect()
    service.start_preview()
    service.start_recording(workspace, session)
    deadline = time.time() + 10.0
    while service.recorded_frame_count < 10 and time.time() < deadline:
        time.sleep(0.005)
    service.shutdown()

    takes = workspace.list_takes()
    assert len(takes) == 1
    assert takes[0].state is TakeState.PARTIAL
    assert takes[0].metrics.frames_written >= 10


def test_discard_take_requires_exact_confirmation(workspace, session) -> None:
    take, paths = workspace.prepare_take(session)
    with pytest.raises(ValidationError) as info:
        workspace.discard_take(take, confirm_take_id="wrong")
    assert info.value.code == "discard_confirmation_mismatch"
    assert paths.root.is_dir(), "data was removed despite a failed confirmation"

    workspace.discard_take(take, confirm_take_id=take.take_id)
    assert not paths.root.exists()
