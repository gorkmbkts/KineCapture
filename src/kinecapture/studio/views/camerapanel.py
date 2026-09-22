"""Camera tools: the seven directions, and the handful of moves worth a button.

A compass rather than a second 3-D scene. The design review is explicit that
this must not become an expensive second viewport or a graphic filling space:
what a reader needs is to know which way they are looking and to get somewhere
else in one press, and a painted dial answers both for the cost of a few
lines.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QMenu,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.camera_presets import (
    PRESETS_BY_KEY,
    PRIMARY_PRESET_KEYS,
    SECONDARY_PRESET_KEYS,
    preset_label,
)
from kinecapture.studio.theme import ThemeTokens

from . import iconset
from .widgets import label, separator


class Compass(QWidget):
    """Which way the camera is looking, relative to the recording's front.

    Painted from two numbers. It is not a viewport: nothing is rendered into
    it, nothing is uploaded for it, and it repaints only when the camera
    actually moves.
    """

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._azimuth = 0.0
        self._elevation = 0.0
        self.setFixedHeight(72)
        self.setAccessibleName("Bakış yönü göstergesi")

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def show_camera(self, azimuth: float, elevation: float) -> None:
        """``azimuth`` is measured from the recording's own front."""
        if (azimuth, elevation) == (self._azimuth, self._elevation):
            return
        self._azimuth, self._elevation = float(azimuth), float(elevation)
        self.setAccessibleDescription(
            f"{int(math.degrees(azimuth)) % 360}° · {int(math.degrees(elevation))}°"
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        side = min(self.width(), self.height()) - 12
        box = QRectF(
            (self.width() - side) / 2.0, (self.height() - side) / 2.0, side, side
        )
        centre = box.center()
        radius = side / 2.0

        ring = QPen(QColor(tokens.colour("KcBorderStrong")))
        ring.setWidth(1)
        painter.setPen(ring)
        painter.setBrush(QColor(tokens.colour("KcSurfaceSunken")))
        painter.drawEllipse(box)

        # The four cardinal marks, in the athlete's own terms rather than the
        # screen's: "ön" is where the recording's front is, and it stays there.
        font = painter.font()
        font.setPointSize(max(7, tokens.font_size("KcFontSizeXs")))
        painter.setFont(font)
        painter.setPen(QColor(tokens.colour("KcTextMuted")))
        for caption, angle in (("Ön", 90.0), ("Sağ", 0.0), ("Arka", 270.0), ("Sol", 180.0)):
            point = QPointF(
                centre.x() + math.cos(math.radians(angle)) * (radius - 12),
                centre.y() - math.sin(math.radians(angle)) * (radius - 12),
            )
            painter.drawText(
                QRectF(point.x() - 18, point.y() - 8, 36, 16),
                int(Qt.AlignmentFlag.AlignCenter),
                caption,
            )

        # Where the viewer is standing. Drawn towards the front mark when the
        # azimuth is zero, so the needle and the captions agree.
        needle = QPen(QColor(tokens.colour("KcAccentPrimary")))
        needle.setWidth(2)
        painter.setPen(needle)
        angle = math.radians(90.0) + self._azimuth
        tip = QPointF(
            centre.x() + math.cos(angle) * (radius - 22),
            centre.y() - math.sin(angle) * (radius - 22),
        )
        painter.drawLine(centre, tip)
        painter.setBrush(QColor(tokens.colour("KcAccentPrimary")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(tip, 3.5, 3.5)

        # Elevation, as a short mark above or below the middle. Enough to say
        # "you are looking down at this"; not a second instrument.
        painter.setPen(QPen(QColor(tokens.colour("KcTextMuted")), 1))
        height = centre.y() - math.sin(self._elevation) * (radius - 30)
        painter.drawLine(
            QPointF(centre.x() - 6, height), QPointF(centre.x() + 6, height)
        )
        painter.end()


class CameraPanel(QWidget):
    """Presets and the moves that go with them."""

    preset_chosen = Signal(str)
    centre_requested = Signal()
    fit_requested = Signal()
    floor_toggled = Signal(bool)
    overlay_toggled = Signal(bool)
    view_saved = Signal()
    view_restored = Signal()
    previous_requested = Signal()
    front_set = Signal()
    reduce_motion_toggled = Signal(bool)
    advanced_requested = Signal()

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        # Everything here is sized to fit the panel without scrolling, which
        # is a hard constraint rather than a preference: it needed 652 px in a
        # 455 px band, and the overflow showed up as the dial drawn over the
        # line under it. What did not fit is not hidden - it is in the
        # "Gelişmiş…" window, named and one press away.
        # Comfortable margins on all four sides. Without them the preset
        # buttons ran into the panel's own edges, which is what made this
        # column read as three slabs rather than as a group of controls.
        pad = tokens.metric("KcSpacingLg")
        column.setContentsMargins(pad, pad, pad, pad)
        column.setSpacing(tokens.metric("KcSpacingMd"))

        column.addWidget(label("BAKIŞ", role="sectionTitle"))
        # The compass dial is gone by the 21 September user decision. It was a
        # painted instrument taking 72 px of the panel's scarcest direction to
        # say something the preset buttons under it already say. What it was
        # *useful* for - stating where "ön" was measured from - is the line
        # below, which stays: an orientation with no provenance is an
        # assertion nobody can check. The widget itself is kept and parented
        # here without being laid out, so the page's camera wiring and the
        # tests that read the azimuth still resolve.
        self.compass = Compass(tokens, self)
        self.compass.hide()

        #: Where the reference front came from. One line, always present.
        self.front_note = QLabel("")
        self.front_note.setWordWrap(True)
        self.front_note.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.front_note)
        self._recording_known = True

        # Five directions on the panel, the rest one menu away on the same
        # row. Eight buttons in a three-wide grid was three rows of a strip
        # whose height is the scarce direction, and the three that moved -
        # behind, the other diagonal, and the recording's own direction - are
        # pressed rarely enough that a menu costs nothing.
        grid = QGridLayout()
        grid.setSpacing(tokens.metric("KcSpacingSm"))
        self.preset_buttons: dict[str, QPushButton] = {}
        for index, key in enumerate(PRIMARY_PRESET_KEYS):
            preset = PRESETS_BY_KEY[key]
            button = QPushButton(preset_label(preset, short=True))
            button.setToolTip(f"{preset.label} · {preset.description}")
            # The accessible name stays the full one: "45°" is a shorthand
            # for the eye, not for somebody being read the screen.
            button.setAccessibleName(preset.label)
            button.setAccessibleDescription(preset.description)
            button.clicked.connect(
                lambda _checked=False, key=key: self.preset_chosen.emit(key)
            )
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            self.preset_buttons[key] = button
            grid.addWidget(button, index // 3, index % 3)

        self.more_presets_button = QPushButton("Diğer ▾")
        self.more_presets_button.setToolTip("Seyrek kullanılan açılar")
        self.more_presets_button.setAccessibleName("Diğer açılar")
        menu = QMenu(self.more_presets_button)
        self.preset_menu = menu
        self.preset_actions: dict[str, QAction] = {}
        for key in SECONDARY_PRESET_KEYS:
            preset = PRESETS_BY_KEY[key]
            action = menu.addAction(preset.label)
            action.setToolTip(preset.description)
            action.triggered.connect(
                lambda _checked=False, key=key: self.preset_chosen.emit(key)
            )
            self.preset_actions[key] = action
        self.more_presets_button.setMenu(menu)
        self.more_presets_button.setMinimumHeight(
            tokens.metric("KcControlHeightLarge")
        )
        grid.addWidget(
            self.more_presets_button,
            len(PRIMARY_PRESET_KEYS) // 3,
            len(PRIMARY_PRESET_KEYS) % 3,
        )
        column.addLayout(grid)

        column.addWidget(separator())
        column.addWidget(label("ARAÇLAR", role="sectionTitle"))

        # The three that are used constantly. The rest - saving a view,
        # returning to the previous one, redefining the front - are
        # occasional, and occasional things do not need to be on screen.
        tools = QHBoxLayout()
        tools.setSpacing(tokens.metric("KcSpacingSm"))
        self.centre_button = self._tool(
            "centre", "Merkezle", "Kamerayı sporcunun ortasına çevir"
        )
        self.centre_button.clicked.connect(self.centre_requested.emit)
        self.fit_button = self._tool("fit", "Sığdır", "Bedeni kadraja sığdır")
        self.fit_button.clicked.connect(self.fit_requested.emit)
        self.previous_button = self._tool(
            "previous-view", "Önceki", "Son preset öncesindeki bakışa dön"
        )
        self.previous_button.clicked.connect(self.previous_requested.emit)
        for button in (self.centre_button, self.fit_button, self.previous_button):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            tools.addWidget(button)
        column.addLayout(tools)

        column.addWidget(separator())
        self.floor_box = QCheckBox("Zemini göster")
        self.floor_box.setChecked(True)
        self.floor_box.toggled.connect(self.floor_toggled.emit)
        column.addWidget(self.floor_box)
        self.overlay_box = QCheckBox("RGB iskelet kaplaması")
        self.overlay_box.setChecked(True)
        self.overlay_box.toggled.connect(self.overlay_toggled.emit)
        column.addWidget(self.overlay_box)

        # What the floor on screen actually is. FLOOR-04: a grid drawn under
        # the lowest foot is a viewing aid and says so, every time.
        self.floor_note = QLabel("")
        self.floor_note.setWordWrap(True)
        self.floor_note.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.floor_note)

        self.advanced_button = QPushButton("Gelişmiş…")
        self.advanced_button.setToolTip(
            "Bakışı kaydet, kayıtlı bakışa dön, bu bakışı 'ön' yap, "
            "hareketi azalt"
        )
        self.advanced_button.clicked.connect(self.advanced_requested.emit)
        self.advanced_button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        # Left-aligned and only as wide as it needs to be. Stretched across
        # the panel it read as the most important thing here, which it is not.
        advanced_row = QHBoxLayout()
        advanced_row.setContentsMargins(0, 0, 0, 0)
        advanced_row.addWidget(self.advanced_button)
        advanced_row.addStretch(1)
        column.addLayout(advanced_row)
        column.addStretch(1)

        # Kept as widgets so the page's wiring and the advanced window can
        # both reach them; they live in that window rather than here.
        self.save_button = self._tool("save-view", "Bakışı kaydet", "Bu bakışı sakla")
        self.save_button.clicked.connect(self.view_saved.emit)
        self.restore_button = self._tool(
            "bookmark", "Kayıtlı bakış", "Saklanan bakışa dön"
        )
        self.restore_button.clicked.connect(self.view_restored.emit)
        self.front_button = self._tool(
            "compass", "Bunu ön yap", "Şu anki bakışı 'ön' yönü olarak tanımla"
        )
        self.front_button.clicked.connect(self.front_set.emit)
        self.motion_box = QCheckBox("Hareketi azalt")
        self.motion_box.setToolTip(
            "Preset geçişleri yumuşak hareket yerine anında yapılır."
        )
        self.motion_box.toggled.connect(self.reduce_motion_toggled.emit)

    def advanced_widgets(self) -> tuple[QWidget, ...]:
        """The occasional controls, for whoever gives them a window."""
        return (
            self.save_button,
            self.restore_button,
            self.front_button,
            self.motion_box,
        )

    def _tool(self, icon: str, name: str, tip: str) -> QPushButton:
        button = QPushButton(name)
        button.setToolTip(tip)
        button.setAccessibleName(name)
        button.setIcon(
            iconset.icon(icon, self._tokens, size=self._tokens.metric("KcIconSize"))
        )
        return button

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.compass.set_tokens(tokens)

    #: What each floor source is called, in the words the interface uses.
    FLOOR_TEXT = {
        "detected": "Zemin kayıttan ölçüldü.",
        "visual_reference": (
            "Ölçülmüş zemin yok. Izgara, referans karelerdeki en alçak ayak "
            "yüksekliğine çizildi; görsel yardımdır, ölçüm değildir."
        ),
        "none": "Bu sürümde zemin bilgisi yok.",
    }

    def show_front_source(self, source: str, text: str) -> None:
        """Say where "ön" came from, in the words the interface uses.

        R-04 asks for the source to be known, not only correct. Measured from
        the shoulders and assumed from the camera are different claims, and
        the one case where the reader has to act - nothing readable in the
        body - is the one that gets the warning colour.
        """
        self.front_note.setText(text)
        self.front_note.setProperty(
            "kcStatus", "warning" if source == "unknown" else None
        )
        style = self.front_note.style()
        if style is not None:
            style.unpolish(self.front_note)
            style.polish(self.front_note)
        self._apply_recording_known()

    def _apply_recording_known(self) -> None:
        """The recording's own direction only means something when the
        recording's convention is known; otherwise it would be an entry that
        moves the camera somewhere nobody chose."""
        for holder in (self.preset_buttons.get("camera"), self.preset_actions.get("camera")):
            if holder is None:
                continue
            holder.setEnabled(self._recording_known)
            holder.setToolTip(
                "Kaydın kendi kamera yönü"
                if self._recording_known
                else "Bu kaydın koordinat sistemi bilinmiyor; kamera yönü çözülemedi."
            )

    def set_recording_known(self, known: bool) -> None:
        self._recording_known = bool(known)
        self._apply_recording_known()

    def show_floor_source(self, source: str, reason: str = "") -> None:
        text = self.FLOOR_TEXT.get(source, self.FLOOR_TEXT["none"])
        if reason and source != "detected":
            text = f"{text} ({reason})"
        self.floor_note.setText(text)
        self.floor_note.setProperty(
            "kcStatus", "warning" if source == "visual_reference" else None
        )
        style = self.floor_note.style()
        if style is not None:
            style.unpolish(self.floor_note)
            style.polish(self.floor_note)


__all__ = ["CameraPanel", "Compass"]
