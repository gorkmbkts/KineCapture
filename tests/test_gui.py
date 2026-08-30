"""GUI construction, theming and page behaviour.

These run offscreen (``QT_QPA_PLATFORM=offscreen``, set in ``conftest.py``) and
never open a window or a camera. They check the things that actually break in a
Qt application: that every widget can be built, that both themes apply cleanly,
that navigation is vetoed while a recording is running, and that the numpy-to-Qt
conversions do not produce dangling buffers.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.domain.enums import HealthLevel  # noqa: E402
from kinecapture.gui.converters import (  # noqa: E402
    depth_to_qimage,
    placeholder_image,
    rgb_to_qimage,
)
from kinecapture.gui.icons import app_icon, get_icon, icon_names  # noqa: E402
from kinecapture.gui.theme import (  # noqa: E402
    DARK_THEME,
    LIGHT_THEME,
    available_themes,
    build_stylesheet,
    get_theme,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path):
    from kinecapture.gui.main_window import MainWindow
    from tests.conftest import authenticate_state

    config = AppConfig(dataset_root=tmp_path / "data", log_dir=tmp_path / "logs")
    window = MainWindow(config)
    user = authenticate_state(window.state)
    window._authentication_completed(user)
    yield window
    window.state.release_capture_service()
    window.close()
    window.deleteLater()


# ---------------------------------------------------------------- theming


def test_both_themes_are_complete() -> None:
    """Every colour token must be a real value in every theme."""
    for theme in (DARK_THEME, LIGHT_THEME):
        for name, value in theme.__dict__.items():
            if not isinstance(value, str) or name in ("name", "extra"):
                continue
            if value.startswith("#"):
                assert len(value) == 7, f"{theme.name}.{name} = {value!r}"
                int(value[1:], 16)  # raises if not hex


def test_stylesheet_builds_for_every_theme() -> None:
    for name in available_themes():
        css = build_stylesheet(get_theme(name))
        assert "QPushButton" in css
        assert ":hover" in css and ":disabled" in css and ":focus" in css


def test_health_colours_are_distinct() -> None:
    colours = {DARK_THEME.health_color(level) for level in HealthLevel}
    assert len(colours) == len(HealthLevel)


def test_health_presentation_pairs_colour_with_icon_and_word() -> None:
    from kinecapture.gui.widgets.common import HEALTH_PRESENTATION

    for level in HealthLevel:
        icon, word = HEALTH_PRESENTATION[level]
        assert icon in icon_names()
        assert word  # colour is never the only signal


# ------------------------------------------------------------------ icons


def test_every_icon_renders(qapp) -> None:
    for name in icon_names():
        icon = get_icon(name, DARK_THEME.text_primary, 18)
        assert not icon.isNull(), name
        assert not icon.pixmap(18, 18).isNull(), name


def test_app_icon_has_multiple_sizes(qapp) -> None:
    icon = app_icon(DARK_THEME.accent, DARK_THEME.bg_surface)
    assert len(icon.availableSizes()) >= 4


def test_icons_scale_for_high_dpi(qapp) -> None:
    pixmap = get_icon("capture", DARK_THEME.accent, 18).pixmap(18, 18)
    assert pixmap.width() >= 18


# ------------------------------------------------------------- converters


def test_rgb_conversion_owns_its_buffer(qapp) -> None:
    """The QImage must survive the source array being freed."""
    source = np.random.randint(0, 255, (32, 48, 3), dtype=np.uint8)
    image = rgb_to_qimage(source)
    expected = int(source[0, 0, 0])
    del source
    assert image.width() == 48 and image.height() == 32
    # Reading a pixel after the source is gone would crash on a borrowed buffer.
    assert (image.pixel(0, 0) >> 16) & 0xFF == expected


def test_rgb_conversion_rejects_bad_shape(qapp) -> None:
    with pytest.raises(ValueError):
        rgb_to_qimage(np.zeros((4, 4), dtype=np.uint8))


def test_depth_conversion_marks_missing_pixels(qapp) -> None:
    depth = np.full((16, 16), 2.0, dtype=np.float32)
    depth[0, 0] = np.nan
    image = depth_to_qimage(depth, DARK_THEME)
    assert image.width() == 16
    missing = image.pixel(0, 0)
    measured = image.pixel(8, 8)
    # A pixel with no depth must not be rendered as if it were a measurement.
    assert missing != measured


def test_depth_conversion_handles_all_nan(qapp) -> None:
    image = depth_to_qimage(np.full((8, 8), np.nan, dtype=np.float32), DARK_THEME)
    assert image.width() == 8


def test_placeholder_image(qapp) -> None:
    image = placeholder_image(64, 32, DARK_THEME)
    assert image.width() == 64 and image.height() == 32


# ------------------------------------------------------------- main window


def test_window_builds_every_page(window) -> None:
    from kinecapture.gui.main_window import _PAGES

    assert len(window._pages) == len(_PAGES)
    for key, _cls in _PAGES:
        assert key in window._pages
        assert window._pages[key].title


def test_navigation_activates_pages(window) -> None:
    for key in ("projects", "participants", "capture", "review", "dataset", "export"):
        window.navigate(key)
        assert window._current_key == key
        assert window._stack.currentWidget() is window._pages[key]


def test_theme_switch_applies_everywhere(window) -> None:
    window.state.set_theme("light")
    assert window.state.theme.name == "light"
    assert LIGHT_THEME.bg_base in window.styleSheet()
    window.state.set_theme("dark")
    assert DARK_THEME.bg_base in window.styleSheet()


def test_navigation_is_vetoed_during_recording(window, monkeypatch) -> None:
    """A running recording must not be abandoned by a stray page change."""
    capture_page = window._pages["capture"]
    window.navigate("capture")
    monkeypatch.setattr(capture_page, "can_leave", lambda: False)
    window.navigate("dataset")
    assert window._current_key == "capture"


def test_error_banner_shows_code_and_remedy(window) -> None:
    from kinecapture.core.errors import CameraError

    error = CameraError(
        "Kamera bulunamadı.", code="no_camera", remedy="USB bağlantısını kontrol edin."
    )
    window.state.report_error(error)
    # isVisible() is False for an unshown window; isVisibleTo() asks the
    # question that actually matters: would it show if the window were shown.
    assert window._banner.isVisibleTo(window)
    text = window._banner._text.text()
    assert "Kamera bulunamadı" in text
    assert "USB bağlantısını" in text
    assert "no_camera" in text
    # The user never sees a traceback.
    assert "Traceback" not in text


def test_context_bar_reflects_state(window, tmp_path) -> None:
    from kinecapture.dataset.workspace import ProjectWorkspace

    workspace = ProjectWorkspace.create(tmp_path / "data", "Bağlam Testi")
    window.state.identity.register_project(window.state.current_user, workspace)
    window.state.open_project(workspace.root)
    participant = workspace.create_participant()
    window.state.set_participant(participant)
    window._context.refresh()
    assert "Bağlam Testi" in window._context._chips["project"]._text.text()
    assert participant.code in window._context._chips["participant"]._text.text()


def test_nav_rail_collapses(window) -> None:
    initial = window._nav.width()
    window._nav.toggle()
    assert window._nav.width() < initial
    window._nav.toggle()
    assert window._nav.width() == initial


# -------------------------------------------------------------- widgets


def test_timeline_maps_positions(qapp) -> None:
    from kinecapture.gui.widgets.timeline import TimelineWidget

    timeline = TimelineWidget(DARK_THEME)
    timeline.resize(400, 140)
    timeline.set_take(300, fps=30.0, markers=[10, 200])
    assert timeline.frame_count == 300
    timeline.set_position(150)
    assert timeline.position == 150
    timeline.set_position(10**6)
    assert timeline.position == 299  # clamped, never out of range
    timeline.zoom_to_range(100, 140)
    timeline.zoom_to_fit()


def test_timeline_survives_an_empty_take(qapp) -> None:
    from kinecapture.gui.widgets.timeline import TimelineWidget

    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(0)
    timeline.set_position(5)
    assert timeline.position == 0


def test_skeleton_view_handles_missing_joints(qapp) -> None:
    from kinecapture.domain.enums import TrackingState
    from kinecapture.domain.models import BodyPose
    from kinecapture.gui.widgets.skeleton_view import SkeletonView3D
    from kinecapture.visualization.skeleton_spec import MOCK_SKELETON

    joints = np.zeros((16, 3), dtype=np.float32)
    joints[:, 1] = 1.0
    joints[:, 2] = 2.5
    joints[4] = np.nan  # a joint the tracker lost
    body = BodyPose(
        tracking_id=1,
        tracking_state=TrackingState.OK,
        body_format=MOCK_SKELETON.name,
        joint_positions_xyz=joints,
        joint_confidences=np.full(16, 0.9, dtype=np.float32),
    )
    view = SkeletonView3D(DARK_THEME)
    view.resize(320, 240)
    view.set_bodies([body], MOCK_SKELETON)
    view.set_preset("front")
    assert view.preset_key == "front"
    view.set_root_centered(False)
    view.set_root_centered(True)
    view.clear()


def test_video_view_accepts_frames_and_bodies(qapp) -> None:
    from kinecapture.gui.widgets.video_view import VideoView
    from kinecapture.visualization.skeleton_spec import MOCK_SKELETON

    view = VideoView(DARK_THEME)
    view.resize(320, 240)
    view.set_rgb(np.zeros((120, 160, 3), dtype=np.uint8))
    view.set_bodies([], MOCK_SKELETON)
    view.set_badge("KAYIT", DARK_THEME.danger)
    view.set_depth(np.full((120, 160), 2.0, dtype=np.float32))
    view.clear()


def test_field_row_shows_inline_validation(qapp) -> None:
    from PySide6.QtWidgets import QLineEdit

    from kinecapture.gui.widgets.common import FieldRow

    field = QLineEdit()
    row = FieldRow("Operatör", field, theme=DARK_THEME, required=True)
    row.set_error("Zorunlu alan.")
    assert field.property("state") == "invalid"
    row.clear_error()
    assert field.property("state") == ""


def test_status_chip_health_pairs_icon_and_text(qapp) -> None:
    from kinecapture.gui.widgets.common import StatusChip

    chip = StatusChip(theme=DARK_THEME)
    chip.set_health(HealthLevel.BLOCKED)
    assert chip._text.text() == "Engel"
    chip.set_health(HealthLevel.READY, "Kamera hazır")
    assert chip._text.text() == "Kamera hazır"
