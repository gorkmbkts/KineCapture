"""The acceptance evidence: a real maximised window, real fonts, real GL.

Screenshots and geometry for every claim the report makes. Nothing here writes
to the user's data: the version is opened read-only and the application's own
state is sandboxed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QPushButton, QWidget

from kinecapture.studio.services.messages import Action, Message, Severity
from real_window import BEFORE, TAKE, newest_run, open_version, open_window, settle

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(tempfile.mkdtemp(prefix="kc-evidence-"))
report: dict = {"shots": [], "measurements": {}}


def shot(window, name: str, note: str) -> None:
    path = OUT / f"{name}.png"
    window.grab().save(str(path))
    report["shots"].append({"file": path.name, "note": note})
    print(f"  shot {name}: {note}")


def visible_widgets(root: QWidget) -> list[QWidget]:
    return [
        w
        for w in root.findChildren(QWidget)
        if w.isVisible() and w.width() > 0 and w.height() > 0
    ]


def overlaps(root: QWidget) -> list[str]:
    """Pairs of sibling controls whose rectangles intersect."""
    from PySide6.QtCore import QRect

    found: list[str] = []
    for parent in [root, *root.findChildren(QWidget)]:
        if not parent.isVisible():
            continue
        kids = [
            k
            for k in parent.children()
            if isinstance(k, QWidget) and k.isVisible() and k.width() and k.height()
        ]
        for index, first in enumerate(kids):
            for second in kids[index + 1 :]:
                a, b = QRect(first.geometry()), QRect(second.geometry())
                if a.intersects(b):
                    area = a.intersected(b)
                    if area.width() > 2 and area.height() > 2:
                        found.append(
                            f"{type(first).__name__}({first.objectName() or first.accessibleName()})"
                            f" ∩ {type(second).__name__}"
                            f"({second.objectName() or second.accessibleName()})"
                            f" = {area.width()}x{area.height()}"
                        )
    return found


def scroll_ranges(root: QWidget) -> list[str]:
    out = []
    for area in root.findChildren(QAbstractScrollArea):
        if not area.isVisible():
            continue
        v = area.verticalScrollBar().maximum()
        h = area.horizontalScrollBar().maximum()
        if v or h:
            out.append(f"{type(area).__name__}: v={v} h={h}")
    return out


def clipped_buttons(root: QWidget) -> list[str]:
    out = []
    for button in root.findChildren(QPushButton):
        if button.isHidden() or not button.text():
            continue
        needed = button.fontMetrics().horizontalAdvance(button.text())
        if button.width() < needed + 8:
            out.append(f"{button.text()!r}: {button.width()}px for {needed}px")
    return out


app, window = open_window(SCRATCH)
print("window:", window.width(), "x", window.height())
report["measurements"]["window"] = [window.width(), window.height()]

# --------------------------------------------------------------- 1. the gate
settle(app, 0.4)
shot(window, "01-projects-first", "Her açılış Projeler; diğer sekmeler kapalı")
gates = {
    item.key: window.viewmodel.gate_reason(item.key)
    for item in window.viewmodel.destinations
}
report["measurements"]["gates_without_project"] = {k: v for k, v in gates.items() if v}
print("  gated without a project:", sorted(k for k, v in gates.items() if v))

seen: list[Message] = []
window.viewmodel.message.subscribe(seen.append)
assert window.viewmodel.navigate("capture") is False
settle(app, 0.5)
report["measurements"]["capture_refusal"] = seen[-1].headline if seen else ""
shot(window, "02-capture-gated", "Proje yokken Yakalama reddediliyor, tek kart")

# A project and a participant, the way a person makes them.
projects = window.viewmodel_for["projects"]
projects.reload_projects()
assert projects.create_project("Kabul 21 Eylül")
settle(app, 0.6)
before_participant = window.viewmodel.gate_reason("capture")
assert projects.create_participant()
settle(app, 0.6)
report["measurements"]["capture_gate_before_participant"] = before_participant
report["measurements"]["capture_gate_after_participant"] = window.viewmodel.gate_reason(
    "capture"
)
print("  capture gate before/after participant:",
      repr(before_participant), "→", repr(window.viewmodel.gate_reason("capture")))

# ------------------------------------------------------------ 2. the capture
assert window.viewmodel.navigate("capture")
settle(app, 0.8)
# The cards from making the project are evidence of their own; they are not
# what these shots are about, and a stack of them sits over the console.
window.toasts.clear()
settle(app, 0.3)
capture = window.page("capture")
capture.apply_stage_geometry()
settle(app, 0.5)


def capture_positions() -> dict:
    out = {}
    for name in (
        "target_value", "subject_label", "clear_subject_button", "mode_state",
        "countdown_box", "duration_box", "mirror_box", "guides_box",
        "framing_label", "framing_advice", "alert_label", "pose_note",
        "status_details_button", "record_button", "marker_button",
    ):
        w = getattr(capture, name, None)
        if isinstance(w, QWidget):
            p = w.mapTo(capture, w.rect().topLeft())
            out[name] = [p.x(), p.y(), w.width(), w.height()]
    return out


from kinecapture.studio.services.framing import Framing
from kinecapture.studio.viewmodels.capture import Alert, AlertLevel

base = capture_positions()
moves: dict[str, int] = {}
states = [
    ("no_person", Framing(state="no_person", text="Kadrajda kimse yok")),
    ("ok", Framing(state="ok", text="Kadraj tamam")),
    ("cut", Framing(state="cut", text="Ayaklar kadraj dışında",
                    advice="Kamerayı biraz geriye alın ya da bir adım geri gidin.")),
    ("tight", Framing(state="tight", text="Kadraj dar")),
    ("crowded", Framing(state="crowded", text="Kadrajda birden fazla kişi var")),
]
for name, framing in states:
    capture._show_framing(framing)
    settle(app, 0.25)
    moved = sum(1 for k, v in capture_positions().items() if v != base[k])
    moves[f"framing:{name}"] = moved
    shot(window, f"03-capture-{name}", f"Kadraj: {name}; hareket eden denetim {moved}")

capture._show_alerts((
    Alert("recording_loss", AlertLevel.ERROR, "12 kare kaydedilemedi. Bu veri kaybıdır."),
    Alert("disk", AlertLevel.WARNING, "Diskte yaklaşık 4 dakikalık yer kaldı."),
))
settle(app, 0.3)
moves["alerts:two"] = sum(1 for k, v in capture_positions().items() if v != base[k])
shot(window, "04-capture-alerts", f"İki uyarı; hareket eden denetim {moves['alerts:two']}")
capture._show_alerts(())
settle(app, 0.3)
moves["alerts:none"] = sum(1 for k, v in capture_positions().items() if v != base[k])


class _Anchor:
    camera_timestamp_ns = 1_700_000_000_000


def _pick_someone(capture, app) -> bool:
    """Click on whoever the light preview found, the way an operator does."""
    for _ in range(40):
        service = capture.viewmodel.service.service
        preview = getattr(service, "pose_preview", None)
        people = getattr(preview, "people", ()) if preview is not None else ()
        if people:
            box = people[0].bbox
            x = float((box[0][0] + box[1][0]) / 2)
            y = float((box[0][1] + box[1][1]) / 2)
            if capture.viewmodel.select_subject(x, y):
                return True
        settle(app, 0.2)
    return False


capture._show_anchor(_Anchor())
settle(app, 0.3)
moves["subject:chosen"] = sum(1 for k, v in capture_positions().items() if v != base[k])
capture._show_anchor(None)
settle(app, 0.3)
moves["subject:cleared"] = sum(1 for k, v in capture_positions().items() if v != base[k])
# A real recording on the synthetic camera, because "no scrolling and no
# clipped control while recording" is a claim about the recording state.
def synthetic_pose(packet):
    """A known selection box for the mock image, not a pose-model result.

    The mock camera renders no human for CPU inference to detect. Keep joints
    missing; only supply the explicit synthetic box needed to exercise the
    normal operator-selection and recording paths.
    """
    import numpy as np
    from kinecapture.preview.pose import PosePreview, PreviewPerson

    width, height = packet.resolution
    person = PreviewPerson(
        bbox=np.asarray([[width * .2, height * .1], [width * .8, height * .9]]),
        points=np.full((33, 2), np.nan),
        confidence=np.zeros(33),
    )
    return PosePreview(packet, (person,))


assert window.viewmodel.session.config.backend.value == "mock"
capture.viewmodel.service._pose_factory = lambda: synthetic_pose
report["measurements"]["capture_backend"] = "mock"
report["measurements"]["selection_evidence"] = "synthetic bounding box; no pose inference"
capture.viewmodel.connect()
deadline = time.time() + 15.0
while time.time() < deadline and not capture.viewmodel.metrics.value.connected:
    settle(app, 0.2)
    capture.viewmodel.refresh()
if capture.viewmodel.metrics.value.connected:
    settle(app, 0.8)
    after_connect = capture_positions()
    moved_names = {k: (base[k], after_connect[k]) for k in base if after_connect[k] != base[k]}
    moves["connected"] = len(moved_names)
    report["measurements"]["moved_on_connect"] = moved_names
    shot(window, "05-capture-connected", f"Kamera bağlı; hareket eden denetim {moves['connected']}")
    picked = _pick_someone(capture, app)
    assert picked, "Synthetic subject selection failed"
    moves["subject:picked"] = sum(1 for k, v in capture_positions().items() if v != base[k])
    started = capture.viewmodel.start_recording()
    assert started, "Recording must start before recording-state geometry is measured"
    settle(app, 1.5)
    capture.viewmodel.refresh()
    settle(app, 0.5)
    assert capture.viewmodel.metrics.value.recording
    assert capture.viewmodel.metrics.value.recorded_frames > 0
    report["measurements"]["recorded_frames"] = capture.viewmodel.metrics.value.recorded_frames
    moves["recording"] = sum(1 for k, v in capture_positions().items() if v != base[k])
    report["measurements"]["moved_on_recording"] = {
        k: [base[k], v] for k, v in capture_positions().items() if v != base[k]
    }
    report["measurements"]["recording_scroll"] = scroll_ranges(capture)
    report["measurements"]["recording_clipped"] = clipped_buttons(capture)
    report["measurements"]["recording_overlaps"] = overlaps(capture)
    shot(window, "06-capture-recording",
         f"Kayıt sürüyor · seçim {picked} · hareket eden denetim {moves['recording']}")
    capture.viewmodel.stop_recording()
    deadline = time.time() + 20.0
    while time.time() < deadline and capture.viewmodel.stopping.value:
        settle(app, 0.2)
    settle(app, 1.0)
    moves["stopped"] = sum(1 for k, v in capture_positions().items() if v != base[k])
    shot(window, "07-capture-stopped", f"Kayıt kapandı; hareket eden denetim {moves['stopped']}")
    report["measurements"]["recording_started"] = bool(started)
    capture.viewmodel.disconnect()
    settle(app, 0.5)
else:
    raise AssertionError("Synthetic camera did not connect")

report["measurements"]["capture_moves"] = moves
print("  capture moves:", moves)
print("  during recording - scroll:", report["measurements"].get("recording_scroll"),
      "clipped:", report["measurements"].get("recording_clipped"),
      "overlaps:", len(report["measurements"].get("recording_overlaps") or []))

stage = capture.stage_geometry
report["measurements"]["capture_stage"] = {
    "preview_width": stage.preview_width,
    "console_width": stage.console_width,
    "console_columns": stage.console_columns,
    "slack": stage.slack,
    "preview_height": capture.preview.height(),
    "ratio": round(stage.preview_width / max(1, capture.preview.height()), 4),
}
report["measurements"]["capture_scroll"] = scroll_ranges(capture)
report["measurements"]["capture_overlaps"] = overlaps(capture)
report["measurements"]["capture_clipped"] = clipped_buttons(capture)
print("  capture stage:", report["measurements"]["capture_stage"])
print("  capture scroll:", report["measurements"]["capture_scroll"],
      "overlaps:", len(report["measurements"]["capture_overlaps"]),
      "clipped:", report["measurements"]["capture_clipped"])

# ------------------------------------------------------------- 3. the labels
run = newest_run()
page, review = open_version(app, window, run)
settle(app, 0.8)
report["measurements"]["review_run"] = run.name
report["measurements"]["inspector_visible"] = page.side_tabs.isVisible()
report["measurements"]["inspector_toggle_enabled"] = (
    window.context_bar.inspector_button.isEnabled()
)
shot(window, "05-review-panel", "Sağ yardımcı panel görünür, düğme kalıcı diyor")

button = window.context_bar.inspector_button
for press in range(3):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    settle(app, 0.2)
report["measurements"]["inspector_after_three_clicks"] = page.side_tabs.isVisible()
window.viewmodel.navigate("projects"); settle(app, 0.3)
window.viewmodel.navigate("review"); settle(app, 0.4)
report["measurements"]["inspector_after_leaving"] = page.side_tabs.isVisible()

for key, name in (("camera", "06-review-camera"), ("labels", "07-review-labels"),
                  ("subject", "08-review-subject")):
    page.side_tabs.show_view(key)
    settle(app, 0.4)
    shot(window, name, f"Panel sekmesi: {key}")
    report["measurements"].setdefault("review_scroll", {})[key] = scroll_ranges(
        page.side_tabs
    )
    report["measurements"].setdefault("review_overlaps_by_tab", {})[key] = overlaps(page)
report["measurements"]["review_overlaps"] = [
    f"{key}: {problem}"
    for key, problems in report["measurements"]["review_overlaps_by_tab"].items()
    for problem in problems
]
report["measurements"]["preset_buttons"] = list(page.camera_panel.preset_buttons)
report["measurements"]["preset_menu"] = [
    a.text() for a in page.camera_panel.preset_actions.values()
]
print("  presets:", report["measurements"]["preset_buttons"],
      "| menu:", report["measurements"]["preset_menu"])

# ------------------------------------------------- 4. the recording, in view
fps = review.fps or 60.0
for label, seconds in (("8.12", 8.12), ("10.60", 10.6), ("11.25", 11.25),
                       ("20.00", 20.0), ("24.00", 24.0)):
    frame = min(review.frames - 1, int(round(seconds * fps)))
    page.viewmodel.seek(frame)
    settle(app, 0.6)
    joints = review.joints_3d(frame)
    present = bool(joints is not None and joints.size and
                   __import__("numpy").isfinite(joints).any())
    shot(window, f"09-review-{label.replace('.', '')}s",
         f"{label} sn (kare {frame}) · iskelet {'var' if present else 'YOK'}")
    report["measurements"].setdefault("skeleton_at", {})[label] = {
        "frame": frame, "present": present
    }
print("  skeleton at:", report["measurements"]["skeleton_at"])

# ----------------------------------------------------------- 5. the messages
window.toasts.clear(); settle(app, 0.3)
window.viewmodel.report(
    Message(
        headline="P0001 kaydı işlendi · notlarla.",
        severity=Severity.WARNING,
        detail=("1475 kareden 1473 tanesi eşleşti · Kayıt sırasındaki bazı kareler "
                "ham kaynakta eşleştirilemedi. · +3 not daha"),
        code="processing_done",
        technical={"issues": ["capture_frames_unmatched", "capture_timestamp_duplicated",
                              "source_frame_count_mismatch", "source_timestamp_gap"]},
        actions=(Action("review:x", "Etiketlemeyi aç", primary=True),
                 Action("goto:library", "Sürüm listesi")),
    )
)
settle(app, 0.5)
card = window.toasts.toasts[-1]
report["measurements"]["toast"] = {
    "size": [card.width(), card.height()],
    "clipped": clipped_buttons(card),
    "buttons": [b.text() for b in card.findChildren(QPushButton) if not b.isHidden()],
}
shot(window, "10-toast-actions", "Bildirim kartı: hiçbir eylem kırpılmadı")
print("  toast:", report["measurements"]["toast"])

QTest.mouseClick(card._details_button, Qt.MouseButton.LeftButton)
settle(app, 0.5)
report["measurements"]["toast_details"] = {
    "window_visible": card.details_visible,
    "chars": len(card.details_text),
}
shot(window, "11-toast-details", "Ayrıntılar ayrı pencerede, tam metin")
card._details_window.close()
settle(app, 0.3)

(OUT / "manifest.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("wrote", OUT / "manifest.json")
window.close()
