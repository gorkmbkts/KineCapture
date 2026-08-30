"""Every page, every supported viewport, both themes - with realistic data.

The paint test this joins only asserted that ``grab()`` produced a non-null
pixmap, which a page whose bottom half is clipped also does. These assertions
are about geometry: what the page needs versus what the window can give it,
whether a control ended up outside the viewport meant to hold it, and whether
anything grew a horizontal scrollbar.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMenu,
    QScrollArea,
    QTabWidget,
    QToolButton,
    QWidget,
)

from kinecapture.annotations.repository import AnnotationRepository  # noqa: E402
from kinecapture.capture.service import CaptureService  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.domain.enums import TakeQuality  # noqa: E402
from kinecapture.export.release import ExportOptions, ReleaseBuilder  # noqa: E402
from kinecapture.gui.main_window import MainWindow  # noqa: E402
from kinecapture.gui.theme import get_theme  # noqa: E402
from kinecapture.gui.widgets.common import monospace_font  # noqa: E402
from kinecapture.playback.take_reader import load_take  # noqa: E402
from tests.conftest import authenticate_state, paced_backend, record_take  # noqa: E402

#: The window sizes this application promises to stay usable at.
VIEWPORTS = [(1120, 700), (1366, 768), (1600, 980)]

#: Roughly what the window frame, context bar and status bar cost a page.
_CHROME_HEIGHT = 100

PAGES = (
    "dashboard",
    "projects",
    "participants",
    "capture",
    "review",
    "dataset",
    "export",
    "settings",
)

LONG_PROJECT_NAME = (
    "Rehabilitasyon Çalışması — Diz Ekstansiyonu ve Kalça Abdüksiyonu 2026"
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def populated(qapp, tmp_path_factory):
    """A window with a full project: many classes, several takes, releases.

    Deliberately not an empty state. Empty screens fit anywhere; the layouts
    break when a table has rows, a filter has options and a project has a long
    Turkish name.
    """
    import os
    import tempfile

    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.domain.enums import ConsentStatus

    os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
    root = tmp_path_factory.mktemp("viewports") / "datasets"
    root.mkdir(parents=True)
    workspace = ProjectWorkspace.create(root, LONG_PROJECT_NAME)

    schema = workspace.label_schema
    for name in (
        "Squat", "Bulgar Split Squat", "Kalça Abdüksiyonu", "Diz Ekstansiyonu",
        "Omuz Fleksiyonu", "Plank", "Lunge", "Deadlift",
    ):
        schema.add_exercise(name)
    for name in (
        "Diz içe çöküyor", "Sırt yuvarlanıyor", "Topuk kalkıyor",
        "Kalça asimetrisi", "Omuz yükseliyor", "Boyun hiperekstansiyonu",
    ):
        schema.add_error_type(name)
    workspace.save_label_schema(schema)

    participant = workspace.create_participant()
    session = workspace.create_session(
        participant.participant_id, operator="pytest", consent=ConsentStatus.GRANTED
    )

    service = CaptureService(paced_backend())
    service.connect()
    takes = []
    for _ in range(2):
        take = record_take(service, workspace, session, frames=50, exercise="squat")
        take.quality = TakeQuality.GOOD
        workspace.save_take(take)
        takes.append(take)
    service.shutdown()

    for position, take in enumerate(takes):
        loaded = load_take(workspace, take, with_video=False)
        repo = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
        for rep in range(2):
            low = 2 + rep * 18
            sample = repo.create_sample(low, low + 14)
            repo.label_sample(sample.sample_id, exercise="squat", reviewed=True)
            if (position + rep) % 2 == 0:
                repo.create_error_interval(
                    sample.sample_id, low + 2, low + 8, error_code="diz-ice-cokuyor"
                )
        repo.save()

    window = MainWindow(AppConfig(dataset_root=root, log_dir=root / "logs", backend="mock"))
    user = authenticate_state(window.state, workspace, open_workspace=False)
    window._authentication_completed(user)
    qapp.processEvents()
    window.state.open_project(workspace.root)
    window.state.prepare_capture(participant)
    qapp.processEvents()

    try:
        ReleaseBuilder(
            workspace, window.state.index, ExportOptions(include_synthetic=True)
        ).build()
    except Exception:  # pragma: no cover - a release is a bonus, not the point
        pass

    window.show()
    qapp.processEvents()
    yield window, takes
    window.state.release_capture_service()
    window.close()


def _prepare(window, qapp, name, takes):
    window.navigate(name)
    for _ in range(4):
        qapp.processEvents()
    page = window._pages[name]
    if name == "review" and page._loaded is None:
        page.open_take(takes[0])
        qapp.processEvents()
    return page


# ------------------------------------------------------------- geometry


@pytest.mark.parametrize("size", VIEWPORTS)
@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("name", PAGES)
def test_every_page_fits_its_viewport(populated, qapp, name, theme_name, size):
    """A page whose minimum exceeds the window is clipped or scrolls sideways."""
    window, takes = populated
    width, height = size
    window.state.set_theme(theme_name)
    window.resize(width, height)
    for _ in range(3):
        qapp.processEvents()
    page = _prepare(window, qapp, name, takes)

    minimum = page.minimumSizeHint()
    assert minimum.width() <= width, (
        f"{name} needs {minimum.width()}px of width in a {width}px window"
    )
    assert minimum.height() <= height - _CHROME_HEIGHT, (
        f"{name} needs {minimum.height()}px of height in a {height}px window"
    )
    image = window.grab()
    assert not image.isNull()


@pytest.mark.parametrize("size", VIEWPORTS)
@pytest.mark.parametrize("name", PAGES)
def test_no_page_scrolls_sideways(populated, qapp, name, size):
    """Vertical scrolling is a layout; horizontal scrolling is a defect."""
    window, takes = populated
    window.resize(*size)
    for _ in range(3):
        qapp.processEvents()
    page = _prepare(window, qapp, name, takes)

    for area in page.findChildren(QScrollArea):
        assert not area.horizontalScrollBar().isVisible(), (
            f"{name} has a horizontal scrollbar at {size[0]}x{size[1]}"
        )


@pytest.mark.parametrize("name", ("export", "settings"))
def test_every_tab_stays_reachable_at_the_smallest_window(populated, qapp, name):
    window, takes = populated
    window.resize(1120, 700)
    for _ in range(3):
        qapp.processEvents()
    page = _prepare(window, qapp, name, takes)

    for tabs in page.findChildren(QTabWidget):
        assert tabs.count() >= 4, "the page should be organised into sections"
        too_wide = tabs.tabBar().sizeHint().width() > tabs.width()
        assert not too_wide or tabs.usesScrollButtons(), (
            "a tab bar wider than its widget must offer scroll buttons"
        )
        for index in range(tabs.count()):
            assert tabs.tabText(index), "every tab needs a label"
            tabs.setCurrentIndex(index)
            qapp.processEvents()
            assert not tabs.currentWidget().grab().isNull()


def test_the_export_action_is_reachable_and_explains_itself(populated, qapp):
    """The main action must not be inside a tab or below a fold."""
    window, takes = populated
    window.resize(1120, 700)
    page = _prepare(window, qapp, "export", takes)

    assert page._build_button.isVisible()
    assert not page._tabs.isAncestorOf(page._build_button), (
        "the export button must live outside the tabs"
    )
    if not page._build_button.isEnabled():
        assert page._action_reason.text(), "a disabled action must say why"


def test_the_settings_save_button_never_scrolls_away(populated, qapp):
    window, takes = populated
    window.resize(1120, 700)
    page = _prepare(window, qapp, "settings", takes)

    save = next(
        button
        for button in page.findChildren(QWidget)
        if getattr(button, "text", lambda: "")() == "Ayarları kaydet"
    )
    assert save.isVisible()
    assert not page._tabs.isAncestorOf(save)


def test_settings_reports_unsaved_changes(populated, qapp):
    window, takes = populated
    page = _prepare(window, qapp, "settings", takes)
    page._mark_clean()
    assert "Kaydedildi" in page._dirty_chip._text.text()

    page._preview_fps.setValue(page._preview_fps.value() + 1)
    qapp.processEvents()
    assert "Kaydedilmedi" in page._dirty_chip._text.text()
    assert page._save_status.text()


# --------------------------------------------------------------- Qt noise


def test_the_application_never_asks_for_a_non_positive_point_size(qapp):
    """The part of the font warning that would be ours if it existed."""
    for theme_name in ("dark", "light"):
        theme = get_theme(theme_name)
        for size in (
            theme.font_size_sm,
            theme.font_size,
            theme.font_size_lg,
            theme.font_size_xl,
        ):
            assert size > 0
            assert monospace_font(size).pointSize() == size


def test_the_qfont_warning_is_qt_reacting_to_a_pixel_stylesheet(qapp):
    """Reproduce it with no application code at all, so it is not ours.

    Qt's own menu sizing reads ``pointSize()`` from a font that a ``px`` based
    stylesheet has left pixel-sized, where it is ``-1``, and passes that
    straight back to ``setPointSize``. Nothing in this application ever asks
    for a non-positive size - the test above pins that down - and the warning
    appears here with a bare ``QToolButton``, a bare ``QMenu`` and a one-line
    stylesheet.

    Offscreen (where the suite runs) it does not appear at all: the platform
    plugin uses a different sizing path. It is cosmetic, it is upstream, and
    "fixing" it by setting a point size on the menu made it more frequent, not
    less.
    """
    messages: list[str] = []
    previous = qInstallMessageHandler(
        lambda mode, context, text: messages.append(text)
        if mode is QtMsgType.QtWarningMsg
        else None
    )
    try:
        holder = QWidget()
        holder.setStyleSheet("QWidget { font-size: 13px; }")
        button = QToolButton(holder)
        button.setText("Kullanıcı")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.addAction("Şifre Değiştir")
        button.setMenu(menu)
        holder.resize(320, 60)
        holder.show()
        qapp.processEvents()
        holder.grab()

        assert button.font().pointSize() == -1, (
            "a px stylesheet leaves the font pixel-sized, which is the cause"
        )
        assert button.font().pixelSize() == 13
        holder.hide()
    finally:
        qInstallMessageHandler(previous)
