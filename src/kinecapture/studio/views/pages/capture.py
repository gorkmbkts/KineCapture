"""The Capture screen.

The image gets the room. Everything else is a thin strip: the alerts that need
answering, the transport, and a row of numbers that updates three times a
second rather than once per frame.

Recording is said in three places at once - the button, a red border on the
image, and the window title - because an operator looking at the participant
rather than the screen needs more than one chance to notice.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.capture import CaptureMetrics
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.capture import RECORDING_MODES, Alert, CaptureViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from ..preview import PreviewView
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: Metrics refresh rate. Two to four times a second, never per frame: a number
#: that changes faster than it can be read costs paint time and gives nothing.
_METRICS_INTERVAL_MS = 300
#: Preview repaint rate, matched to the capture profile's preview target.
_PREVIEW_INTERVAL_MS = 66


class _Metric(QWidget):
    """One labelled number, in the mono face so the row does not jump."""

    def __init__(self, caption: str, tokens: ThemeTokens, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._caption = label(caption, role="contextKey")
        self._value = mono_label("—")
        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        self.setMinimumWidth(96)

    def set_value(self, text: str, *, status: str = "") -> None:
        self._value.setText(text)
        self._value.setProperty("kcStatus", status or None)
        style = self._value.style()
        style.unpolish(self._value)
        style.polish(self._value)


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
        self.body_layout.addWidget(self.alert_strip)

        self.preview = PreviewView(tokens, self)
        self.body_layout.addWidget(self.preview, 1)

        self.pose_note = ElidedLabel("")
        self.pose_note.setProperty("kcRole", "pageSubtitle")
        self.body_layout.addWidget(self.pose_note)

        self.body_layout.addWidget(separator())
        self.body_layout.addLayout(self._build_modes(tokens))
        self.body_layout.addLayout(self._build_transport(tokens))
        self.body_layout.addLayout(self._build_metrics(tokens))

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(_METRICS_INTERVAL_MS)
        self._metrics_timer.timeout.connect(self._tick_metrics)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(_PREVIEW_INTERVAL_MS)
        self._preview_timer.timeout.connect(self._tick_preview)

    # ------------------------------------------------------------- assembly
    def _build_modes(self, tokens: ThemeTokens) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingLg"))
        row.addWidget(label("KAYIT MODU", role="sectionTitle"))
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
            row.addWidget(button)
            if mode.cost:
                row.addWidget(label(mode.cost, role="fieldCost"))
        row.addStretch(1)
        return row

    def _build_transport(self, tokens: ThemeTokens) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingMd"))
        self.connect_button = QPushButton("Bağlan")
        self.record_button = QPushButton("Kayda başla")
        self.record_button.setProperty("kcVariant", "primary")
        self.record_button.setEnabled(False)
        self.marker_button = QPushButton("İşaret koy")
        self.marker_button.setProperty("kcVariant", "quiet")
        self.marker_button.setEnabled(False)
        self.clear_subject_button = QPushButton("Kişi seçimini kaldır")
        self.clear_subject_button.setProperty("kcVariant", "quiet")
        self.clear_subject_button.setEnabled(False)
        self.elapsed = mono_label("00:00")
        self.subject_label = ElidedLabel("Kişi seçilmedi")
        self.subject_label.setProperty("kcRole", "pageSubtitle")

        row.addWidget(self.connect_button)
        row.addWidget(self.record_button)
        row.addWidget(self.elapsed)
        row.addWidget(self.marker_button)
        row.addWidget(separator(Qt.Orientation.Vertical))
        row.addWidget(self.subject_label, 1)
        row.addWidget(self.clear_subject_button)

        self.connect_button.clicked.connect(self._toggle_connection)
        self.record_button.clicked.connect(self._toggle_recording)
        self.marker_button.clicked.connect(self._add_marker)
        self.clear_subject_button.clicked.connect(self._clear_subject)
        self.preview.clicked.connect(self._preview_clicked)
        return row

    def _build_metrics(self, tokens: ThemeTokens) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingXl"))
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
        self.bind(viewmodel.pose_note, self.pose_note.setText)
        self.bind(viewmodel.mode, self._show_mode)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        self._metrics_timer.start()
        self._preview_timer.start()
        if self.viewmodel is not None:
            self.viewmodel.refresh()

    def page_deactivated(self) -> None:
        """Stop the timers. A screen nobody is looking at costs nothing.

        The camera is deliberately *not* closed: leaving Capture to change a
        setting and coming back should not mean waiting for the SDK to open
        again, which on a cold start is measured in minutes.
        """
        self._metrics_timer.stop()
        self._preview_timer.stop()

    # ----------------------------------------------------------------- ticks
    def _tick_metrics(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.refresh()

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
        self.record_button.setEnabled(metrics.connected)
        self.record_button.setText("Kaydı durdur" if metrics.recording else "Kayda başla")
        self.marker_button.setEnabled(metrics.recording)
        self.connect_button.setText("Bağlantıyı kes" if metrics.connected else "Bağlan")
        self.preview.set_placeholder(
            "Kamera bağlı" if metrics.connected else "Kamera bağlı değil"
        )
        window = self.window()
        if window is not None:
            title = "KineCapture Studio · Yakalama"
            window.setWindowTitle(("● KAYIT · " + title) if metrics.recording else title)

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
            self.clear_subject_button.setEnabled(False)
            return
        self.subject_label.setText(
            f"Kişi seçildi · kare zaman damgası {anchor.camera_timestamp_ns} ns"
        )
        self.clear_subject_button.setEnabled(True)

    def _show_mode(self, key: str) -> None:
        button = self._mode_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    # --------------------------------------------------------------- actions
    def _mode_chosen(self, key: str, checked: bool) -> None:
        if checked and self.viewmodel is not None:
            self.viewmodel.set_mode(key)

    def _toggle_connection(self) -> None:
        if self.viewmodel is None:
            return
        if self.viewmodel.service.is_connected:
            self.viewmodel.disconnect()
        else:
            self.viewmodel.connect()

    def _toggle_recording(self) -> None:
        if self.viewmodel is None:
            return
        if self.viewmodel.service.is_recording:
            self.viewmodel.stop_recording()
        else:
            self.viewmodel.start_recording()

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
