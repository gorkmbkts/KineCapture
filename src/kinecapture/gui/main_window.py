"""Main window: navigation rail, context bar, pages and status bar.

Layout:

```text
+--------+--------------------------------------------------------------+
|  nav   |  context bar: project | participant | session | camera | disk |
|  rail  +--------------------------------------------------------------+
| (col-  |                                                              |
| lapsi- |                        active page                           |
|  ble)  |                                                              |
+--------+--------------------------------------------------------------+
| status bar: last message, backend, recording indicator                |
+-----------------------------------------------------------------------+
```

The window owns nothing about the domain: it routes navigation, renders shared
context from :class:`~kinecapture.gui.state.AppState`, and turns structured
errors into a readable banner while the traceback goes to the log.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.config import AppConfig
from kinecapture.core.errors import KineCaptureError
from kinecapture.core.logging import get_logger
from kinecapture.domain.enums import CaptureState
from kinecapture.gui.icons import app_icon, clear_icon_cache, get_icon, icon_size
from kinecapture.gui.pages.base import Page
from kinecapture.gui.pages.capture import CapturePage
from kinecapture.gui.pages.dashboard import DashboardPage
from kinecapture.gui.pages.dataset import DatasetPage
from kinecapture.gui.pages.export import ExportPage
from kinecapture.gui.pages.participants import ParticipantsPage
from kinecapture.gui.pages.projects import ProjectsPage
from kinecapture.gui.pages.review import ReviewPage
from kinecapture.gui.pages.settings import SettingsPage
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme, build_stylesheet
from kinecapture.gui.widgets.common import StatusChip, make_label, restyle

logger = get_logger(__name__)

#: (key, page class) in navigation order.
_PAGES = (
    ("dashboard", DashboardPage),
    ("projects", ProjectsPage),
    ("participants", ParticipantsPage),
    ("capture", CapturePage),
    ("review", ReviewPage),
    ("dataset", DatasetPage),
    ("export", ExportPage),
    ("settings", SettingsPage),
)

_NAV_EXPANDED_WIDTH = 208
_NAV_COLLAPSED_WIDTH = 56
_CONTEXT_REFRESH_MS = 1000


class NavigationRail(QFrame):
    """Collapsible left navigation."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavRail")
        self._theme = theme
        self._expanded = True
        self._buttons: dict[str, QPushButton] = {}
        self._labels: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_sm, theme.space_md, theme.space_sm, theme.space_md
        )
        layout.setSpacing(theme.space_xs)

        self._brand = QLabel(APP_NAME)
        self._brand.setProperty("role", "section")
        self._brand.setWordWrap(True)
        layout.addWidget(self._brand)

        self._version = make_label(f"v{APP_VERSION}", role="caption")
        layout.addWidget(self._version)
        layout.addSpacing(theme.space_md)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._items = QVBoxLayout()
        self._items.setSpacing(theme.space_xs)
        layout.addLayout(self._items)
        layout.addStretch(1)

        self._toggle = QPushButton()
        self._toggle.setProperty("role", "nav")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self.toggle)
        layout.addWidget(self._toggle)

        self.setFixedWidth(_NAV_EXPANDED_WIDTH)
        self._refresh_toggle()

    def add_page(self, key: str, title: str, icon: str) -> QPushButton:
        button = QPushButton(f"  {title}")
        button.setProperty("role", "nav")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(
            get_icon(icon, self._theme.text_secondary, 18, disabled_color=self._theme.text_muted)
        )
        button.setIconSize(icon_size(18))
        button.setToolTip(title)
        self._group.addButton(button)
        self._items.addWidget(button)
        self._buttons[key] = button
        self._labels[key] = title
        return button

    def set_active(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self.setFixedWidth(
            _NAV_EXPANDED_WIDTH if self._expanded else _NAV_COLLAPSED_WIDTH
        )
        for key, button in self._buttons.items():
            button.setText(f"  {self._labels[key]}" if self._expanded else "")
        self._brand.setVisible(self._expanded)
        self._version.setVisible(self._expanded)
        self._refresh_toggle()

    def _refresh_toggle(self) -> None:
        icon = "chevron-left" if self._expanded else "chevron-right"
        self._toggle.setIcon(get_icon(icon, self._theme.text_secondary, 16))
        self._toggle.setText("  Daralt" if self._expanded else "")
        self._toggle.setToolTip("Menüyü daralt" if self._expanded else "Menüyü genişlet")

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_toggle()
        restyle(self)


class ContextBar(QFrame):
    """The always-visible answer to "what am I working on right now?"."""

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self._state = state
        theme = state.theme

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            theme.space_md, theme.space_sm, theme.space_md, theme.space_sm
        )
        layout.setSpacing(theme.space_md)

        self._chips: dict[str, StatusChip] = {}
        for key, icon in (
            ("project", "project"),
            ("participant", "participants"),
            ("session", "clock"),
            ("camera", "camera"),
            ("disk", "disk"),
        ):
            chip = StatusChip("-", theme=theme, icon=icon)
            self._chips[key] = chip
            layout.addWidget(chip)
        layout.addStretch(1)

        self._recording = StatusChip("", theme=theme, icon="record")
        self._recording.setVisible(False)
        layout.addWidget(self._recording)

    def refresh(self) -> None:
        state = self._state
        theme = state.theme

        project = state.project
        self._chips["project"].set_status(
            project.name if project else "Proje yok",
            colour=theme.text_primary if project else theme.text_muted,
        )
        participant = state.participant
        self._chips["participant"].set_status(
            participant.code if participant else "Katılımcı yok",
            colour=theme.text_primary if participant else theme.text_muted,
        )
        session = state.session
        self._chips["session"].set_status(
            f"Oturum {session.session_id[-8:]}" if session else "Oturum yok",
            colour=theme.text_primary if session else theme.text_muted,
        )

        service = state.capture
        if service is None or service.state is CaptureState.DISCONNECTED:
            self._chips["camera"].set_status(
                f"{state.config.backend.value}: bağlı değil",
                icon="camera",
                colour=theme.text_muted,
            )
        else:
            info = service.camera_info
            name = info.display_name if info else service.backend_name
            colour = theme.synthetic if info and info.is_synthetic else theme.success
            self._chips["camera"].set_status(name, icon="camera", colour=colour)

        try:
            import shutil

            usage = shutil.disk_usage(state.config.dataset_root)
            free_gb = usage.free / 1024**3
            colour = (
                theme.danger
                if free_gb < 1
                else (theme.warning if free_gb < 10 else theme.text_secondary)
            )
            self._chips["disk"].set_status(
                f"{free_gb:.0f} GB boş", icon="disk", colour=colour
            )
        except OSError:
            self._chips["disk"].set_status("Disk ?", icon="disk", colour=theme.text_muted)

        recording = service is not None and service.is_recording
        self._recording.setVisible(recording)
        if recording and service is not None:
            elapsed = service.recording_elapsed_s
            self._recording.set_status(
                f"KAYIT  {int(elapsed // 60):02d}:{int(elapsed % 60):02d}  "
                f"({service.recorded_frame_count} kare)",
                icon="record",
                colour=theme.danger,
            )

    def apply_theme(self, theme: Theme) -> None:
        for chip in self._chips.values():
            chip.apply_theme(theme)
        self._recording.apply_theme(theme)
        restyle(self)


class ErrorBanner(QFrame):
    """Inline error strip. The user reads a sentence; the log keeps the trace."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            theme.space_md, theme.space_sm, theme.space_md, theme.space_sm
        )
        layout.setSpacing(theme.space_sm)

        self._icon = QLabel()
        layout.addWidget(self._icon)
        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._text, 1)

        close = QPushButton()
        close.setProperty("variant", "ghost")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(lambda: self.setVisible(False))
        self._close = close
        layout.addWidget(close)

        self.setVisible(False)
        self.apply_theme(theme)

    def show_error(self, error: KineCaptureError) -> None:
        text = f"<b>{error.message}</b>"
        if error.remedy:
            text += f"<br><span>{error.remedy}</span>"
        text += f"<br><span style='opacity:0.6'>Hata kodu: {error.code}</span>"
        self._text.setText(text)
        self.setVisible(True)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._icon.setPixmap(
            get_icon("warning", theme.danger, 18).pixmap(18, 18)
        )
        self._close.setIcon(get_icon("close", theme.text_secondary, 14))
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.bg_elevated};"
            f" border: 1px solid {theme.danger};"
            f" border-radius: {theme.radius_md}px; }}"
            f" QLabel {{ color: {theme.text_primary}; }}"
        )


class MainWindow(QMainWindow):
    """The application window."""

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = AppState(config, self)
        theme = self.state.theme

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon(theme.accent, theme.bg_surface))
        self.resize(1500, 940)
        self.setMinimumSize(1120, 700)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nav = NavigationRail(theme)
        root.addWidget(self._nav)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(
            theme.space_md, theme.space_md, theme.space_md, theme.space_sm
        )
        right_layout.setSpacing(theme.space_sm)

        self._context = ContextBar(self.state)
        right_layout.addWidget(self._context)

        self._banner = ErrorBanner(theme)
        right_layout.addWidget(self._banner)

        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack, 1)
        root.addWidget(right, 1)
        self.setCentralWidget(central)

        self._pages: dict[str, Page] = {}
        self._current_key = ""
        for key, page_class in _PAGES:
            page = page_class(self.state)
            self._pages[key] = page
            self._stack.addWidget(page)
            button = self._nav.add_page(key, page.title, page.icon)
            button.clicked.connect(lambda _=False, k=key: self.navigate(k))
            navigate_signal = getattr(page, "navigate_requested", None)
            if navigate_signal is not None:
                navigate_signal.connect(self.navigate)

        status = QStatusBar()
        self.setStatusBar(status)
        self._status_detail = make_label("", role="muted")
        status.addPermanentWidget(self._status_detail)

        self.state.error_raised.connect(self._banner.show_error)
        self.state.status_message.connect(self._show_status)
        self.state.theme_changed.connect(self._apply_theme)
        self.state.review_requested.connect(lambda _: self.navigate("review"))
        for signal in (
            self.state.project_changed,
            self.state.participant_changed,
            self.state.session_changed,
        ):
            signal.connect(lambda *_: self._context.refresh())

        self._context_timer = QTimer(self)
        self._context_timer.setInterval(_CONTEXT_REFRESH_MS)
        self._context_timer.timeout.connect(self._context.refresh)
        self._context_timer.start()

        self._install_shortcuts()
        self._apply_theme(theme)
        self.navigate("dashboard")
        self._restore_last_project()

    # ----------------------------------------------------------- navigation
    def navigate(self, key: str) -> None:
        """Switch pages, letting the current page veto (recording, export)."""
        if key == self._current_key:
            return
        page = self._pages.get(key)
        if page is None:
            return
        current = self._pages.get(self._current_key)
        if current is not None and not current.can_leave():
            self._nav.set_active(self._current_key)
            return
        if current is not None:
            current.on_deactivated()

        self._current_key = key
        self._stack.setCurrentWidget(page)
        self._nav.set_active(key)
        page.on_activated()
        self._context.refresh()

    def _install_shortcuts(self) -> None:
        for position, (key, _cls) in enumerate(_PAGES, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{position}"), self)
            shortcut.activated.connect(lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._nav.toggle)
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_current)

    def _refresh_current(self) -> None:
        self.state.refresh_dataset(force=True)
        page = self._pages.get(self._current_key)
        if page is not None:
            page.on_activated()

    # ---------------------------------------------------------------- theme
    def _apply_theme(self, theme: Theme) -> None:
        clear_icon_cache()
        app = self.window()
        self.setStyleSheet(build_stylesheet(theme))
        self.setWindowIcon(app_icon(theme.accent, theme.bg_surface))
        self._nav.apply_theme(theme)
        self._context.apply_theme(theme)
        self._banner.apply_theme(theme)
        for page in self._pages.values():
            page.apply_theme(theme)
        # Nav icons are tinted, so they must be re-rendered for the new palette.
        for key, (_key, page_class) in zip(self._pages, _PAGES):
            button = self._nav._buttons[key]
            button.setIcon(
                get_icon(
                    page_class.icon,
                    theme.text_secondary,
                    18,
                    disabled_color=theme.text_muted,
                )
            )
        app.update()

    # -------------------------------------------------------------- status
    def _show_status(self, message: str, timeout: int) -> None:
        self.statusBar().showMessage(message, timeout)
        service = self.state.capture
        backend = self.state.config.backend.value
        state_text = service.state.value if service else "DISCONNECTED"
        self._status_detail.setText(f"{backend} · {state_text}")

    # ------------------------------------------------------------- start-up
    def _restore_last_project(self) -> None:
        """Reopen the last project so closing and reopening keeps state."""
        last = self.state.config.last_project_path
        if last is None or not (last / "project.json").is_file():
            if last is not None:
                self.state.notify(
                    f"Son proje bulunamadı ({last}). Projeler ekranından seçin.", 8000
                )
                self.navigate("projects")
            return
        try:
            workspace = self.state.open_project(last)
            self.state.notify(f"Son proje açıldı: {workspace.project.name}")
        except KineCaptureError as exc:
            logger.warning("Son proje açılamadı: %s", exc.message)
            self.state.notify(
                f"Son proje açılamadı: {exc.message} {exc.remedy}".strip(), 9000
            )
            self.navigate("projects")

    # -------------------------------------------------------------- closing
    def closeEvent(self, event: QCloseEvent) -> None:
        """Never lose a recording to a stray window close."""
        service = self.state.capture
        if service is not None and service.is_recording:
            answer = QMessageBox.question(
                self,
                "Kayıt sürüyor",
                "Bir kayıt hâlâ sürüyor.\n\n"
                "Şimdi kapatırsanız kayıt güvenli biçimde sonlandırılıp "
                "'yarım' olarak işaretlenecek. Devam edilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        for page in self._pages.values():
            try:
                page.on_deactivated()
            except Exception:  # pragma: no cover - shutdown must not raise
                logger.exception("Sayfa kapatılırken hata")
        self._context_timer.stop()
        self.state.shutdown()
        logger.info("Uygulama kapatıldı.")
        event.accept()


__all__ = ["ContextBar", "ErrorBanner", "MainWindow", "NavigationRail"]
