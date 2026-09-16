"""The Studio window: context bar on top, page in the middle, workflow below.

The inspector on the right is optional and, when closed, takes **no** width -
not a collapsed stub, not a sliver. On a 1120x700 laptop the difference is
whether the viewport is usable.

Pages are built lazily: opening the application constructs one page, not eight.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.services.settings import SettingsService
from kinecapture.studio.services.window_state import WindowState, save_window_state
from kinecapture.studio.theme import ThemeTokens, load_tokens
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.capture import CaptureViewModel
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.services.inspectors import (
    LogBuffer,
    device_sections,
    diagnostics_sections,
    environment_sections,
    log_file_section,
    provenance_sections,
    raw_parameter_sections,
    source_audit_sections,
)
from kinecapture.studio.viewmodels.dataset import DatasetViewModel
from kinecapture.studio.viewmodels.export import ExportViewModel
from kinecapture.studio.viewmodels.review import ReviewViewModel
from kinecapture.studio.viewmodels.processing import ProcessingViewModel
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from kinecapture.studio.viewmodels.settings import SettingsViewModel
from kinecapture.studio.viewmodels.shell import ShellViewModel

from .auth import AuthView
from .contextbar import ContextBar
from .navbar import NavBar
from .pages import StudioPage, build_page
from .windows import WINDOW_TITLES, LogWindow, ToolWindow


def log_sections():  # noqa: ANN201 - tuple[Section, ...]
    """Where the log file is; the lines come from the buffer."""
    return (log_file_section(), *environment_sections())
from .qt_bridge import BoundView
from .tasks import QtTaskRunner
from .theming import apply_application_theme
from .toasts import ToastLayer
from .widgets import SectionList, label, separator

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
        #: Helper windows, built on first open and reused afterwards.
        self._tool_windows: dict[str, object] = {}
        #: Diagnostics as a state machine rather than a value that may be None.
        self._diagnostics_state = "idle"
        self._diagnostics_report = None
        self._diagnostics_error = ""
        self._diagnostics_delivering = False
        #: Screens whose summaries are known to be behind the data.
        self._stale: set[str] = set()
        #: Whether the inspector is open, remembered per screen. A screen
        #: with an inspector of its own starts with it open, because that
        #: panel is part of doing the work there; the shell's generic one
        #: starts closed, because an empty panel is not.
        self._inspector_by_page: dict[str, bool] = {}
        self.log_buffer = LogBuffer().install()
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
        self._context_timer.timeout.connect(self._tick)
        self._context_timer.start()

    def _tick(self) -> None:
        """One shell heartbeat: the context bar, the recording, the inspector."""
        self.viewmodel.refresh_context()
        if self.inspector.isVisible():
            self._refresh_inspector()

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
        # Messages are drawn over the page, never inserted into it: the video,
        # the 3-D view and the timeline keep their geometry to the pixel.
        self.toasts = ToastLayer(self._tokens, self.stack)

        self.inspector = self._build_inspector()
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        outer.addWidget(self.splitter, 1)

        outer.addWidget(separator())
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(0)
        self.nav_bar = NavBar(self.viewmodel.destinations, self._tokens, self)
        bottom.addWidget(self.nav_bar, 1)
        bottom.addWidget(self._build_tools_button())
        outer.addLayout(bottom)

        # The gate: nothing of the workspace is built, shown or reachable
        # before somebody is signed in.
        self.shell_body = central
        self.auth_view = AuthView(self.auth_viewmodel, self._tokens, self)
        self.gate = QStackedWidget(self)
        self.gate.addWidget(self.auth_view)
        self.gate.addWidget(self.shell_body)
        self.setCentralWidget(self.gate)

    def _build_tools_button(self) -> QToolButton:
        """The six helper windows, behind one button.

        Out of the main flow on purpose: none of them is part of doing the
        work, and all of them are wanted at the moment something looks wrong.
        """
        button = QToolButton(self)
        button.setText("Araçlar")
        button.setToolTip("Log, tanılama, cihaz, denetim, köken ve parametre pencereleri")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setAutoRaise(True)
        menu = QMenu(button)
        for key, (title, subtitle) in WINDOW_TITLES.items():
            action = menu.addAction(title)
            action.setToolTip(subtitle)
            action.triggered.connect(
                lambda _checked=False, k=key: self.open_tool_window(k)
            )
        button.setMenu(menu)
        self.tools_button = button
        return button

    def open_tool_window(self, key: str):  # noqa: ANN201 - ToolWindow
        """Open (or raise) one helper window. Modeless: nothing is blocked."""
        existing = self._tool_windows.get(key)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing

        if key == "log":
            window = LogWindow(self._tokens, self.log_buffer, log_sections)
        else:
            window = ToolWindow(key, self._tokens, self._tool_provider(key))
        self._tool_windows[key] = window
        window.show()
        return window

    def _tool_provider(self, key: str):  # noqa: ANN201
        """What each window reads, resolved fresh every refresh."""
        if key == "diagnostics":
            return self._diagnostics_sections
        if key == "device":
            return lambda: device_sections(self._camera_info())
        if key == "audit":
            return lambda: source_audit_sections(self._selected_run())
        if key == "provenance":
            return lambda: provenance_sections(self._selected_run())
        if key == "parameters":
            return lambda: raw_parameter_sections(self._selected_run())
        return environment_sections

    def _diagnostics_sections(self):  # noqa: ANN201 - tuple[Section, ...]
        """Diagnostics as four honest states, gathered off the GUI thread.

        Collecting them imports the SDK and stats a data folder, which is slow
        enough to freeze a window. The previous version called
        ``collect_diagnostics`` with the wrong signature, swallowed the
        ``TypeError`` and reported "henüz çalıştırılmadı" - a failure dressed
        as an idle state.
        """
        if not self._diagnostics_delivering and self._diagnostics_state != "running":
            self._start_diagnostics()
        return diagnostics_sections(
            self._diagnostics_report,
            state=self._diagnostics_state,
            error=self._diagnostics_error,
        )

    def _start_diagnostics(self) -> None:
        config = self.viewmodel.session.config
        self._diagnostics_state = "running"
        self._diagnostics_error = ""

        def work():  # noqa: ANN202
            from kinecapture.core.diagnostics import collect_diagnostics
            from kinecapture.domain.enums import BackendKind

            raw = getattr(config.backend, "value", config.backend)
            try:
                backend = BackendKind(raw)
            except ValueError:
                backend = None
            return collect_diagnostics(
                dataset_root=config.dataset_root, backend=backend
            )

        def done(report) -> None:  # noqa: ANN001
            self._diagnostics_report = report
            self._diagnostics_state = "done"
            self._deliver_diagnostics()

        def failed(exc: BaseException) -> None:
            logger.warning("Tanılama toplanamadı: %s", exc)
            self._diagnostics_report = None
            self._diagnostics_state = "failed"
            self._diagnostics_error = f"{type(exc).__name__}: {exc}"
            self._deliver_diagnostics()

        self.runner.run(work, done, failed)

    def _deliver_diagnostics(self) -> None:
        """Repaint the window without that repaint starting another run."""
        window = self._tool_windows.get("diagnostics")
        if window is None:
            return
        self._diagnostics_delivering = True
        try:
            window.refresh()
        finally:
            self._diagnostics_delivering = False

    def _camera_info(self):  # noqa: ANN201
        capture = self._viewmodels.get("capture")
        service = getattr(capture, "service", None)
        return getattr(service, "camera_info", None) if service else None

    def _selected_run(self) -> Optional[Path]:
        """The version the user is looking at, on the screen they are on.

        The page decides, not a fixed preference order: a version left open in
        Etiketleme used to win over the row selected in the library, so the
        audit window described a different version from the one on screen.
        """
        active = self.viewmodel.active_page.value
        order = ("review", "library") if active == "review" else ("library", "review")
        for key in order:
            found = self._run_of(key)
            if found is not None:
                return found
        return None

    def _run_of(self, key: str) -> Optional[Path]:
        viewmodel = self._viewmodels.get(key)
        if viewmodel is None:
            return None
        if key == "review":
            session = getattr(viewmodel, "review", None)
            return Path(session.dataset.directory) if session is not None else None
        selected = getattr(viewmodel, "selected", None)
        row = selected.value if selected is not None else None
        return Path(row.directory) if row is not None else None

    def _build_inspector(self) -> QFrame:
        """The one inspector. What it shows depends on what is selected.

        It used to be a fixed sentence promising details it never delivered,
        while Etiketleme carried a second, real inspector next to it. Now the
        active page supplies the content, and a page with an inspector of its
        own keeps this one shut rather than competing with it.
        """
        frame = QFrame(self)
        frame.setObjectName("kcInspector")
        frame.setMinimumWidth(self._tokens.metric("KcInspectorMinWidth"))
        layout = QVBoxLayout(frame)
        margin = self._tokens.metric("KcSpacingXl")
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(self._tokens.metric("KcSpacingLg"))
        self.inspector_title = label("İNCELEME", role="sectionTitle")
        layout.addWidget(self.inspector_title)
        self.inspector_body = SectionList(self._tokens, frame)
        layout.addWidget(self.inspector_body, 1)
        frame.hide()
        return frame

    # ------------------------------------------------------------- inspector
    def _refresh_inspector(self) -> None:
        """Re-read the active page's selection, and redraw only on a change."""
        page = self.stack.currentWidget()
        if not isinstance(page, StudioPage):
            return
        if page.owns_inspector:
            return
        try:
            sections = tuple(page.inspector_sections())
        except Exception as exc:  # noqa: BLE001 - an inspector never crashes a page
            logger.debug("İnceleme paneli okunamadı: %s", exc)
            sections = ()
        self.inspector_title.setText(f"İNCELEME · {page.destination.title.upper()}")
        self.inspector_body.show_sections(sections)

    def _inspector_wanted(self, page) -> bool:  # noqa: ANN001 - StudioPage
        """Whether this screen's inspector should be open right now.

        Remembered per screen: closing the generic panel on Projeler must not
        also close the label panel on Etiketleme, which is not an optional
        extra there but the place the work is done.
        """
        key = page.destination.key if isinstance(page, StudioPage) else ""
        if key in self._inspector_by_page:
            return self._inspector_by_page[key]
        if isinstance(page, StudioPage) and page.owns_inspector:
            return True
        return self.viewmodel.inspector_open.value

    def _apply_inspector_target(self, visible: Optional[bool] = None) -> None:
        """Point the toggle at whichever inspector belongs to this page."""
        page = self.stack.currentWidget()
        if not isinstance(page, StudioPage):
            return
        key = page.destination.key
        if visible is None:
            visible = self._inspector_wanted(page)
        else:
            self._inspector_by_page[key] = bool(visible)
        owns = page.owns_inspector
        self.inspector.setVisible(bool(visible) and not owns)
        if owns:
            page.set_inspector_visible(bool(visible))
        self.context_bar.inspector_button.setChecked(bool(visible))
        if visible and not owns:
            self._refresh_inspector()

    def _connect(self) -> None:
        self.nav_bar.navigate.connect(self.viewmodel.navigate)
        self.context_bar.theme_button.clicked.connect(self.viewmodel.toggle_theme)
        self.context_bar.inspector_button.clicked.connect(
            self.viewmodel.toggle_inspector
        )

        self.context_bar.recording.stop_requested.connect(self._stop_recording)
        self.toasts.action_triggered.connect(self.run_action)

        self.bind(self.viewmodel.active_page, self._show_page)
        self.bind(self.viewmodel.context, self.context_bar.update_context)
        self.bind(self.viewmodel.recording, self._show_recording)
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
        # Reachable from every screen, because the recording is.
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(
            self._stop_recording
        )
        self.auth_viewmodel.signed_in.subscribe(lambda _user: self._signed_in())

    def _stop_recording(self) -> None:
        """Close the open take from wherever the user happens to be."""
        self.viewmodel.stop_recording()

    # -------------------------------------------------------- next-step links
    def run_action(self, key: str) -> bool:
        """Carry out an action offered on a message.

        The whole point is that a message about a finished recording can *take*
        the user to the screen that processes it, instead of naming the screen
        and leaving them to find the take again.

        ``goto:<page>`` navigates. ``review:<directory>`` opens one version in
        Etiketleme, which is the same handover the library uses.
        """
        verb, _, argument = key.partition(":")
        if verb == "goto":
            return self.viewmodel.navigate(argument) or (
                self.viewmodel.active_page.value == argument
            )
        if verb == "review" and argument:
            self.pending_review = argument
            self.viewmodel.navigate("review")
            return True
        return False

    # -------------------------------------------------------------- theming
    def apply_theme(self, name: str) -> None:
        """Switch theme everywhere at once - including windows already open.

        Style, palette, stylesheet images and stylesheet, then every widget
        that caches a colour of its own. Doing less than this is what left a
        light shell wrapped around a dark form in the 15 September audit.
        """
        self._tokens = apply_application_theme(name)
        self.auth_view.apply_tokens(self._tokens)
        self.context_bar.apply_tokens(self._tokens)
        self.nav_bar.apply_tokens(self._tokens)
        self.toasts.set_tokens(self._tokens)
        for page in self._pages.values():
            page.apply_tokens(self._tokens)
        # Helper windows are top-level in their own right, so nothing else
        # reaches them: a window opened under the dark theme would otherwise
        # keep it for the rest of the session.
        for window in self._tool_windows.values():
            setter = getattr(window, "set_tokens", None)
            if callable(setter):
                setter(self._tokens)
        # The context bar caches its icons per theme; force one repaint so the
        # pills are not left tinted for the theme we just left.
        self.context_bar.update_context(self.viewmodel.context.value)
        self.context_bar.recording.show_status(self.viewmodel.recording.value)
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
            viewmodel = CaptureViewModel(self.viewmodel.session, runner=self.runner)
            # A live recording needs the GPU back. The running jobs are held
            # rather than cancelled, and resumed when the take is finished.
            viewmodel.take_finished.subscribe(lambda _take: self._take_finished())
            # From here on the shell can show and stop the recording from any
            # screen, without knowing anything about a camera.
            self.viewmodel.set_recording_source(
                viewmodel.read_status, viewmodel.stop_recording
            )
        elif key == "processing":
            viewmodel = ProcessingViewModel(
                self.viewmodel.session, runner=self.runner, settings=self._settings_service
            )
            # A finished job changes what the library and the project counts
            # should say, wherever the user happens to be standing.
            viewmodel.job_finished.subscribe(
                lambda _job: self._invalidate("projects", "library", "dataset", "export")
            )
        elif key == "library":
            viewmodel = LibraryViewModel(self.viewmodel.session, runner=self.runner)
            # "Etiketle" on a version is what takes the user to the next step.
            viewmodel.open_for_review.subscribe(self._review_version)
            viewmodel.recompute_requested.subscribe(self._recompute_version)
        elif key == "review":
            viewmodel = ReviewViewModel(self.viewmodel.session, runner=self.runner)
        elif key == "dataset":
            viewmodel = DatasetViewModel(self.viewmodel.session, runner=self.runner)
        elif key == "export":
            viewmodel = ExportViewModel(self.viewmodel.session, runner=self.runner)
            # The set of versions to consider is the library's; building it a
            # second time here would be a second answer to the same question.
            library = self._viewmodels.get("library")
            if library is None:
                library = LibraryViewModel(self.viewmodel.session, runner=self.runner)
                library.open_for_review.subscribe(self._review_version)
                library.recompute_requested.subscribe(self._recompute_version)
                self._viewmodels["library"] = library
            page.use_library(library)
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

    def _recompute_version(self, row) -> None:  # noqa: ANN001 - VersionRow
        """Queue another run of the take behind a version, and show the queue.

        The existing version is left alone: a new run writes a new folder, and
        the labels already attached to the old one keep pointing at it.
        """
        self.viewmodel.navigate("processing")
        processing = self._viewmodels.get("processing")
        if processing is None:
            return
        take = next(
            (
                summary
                for summary in (processing.index or ())
                if summary.take_id == row.take_id
            ),
            None,
        )
        if take is None:
            self.viewmodel.report(
                Message(
                    headline="Bu kaydın dizini okunamadı.",
                    severity=Severity.WARNING,
                    detail="Verileri Hesapla ekranında 'Yenile' deneyin.",
                    code="take_not_indexed",
                )
            )
            return
        processing.start(take)

    def _resume_jobs(self) -> None:
        processing = self._viewmodels.get("processing")
        if processing is not None:
            processing.service.resume_all()

    def _take_finished(self) -> None:
        self._resume_jobs()
        self._invalidate()
        self.viewmodel.refresh_recording()

    # ------------------------------------------------------------- freshness
    #: Which screens a finished take or job makes out of date.
    _DERIVED_SCREENS = ("projects", "processing", "library", "dataset", "export")

    def _invalidate(self, *keys: str) -> None:
        """Mark screens as behind the data, and refresh the visible one now.

        A recording that finished while the user was looking at Projeler has
        to change the counts there; making every page change rescan the whole
        project instead would cost far more and still be late.
        """
        self._stale.update(keys or self._DERIVED_SCREENS)
        current = self.viewmodel.active_page.value
        if current in self._stale:
            self._refresh_page(current)

    def _refresh_page(self, key: str) -> None:
        self._stale.discard(key)
        page = self._pages.get(key)
        viewmodel = self._viewmodels.get(key)
        if viewmodel is None:
            return
        reload_page = getattr(page, "reload", None)
        if callable(reload_page):
            reload_page()
            return
        reload_model = getattr(viewmodel, "reload", None)
        if callable(reload_model):
            reload_model(force=True)

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
        if key in self._stale:
            self._refresh_page(key)
        # The inspector belongs to whichever page is now in front, with
        # whatever that page was last left showing.
        self._apply_inspector_target()
        self._update_title()

    def _show_recording(self, status) -> None:  # noqa: ANN001 - RecordingStatus
        self.context_bar.recording.show_status(status)
        self._update_title()

    def _update_title(self) -> None:
        """The title says the page, and says RECORDING while one is open.

        Written in one place so leaving Yakalama cannot take the marker with
        it - which is exactly what the audit saw happen.
        """
        page = self.stack.currentWidget()
        name = page.destination.title if isinstance(page, StudioPage) else ""
        base = f"KineCapture Studio · {name}" if name else "KineCapture Studio"
        status = self.viewmodel.recording.value
        self.setWindowTitle(("● KAYIT · " + base) if status.is_open else base)

    def _set_inspector_visible(self, visible: bool) -> None:
        self._apply_inspector_target(visible)
        if visible and self.inspector.isVisible():
            width = self._state.inspector_width
            total = max(self.splitter.width(), width + 400)
            self.splitter.setSizes([total - width, width])

    def _show_message(self, message: Message) -> None:
        self.toasts.show_message(message)

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
                capture.close()
                capture.service.disconnect()
            except Exception as exc:  # noqa: BLE001 - never block the close
                logger.warning("Kamera kapanışında hata: %s", exc)
        self.unbind_all()
        self.viewmodel.close()
        super().closeEvent(event)


__all__ = ["StudioWindow"]
