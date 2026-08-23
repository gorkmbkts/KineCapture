"""Choosing what goes into a dataset release.

There are three dozen selectable arrays. Squeezing that many checkboxes into
the export card would make the common case - "just give me the canonical
release" - harder rather than easier, so the whole catalogue lives in its own
searchable, scrollable dialog and the card shows a one-line summary.

Every row says the same four things, because a name alone is not enough to
decide with: what the feature is, roughly what shape and unit it produces,
whether it is experimental, and - when it is greyed out - *why* it is not
available for this export. A checkbox the user cannot tick and cannot explain
is worse than an absent one.

Presets only tick boxes. What actually reaches :class:`ExportOptions` is always
the resolved list of feature ids, so a preset that is later redefined cannot
silently change what an old configuration meant.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.features.base import (
    EXPERIMENTAL_GROUP_LABEL,
    FeatureCategory,
    FeatureDefinition,
)
from kinecapture.features.registry import (
    FEATURES,
    PRESETS,
    applicability,
    array_keys_for,
    get_preset,
    match_preset,
    order_features,
)
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import make_button, make_label
from kinecapture.visualization.skeleton_spec import SkeletonSpec

_FEATURE_ROLE = Qt.ItemDataRole.UserRole + 1


def _group_order() -> list[str]:
    """Category labels in registry order, with experimental last."""
    return [category.label for category in FeatureCategory] + [
        EXPERIMENTAL_GROUP_LABEL
    ]


def summarise(definition: FeatureDefinition) -> str:
    """``[T, J, 3] float32 · length_unit`` - the shape/unit at a glance."""
    first = definition.arrays[0]
    unit = first.unit if first.unit not in ("-", "") else ""
    parts = [first.shape, first.dtype]
    if unit:
        parts.append(unit)
    return "  ·  ".join(parts)


class FeatureSelectionDialog(QDialog):
    """The full catalogue, grouped, searchable and explained."""

    def __init__(
        self,
        theme: Theme,
        *,
        selected: Iterable[str],
        spec: Optional[SkeletonSpec],
        mapping_active: bool,
        available_sources: Optional[tuple[str, ...]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Veri ve özellik seçimi")
        self.setMinimumSize(720, 520)
        self._theme = theme
        self._spec = spec
        self._mapping_active = mapping_active
        self._available_sources = available_sources

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )
        layout.setSpacing(theme.space_sm)

        intro = make_label(
            "Canonical iskelet verisi her sürümde bulunur. Aşağıdakiler onun "
            "yanına, ayrı ve açık isimli diziler olarak yazılır.",
            role="muted",
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        preset_row = QHBoxLayout()
        preset_row.addWidget(make_label("Preset:", role="caption"))
        for preset in PRESETS:
            button = make_button(preset.label, theme=theme)
            button.setToolTip(preset.description)
            button.clicked.connect(
                lambda _checked=False, pid=preset.preset_id: self._apply_preset(pid)
            )
            preset_row.addWidget(button)
        preset_row.addStretch(1)
        container = QWidget()
        container.setLayout(preset_row)
        layout.addWidget(container)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Özellik ara (ad, açıklama veya dizi adı)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Özellik", "Dizi / birim", "Durum"])
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemChanged.connect(self._item_changed)
        layout.addWidget(self._tree, 1)

        self._summary = make_label("", role="muted")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._populate(set(order_features(selected)))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Uygula")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ----------------------------------------------------------- population
    def _populate(self, selected: set[str]) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for label in _group_order():
            parent = QTreeWidgetItem(self._tree, [label, "", ""])
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            parent.setFirstColumnSpanned(False)
            parent.setExpanded(True)
            groups[label] = parent

        for definition in FEATURES:
            parent = groups[definition.group_label]
            item = QTreeWidgetItem(parent)
            item.setText(0, definition.label)
            item.setText(1, summarise(definition))
            item.setData(0, _FEATURE_ROLE, definition.feature_id)
            item.setToolTip(0, definition.description)
            item.setToolTip(1, "\n".join(key for key in definition.array_keys))

            status, enabled = self._status_for(definition)
            item.setText(2, status)
            if definition.locked:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setCheckState(0, Qt.CheckState.Checked)
            elif not enabled:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setForeground(0, self.palette().brush(self.foregroundRole()))
            else:
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    0,
                    Qt.CheckState.Checked
                    if definition.feature_id in selected
                    else Qt.CheckState.Unchecked,
                )

        for label, parent in groups.items():
            parent.setHidden(parent.childCount() == 0)
        self._tree.resizeColumnToContents(0)
        self._tree.blockSignals(False)
        self._update_summary()

    def _status_for(self, definition: FeatureDefinition) -> tuple[str, bool]:
        """The rightmost column: why a row is offered, or why it is not."""
        pieces: list[str] = []
        if definition.experimental:
            pieces.append("DENEYSEL")
        if definition.locked:
            pieces.append("zorunlu")
        if self._spec is None:
            return ("  ·  ".join(pieces) or "-", True)
        verdict = applicability(
            definition,
            self._spec,
            mapping_active=self._mapping_active,
            available_sources=self._available_sources,
        )
        if not verdict.supported:
            return (f"Kullanılamıyor: {verdict.reason}", False)
        pieces.append(definition.mapping_support.label)
        return ("  ·  ".join(pieces), True)

    # -------------------------------------------------------------- actions
    def _apply_preset(self, preset_id: str) -> None:
        preset = get_preset(preset_id)
        self._populate(set(order_features(preset.feature_ids)))

    def _item_changed(self, *_args: object) -> None:
        self._update_summary()

    def _filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for group_index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(group_index)
            visible_children = 0
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                feature_id = str(child.data(0, _FEATURE_ROLE) or "")
                haystack = " ".join(
                    [
                        child.text(0),
                        feature_id,
                        child.toolTip(0),
                        child.toolTip(1),
                    ]
                ).casefold()
                match = not needle or needle in haystack
                child.setHidden(not match)
                visible_children += int(match)
            group.setHidden(visible_children == 0)

    # -------------------------------------------------------------- results
    def selected_feature_ids(self) -> tuple[str, ...]:
        chosen: list[str] = []
        for group_index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(group_index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                if child.checkState(0) == Qt.CheckState.Checked:
                    chosen.append(str(child.data(0, _FEATURE_ROLE)))
        return order_features(chosen)

    def _update_summary(self) -> None:
        selection = self.selected_feature_ids()
        keys = array_keys_for(selection)
        preset = match_preset(selection)
        preset_text = (
            f"Preset: {get_preset(preset).label}" if preset else "Preset: özel seçim"
        )
        self._summary.setText(
            f"{len(selection)} özellik  ·  {len(keys)} dizi  ·  {preset_text}"
        )

    def matched_preset(self) -> Optional[str]:
        return match_preset(self.selected_feature_ids())


class FeatureSummaryLabel(QWidget):
    """The one-line stand-in the export card shows for the whole catalogue."""

    edit_requested = Signal()

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_sm)
        self._label = make_label("-", role="muted")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, 1)
        button = make_button("Özellikleri seç...", theme=theme, icon="settings")
        button.clicked.connect(self.edit_requested.emit)
        layout.addWidget(button)

    def set_selection(self, feature_ids: Iterable[str]) -> None:
        selection = order_features(feature_ids)
        keys = array_keys_for(selection)
        preset = match_preset(selection)
        name = get_preset(preset).label if preset else "özel seçim"
        self._label.setText(
            f"{len(selection)} özellik · {len(keys)} dizi · {name}"
        )


__all__ = ["FeatureSelectionDialog", "FeatureSummaryLabel", "summarise"]
