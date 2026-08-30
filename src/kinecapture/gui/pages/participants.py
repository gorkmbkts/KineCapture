"""Minimal participant selection and one-click transition into capture."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.project import Participant
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    KeyValueList,
    make_button,
    make_label,
)


class NewParticipantDialog(QDialog):
    def __init__(
        self, code: str, theme: Theme, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.start_after_add = False
        self.setWindowTitle("Yeni katılımcı")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(theme.space_md)
        title = make_label(f"Katılımcı kodu: {code}", role="section")
        layout.addWidget(title)
        note = make_label(
            "Kod otomatik oluşturulacaktır. Kesin kod, Ekle düğmesine "
            "basıldığında güvenli biçimde ayrılır.",
            role="muted",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox()
        cancel = buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole)
        add = buttons.addButton("Ekle", QDialogButtonBox.ButtonRole.AcceptRole)
        start = buttons.addButton(
            "Ekle ve Kayda Başla", QDialogButtonBox.ButtonRole.ActionRole
        )
        cancel.clicked.connect(self.reject)
        add.clicked.connect(self.accept)
        start.clicked.connect(self._accept_and_start)
        layout.addWidget(buttons)

    def _accept_and_start(self) -> None:
        self.start_after_add = True
        self.accept()


class ParticipantsPage(Page):
    """Anonymous roster with recording counts and a primary capture action."""

    navigate_requested = Signal(str)
    title = "Katılımcılar"
    description = "Katılımcıyı seçin ve Kayda Başla ile doğrudan çekime geçin."
    icon = "participants"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme
        self._new_participant = make_button(
            "Katılımcı Ekle", variant="primary", icon="add", theme=theme
        )
        self._new_participant.clicked.connect(self._create_participant)
        self.header.add_action(self._new_participant)

        self._empty = EmptyState(
            "Önce bir proje seçin",
            "Katılımcılar erişebildiğiniz projeler içinde tutulur.",
            theme=theme,
            icon="project",
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        columns = QHBoxLayout(self._body)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(theme.space_md)
        columns.addWidget(self._build_list(theme), 3)
        columns.addWidget(self._build_actions(theme), 2)
        self.content.addWidget(self._body, 1)
        state.project_changed.connect(lambda _: self._reload())
        state.dataset_changed.connect(self._reload)
        self._set_empty(True)

    def _build_list(self, theme: Theme) -> QWidget:
        card = Card(
            "Katılımcılar",
            subtitle="Kod, kayıt sayısı ve son kayıt zamanına göre seçim yapın.",
            theme=theme,
            icon="participants",
        )
        self._search = QLineEdit()
        self._search.setPlaceholderText("Katılımcı kodunda ara…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        card.add_widget(self._search)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(
            lambda current, _: self._select(current)
        )
        self._list.itemDoubleClicked.connect(lambda _: self._start_capture())
        card.add_widget(self._list, 1)
        return card

    def _build_actions(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)
        detail = Card("Seçili katılımcı", theme=theme, icon="info")
        self._details = KeyValueList(theme)
        detail.add_widget(self._details)
        layout.addWidget(detail)
        action = Card(
            "Kayıt",
            subtitle="Operatör ve teknik oturum giriş yapan kullanıcıdan otomatik gelir.",
            theme=theme,
            icon="capture",
        )
        self._start = make_button(
            "Kayda Başla", variant="primary", icon="capture", theme=theme
        )
        self._start.clicked.connect(self._start_capture)
        action.add_widget(self._start)
        self._recordings = make_button("Kayıtlarını Gör", theme=theme)
        self._recordings.clicked.connect(self._show_recordings)
        action.add_widget(self._recordings)
        layout.addWidget(action)
        layout.addStretch(1)
        return wrapper

    def on_activated(self) -> None:
        self._reload()

    def _set_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._body.setVisible(not empty)
        self._new_participant.setEnabled(not empty)

    def _reload(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            self._set_empty(True)
            return
        self._set_empty(False)
        selected = self.state.participant.participant_id if self.state.participant else ""
        try:
            participants = self.state.list_participants()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._list.blockSignals(True)
        self._list.clear()
        for participant in participants:
            takes = workspace.list_takes(participant.participant_id)
            recent = max(
                (take.ended_at or take.started_at for take in takes), default=""
            )
            recent_text = recent[:19].replace("T", " ") if recent else "Henüz kayıt yok"
            item = QListWidgetItem(
                f"{participant.code}\n{len(takes)} kayıt · {recent_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, participant.participant_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, participant.code.casefold())
            self._list.addItem(item)
            if participant.participant_id == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        if not participants:
            item = QListWidgetItem(
                "Henüz katılımcı yok.\nKatılımcı Ekle ile ilk anonim kodu oluşturun."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        self._filter(self._search.text())
        self._refresh_details()

    def _filter(self, text: str) -> None:
        query = text.strip().casefold()
        for index in range(self._list.count()):
            item = self._list.item(index)
            code = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
            item.setHidden(bool(query) and query not in code)

    def _select(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        participant_id = item.data(Qt.ItemDataRole.UserRole)
        if not participant_id:
            return
        try:
            self.state.set_participant(self.state.load_participant(str(participant_id)))
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._refresh_details()

    def _refresh_details(self) -> None:
        participant = self.state.participant
        workspace = self.state.workspace
        if participant is None or workspace is None:
            self._details.set_items([("Durum", "Katılımcı seçilmedi")])
            self._start.setEnabled(False)
            self._recordings.setEnabled(False)
            return
        takes = workspace.list_takes(participant.participant_id)
        recent = max((take.ended_at or take.started_at for take in takes), default="")
        self._details.set_items(
            [
                ("Kod", participant.code),
                ("Oluşturma", participant.created_at[:19].replace("T", " ")),
                ("Toplam kayıt", str(len(takes))),
                ("Son kayıt", recent[:19].replace("T", " ") if recent else "Henüz kayıt yok"),
            ]
        )
        self._start.setEnabled(True)
        self._recordings.setEnabled(bool(takes))

    def _create_participant(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        try:
            preview = workspace.preview_next_participant_code()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        dialog = NewParticipantDialog(preview, self.theme, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            participant = self.state.create_participant()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(f"Katılımcı oluşturuldu: {participant.code}")
        self._reload()
        if dialog.start_after_add:
            self._start_capture()

    def _start_capture(self) -> None:
        participant = self.state.participant
        workspace = self.state.workspace
        if participant is None or workspace is None:
            self.state.notify("Önce bir katılımcı seçin.", 5000)
            return
        protocol_id: Optional[str] = None
        protocols = workspace.project.protocols
        if len(protocols) > 1:
            labels = [protocol.name for protocol in protocols]
            label, accepted = QInputDialog.getItem(
                self,
                "Kayıt Planı Seçin",
                "Bu kayıt için Kayıt Planı:",
                labels,
                0,
                False,
            )
            if not accepted:
                return
            protocol_id = protocols[labels.index(label)].protocol_id
        try:
            self.state.prepare_capture(participant, protocol_id=protocol_id)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(f"{participant.code} için çekim hazır.")
        self.navigate_requested.emit("capture")

    def _show_recordings(self) -> None:
        if self.state.participant is not None:
            self.navigate_requested.emit("review")


__all__ = ["NewParticipantDialog", "ParticipantsPage"]
