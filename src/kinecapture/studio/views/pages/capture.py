"""The Capture screen: one scene, one console beside it, one transport below.

The shape is an operator's desk, not a form. The camera image is the work, so
it takes the whole left side and every pixel left over. Everything that
*configures* the shot stands in a column beside it, at a readable width, and
everything that *starts and stops* the shot is one bar along the bottom where
a hand can find it without reading.

Three things this layout exists to get right:

* **Nothing scrolls.** An earlier version put the settings in a scroll area
  under the image, which meant controls were hidden below a fold while a third
  of the window sat empty. Width was the room that was going spare, so width is
  where the settings went.
* **The person in the frame is chosen by clicking on them.** There is no
  dropdown for it and there never should be: the operator is looking at the
  image, and the thing they want is under the pointer.
* **Who owns the data is shown, never asked for here.** The participant is a
  property of the project and is chosen on Projeler. This screen states it
  plainly so a recording can never go somewhere the operator did not expect,
  which is what the 15 September audit caught it doing.

Recording is said in three places at once - the button, a red border on the
image, and the shell's recording strip - because an operator looking at the
participant rather than the screen needs more than one chance to notice.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.capture import CaptureMetrics
from kinecapture.studio.services.session import WorkTarget
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.capture import (
    COUNTDOWN_CHOICES,
    DURATION_CHOICES,
    RECORDING_MODES,
    Alert,
    CaptureViewModel,
)
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
from ..preview import PreviewView
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: Metrics refresh rate. Two to four times a second, never per frame: a number
#: that changes faster than it can be read costs paint time and gives nothing.
_METRICS_INTERVAL_MS = 300
#: Preview repaint rate, matched to the capture profile's preview target.
_PREVIEW_INTERVAL_MS = 66

#: The console column's width. Wide enough for a sentence about the target,
#: narrow enough that the camera image keeps the room.
_CONSOLE_WIDTH = 360


class _Metric(QWidget):
    """One labelled number, in the mono face so the row does not jump."""

    def __init__(self, caption: str, tokens: ThemeTokens, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        layout = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingSm")
        layout.setContentsMargins(0, margin, 0, margin)
        layout.setSpacing(tokens.metric("KcSpacingXs"))
        self._caption = label(caption, role="contextKey")
        self._value = mono_label("—")
        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        self.setMinimumWidth(104)

    def set_value(self, text: str, *, status: str = "") -> None:
        self._value.setText(text)
        self._value.setProperty("kcStatus", status or None)
        style = self._value.style()
        style.unpolish(self._value)
        style.polish(self._value)


class _ConsoleGroup(QWidget):
    """One titled block in the console column."""

    def __init__(self, title: str, tokens: ThemeTokens, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(tokens.metric("KcSpacingSm"))
        self.column.addWidget(label(title, role="sectionTitle"))

    def add(self, widget: QWidget) -> QWidget:
        self.column.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:  # noqa: ANN001
        self.column.addLayout(layout)


class CapturePage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[CaptureViewModel] = None

        self.alert_strip = QWidget(self)
        self._alert_layout = QVBoxLayout(self.alert_strip)
        self._alert_layout.setContentsMargins(0, 0, 0, 0)
        self._alert_layout.setSpacing(tokens.metric("KcSpacingSm"))
        self.alert_strip.hide()
        self.body_layout.addWidget(self.alert_strip)

        # The scene and its console, side by side. The image takes the slack.
        stage = QHBoxLayout()
        stage.setSpacing(tokens.metric("KcSpacingXl"))
        self.preview = PreviewView(tokens, self)
        stage.addWidget(self.preview, 1)
        stage.addWidget(self._build_console(tokens))
        self.body_layout.addLayout(stage, 1)

        self.body_layout.addWidget(separator())
        self.body_layout.addLayout(self._build_transport(tokens))
        self.body_layout.addLayout(self._build_metrics(tokens))

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(_METRICS_INTERVAL_MS)
        self._metrics_timer.timeout.connect(self._tick_metrics)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(_PREVIEW_INTERVAL_MS)
        self._preview_timer.timeout.connect(self._tick_preview)
        # The countdown and the optional timed stop both live on one second,
        # which is the only clock this screen needs and the viewmodel has none.
        self._second = QTimer(self)
        self._second.setInterval(1000)
        self._second.timeout.connect(self._tick_second)

        # Reachable from the frame: somebody standing in the shot cannot aim
        # at a button, and pressing the wrong one of two is worse than one key
        # that does the right thing whatever the state is.
        for sequence in ("Space", "F5"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._toggle_recording)

    # ------------------------------------------------------------- assembly
    def _build_console(self, tokens: ThemeTokens) -> QWidget:
        """Everything that configures the shot, in one readable column."""
        panel = QFrame(self)
        panel.setProperty("kcSurface", "raised")
        panel.setFixedWidth(_CONSOLE_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        column = QVBoxLayout(panel)
        # No margins here: ``QFrame[kcSurface="raised"]`` carries the inset, so
        # the gap between a border and what it holds is decided in one place.
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingXl"))

        column.addWidget(self._build_target_group(tokens))
        column.addWidget(separator())
        column.addWidget(self._build_subject_group(tokens))
        column.addWidget(separator())
        column.addWidget(self._build_mode_group(tokens))
        column.addWidget(separator())
        column.addWidget(self._build_solo_group(tokens))
        column.addStretch(1)
        return panel

    def _build_target_group(self, tokens: ThemeTokens) -> QWidget:
        """Who the take is written to. Stated here, chosen on Projeler.

        Deliberately not a control: the participant belongs to the project, and
        a second place to change it is a second answer to the same question -
        which is how a take ended up under P0001 with P0002 selected.
        """
        group = _ConsoleGroup("KAYIT HEDEFİ", tokens, self)
        self.target_value = label("—", role="fieldLabel")
        self.target_value.setWordWrap(True)
        group.add(self.target_value)
        self.target_detail = label("", role="pageSubtitle")
        self.target_detail.setWordWrap(True)
        group.add(self.target_detail)
        return group

    def _build_subject_group(self, tokens: ThemeTokens) -> QWidget:
        """The person in the frame, picked by clicking on them."""
        group = _ConsoleGroup("GÖRÜNTÜDEKİ KİŞİ", tokens, self)
        self.subject_label = label("Kişi seçilmedi", role="fieldLabel")
        self.subject_label.setWordWrap(True)
        group.add(self.subject_label)
        self.subject_hint = label(
            "Kaydedilecek kişiyi görüntüde üzerine tıklayarak seçin.",
            role="pageSubtitle",
        )
        self.subject_hint.setWordWrap(True)
        group.add(self.subject_hint)
        self.clear_subject_button = QPushButton("Kişi seçimini kaldır")
        self.clear_subject_button.setProperty("kcVariant", "quiet")
        self.clear_subject_button.setEnabled(False)
        self.clear_subject_button.clicked.connect(self._clear_subject)
        group.add(self.clear_subject_button)
        return group

    def _build_mode_group(self, tokens: ThemeTokens) -> QWidget:
        group = _ConsoleGroup("KAYIT MODU", tokens, self)
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[str, QRadioButton] = {}
        for mode in RECORDING_MODES:
            button = QRadioButton(mode.label)
            tip = mode.detail + (f"  ({mode.cost})" if mode.cost else "")
            button.setToolTip(tip)
            button.setAccessibleDescription(tip)
            button.toggled.connect(
                lambda checked, key=mode.key: self._mode_chosen(key, checked)
            )
            self._mode_group.addButton(button)
            self._mode_buttons[mode.key] = button
            group.add(button)
            if mode.cost:
                cost = label(mode.cost, role="fieldCost")
                cost.setWordWrap(True)
                group.add(cost)

        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingMd"))
        # "Etkin" is a claim about the camera, so it is a separate readout from
        # the radio button, which is only a claim about what was clicked.
        self.mode_state = label("—", role="contextValue")
        self.mode_state.setProperty("kcStatus", "neutral")
        self.mode_state.setToolTip(
            "Seçilen mod ile kameranın gerçekten çalıştığı mod ayrı gösterilir."
        )
        row.addWidget(self.mode_state)
        self.apply_mode_button = QPushButton("Modu uygula")
        self.apply_mode_button.setProperty("kcVariant", "quiet")
        self.apply_mode_button.setToolTip(
            "Kamerayı seçilen kayıt moduyla yeniden bağlar."
        )
        self.apply_mode_button.setVisible(False)
        self.apply_mode_button.clicked.connect(self._apply_mode)
        row.addWidget(self.apply_mode_button)
        row.addStretch(1)
        group.add_layout(row)
        return group

    def _build_solo_group(self, tokens: ThemeTokens) -> QWidget:
        """Everything needed to record without a second person in the room."""
        group = _ConsoleGroup("TEK BAŞINA", tokens, self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.metric("KcSpacingLg"))
        grid.setVerticalSpacing(tokens.metric("KcSpacingMd"))
        grid.setColumnStretch(1, 1)

        grid.addWidget(label("Geri sayım"), 0, 0)
        self.countdown_box = QComboBox()
        self.countdown_box.setAccessibleName("Geri sayım süresi")
        self.countdown_box.setToolTip(
            "Kayıt bu kadar saniye sonra başlar. Kadraja girmek için süre bırakır."
        )
        for seconds in COUNTDOWN_CHOICES:
            self.countdown_box.addItem(
                "kapalı" if not seconds else f"{seconds} sn", seconds
            )
        self.countdown_box.activated.connect(self._countdown_chosen)
        grid.addWidget(self.countdown_box, 0, 1)

        grid.addWidget(label("Süre sonunda dur"), 1, 0)
        self.duration_box = QComboBox()
        self.duration_box.setAccessibleName("Kayıt süresi sınırı")
        self.duration_box.setToolTip("Bu süre dolunca kayıt kendiliğinden kapanır.")
        for seconds in DURATION_CHOICES:
            self.duration_box.addItem(
                "sınırsız" if not seconds else f"{seconds} sn", seconds
            )
        self.duration_box.activated.connect(self._duration_chosen)
        grid.addWidget(self.duration_box, 1, 1)
        group.add_layout(grid)

        self.mirror_box = QCheckBox("Önizlemeyi aynala")
        self.mirror_box.setToolTip(
            "Önizlemeyi yatay çevirir. Kaydedilen görüntü değişmez."
        )
        self.mirror_box.toggled.connect(self._mirror_toggled)
        group.add(self.mirror_box)
        self.guides_box = QCheckBox("Kadraj kılavuzu")
        self.guides_box.setToolTip(
            "Üçte bir çizgileri ve baş/ayak payı. Yalnız çerçeveleme yardımıdır; "
            "kişinin kadrajda olduğunu ölçmez."
        )
        self.guides_box.toggled.connect(self._guides_toggled)
        group.add(self.guides_box)

        self.framing_label = label("", role="fieldLabel")
        self.framing_label.setWordWrap(True)
        self.framing_label.setToolTip(
            "Tüm vücudun kadrajda olup olmadığı. Canlı önizleme pozundan "
            "ölçülür; kaydedilen veriyi etkilemez."
        )
        group.add(self.framing_label)
        self.framing_advice = label("", role="pageSubtitle")
        self.framing_advice.setWordWrap(True)
        self.framing_advice.hide()
        group.add(self.framing_advice)

        self.pose_note = label("", role="pageSubtitle")
        self.pose_note.setWordWrap(True)
        self.pose_note.hide()
        group.add(self.pose_note)
        return group

    def _build_transport(self, tokens: ThemeTokens) -> QHBoxLayout:
        """Start and stop, where a hand can find them without reading."""
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingLg"))

        self.connect_button = QPushButton("Bağlan")
        self.connect_button.setMinimumWidth(150)
        self.record_button = QPushButton("Kayda başla")
        self.record_button.setProperty("kcVariant", "primary")
        self.record_button.setMinimumWidth(190)
        self.record_button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.record_button.setEnabled(False)
        self.marker_button = QPushButton("İşaret koy")
        self.marker_button.setProperty("kcVariant", "quiet")
        self.marker_button.setEnabled(False)

        self.elapsed = mono_label("00:00")
        self.elapsed.setToolTip("Açık kaydın süresi")
        self.countdown_label = mono_label("")
        self.countdown_label.setProperty("kcStatus", "warning")
        self.countdown_label.setVisible(False)

        row.addWidget(self.connect_button)
        row.addWidget(self.record_button)
        row.addWidget(self.elapsed)
        row.addWidget(self.countdown_label)
        row.addWidget(self.marker_button)
        row.addStretch(1)
        row.addWidget(
            label("Boşluk veya F5: başlat / durdur", role="pageSubtitle")
        )

        self.connect_button.clicked.connect(self._toggle_connection)
        self.record_button.clicked.connect(self._toggle_recording)
        self.marker_button.clicked.connect(self._add_marker)
        self.preview.clicked.connect(self._preview_clicked)
        return row

    def _build_metrics(self, tokens: ThemeTokens) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingXxl"))
        self.metrics_widgets = {
            "acquisition": _Metric("Yakalama FPS", tokens, self),
            "recorded": _Metric("Kaydedilen kare", tokens, self),
            # The two loss counters are never merged: one is the interface
            # keeping up, the other is data that will not exist.
            "recording_loss": _Metric("Kayıt kaybı", tokens, self),
            "preview_loss": _Metric("Önizleme kaybı", tokens, self),
            "disk": _Metric("Diskte kalan", tokens, self),
        }
        for widget in self.metrics_widgets.values():
            row.addWidget(widget)
        row.addStretch(1)
        return row

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: CaptureViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.metrics, self._show_metrics)
        self.bind(viewmodel.alerts, self._show_alerts)
        self.bind(viewmodel.anchor, self._show_anchor)
        self.bind(viewmodel.pose_note, self._show_pose_note)
        self.bind(viewmodel.framing, self._show_framing)
        self.bind(viewmodel.mode, self._show_mode)
        self.bind(viewmodel.active_mode, lambda _m: self._show_mode_state())
        self.bind(viewmodel.mode_pending, lambda _p: self._show_mode_state())
        self.bind(viewmodel.target, self._show_target)
        self.bind(viewmodel.countdown, self._show_countdown)
        self.bind(viewmodel.countdown_seconds, self._show_countdown_choice)
        self.bind(viewmodel.auto_stop_seconds, self._show_duration_choice)
        self.bind(viewmodel.mirrored, self._show_mirror)
        self.bind(viewmodel.guides, self._show_guides)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        self._metrics_timer.start()
        self._preview_timer.start()
        self._second.start()
        if self.viewmodel is not None:
            self.viewmodel.refresh_target()
            self.viewmodel.refresh()

    def page_deactivated(self) -> None:
        """Stop the timers. A screen nobody is looking at costs nothing.

        The camera is deliberately *not* closed: leaving Capture to change a
        setting and coming back should not mean waiting for the SDK to open
        again, which on a cold start is measured in minutes.
        """
        self._metrics_timer.stop()
        self._preview_timer.stop()
        self._second.stop()
        # A countdown belongs to the screen the operator is looking at. Leaving
        # it must not start a recording behind their back.
        if self.viewmodel is not None:
            self.viewmodel.cancel_countdown()

    # ----------------------------------------------------------------- ticks
    def _tick_metrics(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.refresh()

    def _tick_second(self) -> None:
        if self.viewmodel is None:
            return
        self.viewmodel.tick_countdown()
        self.viewmodel.tick_auto_stop()

    def _tick_preview(self) -> None:
        if self.viewmodel is None:
            return
        packet = self.viewmodel.service.latest_frame()
        if packet is None or packet.color_frame is None:
            return
        self.preview.set_frame(packet.color_frame, tuple(packet.resolution))
        preview = self.viewmodel.service.pose_preview()
        if preview is not None and preview.packet is packet:
            from kinecapture.preview.pose import BONES

            self.preview.set_people(preview.people, BONES)
        # Measured per frame and painted over the picture, because the person
        # who has to act on it is standing three metres away from the keyboard.
        framing = self.viewmodel.observe_framing()
        self.preview.set_framing(
            framing.text, framing.state, self.viewmodel.framing_history.value
        )

    # ----------------------------------------------------------------- slots
    def _show_metrics(self, metrics: CaptureMetrics) -> None:
        widgets = self.metrics_widgets
        widgets["acquisition"].set_value(f"{metrics.acquisition_fps:5.1f}")
        widgets["recorded"].set_value(f"{metrics.recorded_frames}")
        widgets["recording_loss"].set_value(
            f"{metrics.recording_dropped}",
            status="error" if metrics.recording_dropped else "",
        )
        widgets["preview_loss"].set_value(f"{metrics.preview_dropped}")
        widgets["disk"].set_value(
            f"{metrics.free_minutes:5.0f} dk" if metrics.free_bytes else "—",
            status="warning" if 0 < metrics.free_minutes < 10 else "",
        )
        self.elapsed.setText(metrics.elapsed_text)
        self.preview.set_recording(metrics.recording)

        stopping = bool(self.viewmodel and self.viewmodel.stopping.value)
        connecting = bool(self.viewmodel and self.viewmodel.connecting.value)
        counting = bool(self.viewmodel and self.viewmodel.countdown.value)

        # Enabled whenever there is a camera to record from. A missing
        # participant is answered when the button is pressed, with a sentence
        # saying what to do - never by a button that silently does nothing,
        # which is what made the ZED impossible to record with.
        self.record_button.setEnabled(
            counting or (metrics.connected and not stopping)
        )
        if stopping:
            self.record_button.setText("Kapatılıyor…")
        elif counting:
            self.record_button.setText("Geri sayımı iptal et")
        else:
            self.record_button.setText(
                "Kaydı durdur" if metrics.recording else "Kayda başla"
            )
        self.marker_button.setEnabled(metrics.recording)
        self.connect_button.setEnabled(
            not metrics.recording and not stopping and not connecting
        )
        if connecting:
            self.connect_button.setText("Bağlanıyor…")
        else:
            self.connect_button.setText(
                "Bağlantıyı kes" if metrics.connected else "Bağlan"
            )
        self.preview.set_placeholder(
            "Kamera bağlı" if metrics.connected else "Kamera bağlı değil"
        )
        # The window title is the shell's: it has to keep saying RECORDING on
        # the seven screens that are not this one.

    def _show_alerts(self, alerts: tuple[Alert, ...]) -> None:
        while self._alert_layout.count():
            item = self._alert_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for alert in alerts:
            strip = ElidedLabel(alert.text)
            strip.setProperty("kcStatus", alert.level.value)
            strip.setToolTip(alert.text)
            strip.setAccessibleName(f"{alert.level.value}: {alert.text}")
            self._alert_layout.addWidget(strip)
        self.alert_strip.setVisible(bool(alerts))

    def _show_anchor(self, anchor) -> None:  # noqa: ANN001
        if anchor is None:
            self.subject_label.setText("Kişi seçilmedi")
            self.subject_label.setToolTip("")
            self.subject_hint.setText(
                "Kaydedilecek kişiyi görüntüde üzerine tıklayarak seçin."
            )
            self.clear_subject_button.setEnabled(False)
            return
        self.subject_label.setText("Kişi seçildi")
        self.subject_hint.setText(
            "Seçim gösterilen karenin zaman damgasına bağlandı; eşleştirme "
            "kayıttan sonra yapılır. Değiştirmek için başka birine tıklayın."
        )
        self.subject_label.setToolTip(
            f"kare zaman damgası {anchor.camera_timestamp_ns} ns"
        )
        self.clear_subject_button.setEnabled(True)

    def _show_framing(self, framing) -> None:  # noqa: ANN001 - Framing
        """Repeat the badge in the console, with the reason spelled out."""
        self.framing_label.setText(framing.text)
        self.framing_label.setProperty(
            "kcStatus",
            {"ok": "live", "tight": "warning", "cut": "error", "crowded": "warning"}.get(
                framing.state, ""
            ),
        )
        self.framing_label.style().unpolish(self.framing_label)
        self.framing_label.style().polish(self.framing_label)
        self.framing_advice.setText(framing.advice)
        self.framing_advice.setVisible(bool(framing.advice))

    def _show_pose_note(self, text: str) -> None:
        """Only takes height when it has something to say."""
        self.pose_note.setText(text)
        self.pose_note.setVisible(bool(text))

    def _show_mode(self, key: str) -> None:
        button = self._mode_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._show_mode_state()

    def _show_mode_state(self) -> None:
        """Say which mode is in force, which is not the same as which is ticked."""
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        active = viewmodel.active_mode.value
        pending = viewmodel.mode_pending.value
        if not active:
            text, status = "kamera bağlı değil", "neutral"
        elif pending:
            text, status = "seçildi · etkin değil", "warning"
        else:
            text, status = "etkin", "live"
        self.mode_state.setText(text)
        self.mode_state.setProperty("kcStatus", status)
        style = self.mode_state.style()
        style.unpolish(self.mode_state)
        style.polish(self.mode_state)
        self.apply_mode_button.setVisible(pending)
        self.apply_mode_button.setEnabled(
            pending and not viewmodel.metrics.value.recording
        )

    def _show_target(self, target: WorkTarget) -> None:
        if not target.is_set:
            self.target_value.setText("Seçilmedi")
            self.target_detail.setText(
                "Kayıt hedefi Projeler ekranında seçilir. Seçilmemişse kayda "
                "başlarken bu proje için bir katılımcı hazırlanır."
            )
            return
        self.target_value.setText(target.participant_code)
        if target.session_open:
            self.target_detail.setText(
                f"{target.project_name} · açık oturum {target.session_id}"
            )
        else:
            self.target_detail.setText(
                f"{target.project_name} · kayda başlayınca yeni oturum açılır"
            )

    def _show_countdown(self, seconds: int) -> None:
        self.preview.set_countdown(seconds)
        self.countdown_label.setText(f"{seconds} sn" if seconds else "")
        self.countdown_label.setVisible(bool(seconds))

    def _show_countdown_choice(self, seconds: int) -> None:
        index = self.countdown_box.findData(seconds)
        if index >= 0:
            self.countdown_box.setCurrentIndex(index)

    def _show_duration_choice(self, seconds: int) -> None:
        index = self.duration_box.findData(seconds)
        if index >= 0:
            self.duration_box.setCurrentIndex(index)

    def _show_mirror(self, mirrored: bool) -> None:
        self.preview.set_mirrored(mirrored)
        if self.mirror_box.isChecked() != mirrored:
            self.mirror_box.setChecked(mirrored)

    def _show_guides(self, shown: bool) -> None:
        self.preview.set_guides(shown)
        if self.guides_box.isChecked() != shown:
            self.guides_box.setChecked(shown)

    # --------------------------------------------------------------- actions
    def _mode_chosen(self, key: str, checked: bool) -> None:
        if checked and self.viewmodel is not None:
            self.viewmodel.set_mode(key)

    def _apply_mode(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.apply_mode()

    def _countdown_chosen(self, _index: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_countdown_seconds(self.countdown_box.currentData())

    def _duration_chosen(self, _index: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_auto_stop_seconds(self.duration_box.currentData())

    def _mirror_toggled(self, mirrored: bool) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_mirrored(mirrored)

    def _guides_toggled(self, shown: bool) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_guides(shown)

    def _toggle_connection(self) -> None:
        if self.viewmodel is None:
            return
        if self.viewmodel.service.is_connected:
            self.viewmodel.disconnect()
        else:
            self.viewmodel.connect()

    def _toggle_recording(self) -> None:
        """Start, cancel the countdown, or stop - whichever applies now."""
        if self.viewmodel is not None:
            self.viewmodel.toggle_recording()

    def _add_marker(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.add_marker()

    def _clear_subject(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.clear_subject()

    def _preview_clicked(self, x: float, y: float) -> None:
        if self.viewmodel is not None:
            self.viewmodel.select_subject(x, y)


__all__ = ["CapturePage"]
