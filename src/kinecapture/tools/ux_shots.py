"""Screenshots of the real, maximised Studio window, over synthetic data.

The 15 September brief asks for visual evidence taken the way the product is
actually used: the real Windows platform plugin, a maximised window on the
real desktop, and the real ``QtTaskRunner``. ``offscreen`` reports no font
families at all, so anything measured there is measured against tofu boxes -
see ``tests/test_studio_shell_gui.py::has_real_fonts``.

Everything this tool touches is its own. It builds a throwaway identity
database, a throwaway dataset root and a throwaway window-state file under the
output folder, records from the **mock** backend, and never opens a camera or
reads the user's own data or preferences.

    python -m kinecapture.tools.ux_shots --output C:\\temp\\kc-shots

Nothing here is part of the application; it is a way of producing the evidence
a visual review needs without a person clicking through eight screens twice.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

#: The throwaway sandbox account's password: made per run, never a literal
#: shipped in the package (release gate B2 scan, 24 September 2026).
_DEMO_PASSWORD = secrets.token_urlsafe(12)

#: Must be decided before Qt is imported, and this tool exists to *not* be
#: offscreen.
os.environ.setdefault("QT_QPA_PLATFORM", "windows")


def _record_take(workspace, session, *, frames: int = 90):
    """One synthetic take, written the way the recorder writes one."""
    from kinecapture.camera.mock import MockCameraBackend
    from kinecapture.recording.take_writer import TakeWriter

    profile = session.capture_profile
    backend = MockCameraBackend(
        width=640, height=360, fps=30, seed=7, profile=profile, real_time=False
    )
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(
        session, origin=backend.origin, camera_info=info
    )
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(frames):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()
    return take, paths


def _process(paths):  # noqa: ANN001
    """Run the offline pass in-process, with an anchor so a subject exists."""
    import numpy as np

    from kinecapture.core.jsonio import write_json
    from kinecapture.processing import ProcessingConfig, process_take
    from kinecapture.processing.sources import SyntheticSource

    config = ProcessingConfig(store_depth=False, store_proxy=True)
    take_json = paths.root / "take.json"
    from kinecapture.core.jsonio import read_json
    from kinecapture.domain.project import Take

    take = Take.from_dict(read_json(take_json))
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(
        paths.raw_dir / "subject_anchors.json",
        [
            {
                "camera_timestamp_ns": packet.camera_timestamp_ns,
                "source_resolution": list(packet.resolution),
                "point_xy": np.nanmean(points, axis=0).tolist(),
                "bbox_xyxy": np.r_[
                    np.nanmin(points, axis=0), np.nanmax(points, axis=0)
                ].tolist(),
            }
        ],
    )
    source.close()
    return process_take(paths.root, config)


def _seed(config, *, frames: int):  # noqa: ANN001
    """A signed-in owner, a project, two participants and one processed take."""
    from kinecapture.domain.enums import ConsentStatus
    from kinecapture.identity.database import IdentityDatabase
    from kinecapture.identity.service import IdentityService

    database = IdentityDatabase(config.identity_db_path)
    database.initialize()
    identity = IdentityService(database)
    user = identity.create_initial_owner(
        first_name="UX", last_name="Denetim", title="",
        username="ux-denetim", password=_DEMO_PASSWORD,
    )
    workspace = identity.create_project(
        user, Path(config.dataset_root), "UX Denetimi 15 Eylül",
        description="Görsel kabul turu için sentetik proje",
    )
    first = workspace.create_participant(created_by_user_id=user.user_id)
    workspace.create_participant(created_by_user_id=user.user_id)
    session = workspace.create_session(
        first.participant_id,
        operator=user.full_name,
        operator_user_id=user.user_id,
        consent=ConsentStatus.GRANTED,
    )
    _take, paths = _record_take(workspace, session, frames=frames)
    run = _process(paths)
    return user, workspace, first, run


def _label(run: Path, workspace) -> None:  # noqa: ANN001
    """Two repetitions of one class, and two faults of one class.

    The brief asks the screenshots to show that a class keeps its colour, so
    the sample has to contain a repeat of each kind.
    """
    from kinecapture.studio.services.annotation_store import AnnotationStore
    from kinecapture.studio.services.review import ReviewSession

    schema = workspace.label_schema
    squat = schema.ensure_exercise("Squat")
    lunge = schema.ensure_exercise("Lunge")
    knee = schema.ensure_error_type("Diz içe kaçıyor")
    schema.ensure_error_type("Sırt yuvarlak")
    workspace.save_label_schema(schema)

    with ReviewSession.open(run) as review:
        store = AnnotationStore(
            take_dir=review.take_dir,
            document=review.empty_document(),
            annotator="UX Denetim",
            resolve=review.dataset.position_of_anchor,
            anchor_at=review.dataset.anchor_at,
            frames=review.frames,
            known_exercises=schema.exercise_codes(),
            known_error_classes=schema.error_type_codes(),
        )
        last = review.frames - 1
        spans = [
            (int(last * 0.05), int(last * 0.28), squat.code),
            (int(last * 0.34), int(last * 0.58), squat.code),
            (int(last * 0.64), int(last * 0.92), lunge.code),
        ]
        for index, (start, end, code) in enumerate(spans):
            sample = store.add_movement(start, end)
            store.label_movement(sample.sample_id, code)
            if index < 2:
                interval = store.add_error(
                    sample.sample_id, start + 4, start + 14
                )
                store.label_error(
                    sample.sample_id, interval.interval_id, error_class=knee.code
                )
        store.flush()


def _settle(application, seconds: float = 0.6) -> None:  # noqa: ANN001
    """Let Qt lay out, load and paint before the picture is taken."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        application.processEvents()
        time.sleep(0.01)


def _grab(window, output: Path, name: str) -> Path:  # noqa: ANN001
    path = output / f"{name}.png"
    window.grab().save(str(path))
    return path


def capture(output: Path, *, frames: int = 90) -> list[Path]:
    """Produce the whole set. Returns the files written, in order."""
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication

    from kinecapture.core.config import AppConfig
    from kinecapture.studio.app import build_window
    from kinecapture.studio.services.messages import Message, Severity
    from kinecapture.studio.views.skeleton3d import default_surface_format
    from kinecapture.studio.views.theming import apply_application_theme

    output.mkdir(parents=True, exist_ok=True)
    config = AppConfig()
    config.dataset_root = output / "data"
    config.identity_db_path = output / "identity.sqlite3"
    config.log_dir = output / "logs"
    config.dataset_root.mkdir(parents=True, exist_ok=True)
    config.backend = "mock"
    config.theme = "dark"
    config.extra["preview_pose_enabled"] = False
    config.capture.min_free_disk_minutes = 0

    _user, workspace, participant, run = _seed(config, frames=frames)
    _label(run, workspace)

    QSurfaceFormat.setDefaultFormat(default_surface_format())
    application = QApplication.instance() or QApplication(sys.argv)
    apply_application_theme(config.theme)

    window = build_window(config, state_path=output / "window_state.json")
    window.showMaximized()
    _settle(application, 1.0)

    written: list[Path] = []
    # The gate, before anything is signed in: this is where the institution
    # leads, so it is part of the evidence.
    written.append(_grab(window, output, "00-giris-ekrani"))
    window.viewmodel.set_theme("light")
    _settle(application, 0.6)
    written.append(_grab(window, output, "00b-giris-ekrani-acik-tema"))
    window.viewmodel.set_theme("dark")
    _settle(application, 0.6)

    assert window.auth_viewmodel.sign_in("ux-denetim", _DEMO_PASSWORD)
    _settle(application, 0.6)
    size = window.size()
    print(f"pencere: {size.width()} x {size.height()} mantıksal piksel")
    ratio = window.devicePixelRatioF()
    print(f"cihaz piksel oranı: {ratio} -> {int(size.width()*ratio)} x {int(size.height()*ratio)} fiziksel")

    # --- Projects, populated -------------------------------------------
    window.viewmodel.navigate("projects")
    _settle(application, 0.8)
    projects = window.viewmodel_for.get("projects")
    if projects is not None:
        projects.select_participant(participant.participant_id)
    _settle(application)
    written.append(_grab(window, output, "01-projeler-dolu"))

    # --- Capture, connected, then recording -----------------------------
    window.viewmodel.navigate("capture")
    _settle(application, 0.5)
    capture_vm = window.viewmodel_for.get("capture")
    if capture_vm is not None:
        capture_vm.connect()
        _settle(application, 1.2)
        written.append(_grab(window, output, "02-yakalama-bagli"))
        capture_vm.start_recording()
        _settle(application, 1.2)
        written.append(_grab(window, output, "03-yakalama-kayitta"))
        # The recording strip has to be there on another screen, too.
        window.viewmodel.navigate("processing")
        _settle(application, 0.8)
        written.append(_grab(window, output, "04-kayit-surerken-isleme"))
        capture_vm.stop_recording()
        _settle(application, 1.5)

    # --- Library, a version selected -------------------------------------
    window.viewmodel.navigate("library")
    _settle(application, 1.2)
    library = window.viewmodel_for.get("library")
    rows = library.rows.value if library is not None else ()
    if rows:
        library.select(rows[0])
    _settle(application, 0.6)
    written.append(_grab(window, output, "05-kutuphane-secili-surum"))

    # --- Labelling, a full timeline --------------------------------------
    if rows:
        window.pending_review = rows[0]
    window.viewmodel.navigate("review")
    _settle(application, 2.5)
    review = window.viewmodel_for.get("review")
    page = window.page("review")
    written.append(_grab(window, output, "06-etiketleme-dolu-timeline"))

    # Selected, hovered and mid-trim, so the three states can be compared.
    if review is not None and review.movements.value:
        first = review.movements.value[0]
        review.select_movement(first.sample_id)
        _settle(application, 0.4)
        written.append(_grab(window, output, "07-etiketleme-secili-aralik"))
        timeline = page.timeline
        x = timeline._frame_to_x(first.start) + 1
        y = int(timeline._lane_rects()["movements"].center().y())
        timeline._set_hover(first.sample_id, timeline._hit(_point(x, y))[1])
        _settle(application, 0.3)
        written.append(_grab(window, output, "08-etiketleme-hover-uc"))
        _drag_edge(timeline, first, application)
        written.append(_grab(window, output, "09-etiketleme-trim-suruklerken"))
        timeline._drag = None
        timeline.update()
        _settle(application, 0.3)

    # --- The notification, and the geometry either side of it -------------
    before = _rectangles(page, window)
    written.append(_grab(window, output, "10-bildirim-oncesi"))
    window.viewmodel.report(
        Message(
            headline="Ham kayıt kaydedildi · İskelet bekliyor",
            severity=Severity.INFO,
            detail="1231 kare, 41.0 sn. Hesaplamak için Verileri Hesapla ekranını kullanın.",
            code="awaiting_processing",
        )
    )
    _settle(application, 0.5)
    written.append(_grab(window, output, "11-bildirim-gorunurken"))
    after = _rectangles(page, window)
    print("bildirim öncesi/sonrası ana dikdörtgenler:")
    for name in sorted(before):
        mark = "aynı" if before[name] == after[name] else f"DEĞİŞTİ {before[name]} -> {after[name]}"
        print(f"  {name}: {before[name]}  {mark}")

    # --- Light theme ------------------------------------------------------
    window.viewmodel.set_theme("light")
    _settle(application, 0.8)
    written.append(_grab(window, output, "12-acik-tema-etiketleme"))
    window.viewmodel.navigate("settings")
    _settle(application, 0.8)
    written.append(_grab(window, output, "13-acik-tema-ayarlar"))
    window.viewmodel.navigate("dataset")
    _settle(application, 1.0)
    written.append(_grab(window, output, "14-acik-tema-veri-seti"))
    window.viewmodel.set_theme("dark")
    _settle(application, 0.8)
    window.viewmodel.navigate("export")
    _settle(application, 1.0)
    written.append(_grab(window, output, "15-disa-aktarim"))
    window.viewmodel.navigate("processing")
    _settle(application, 0.8)
    written.append(_grab(window, output, "16-verileri-hesapla"))

    window.close()
    _settle(application, 0.3)
    return written


def _point(x: float, y: int):  # noqa: ANN201
    from PySide6.QtCore import QPoint

    return QPoint(int(x), int(y))


def _drag_edge(timeline, row, application) -> None:  # noqa: ANN001
    """Put the timeline into the middle of a trim, so the badge is on screen."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    y = int(timeline._lane_rects()["movements"].center().y())
    start_x = timeline._frame_to_x(row.start) + 1
    end_x = start_x + 40

    def event(kind, x):  # noqa: ANN001
        local = QPointF(x, y)
        return QMouseEvent(
            kind, local, local,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    timeline.mousePressEvent(event(QMouseEvent.Type.MouseButtonPress, start_x))
    timeline.mouseMoveEvent(event(QMouseEvent.Type.MouseMove, end_x))
    _settle(application, 0.3)


def _rectangles(page, window) -> dict[str, tuple]:  # noqa: ANN001
    """Where the main content rectangles are, in window coordinates."""
    found: dict[str, tuple] = {}
    for name in ("viewer", "skeleton", "timeline"):
        widget = getattr(page, name, None)
        if widget is None:
            continue
        origin = widget.mapTo(window, widget.rect().topLeft())
        found[name] = (origin.x(), origin.y(), widget.width(), widget.height())
    return found


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Görüntülerin yazılacağı klasör"
    )
    parser.add_argument("--frames", type=int, default=90)
    arguments = parser.parse_args(argv)
    written = capture(arguments.output, frames=arguments.frames)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - a tool, not a library
    raise SystemExit(main())
