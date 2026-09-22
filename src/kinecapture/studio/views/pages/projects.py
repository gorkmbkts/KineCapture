"""Projects, participants and sessions.

Three virtualised lists side by side: pick a project, see its participants,
pick a participant, see its sessions. Counts come from the derived index, which
is refreshed on a worker thread - the list stays usable while it runs and keeps
showing what it had.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.services.formatting import (
    local_date,
    local_datetime,
    timezone_note,
)
from kinecapture.studio.services.projects import ParticipantRow, ProjectRow, SessionRow
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.projects import ProjectsViewModel

from .. import iconset
from ..models import ROW_ROLE, Column, RowTableModel, SearchProxy, configure_columns
from ..widgets import ElidedLabel, label, separator
from .base import StudioPage


def _project_columns() -> tuple[Column[ProjectRow], ...]:
    return (
        # The name is the only thing here with no natural length, so it is the
        # one that takes the leftover width.
        Column(
            "name",
            "Proje",
            lambda r: r.name,
            tooltip=lambda r: f"{r.name}\n{r.path}",
            stretch=True,
        ),
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
            lambda r: local_date(r.created_at),
            sort_key=lambda r: r.created_at,
            tooltip=lambda r: timezone_note(r.created_at),
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
            lambda r: local_datetime(r.last_take_at) if r.last_take_at else "—",
            sort_key=lambda r: r.last_take_at,
            tooltip=lambda r: timezone_note(r.last_take_at),
            numeric=True,
        ),
    )


def _session_columns() -> tuple[Column[SessionRow], ...]:
    return (
        Column(
            "started",
            "Oturum",
            lambda r: local_datetime(r.started_at),
            sort_key=lambda r: r.started_at,
            tooltip=lambda r: f"{r.session_id}\n{timezone_note(r.started_at)}",
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


class _DeleteDialog(QDialog):
    """Says exactly what is about to be erased, then asks for the name back.

    Two deliberate frictions, because this is the one action in the product
    that cannot be undone: the path and the measured size are shown *before*
    the question, and the confirm button stays disabled until the project's
    own name has been typed. A dialog that can be dismissed with a reflex is
    not consent.
    """

    def __init__(self, name: str, path: str, note: str, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("Projeyi sil")
        self.setModal(True)
        self._name = name

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        headline = QLabel(f"“{name}” kalıcı olarak silinecek.")
        headline.setWordWrap(True)
        headline.setProperty("kcRole", "fieldLabel")
        layout.addWidget(headline)

        detail = QLabel(
            "Bu projedeki bütün kayıtlar, işlenmiş sürümler ve etiketler "
            "diskten silinir. Bu işlem geri alınamaz."
        )
        detail.setWordWrap(True)
        detail.setProperty("kcRole", "pageSubtitle")
        layout.addWidget(detail)

        target = QLabel(path)
        target.setWordWrap(True)
        target.setProperty("kcRole", "mono")
        target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(target)

        if note:
            measured = QLabel(note)
            measured.setWordWrap(True)
            measured.setProperty("kcRole", "pageSubtitle")
            layout.addWidget(measured)

        prompt = QLabel(f"Onaylamak için proje adını yazın: {name}")
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        self.confirm = QLineEdit()
        self.confirm.setPlaceholderText(name)
        self.confirm.setAccessibleName("Silmeyi onaylamak için proje adı")
        layout.addWidget(self.confirm)

        buttons = QDialogButtonBox()
        self._delete = buttons.addButton(
            "Kalıcı olarak sil", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self._delete.setProperty("kcVariant", "danger")
        self._delete.setEnabled(False)
        cancel = buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setDefault(True)
        self._delete.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.confirm.textChanged.connect(self._sync)
        self.confirm.setFocus()

    def _sync(self) -> None:
        self._delete.setEnabled(self.confirm.text().strip() == self._name)


class ProjectsPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ProjectsViewModel] = None
        #: Whose list is on screen. ``None`` means nobody's.
        self._loaded_for: Optional[str] = None

        gap = tokens.metric("KcSpacingMd")
        actions = QHBoxLayout()
        actions.setSpacing(gap)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Proje, katılımcı veya oturum ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Proje, katılımcı ve oturum araması")
        self.search.setToolTip(
            "Aşağıdaki üç listeyi birlikte daraltır: proje adı, katılımcı kodu "
            "ve oturum tarihi."
        )
        # A magnifier inside the field, so what the box is for is legible
        # before anything is typed into it and without a second caption.
        self.search.addAction(
            iconset.icon("search", tokens, size=tokens.metric("KcIconSize")),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        # Wide enough for the placeholder to be read *whole* - measured from
        # the placeholder itself rather than guessed, because an explanation
        # that is elided at its end explains nothing - and for a typed query
        # not to scroll inside a slot narrower than the words offering it.
        # Still capped: a search box stretched across 1900 pixels is not
        # easier to type into, it is just the widest thing on the screen.
        hint = QFontMetrics(self.search.font()).horizontalAdvance(
            self.search.placeholderText()
        )
        self.search.setMinimumWidth(min(560, hint + 96))
        self.search.setMaximumWidth(560)
        self.search.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.new_project_button = QPushButton("Yeni proje")
        self.new_project_button.setProperty("kcVariant", "primary")
        self.new_participant_button = QPushButton("Katılımcı ekle")
        self.delete_project_button = QPushButton("Projeyi sil")
        self.delete_project_button.setProperty("kcVariant", "danger")
        self.delete_project_button.setToolTip(
            "Seçili projeyi ve içindeki bütün kayıtları kalıcı olarak siler."
        )
        self.delete_project_button.setEnabled(False)
        # Deliberately *not* the "quiet" variant. Quiet draws no surface and
        # no border, so beside three real buttons it read as a word somebody
        # had left in the row rather than as something to press. It keeps the
        # neutral colour - it is not a primary action and not a dangerous one
        # - but it now has the same height, surface and border as its
        # neighbours.
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setIcon(
            iconset.icon("refresh", tokens, size=tokens.metric("KcIconSize"))
        )
        self.refresh_button.setToolTip("Listeleri diskten yeniden okur.")
        # One button family: the same height for all four, so the row reads as
        # a row rather than as four differently sized things.
        for button in (
            self.new_participant_button,
            self.delete_project_button,
            self.refresh_button,
            self.new_project_button,
        ):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        actions.addWidget(self.search)
        actions.addStretch(1)
        actions.addWidget(self.new_participant_button)
        actions.addWidget(self.delete_project_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.new_project_button)
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
        # Master, detail, detail-of-detail: the project list is a chooser, the
        # participants are the thing being worked on, the sessions support them.
        splitter.setSizes([420, 720, 420])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        self.body_layout.addWidget(splitter, 1)

        self.search.textChanged.connect(self._apply_search)
        self.new_project_button.clicked.connect(self._new_project)
        self.new_participant_button.clicked.connect(self._new_participant)
        self.refresh_button.clicked.connect(self._force_refresh)
        self.delete_project_button.clicked.connect(self._delete_project)
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
        view.setWordWrap(False)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Only the project table has a genuinely variable-length column
        # (the name). The other two are fixed values, so they are sized
        # to their content and the leftover width is left alone.
        configure_columns(
            view, columns, fill=any(column.stretch for column in columns)
        )
        view.setAccessibleName(caption)
        return model, proxy, view

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: ProjectsViewModel) -> None:
        """Wire the page to its viewmodel. Named ``attach`` so it cannot be
        confused with ``BoundView.bind``, which binds a single observable."""
        self.viewmodel = viewmodel
        self.bind(viewmodel.projects, self._show_projects)
        self.bind(viewmodel.participants, self._show_participants)
        self.bind(viewmodel.sessions, self.session_model.set_rows)
        self.bind(viewmodel.summary, self._set_summary)
        self.bind(viewmodel.busy, self._set_busy)
        self.bind(viewmodel.deleting, self._set_deleting)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        """Load once per signed-in user, not once per process.

        The page can be activated before anybody has signed in; the list that
        produces is empty by definition and must not be kept as the answer.
        """
        if self.viewmodel is None:
            return
        user = self.viewmodel.current_user_id
        if user and self._loaded_for == user:
            return
        self._loaded_for = user or None
        self.viewmodel.reload_projects()

    def reload(self) -> None:
        """Force a full reload. Used by the shell when the data changed."""
        if self.viewmodel is None:
            return
        self._loaded_for = self.viewmodel.current_user_id or None
        self.viewmodel.refresh_all()

    # --------------------------------------------------------------- slots
    def _show_projects(self, rows) -> None:  # noqa: ANN001 - tuple[ProjectRow, ...]
        self.project_model.set_rows(rows)
        self._restore_selection(
            self.project_view,
            self.project_proxy,
            "project_id",
            self.viewmodel.selected_project.value if self.viewmodel else "",
        )

    def _show_participants(self, rows) -> None:  # noqa: ANN001
        self.participant_model.set_rows(rows)
        self._restore_selection(
            self.participant_view,
            self.participant_proxy,
            "participant_id",
            self.viewmodel.selected_participant.value if self.viewmodel else "",
        )

    def _restore_selection(self, view, proxy, attribute: str, value: str) -> None:  # noqa: ANN001
        """Put the highlight back on the row the user chose.

        ``set_rows`` resets the model, and a reset clears the selection. The
        user's choice did not change, so the highlight must not either - losing
        it is what made it possible to record against a participant nobody
        could see was selected.
        """
        if not value:
            return
        model = proxy.sourceModel()
        for position in range(model.rowCount()):
            row = model.row_at(position)
            if row is not None and getattr(row, attribute, None) == value:
                index = proxy.mapFromSource(model.index(position, 0))
                if index.isValid():
                    view.selectionModel().blockSignals(True)
                    try:
                        view.selectRow(index.row())
                    finally:
                        view.selectionModel().blockSignals(False)
                return

    def inspector_sections(self) -> tuple:
        """The selected project and participant, in full.

        This is where the long identifiers and the full path live, so the rows
        themselves can stay readable.
        """
        from kinecapture.studio.services.inspectors import Row, Section

        sections: list[Section] = []
        project = self._selected(self.project_view)
        if project is not None:
            sections.append(
                Section(
                    "Proje",
                    (
                        Row("Ad", project.name),
                        Row("Kimlik", project.project_id),
                        Row("Klasör", project.path, detail=project.path),
                        Row(
                            "Oluşturuldu",
                            local_datetime(project.created_at),
                            detail=timezone_note(project.created_at),
                        ),
                        Row(
                            "Erişim",
                            "sahibi sizsiniz" if project.is_owner else "paylaşılan",
                        ),
                        Row(
                            "Klasör durumu",
                            "var" if project.exists else "bulunamadı",
                            level="ready" if project.exists else "warning",
                            detail=(
                                ""
                                if project.exists
                                else "Veri diski bağlı olmayabilir. Kayıt silinmedi."
                            ),
                        ),
                    ),
                )
            )
        participant = self._selected(self.participant_view)
        if participant is not None:
            sections.append(
                Section(
                    "Katılımcı",
                    (
                        Row("Kod", participant.code),
                        Row("Kimlik", participant.participant_id),
                        Row("Kayıt", str(participant.take_count)),
                        Row("İşlenmiş", str(participant.processed_count)),
                        Row(
                            "İşlenmeyi bekleyen",
                            str(participant.awaiting_count),
                            level="warning" if participant.has_work_waiting else "neutral",
                        ),
                        Row(
                            "Son kayıt",
                            local_datetime(participant.last_take_at)
                            if participant.last_take_at
                            else "—",
                            detail=timezone_note(participant.last_take_at),
                        ),
                    ),
                    note="Kayıt hedefi bu katılımcıdır.",
                )
            )
        return tuple(sections)

    def _set_summary(self, text: str) -> None:
        self.status.setText(text)

    def _set_busy(self, busy: bool) -> None:
        # The rows stay on screen while a refresh runs; blanking them would
        # lose the user's place to say something they can already see.
        self.refresh_button.setEnabled(not busy)
        self.refresh_button.setText("Yenileniyor…" if busy else "Yenile")

    def _set_deleting(self, deleting: bool) -> None:
        """Erasing a project takes a while; the list stays, the actions wait."""
        for button in (
            self.delete_project_button,
            self.new_project_button,
            self.new_participant_button,
            self.refresh_button,
        ):
            button.setEnabled(not deleting)
        self.delete_project_button.setText(
            "Siliniyor…" if deleting else "Projeyi sil"
        )
        if not deleting:
            self.delete_project_button.setEnabled(
                self._selected(self.project_view) is not None
            )

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
        self.delete_project_button.setEnabled(row is not None)
        if row is not None and self.viewmodel is not None:
            self.viewmodel.open_project(row.project_id)

    def _delete_project(self) -> None:
        """Ask, with the facts on screen, then erase off the GUI thread."""
        row = self._selected(self.project_view)
        if row is None or self.viewmodel is None:
            return
        report = self.viewmodel.deletion_preflight(row.project_id)
        if report is None:
            return
        if not report.ok:
            self.show_message(
                Message(
                    headline="Bu proje silinemez.",
                    severity=Severity.WARNING,
                    detail=report.reason,
                    code=report.code or "delete_refused",
                    technical={"yol": row.path},
                )
            )
            return
        note = ""
        resolved = str(report.resolved) if report.resolved is not None else row.path
        dialog = _DeleteDialog(row.name, resolved, note, self)
        if self.run_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        self.viewmodel.delete_project(row.project_id)

    def _participant_chosen(self, *_args) -> None:
        row = self._selected(self.participant_view)
        if row is not None and self.viewmodel is not None:
            self.viewmodel.select_participant(row.participant_id)

    def _force_refresh(self) -> None:
        self.reload()

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
