"""The Studio window: context bar on top, page in the middle, workflow below.

The inspector on the right is optional and, when closed, takes **no** width -
not a collapsed stub, not a sliver. On a 1120x700 laptop the difference is
whether the viewport is usable.

Pages are built lazily: opening the application constructs one page, not eight.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.messages import Message
from kinecapture.studio.services.settings import SettingsService
from kinecapture.studio.services.window_state import WindowState, save_window_state
from kinecapture.studio.theme import ThemeTokens, load_tokens, stylesheet_for
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.capture import CaptureViewModel
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.processing import ProcessingViewModel
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from kinecapture.studio.viewmodels.settings import SettingsViewModel
from kinecapture.studio.viewmodels.shell import ShellViewModel

from .auth import AuthView
from .contextbar import ContextBar
from .navbar import NavBar
from .pages import StudioPage, build_page
from .qt_bridge import BoundView
from .tasks import QtTaskRunner
from .widgets import label, separator

logger = logging.getLogger(__name__)

#: Context bar refresh rate. Metrics update 2-4 times a second, never per frame.
_CONTEXT_INTERVAL_MS = 330


class StudioWindow(QMainWindow, BoundView):
    def __init__(
        self,
        viewmodel: ShellViewModel,
        window_state: Optional[WindowState] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        QMainWindow.__init__(self, parent)
        BoundView.__init__(self)
        self.viewmodel = viewmodel
        self._state = (window_state or WindowState()).normalised()
        self._tokens: ThemeTokens = load_tokens(viewmodel.theme.value)
        self._pages: dict[str, StudioPage] = {}
        self._state_path: Optional[object] = None
        # Slow work - scanning a project, mostly - runs here and comes back on
        # the GUI thread. Viewmodels see only the TaskRunner interface.
        self.runner = QtTaskRunner(self)
        self._viewmodels: dict[str, object] = {}
        #: Set by the library when a version is chosen; read by the labelling
        #: screen when it opens. F8 turns this into the real handover.
        self.pending_review: object = None
        self._settings_service = SettingsService(viewmodel.session.config)
        self.auth_viewmodel = AuthViewModel(viewmodel.session)

        self.setWindowTitle("KineCapture Studio")
        self.setMinimumSize(
            self._tokens.metric("KcWindowMinWidth"),
            self._tokens.metric("KcWindowMinHeight"),
        )
        self.resize(self._state.width, self._state.height)

        self._build()
        self._connect()
        self.apply_theme(viewmodel.theme.value)

        self.viewmodel.navigate(self._state.active_page)
        self._show_page(self.viewmodel.active_page.value)
        self.inspector.setVisible(self._state.inspector_open)
        self.context_bar.inspector_button.setChecked(self._state.inspector_open)
        self._update_gate()

        self._context_timer = QTimer(self)
        self._context_timer.setInterval(_CONTEXT_INTERVAL_MS)
        self._context_timer.timeout.connect(self.viewmodel.refresh_context)
        self._context_timer.start()

    # ------------------------------------------------------------- assembly
    def _build(self) -> None:
        central = QWidget(self)
        shell_layout = QVBoxLayout(central)
        outer = shell_layout
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.context_bar = ContextBar(self._tokens, self)
        outer.addWidget(self.context_bar)
        outer.addWidget(separator())

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(self._tokens.metric("KcBorderWidth"))

        self.stack = QStackedWidget(self)
        self.splitter.addWidget(self.stack)

        self.inspector = self._build_inspector()
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        outer.addWidget(self.splitter, 1)

        outer.addWidget(separator())
        self.nav_bar = NavBar(self.viewmodel.destinations, self._tokens, self)
        outer.addWidget(self.nav_bar)

        # The gate: nothing of the workspace is built, shown or reachable
        # before somebody is signed in.
        self.shell_body = central
        self.auth_view = AuthView(self.auth_viewmodel, self._tokens, self)
        self.gate = QStackedWidget(self)
        self.gate.addWidget(self.auth_view)
        self.gate.addWidget(self.shell_body)
        self.setCentralWidget(self.gate)

    def _build_inspector(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("kcInspector")
        frame.setMinimumWidth(self._tokens.metric("KcInspectorMinWidth"))
        layout = QVBoxLayout(frame)
        margin = self._tokens.metric("KcSpacingLg")
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(self._tokens.metric("KcSpacingMd"))
        layout.addWidget(label("İNCELEME", role="sectionTitle"))
        self.inspector_body = QWidget(frame)
        self.inspector_layout = QVBoxLayout(self.inspector_body)
        self.inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.inspector_layout.setSpacing(self._tokens.metric("KcSpacingMd"))
        self.inspector_layout.addWidget(
            label("Seçili öğenin ayrıntıları burada görünür.", role="pageSubtitle")
        )
        self.inspector_layout.addStretch(1)
        layout.addWidget(self.inspector_body, 1)
        frame.hide()
        return frame

    def _connect(self) -> None:
        self.nav_bar.navigate.connect(self.viewmodel.navigate)
        self.context_bar.theme_button.clicked.connect(self.viewmodel.toggle_theme)
        self.context_bar.inspector_button.clicked.connect(
            self.viewmodel.toggle_inspector
        )

        self.bind(self.viewmodel.active_page, self._show_page)
        self.bind(self.viewmodel.context, self.context_bar.update_context)
        self.bind(self.viewmodel.inspector_open, self._set_inspector_visible)
        self.bind(self.viewmodel.theme, self.apply_theme)
        self.bind_event(self.viewmodel.message, self._show_message)

        for index, item in enumerate(self.viewmodel.destinations, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(
                lambda key=item.key: self.viewmodel.navigate(key)
            )
        QShortcut(QKeySequence("Ctrl+PgDown"), self).activated.connect(
            lambda: self.viewmodel.step(1)
        )
        QShortcut(QKeySequence("Ctrl+PgUp"), self).activated.connect(
            lambda: self.viewmodel.step(-1)
        )
        QShortcut(QKeySequence("F9"), self).activated.connect(
            self.viewmodel.toggle_inspector
        )
        self.auth_viewmodel.signed_in.subscribe(lambda _user: self._signed_in())

    # -------------------------------------------------------------- theming
    def apply_theme(self, name: str) -> None:
        self._tokens = load_tokens(name)
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(stylesheet_for(name))
        self.context_bar.apply_tokens(self._tokens)
        self.nav_bar.apply_tokens(self._tokens)
        for page in self._pages.values():
            page.apply_tokens(self._tokens)
        # The context bar caches its icons per theme; force one repaint so the
        # pills are not left tinted for the theme we just left.
        self.context_bar.update_context(self.viewmodel.context.value)
        self.nav_bar.set_active(self.viewmodel.active_page.value)

    @property
    def tokens(self) -> ThemeTokens:
        return self._tokens

    # ------------------------------------------------------------ behaviour
    def page(self, key: str) -> StudioPage:
        """Build the page on first visit, then reuse it."""
        existing = self._pages.get(key)
        if existing is not None:
            return existing
        from kinecapture.studio.viewmodels.navigation import destination

        item = destination(key)
        if item is None:  # pragma: no cover - navigate() refuses unknown keys
            raise KeyError(key)
        page = build_page(item, self._tokens, self)
        self._attach_viewmodel(key, page)
        self._pages[key] = page
        self.stack.addWidget(page)
        return page

    def _attach_viewmodel(self, key: str, page: StudioPage) -> None:
        """Give a page the viewmodel it was written against, if it has one.

        Built here rather than up front so opening the application does not
        construct state for screens nobody visited.
        """
        attach = getattr(page, "attach", None)
        if attach is None:
            return
        if key == "projects":
            viewmodel = ProjectsViewModel(self.viewmodel.session, self.runner)
        elif key == "capture":
            viewmodel = CaptureViewModel(self.viewmodel.session)
            # A live recording needs the GPU back. The running jobs are held
            # rather than cancelled, and resumed when the take is finished.
            viewmodel.take_finished.subscribe(lambda _take: self._resume_jobs())
        elif key == "processing":
            viewmodel = ProcessingViewModel(
                self.viewmodel.session, runner=self.runner, settings=self._settings_service
            )
        elif key == "library":
            viewmodel = LibraryViewModel(self.viewmodel.session, runner=self.runner)
            # "Etiketle" on a version is what takes the user to the next step.
            viewmodel.open_for_review.subscribe(self._review_version)
        elif key == "settings":
            viewmodel = SettingsViewModel(self._settings_service)
        else:  # pragma: no cover - every attachable page is listed above
            return
        self._viewmodels[key] = viewmodel
        attach(viewmodel)

    def _review_version(self, row) -> None:  # noqa: ANN001 - VersionRow
        """Carry the chosen version to the labelling screen."""
        self.pending_review = row
        self.viewmodel.navigate("review")

    def _resume_jobs(self) -> None:
        processing = self._viewmodels.get("processing")
        if processing is not None:
            processing.service.resume_all()

    # ------------------------------------------------------------------ gate
    def _update_gate(self) -> None:
        signed_in = self.viewmodel.session.is_authenticated
        self.gate.setCurrentWidget(self.shell_body if signed_in else self.auth_view)

    def _signed_in(self) -> None:
        self._update_gate()
        self.viewmodel.refresh_context()
        current = self.stack.currentWidget()
        if isinstance(current, StudioPage):
            current.page_activated()

    @property
    def viewmodel_for(self) -> dict[str, object]:
        return self._viewmodels

    def _show_page(self, key: str) -> None:
        page = self.page(key)
        previous = self.stack.currentWidget()
        if previous is not None and previous is not page and isinstance(previous, StudioPage):
            previous.page_deactivated()
        self.stack.setCurrentWidget(page)
        self.nav_bar.set_active(key)
        page.page_activated()
        self.setWindowTitle(f"KineCapture Studio · {page.destination.title}")

    def _set_inspector_visible(self, visible: bool) -> None:
        self.inspector.setVisible(visible)
        self.context_bar.inspector_button.setChecked(visible)
        if visible:
            width = self._state.inspector_width
            total = max(self.splitter.width(), width + 400)
            self.splitter.setSizes([total - width, width])

    def _show_message(self, message: Message) -> None:
        current = self.stack.currentWidget()
        if isinstance(current, StudioPage):
            current.show_message(message)

    # ---------------------------------------------------------------- state
    def current_window_state(self) -> WindowState:
        sizes = self.splitter.sizes()
        inspector_width = sizes[1] if len(sizes) > 1 and sizes[1] else self._state.inspector_width
        base = WindowState(
            width=self.width(),
            height=self.height(),
            maximised=self.isMaximized(),
            active_page=self.viewmodel.active_page.value,
            inspector_open=self.inspector.isVisible(),
            inspector_width=inspector_width,
            theme=self.viewmodel.theme.value,
        )
        return self.viewmodel.window_state(base)

    def set_state_path(self, path) -> None:  # noqa: ANN001 - Path or None
        self._state_path = path

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        """Remember the window, then let everything detach cleanly.

        Failing to save the geometry must not block the close - the user asked
        to leave, and a preference file is not worth refusing that.
        """
        self._context_timer.stop()
        # A task still in flight would deliver into widgets that are being torn
        # down. Waiting is the difference between a clean exit and a crash on
        # the way out.
        self.runner.wait(5_000)
        try:
            save_window_state(self.current_window_state(), self._state_path)
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.warning("Pencere durumu kaydedilemedi: %s", exc)
        for page in self._pages.values():
            page.page_deactivated()
            page.unbind_all()
        # The camera is held open across page changes, so closing the window is
        # the one place it has to be released - and a half-closed take
        # finalised - rather than left to the process exiting.
        processing = self._viewmodels.get("processing")
        if processing is not None:
            try:
                processing.shutdown()
            except Exception as exc:  # noqa: BLE001 - never block the close
                logger.warning("İşleme kapanışında hata: %s", exc)
        capture = self._viewmodels.get("capture")
        if capture is not None:
            try:
                capture.service.disconnect()
            except Exception as exc:  # noqa: BLE001 - never block the close
                logger.warning("Kamera kapanışında hata: %s", exc)
        self.unbind_all()
        self.viewmodel.close()
        super().closeEvent(event)


__all__ = ["StudioWindow"]
