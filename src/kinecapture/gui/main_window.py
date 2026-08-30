"""Main window: navigation rail, context bar, pages and status bar.

Layout:

```text
+--------+--------------------------------------------------------------+
|  nav   |  context: user | project | participant | camera | disk         |
|  rail  +--------------------------------------------------------------+
| (col-  |                                                              |
| lapsi- |                        active page                           |
|  ble)  |                                                              |
+--------+--------------------------------------------------------------+
| status bar: last message, backend, recording indicator                |
+-----------------------------------------------------------------------+
```

Authentication gates the workspace before navigation becomes visible. The
window routes navigation, renders shared context from
:class:`~kinecapture.gui.state.AppState`, and turns structured errors into a
readable banner while the traceback goes to the log.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QMenu,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.config import AppConfig
from kinecapture.core.errors import KineCaptureError
from kinecapture.core.logging import get_logger
from kinecapture.gui.assets import YTU_LOGO, asset_bytes
from kinecapture.domain.enums import CaptureState
from kinecapture.gui.icons import app_icon, clear_icon_cache, get_icon, icon_size
from kinecapture.gui.admin import ManageUsersDialog
from kinecapture.gui.auth import AuthPage, ChangePasswordDialog
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
#: Tall enough to read the crest, short enough that at 700px the navigation
#: items and the collapse button still fit above it.
_NAV_LOGO_MAX_HEIGHT = 96


def _load_logo_pixmap() -> Optional[QPixmap]:
    """The university logo as a pixmap, or ``None`` if it cannot be loaded.

    Never raises. A decoration that fails to load must leave the navigation
    completely usable, and leave a diagnosable warning in the log rather than
    a crash on start.
    """
    data = asset_bytes(YTU_LOGO)
    if not data:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(data, "PNG") or pixmap.isNull():
        logger.warning("Logo görseli çözümlenemedi: %s", YTU_LOGO)
        return None
    return pixmap
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

        # The university mark sits at the foot of the rail, above the collapse
        # button. It is decoration: it is given whatever space is left after
        # the navigation has taken what it needs, so on a 700px-tall screen the
        # logo shrinks rather than pushing a page button off the bottom.
        self._logo_source = _load_logo_pixmap()
        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setVisible(self._logo_source is not None)
        layout.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignHCenter)

        self._toggle = QPushButton()
        self._toggle.setProperty("role", "nav")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self.toggle)
        layout.addWidget(self._toggle)

        self.setFixedWidth(_NAV_EXPANDED_WIDTH)
        self._refresh_toggle()
        self._refresh_logo()

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
        self._refresh_logo()

    def _refresh_toggle(self) -> None:
        icon = "chevron-left" if self._expanded else "chevron-right"
        self._toggle.setIcon(get_icon(icon, self._theme.text_secondary, 16))
        self._toggle.setText("  Daralt" if self._expanded else "")
        self._toggle.setToolTip("Menüyü daralt" if self._expanded else "Menüyü genişlet")

    def _refresh_logo(self) -> None:
        """Scale the logo to the collapsed/expanded rail, or hide it entirely.

        Collapsed, it is hidden rather than shrunk to an icon: a 40px-wide
        university crest is unreadable, and it would still be taking vertical
        space from the navigation in the state chosen precisely to save space.
        The label is emptied as well so it contributes no height.
        """
        source = self._logo_source
        if source is None:
            self._logo.setVisible(False)
            return
        if not self._expanded:
            self._logo.setVisible(False)
            self._logo.clear()
            self._logo.setFixedHeight(0)
            return

        width = _NAV_EXPANDED_WIDTH - 4 * self._theme.space_sm
        height = int(round(width * source.height() / max(1, source.width())))
        height = min(height, _NAV_LOGO_MAX_HEIGHT)
        width = int(round(height * source.width() / max(1, source.height())))
        # Rescaled from the original every time rather than from the last
        # scaled copy, so repeated collapse/expand cannot accumulate blur.
        self._logo.setPixmap(
            source.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._logo.setFixedHeight(height)
        self._logo.setToolTip("Yıldız Teknik Üniversitesi")
        self._logo.setAccessibleName("Yıldız Teknik Üniversitesi logosu")
        self._logo.setVisible(True)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_toggle()
        self._refresh_logo()
        restyle(self)


class ContextBar(QFrame):
    """The always-visible answer to "what am I working on right now?"."""

    change_password_requested = Signal()
    logout_requested = Signal()
    manage_users_requested = Signal()

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

        self._user_button = QToolButton()
        self._user_button.setText("Kullanıcı yok")
        self._user_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._user_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._user_button.setIcon(get_icon("participants", theme.text_secondary, 16))
        self._user_menu = QMenu(self._user_button)
        self._change_password_action = self._user_menu.addAction("Şifre Değiştir")
        self._change_password_action.triggered.connect(self.change_password_requested)
        self._manage_users_action = self._user_menu.addAction("Kullanıcıları Yönet")
        self._manage_users_action.triggered.connect(self.manage_users_requested)
        self._user_menu.addSeparator()
        self._logout_action = self._user_menu.addAction("Oturumu Kapat")
        self._logout_action.triggered.connect(self.logout_requested)
        self._user_button.setMenu(self._user_menu)
        layout.addWidget(self._user_button)

        self._chips: dict[str, StatusChip] = {}
        for key, icon in (
            ("project", "project"),
            ("participant", "participants"),
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

        user = state.current_user
        self._user_button.setText(user.display_name if user else "Kullanıcı yok")
        self._user_button.setEnabled(user is not None)
        self._manage_users_action.setVisible(bool(user and user.is_owner))

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
        self._user_button.setIcon(get_icon("participants", theme.text_secondary, 16))
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

        shell = QWidget()
        root = QHBoxLayout(shell)
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
        self._root_stack = QStackedWidget()
        self._auth_page = AuthPage(self.state)
        self._root_stack.addWidget(self._auth_page)
        self._root_stack.addWidget(shell)
        self.setCentralWidget(self._root_stack)
        self._shell = shell

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
        self.state.user_changed.connect(lambda *_: self._context.refresh())
        self.state.review_requested.connect(lambda _: self.navigate("review"))
        for signal in (
            self.state.project_changed,
            self.state.participant_changed,
            self.state.session_changed,
        ):
            signal.connect(lambda *_: self._context.refresh())
        self._context.change_password_requested.connect(self._change_password)
        self._context.logout_requested.connect(self._logout)
        self._context.manage_users_requested.connect(self._manage_users)
        self._auth_page.authenticated.connect(self._authentication_completed)

        self._context_timer = QTimer(self)
        self._context_timer.setInterval(_CONTEXT_REFRESH_MS)
        self._context_timer.timeout.connect(self._context.refresh)
        self._context_timer.start()

        self._install_shortcuts()
        self._apply_theme(theme)
        self.navigate("dashboard")
        self._root_stack.setCurrentWidget(self._auth_page)

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
        self._auth_page.apply_theme(theme)
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

    # -------------------------------------------------------- authentication
    def _authentication_completed(self, _user: object) -> None:
        self._root_stack.setCurrentWidget(self._shell)
        self._context.refresh()
        self._recover_interrupted_deletions()
        self._route_after_login()

    def _recover_interrupted_deletions(self) -> None:
        """Resolve any project deletion a crash left half-finished.

        A filesystem and SQLite cannot commit together, so a deletion that dies
        between them leaves a tombstone saying which side got there. This is
        where that is settled - once, at login, before the user can open a
        project that may be about to reappear or vanish underneath them.
        """
        try:
            notes = self.state.recover_interrupted_deletions()
        except Exception:  # pragma: no cover - never block login on cleanup
            logger.exception("Yarım kalan silme kurtarması başarısız")
            return
        if notes:
            self.state.notify(
                "Yarım kalan proje silme işlemi çözüldü: " + notes[0], 9000
            )

    def _route_after_login(self) -> None:
        """Apply the deterministic project-selection rules after login."""
        try:
            projects = self.state.list_accessible_projects()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            self.navigate("projects")
            return
        if len(projects) == 1:
            try:
                workspace = self.state.open_project(projects[0].path)
            except KineCaptureError as exc:
                self.state.report_error(exc)
                self.navigate("projects")
                return
            self.state.notify(f"Proje açıldı: {workspace.project.name}")
            self.navigate("participants")
            return
        # With zero or multiple projects, selection stays explicit. A stale or
        # unauthorized last_project_path is never handed to ProjectWorkspace.
        self.navigate("projects")

    def _restore_last_project(self) -> None:
        """Compatibility entry point; authorization always precedes opening."""
        if not self.state.is_authenticated:
            return
        self._route_after_login()

    def _change_password(self) -> None:
        user = self.state.current_user
        if user is None:
            return
        dialog = ChangePasswordDialog(self.state, user, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.updated_user:
            self.state.replace_current_user(dialog.updated_user)
            self.state.notify("Şifreniz değiştirildi.")

    def _manage_users(self) -> None:
        user = self.state.current_user
        if user is None or not user.is_owner:
            return
        try:
            ManageUsersDialog(self.state, self).exec()
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _logout(self) -> None:
        service = self.state.capture
        abort = False
        if service is not None and service.is_recording:
            answer = QMessageBox.question(
                self,
                "Kayıt sürüyor",
                "Oturumu kapatmadan önce devam eden kayıt güvenli biçimde "
                "sonlandırılıp yarım olarak işaretlenecek. Devam edilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            abort = True
        try:
            self.state.logout(abort_recording=abort)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._auth_page.refresh_mode()
        self._current_key = ""
        self._root_stack.setCurrentWidget(self._auth_page)
        self._password_focus()

    def _password_focus(self) -> None:
        password = getattr(self._auth_page, "_password", None)
        if password is not None:
            password.clear()
            password.setFocus()

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
