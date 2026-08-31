"""Choosing which anatomical joints an error is about, by clicking a figure.

The coach has just marked *when* an error is visible. This asks *where*, and it
has to be answerable in a couple of seconds between repetitions, so it is a
front-on figure you click rather than a list of twenty-six checkboxes.

Three decisions worth stating:

**The figure is a schematic, not the recording.** It is laid out once, in
anatomical coordinates, and every take of every format uses the same picture.
A layout derived from the take's own joint positions would wobble from take to
take and put the same body part in a different place each time. Which joints
are *offered* still comes from the take's own :class:`SkeletonSpec`, so a
BODY_18 recording simply has no pelvis to click.

**Only canonical roles are targets.** Face landmarks and auxiliary tracker
points stay in the exported arrays - nothing here removes a joint from the
data - but they are not things a coach says an error is "about", and putting
thirty-eight dots on a figure would make the fourteen that matter harder to
hit. The count of non-target joints is stated in words instead of drawn at
positions this module would have to invent.

**Left and right are the athlete's.** A front view mirrors them, and a coach
looking at the screen will otherwise click the wrong knee. The figure is
labelled with the athlete's own sides and the hit targets are placed
accordingly: the athlete's left appears on the viewer's right.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.domain.enums import JointAnnotationStatus
from kinecapture.features.roles import ALL_ROLES, resolve_roles
from kinecapture.gui.theme import Theme
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Turkish names shown to the coach. Sides are the *athlete's*, spelled out on
#: the figure so a front view cannot be misread.
ROLE_LABELS: dict[str, str] = {
    "pelvis": "Pelvis",
    "spine_mid": "Bel omurgası",
    "chest": "Göğüs omurgası",
    "neck": "Boyun",
    "head": "Baş",
    "nose": "Burun",
    "left_clavicle": "Sol köprücük",
    "right_clavicle": "Sağ köprücük",
    "left_shoulder": "Sol omuz",
    "right_shoulder": "Sağ omuz",
    "left_elbow": "Sol dirsek",
    "right_elbow": "Sağ dirsek",
    "left_wrist": "Sol el bileği",
    "right_wrist": "Sağ el bileği",
    "left_hand": "Sol el",
    "right_hand": "Sağ el",
    "left_hip": "Sol kalça",
    "right_hip": "Sağ kalça",
    "left_knee": "Sol diz",
    "right_knee": "Sağ diz",
    "left_ankle": "Sol ayak bileği",
    "right_ankle": "Sağ ayak bileği",
    "left_foot": "Sol ayak",
    "right_foot": "Sağ ayak",
    "left_heel": "Sol topuk",
    "right_heel": "Sağ topuk",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


#: Anatomical layout in a 0..1 box, ``x`` across and ``y`` down. These are the
#: *athlete's* coordinates: ``left_*`` roles have x < 0.5, and the widget
#: mirrors them when drawing so the athlete's left lands on the viewer's right.
_LAYOUT: dict[str, tuple[float, float]] = {
    "head": (0.50, 0.055),
    "nose": (0.50, 0.095),
    "neck": (0.50, 0.150),
    "chest": (0.50, 0.235),
    "spine_mid": (0.50, 0.320),
    "pelvis": (0.50, 0.405),
    "left_clavicle": (0.435, 0.172),
    "right_clavicle": (0.565, 0.172),
    "left_shoulder": (0.355, 0.200),
    "right_shoulder": (0.645, 0.200),
    "left_elbow": (0.295, 0.330),
    "right_elbow": (0.705, 0.330),
    "left_wrist": (0.255, 0.455),
    "right_wrist": (0.745, 0.455),
    "left_hand": (0.240, 0.515),
    "right_hand": (0.760, 0.515),
    "left_hip": (0.420, 0.435),
    "right_hip": (0.580, 0.435),
    "left_knee": (0.400, 0.630),
    "right_knee": (0.600, 0.630),
    "left_ankle": (0.390, 0.825),
    "right_ankle": (0.610, 0.825),
    "left_heel": (0.378, 0.878),
    "right_heel": (0.622, 0.878),
    "left_foot": (0.415, 0.905),
    "right_foot": (0.585, 0.905),
}

#: Drawn between roles when the take's own skeleton connects them. Purely the
#: figure's skeleton lines; selection never depends on it.
_LIMBS: tuple[tuple[str, str], ...] = (
    ("head", "nose"),
    ("nose", "neck"),
    ("neck", "chest"),
    ("chest", "spine_mid"),
    ("spine_mid", "pelvis"),
    ("neck", "left_clavicle"),
    ("neck", "right_clavicle"),
    ("left_clavicle", "left_shoulder"),
    ("right_clavicle", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("right_shoulder", "right_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_elbow", "right_wrist"),
    ("left_wrist", "left_hand"),
    ("right_wrist", "right_hand"),
    ("pelvis", "left_hip"),
    ("pelvis", "right_hip"),
    ("left_hip", "left_knee"),
    ("right_hip", "right_knee"),
    ("left_knee", "left_ankle"),
    ("right_knee", "right_ankle"),
    ("left_ankle", "left_heel"),
    ("left_ankle", "left_foot"),
    ("right_ankle", "right_heel"),
    ("right_ankle", "right_foot"),
)

#: How far from a node's centre a click still counts. Generous on purpose: a
#: coach with a trackpad should not have to hit an 8px dot.
_HIT_RADIUS = 17.0
_NODE_RADIUS = 7.0
_SELECTED_RADIUS = 10.0


class JointRolePicker(QWidget):
    """A clickable front-view figure over one take's available joint roles."""

    selection_changed = Signal()

    def __init__(
        self,
        theme: Theme,
        spec: Optional[SkeletonSpec] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._spec: Optional[SkeletonSpec] = None
        self._available: tuple[str, ...] = ()
        self._resolved: dict[str, Optional[int]] = {}
        self._selected: set[str] = set()
        self._hovered = ""
        self._focus_index = 0
        self._enabled_selection = True

        # A floor, not a target: the figure carries the layout stretch and
        # grows into whatever the dialog has. This only decides what happens
        # in the smallest window the application supports.
        self.setMinimumSize(200, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Etkilenen eklem seçici")
        self.set_spec(spec)

    # ------------------------------------------------------------- content
    def set_spec(self, spec: Optional[SkeletonSpec]) -> None:
        """Offer exactly the roles this take's skeleton actually has."""
        self._spec = spec
        if spec is None:
            self._resolved = {}
            self._available = ()
        else:
            self._resolved = resolve_roles(spec)
            self._available = tuple(
                role
                for role in ALL_ROLES
                if role in _LAYOUT and self._resolved.get(role) is not None
            )
        # A role the new format cannot express is dropped rather than kept as a
        # target nothing could point at.
        self._selected &= set(self._available)
        self._focus_index = 0
        self.update()

    @property
    def spec(self) -> Optional[SkeletonSpec]:
        return self._spec

    @property
    def available_roles(self) -> tuple[str, ...]:
        return self._available

    @property
    def unavailable_roles(self) -> tuple[str, ...]:
        """Canonical roles this format has no joint for."""
        return tuple(role for role in ALL_ROLES if role not in self._available)

    @property
    def non_target_joint_count(self) -> int:
        """Joints in the take that are not selectable targets.

        Still exported, still seen by a model - just not something a coach
        names as the site of an error.
        """
        if self._spec is None:
            return 0
        used = {
            index
            for role, index in self._resolved.items()
            if role in self._available and index is not None
        }
        return max(0, self._spec.num_joints - len(used))

    # ----------------------------------------------------------- selection
    def selected_roles(self) -> tuple[str, ...]:
        return tuple(role for role in ALL_ROLES if role in self._selected)

    def set_selected_roles(self, roles: Iterable[str]) -> None:
        wanted = {str(role) for role in roles}
        self._selected = wanted & set(self._available)
        self.update()

    def clear_selection(self) -> None:
        if not self._selected:
            return
        self._selected.clear()
        self.update()
        self.selection_changed.emit()

    def set_selection_enabled(self, enabled: bool) -> None:
        """Grey the figure out while an explicit "no joint" state is chosen."""
        self._enabled_selection = enabled
        self.update()

    def toggle_role(self, role: str) -> None:
        if role not in self._available or not self._enabled_selection:
            return
        if role in self._selected:
            self._selected.discard(role)
        else:
            self._selected.add(role)
        self.update()
        self.selection_changed.emit()

    # ------------------------------------------------------------ geometry
    def _figure_rect(self) -> QRectF:
        """The largest 3:4 box that fits, centred - so the figure never skews."""
        margin = 12.0
        # A reserved band across the top for the "whose left is whose" labels,
        # which must never be clipped: they are the difference between marking
        # the right knee and the wrong one.
        header = 22.0
        width = max(1.0, self.width() - 2 * margin)
        height = max(1.0, self.height() - 2 * margin - header)
        if width / height > 0.75:
            width = height * 0.75
        else:
            height = width / 0.75
        return QRectF(
            (self.width() - width) / 2.0,
            margin + header,
            width,
            height,
        )

    def _point(self, role: str) -> Optional[QPointF]:
        layout = _LAYOUT.get(role)
        if layout is None:
            return None
        box = self._figure_rect()
        x, y = layout
        # Mirror: the athlete's left is drawn on the viewer's right.
        return QPointF(box.left() + (1.0 - x) * box.width(), box.top() + y * box.height())

    def role_at(self, position: QPointF) -> str:
        """The nearest selectable role within the hit radius, or ``""``."""
        best, best_distance = "", _HIT_RADIUS
        for role in self._available:
            point = self._point(role)
            if point is None:
                continue
            distance = (
                (point.x() - position.x()) ** 2 + (point.y() - position.y()) ** 2
            ) ** 0.5
            if distance <= best_distance:
                best, best_distance = role, distance
        return best

    # -------------------------------------------------------------- events
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        role = self.role_at(QPointF(event.position()))
        if role:
            self._focus_index = max(0, self._available.index(role))
            self.toggle_role(role)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        role = self.role_at(QPointF(event.position()))
        if role != self._hovered:
            self._hovered = role
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if role
                else Qt.CursorShape.ArrowCursor
            )
            self.setToolTip(role_label(role) if role else "")
            self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hovered = ""
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Arrow keys walk the joints; Space/Enter toggles the focused one."""
        if not self._available:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._focus_index = (self._focus_index + 1) % len(self._available)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self._focus_index = (self._focus_index - 1) % len(self._available)
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle_role(self._available[self._focus_index])
        else:
            super().keyPressEvent(event)
            return
        role = self._available[self._focus_index]
        self.setAccessibleDescription(f"Odaktaki eklem: {role_label(role)}")
        event.accept()
        self.update()

    # --------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = self._theme
        painter.fillRect(self.rect(), QColor(theme.bg_sunken))

        if self._spec is None or not self._available:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Bu kayıt için iskelet bilgisi yok",
            )
            painter.end()
            return

        self._paint_side_labels(painter)
        self._paint_limbs(painter)
        self._paint_nodes(painter)
        painter.end()

    def _paint_side_labels(self, painter: QPainter) -> None:
        """Say whose left is whose, at the top of the figure.

        A front view mirrors the athlete, and "left knee" meaning the knee on
        the right of the screen is the single easiest mistake to make here.
        """
        theme = self._theme
        box = self._figure_rect()
        painter.setPen(QColor(theme.text_secondary))
        metrics = QFontMetrics(painter.font())
        # The full widget width, not the figure's: the figure is narrow on a
        # small dialog and the two labels would meet and overprint each other
        # in the middle, which is worse than not saying it at all.
        band = QRectF(
            2.0,
            box.top() - 20.0,
            max(0.0, self.width() - 4.0),
            metrics.height() + 2.0,
        )
        left_text, right_text = "◀ Sporcunun sağı", "Sporcunun solu ▶"
        needed = (
            metrics.horizontalAdvance(left_text)
            + metrics.horizontalAdvance(right_text)
            + 16.0
        )
        if needed > band.width():
            # Not enough room for both; one unambiguous sentence beats two
            # that collide. Shortened by choice rather than by elision, so the
            # meaning survives - "sporcunun solu sağ…" would say nothing.
            for candidate in (
                "Önden görünüş: sporcunun solu sağda",
                "Sporcunun solu sağda",
                "Solu sağda",
            ):
                if metrics.horizontalAdvance(candidate) <= band.width():
                    painter.drawText(
                        band,
                        int(
                            Qt.AlignmentFlag.AlignHCenter
                            | Qt.AlignmentFlag.AlignVCenter
                        ),
                        candidate,
                    )
                    break
            return
        half = band.width() / 2.0
        # Mirrored, like the figure: the athlete's right is on the viewer's left.
        painter.drawText(
            QRectF(band.left(), band.top(), half, band.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            left_text,
        )
        painter.drawText(
            QRectF(band.left() + half, band.top(), half, band.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            right_text,
        )

    def _paint_limbs(self, painter: QPainter) -> None:
        theme = self._theme
        pen = QPen(QColor(theme.border_strong))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        for first, second in _LIMBS:
            if first not in self._available or second not in self._available:
                continue
            start, end = self._point(first), self._point(second)
            if start is not None and end is not None:
                painter.drawLine(start, end)

    def _paint_nodes(self, painter: QPainter) -> None:
        theme = self._theme
        focused = (
            self._available[self._focus_index]
            if self._available and self.hasFocus()
            else ""
        )
        for role in self._available:
            point = self._point(role)
            if point is None:
                continue
            selected = role in self._selected
            radius = _SELECTED_RADIUS if selected else _NODE_RADIUS
            if selected:
                colour = QColor(theme.warning if self._enabled_selection else theme.text_muted)
            else:
                colour = QColor(theme.bg_base)

            pen = QPen(QColor(theme.accent if role == self._hovered else theme.border_strong))
            pen.setWidthF(2.4 if role == self._hovered else 1.4)
            painter.setPen(pen)
            painter.setBrush(colour)
            painter.drawEllipse(point, radius, radius)

            if selected:
                # A tick as well as a fill: colour alone is not a state.
                tick = QPen(QColor(theme.text_on_accent))
                tick.setWidthF(2.0)
                painter.setPen(tick)
                painter.drawLine(
                    QPointF(point.x() - 4.0, point.y()),
                    QPointF(point.x() - 1.0, point.y() + 3.5),
                )
                painter.drawLine(
                    QPointF(point.x() - 1.0, point.y() + 3.5),
                    QPointF(point.x() + 4.5, point.y() - 3.5),
                )

            if role == focused:
                ring = QPen(QColor(theme.accent))
                ring.setWidthF(1.6)
                ring.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(ring)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(point, radius + 4.0, radius + 4.0)


def describe_joint_annotation(interval) -> str:  # type: ignore[no-untyped-def]
    """One short phrase for a status bar or tooltip.

    Deliberately says something in all four states: "no joints" and "not asked
    yet" look identical if you only print the list.
    """
    status = interval.joint_status
    if status is JointAnnotationStatus.SELECTED and interval.affected_roles:
        names = ", ".join(role_label(role) for role in interval.affected_roles)
        return f"eklem: {names}"
    return {
        JointAnnotationStatus.NOT_APPLICABLE: "eklem: belirli eklem yok",
        JointAnnotationStatus.INDETERMINATE: "eklem: belirlenemiyor",
    }.get(status, "eklem: incelenmedi")


__all__ = [
    "ROLE_LABELS",
    "JointRolePicker",
    "describe_joint_annotation",
    "role_label",
]
