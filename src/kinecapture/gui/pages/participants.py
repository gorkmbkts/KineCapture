"""Participants and sessions: who is being recorded, and under what conditions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.errors import KineCaptureError
from kinecapture.core.ids import utc_now_iso
from kinecapture.domain.enums import ConsentStatus
from kinecapture.domain.project import Participant, Session
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    FieldRow,
    KeyValueList,
    StatusChip,
    make_button,
    make_label,
)

_CONSENT_LABELS = {
    ConsentStatus.UNKNOWN: "Belirtilmedi",
    ConsentStatus.GRANTED: "Onay alındı",
    ConsentStatus.WITHDRAWN: "Onay geri çekildi",
}


class ParticipantsPage(Page):
    """Participant roster on the left, session form and history on the right."""

    title = "Katılımcılar ve Oturumlar"
    description = (
        "Katılımcılar anonim kodla temsil edilir. Kişisel veri toplanmaz."
    )
    icon = "participants"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme

        self._new_participant = make_button(
            "Yeni katılımcı", variant="primary", icon="add", theme=theme
        )
        self._new_participant.clicked.connect(self._create_participant)
        self.header.add_action(self._new_participant)

        self._empty = EmptyState(
            "Önce bir proje açın",
            "Katılımcılar bir projeye aittir.",
            theme=theme,
            icon="project",
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        layout = QHBoxLayout(self._body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)
        layout.addWidget(self._build_roster(theme), 2)
        layout.addWidget(self._build_session_panel(theme), 3)
        self.content.addWidget(self._body, 1)

        state.project_changed.connect(lambda _: self._reload())
        state.dataset_changed.connect(self._reload)
        self._set_empty(True)

    # --------------------------------------------------------------- layout
    def _build_roster(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        card = Card("Katılımcılar", theme=theme, icon="participants")
        self._participant_list = QListWidget()
        self._participant_list.setAlternatingRowColors(True)
        self._participant_list.currentItemChanged.connect(
            lambda current, _: self._participant_selected(current)
        )
        card.add_widget(self._participant_list, 1)
        layout.addWidget(card, 2)

        detail = Card("Katılımcı ayrıntısı", theme=theme, icon="info")
        self._participant_details = KeyValueList(theme)
        detail.add_widget(self._participant_details)

        form = QWidget()
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(theme.space_sm)

        metrics = QHBoxLayout()
        self._height = QDoubleSpinBox()
        self._height.setRange(0.0, 260.0)
        self._height.setSuffix(" cm")
        self._height.setSpecialValueText("belirtilmedi")
        metrics.addWidget(FieldRow("Boy", self._height, theme=theme))
        self._mass = QDoubleSpinBox()
        self._mass.setRange(0.0, 400.0)
        self._mass.setSuffix(" kg")
        self._mass.setSpecialValueText("belirtilmedi")
        metrics.addWidget(FieldRow("Kilo", self._mass, theme=theme))
        self._dominant = QComboBox()
        self._dominant.addItems(["unknown", "right", "left", "ambidextrous"])
        metrics.addWidget(FieldRow("Dominant taraf", self._dominant, theme=theme))
        metrics_container = QWidget()
        metrics_container.setLayout(metrics)
        form_layout.addWidget(metrics_container)

        self._participant_notes = QPlainTextEdit()
        self._participant_notes.setMaximumHeight(60)
        self._participant_notes.setPlaceholderText(
            "Kişisel bilgi yazmayın; yalnızca çalışmayla ilgili not."
        )
        form_layout.addWidget(
            FieldRow("Not", self._participant_notes, theme=theme)
        )

        save_button = make_button("Katılımcıyı kaydet", icon="check", theme=theme)
        save_button.clicked.connect(self._save_participant)
        form_layout.addWidget(save_button)
        detail.add_widget(form)
        layout.addWidget(detail, 3)
        return wrapper

    def _build_session_panel(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        card = Card(
            "Yeni oturum",
            subtitle="Zorunlu alanlar proje şemasıyla belirlenir.",
            theme=theme,
            icon="clock",
        )
        self._active_chip = StatusChip("Oturum seçilmedi", theme=theme, icon="info")
        card.add_header_widget(self._active_chip)

        self._operator = QLineEdit()
        self._operator.setPlaceholderText("Operatör adı veya kodu")
        self._operator_row = FieldRow(
            "Operatör", self._operator, theme=theme, required=True
        )
        card.add_widget(self._operator_row)

        self._protocol = QComboBox()
        card.add_widget(FieldRow("Protokol", self._protocol, theme=theme))

        self._consent = QComboBox()
        for status in ConsentStatus:
            self._consent.addItem(_CONSENT_LABELS[status], status.value)
        self._consent_row = FieldRow(
            "Onam durumu",
            self._consent,
            theme=theme,
            help_text="Onam metni bu uygulamada saklanmaz; yalnızca durum kaydedilir.",
        )
        card.add_widget(self._consent_row)

        self._session_notes = QPlainTextEdit()
        self._session_notes.setMaximumHeight(56)
        card.add_widget(FieldRow("Oturum notu", self._session_notes, theme=theme))

        buttons = QHBoxLayout()
        self._start_session = make_button(
            "Oturumu başlat", variant="primary", icon="add", theme=theme
        )
        self._start_session.clicked.connect(self._create_session)
        buttons.addWidget(self._start_session)
        self._end_session = make_button("Oturumu kapat", icon="check", theme=theme)
        self._end_session.clicked.connect(self._close_session)
        buttons.addWidget(self._end_session)
        buttons.addStretch(1)
        container = QWidget()
        container.setLayout(buttons)
        card.add_widget(container)
        layout.addWidget(card)

        history = Card("Oturumlar", theme=theme, icon="list")
        self._session_list = QListWidget()
        self._session_list.setAlternatingRowColors(True)
        self._session_list.itemDoubleClicked.connect(self._activate_session)
        history.add_widget(self._session_list, 1)
        activate = make_button(
            "Seçili oturumu aktif yap", variant="primary", theme=theme
        )
        activate.clicked.connect(
            lambda: self._activate_session(self._session_list.currentItem())
        )
        history.add_widget(activate)
        self._session_hint = make_label("", role="muted")
        self._session_hint.setWordWrap(True)
        history.add_widget(self._session_hint)
        layout.addWidget(history, 1)
        return wrapper

    # ----------------------------------------------------------------- data
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

        selected_id = (
            self.state.participant.participant_id if self.state.participant else None
        )
        self._participant_list.blockSignals(True)
        self._participant_list.clear()
        participants = workspace.list_participants()
        for participant in participants:
            sessions = workspace.list_sessions(participant.participant_id)
            takes = workspace.list_takes(participant.participant_id)
            item = QListWidgetItem(
                f"{participant.code}\n{len(sessions)} oturum · {len(takes)} kayıt"
            )
            item.setData(Qt.ItemDataRole.UserRole, participant.participant_id)
            self._participant_list.addItem(item)
            if participant.participant_id == selected_id:
                self._participant_list.setCurrentItem(item)
        self._participant_list.blockSignals(False)

        if not participants:
            item = QListWidgetItem(
                "Katılımcı yok.\n'Yeni katılımcı' ile P0001 oluşturun."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._participant_list.addItem(item)

        self._protocol.clear()
        self._protocol.addItem("(protokolsüz serbest kayıt)", None)
        for protocol in workspace.project.protocols:
            self._protocol.addItem(protocol.name, protocol.protocol_id)

        self._refresh_participant_detail()
        self._refresh_sessions()

    def _participant_selected(self, item: Optional[QListWidgetItem]) -> None:
        workspace = self.state.workspace
        if workspace is None or item is None:
            return
        participant_id = item.data(Qt.ItemDataRole.UserRole)
        if not participant_id:
            return
        try:
            participant = workspace.load_participant(participant_id)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.set_participant(participant)
        self._refresh_participant_detail()
        self._refresh_sessions()

    def _refresh_participant_detail(self) -> None:
        participant = self.state.participant
        if participant is None:
            self._participant_details.set_items([("Durum", "Katılımcı seçilmedi")])
            return
        workspace = self.state.workspace
        sessions = (
            workspace.list_sessions(participant.participant_id) if workspace else []
        )
        takes = workspace.list_takes(participant.participant_id) if workspace else []
        self._participant_details.set_items(
            [
                ("Kod", participant.code),
                ("Oluşturma", participant.created_at[:19].replace("T", " ")),
                ("Oturum", str(len(sessions))),
                ("Kayıt", str(len(takes))),
            ]
        )
        self._height.setValue(participant.height_cm or 0.0)
        self._mass.setValue(participant.mass_kg or 0.0)
        self._dominant.setCurrentText(participant.dominant_side)
        self._participant_notes.setPlainText(participant.notes)

    def _refresh_sessions(self) -> None:
        workspace = self.state.workspace
        participant = self.state.participant
        self._session_list.clear()
        if workspace is None or participant is None:
            self._session_hint.setText("Önce bir katılımcı seçin.")
            self._start_session.setEnabled(False)
            return
        self._start_session.setEnabled(True)

        sessions = sorted(
            workspace.list_sessions(participant.participant_id),
            key=lambda s: s.started_at,
            reverse=True,
        )
        active = self.state.session
        for session in sessions:
            takes = workspace.list_takes(participant.participant_id, session.session_id)
            status = "AÇIK" if session.is_open else "kapalı"
            marker = " ← aktif" if active and active.session_id == session.session_id else ""
            item = QListWidgetItem(
                f"{session.started_at[:19].replace('T', ' ')}  ·  {status}{marker}\n"
                f"{len(takes)} kayıt · operatör: {session.operator or '-'} · "
                f"{_CONSENT_LABELS[session.consent]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            self._session_list.addItem(item)

        if not sessions:
            item = QListWidgetItem("Bu katılımcı için oturum yok.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._session_list.addItem(item)

        self._update_active_chip()

    def _update_active_chip(self) -> None:
        session = self.state.session
        if session is None:
            self._active_chip.set_status(
                "Oturum seçilmedi", icon="info", colour=self.theme.text_muted
            )
            self._end_session.setEnabled(False)
            self._session_hint.setText(
                "Kayıt almak için bir oturum başlatın veya var olanı aktif yapın."
            )
            return
        self._active_chip.set_status(
            f"Aktif: {session.session_id[-12:]}",
            icon="check",
            colour=self.theme.success,
        )
        self._end_session.setEnabled(session.is_open)
        self._session_hint.setText(
            f"Aktif oturum {session.session_id}. Capture ekranından kayıt alabilirsiniz."
        )

    # -------------------------------------------------------------- actions
    def _create_participant(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        try:
            participant = workspace.create_participant()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.set_participant(participant)
        self.state.refresh_dataset(force=True)
        self.state.notify(f"Katılımcı oluşturuldu: {participant.code}")
        self._reload()

    def _save_participant(self) -> None:
        workspace = self.state.workspace
        participant = self.state.participant
        if workspace is None or participant is None:
            return
        participant.height_cm = self._height.value() or None
        participant.mass_kg = self._mass.value() or None
        participant.dominant_side = self._dominant.currentText()
        participant.notes = self._participant_notes.toPlainText().strip()
        try:
            workspace.save_participant(participant)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(f"{participant.code} güncellendi.")
        self._refresh_participant_detail()

    def _validate_session_form(self) -> bool:
        """Field-level validation driven by the project's required-field list."""
        workspace = self.state.workspace
        if workspace is None:
            return False
        required = set(workspace.project.required_session_fields)
        valid = True
        if "operator" in required and not self._operator.text().strip():
            self._operator_row.set_error("Operatör alanı bu projede zorunludur.")
            valid = False
        else:
            self._operator_row.clear_error()
        if "consent" in required and self._consent.currentData() == ConsentStatus.UNKNOWN.value:
            self._consent_row.set_error("Onam durumu bu projede zorunludur.")
            valid = False
        else:
            self._consent_row.clear_error()
        return valid

    def _create_session(self) -> None:
        workspace = self.state.workspace
        participant = self.state.participant
        if workspace is None or participant is None:
            self.state.notify("Önce bir katılımcı seçin.", 5000)
            return
        if not self._validate_session_form():
            return
        try:
            session = workspace.create_session(
                participant.participant_id,
                operator=self._operator.text().strip(),
                protocol_id=self._protocol.currentData(),
                consent=ConsentStatus(self._consent.currentData()),
                notes=self._session_notes.toPlainText().strip(),
                capture_profile=self.state.config.capture,
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.set_session(session)
        self.state.refresh_dataset(force=True)
        self.state.notify(f"Oturum başlatıldı: {session.session_id}")
        self._session_notes.clear()
        self._refresh_sessions()

    def _activate_session(self, item: Optional[QListWidgetItem]) -> None:
        workspace = self.state.workspace
        participant = self.state.participant
        if workspace is None or participant is None or item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return
        try:
            session = workspace.load_session(participant.participant_id, session_id)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.set_session(session)
        self.state.notify(f"Aktif oturum: {session.session_id}")
        self._refresh_sessions()

    def _close_session(self) -> None:
        workspace = self.state.workspace
        session = self.state.session
        if workspace is None or session is None:
            return
        session.ended_at = utc_now_iso()
        try:
            workspace.save_session(session)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.set_session(session)
        self.state.notify("Oturum kapatıldı.")
        self._refresh_sessions()


__all__ = ["ParticipantsPage"]
