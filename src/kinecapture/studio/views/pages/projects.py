"""Projects, participants and sessions.

Three virtualised lists side by side: pick a project, see its participants,
pick a participant, see its sessions. Counts come from the derived index, which
is refreshed on a worker thread - the list stays usable while it runs and keeps
showing what it had.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.projects import ParticipantRow, ProjectRow, SessionRow
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.projects import ProjectsViewModel

from ..models import ROW_ROLE, Column, RowTableModel, SearchProxy
from ..widgets import ElidedLabel, label, separator
from .base import StudioPage


def _project_columns() -> tuple[Column[ProjectRow], ...]:
    return (
        Column("name", "Proje", lambda r: r.name, tooltip=lambda r: r.path),
        Column(
            "status",
            "Durum",
            lambda r: r.status_text or ("sahibi sizsiniz" if r.is_owner else "paylaşılan"),
            status=lambda r: "warning" if not r.exists else "",
            tooltip=lambda r: r.path,
        ),
        Column(
            "created",
            "Oluşturuldu",
            lambda r: r.created_at[:10],
            sort_key=lambda r: r.created_at,
            numeric=True,
        ),
    )


def _participant_columns() -> tuple[Column[ParticipantRow], ...]:
    def waiting_text(row: ParticipantRow) -> str:
        if row.awaiting_count:
            return f"{row.awaiting_count} bekliyor"
        if row.legacy_count and not row.processed_count:
            return f"{row.legacy_count} eski biçim"
        return "—" if not row.take_count else "hazır"

    return (
        Column("code", "Katılımcı", lambda r: r.code),
        Column("takes", "Kayıt", lambda r: str(r.take_count), sort_key=lambda r: r.take_count, numeric=True),
        Column(
            "processed",
            "İşlenmiş",
            lambda r: str(r.processed_count),
            sort_key=lambda r: r.processed_count,
            numeric=True,
        ),
        Column(
            "waiting",
            "Durum",
            waiting_text,
            status=lambda r: "warning" if r.has_work_waiting else "",
            sort_key=lambda r: r.awaiting_count,
        ),
        Column(
            "last",
            "Son kayıt",
            lambda r: (r.last_take_at[:16].replace("T", " ") if r.last_take_at else "—"),
            sort_key=lambda r: r.last_take_at,
            numeric=True,
        ),
    )


def _session_columns() -> tuple[Column[SessionRow], ...]:
    return (
        Column(
            "started",
            "Oturum",
            lambda r: r.started_at[:16].replace("T", " "),
            sort_key=lambda r: r.started_at,
            numeric=True,
        ),
        Column("takes", "Kayıt", lambda r: str(r.take_count), sort_key=lambda r: r.take_count, numeric=True),
        Column(
            "state",
            "Durum",
            lambda r: "açık" if r.is_open else "kapandı",
            status=lambda r: "live" if r.is_open else "",
        ),
    )


class _TextDialog(QDialog):
    """One or two short text fields. Used for "new project"."""

    def __init__(self, title: str, fields: tuple[tuple[str, str], ...], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, caption in fields:
            edit = QLineEdit()
            edit.setClearButtonEnabled(True)
            self._edits[key] = edit
            form.addRow(caption, edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        first = next(iter(self._edits.values()), None)
        if first is not None:
            first.textChanged.connect(self._sync)
            first.setFocus()
        self._sync()

    def _sync(self) -> None:
        first = next(iter(self._edits.values()), None)
        self._ok.setEnabled(bool(first and first.text().strip()))

    def values(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self._edits.items()}


class ProjectsPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ProjectsViewModel] = None
        self._loaded = False

        gap = tokens.metric("KcSpacingMd")
        actions = QHBoxLayout()
        actions.setSpacing(gap)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara")
        self.search.setClearButtonEnabled(True)
        self.new_project_button = QPushButton("Yeni proje")
        self.new_project_button.setProperty("kcVariant", "primary")
        self.new_participant_button = QPushButton("Katılımcı ekle")
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setProperty("kcVariant", "quiet")
        actions.addWidget(self.search, 1)
        actions.addWidget(self.new_project_button)
        actions.addWidget(self.new_participant_button)
        actions.addWidget(self.refresh_button)
        self.body_layout.addLayout(actions)

        self.status = ElidedLabel("")
        self.status.setProperty("kcRole", "sectionTitle")
        self.body_layout.addWidget(self.status)
        self.body_layout.addWidget(separator())

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        self.project_model, self.project_proxy, self.project_view = self._make_table(
            _project_columns(), "Projeler"
        )
        self.participant_model, self.participant_proxy, self.participant_view = self._make_table(
            _participant_columns(), "Katılımcılar"
        )
        self.session_model, self.session_proxy, self.session_view = self._make_table(
            _session_columns(), "Oturumlar"
        )
        for caption, view in (
            ("PROJELER", self.project_view),
            ("KATILIMCILAR", self.participant_view),
            ("OTURUMLAR", self.session_view),
        ):
            column = QWidget()
            inner = QVBoxLayout(column)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(tokens.metric("KcSpacingSm"))
            inner.addWidget(label(caption, role="sectionTitle"))
            inner.addWidget(view, 1)
            splitter.addWidget(column)
        splitter.setSizes([320, 420, 300])
        self.body_layout.addWidget(splitter, 1)

        self.search.textChanged.connect(self._apply_search)
        self.new_project_button.clicked.connect(self._new_project)
        self.new_participant_button.clicked.connect(self._new_participant)
        self.refresh_button.clicked.connect(self._force_refresh)
        self.project_view.selectionModel().selectionChanged.connect(self._project_chosen)
        self.participant_view.selectionModel().selectionChanged.connect(
            self._participant_chosen
        )

    # ------------------------------------------------------------- assembly
    def _make_table(self, columns, caption: str):  # noqa: ANN001
        model = RowTableModel(columns, self)
        proxy = SearchProxy(self)
        proxy.setSourceModel(model)
        view = QTableView(self)
        view.setModel(proxy)
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.verticalHeader().setVisible(False)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        view.horizontalHeader().setStretchLastSection(True)
        view.setAccessibleName(caption)
        return model, proxy, view

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: ProjectsViewModel) -> None:
        """Wire the page to its viewmodel. Named ``attach`` so it cannot be
        confused with ``BoundView.bind``, which binds a single observable."""
        self.viewmodel = viewmodel
        self.bind(viewmodel.projects, self.project_model.set_rows)
        self.bind(viewmodel.participants, self.participant_model.set_rows)
        self.bind(viewmodel.sessions, self.session_model.set_rows)
        self.bind(viewmodel.summary, self._set_summary)
        self.bind(viewmodel.busy, self._set_busy)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        if self.viewmodel is None or self._loaded:
            return
        self._loaded = True
        self.viewmodel.reload_projects()

    # --------------------------------------------------------------- slots
    def _set_summary(self, text: str) -> None:
        self.status.setText(text)

    def _set_busy(self, busy: bool) -> None:
        # The rows stay on screen while a refresh runs; blanking them would
        # lose the user's place to say something they can already see.
        self.refresh_button.setEnabled(not busy)
        self.refresh_button.setText("Yenileniyor…" if busy else "Yenile")

    def _apply_search(self, text: str) -> None:
        for proxy in (self.project_proxy, self.participant_proxy, self.session_proxy):
            proxy.set_search(text)

    def _selected(self, view: QTableView):  # noqa: ANN001
        indexes = view.selectionModel().selectedRows()
        if not indexes:
            return None
        return indexes[0].data(ROW_ROLE)

    def _project_chosen(self, *_args) -> None:
        row = self._selected(self.project_view)
        if row is not None and self.viewmodel is not None:
            self.viewmodel.open_project(row.project_id)

    def _participant_chosen(self, *_args) -> None:
        row = self._selected(self.participant_view)
        if row is not None and self.viewmodel is not None:
            self.viewmodel.select_participant(row.participant_id)

    def _force_refresh(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.refresh_index(force=True)

    def _new_project(self) -> None:
        if self.viewmodel is None:
            return
        dialog = _TextDialog(
            "Yeni proje",
            (("name", "Proje adı"), ("description", "Açıklama (isteğe bağlı)")),
            self,
        )
        if self.run_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.viewmodel.create_project(values["name"], values.get("description", ""))

    def _new_participant(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.create_participant()

    def run_dialog(self, dialog: QDialog) -> int:
        """The single modal entry point, so tests can drive dialogs headlessly."""
        return dialog.exec()


__all__ = ["ProjectsPage"]
