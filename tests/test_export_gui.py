"""The export screen's feature selection, driven the way a user drives it.

A checkbox that looks tickable but produces nothing, or a preset that says one
thing and exports another, would be worse than no dialog at all. These tests
click through the real widgets - offscreen, but really constructed and really
painted - and check that what the screen promises is what reaches
:class:`ExportOptions`.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from kinecapture.core.config import AppConfig
from kinecapture.features.registry import (
    array_keys_for,
    get_feature,
    get_preset,
    order_features,
)
from kinecapture.gui.pages.export import ExportPage
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import get_theme
from kinecapture.gui.widgets import feature_picker as picker
from kinecapture.visualization.skeleton_spec import (
    MOCK_SKELETON,
    REHAB24_6_MOCAP,
    ZED_BODY_18,
)
from tests.test_export import _record_and_label


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=["dark", "light"])
def theme(request, qt_app):
    return get_theme(request.param)


def _rows(dialog) -> dict[str, tuple[bool, str, Qt.CheckState]]:
    """Every feature row: ``id -> (enabled, status text, check state)``."""
    result: dict[str, tuple[bool, str, Qt.CheckState]] = {}
    for group_index in range(dialog._tree.topLevelItemCount()):
        group = dialog._tree.topLevelItem(group_index)
        for child_index in range(group.childCount()):
            child = group.child(child_index)
            feature_id = str(child.data(0, picker._FEATURE_ROLE))
            result[feature_id] = (
                bool(child.flags() & Qt.ItemFlag.ItemIsEnabled),
                child.text(2),
                child.checkState(0),
            )
    return result


def _visible_ids(dialog) -> set[str]:
    visible: set[str] = set()
    for group_index in range(dialog._tree.topLevelItemCount()):
        group = dialog._tree.topLevelItem(group_index)
        for child_index in range(group.childCount()):
            child = group.child(child_index)
            if not child.isHidden():
                visible.add(str(child.data(0, picker._FEATURE_ROLE)))
    return visible


def _tick(dialog, feature_id: str) -> None:
    for group_index in range(dialog._tree.topLevelItemCount()):
        group = dialog._tree.topLevelItem(group_index)
        for child_index in range(group.childCount()):
            child = group.child(child_index)
            if str(child.data(0, picker._FEATURE_ROLE)) == feature_id:
                child.setCheckState(0, Qt.CheckState.Checked)
                return
    raise AssertionError(f"no row for {feature_id}")


# ------------------------------------------------------------- the dialog


def test_dialog_lists_every_feature_exactly_once(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    rows = _rows(dialog)
    from kinecapture.features.registry import FEATURES

    assert set(rows) == {definition.feature_id for definition in FEATURES}


def test_canonical_row_is_checked_and_cannot_be_unticked(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    enabled, status, state = _rows(dialog)["canonical_pose"]
    assert state == Qt.CheckState.Checked
    assert not (enabled and "zorunlu" not in status)
    assert "zorunlu" in status
    assert dialog.selected_feature_ids() == ("canonical_pose",)


def test_every_preset_button_produces_that_preset(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    for preset_id in ("minimal", "kinesynth_compat", "kinematics_research",
                      "classical_ml", "research_all"):
        dialog._apply_preset(preset_id)
        assert dialog.matched_preset() == preset_id
        assert set(dialog.selected_feature_ids()) == set(
            order_features(get_preset(preset_id).feature_ids)
        )


def test_ticking_a_dependent_feature_pulls_in_what_it_needs(theme) -> None:
    """The summary vector needs angles; the user should not have to know that."""
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    _tick(dialog, "summary_vector")
    selection = dialog.selected_feature_ids()
    assert "summary_vector" in selection
    assert "joint_angles" in selection
    assert "body_aligned_positions" in selection


def test_a_feature_the_skeleton_cannot_support_is_disabled_with_a_reason(
    theme,
) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=ZED_BODY_18, mapping_active=False
    )
    rows = _rows(dialog)
    enabled, status, _state = rows["body_scale"]
    assert not enabled
    assert "Kullanılamıyor" in status and "pelvis" in status
    # A feature that does work is still offered.
    assert rows["joint_angles"][0]


def test_a_native_only_feature_is_disabled_when_a_mapping_is_active(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme,
        selected=("tracker_joint_orientations",),
        spec=REHAB24_6_MOCAP,
        mapping_active=True,
    )
    rows = _rows(dialog)
    for feature_id in (
        "tracker_joint_orientations",
        "tracker_local_joint_positions",
        "quaternion_angular_speed",
    ):
        enabled, status, state = rows[feature_id]
        assert not enabled, feature_id
        assert "eşleştirme" in status.lower()
        assert state == Qt.CheckState.Unchecked
    # An index-remappable field survives the mapping and stays offered.
    assert rows["tracker_joint_positions_2d"][0]


def test_experimental_features_are_grouped_and_marked(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    groups = {
        dialog._tree.topLevelItem(index).text(0): dialog._tree.topLevelItem(index)
        for index in range(dialog._tree.topLevelItemCount())
    }
    experimental = groups[picker.EXPERIMENTAL_GROUP_LABEL]
    ids = {
        str(experimental.child(index).data(0, picker._FEATURE_ROLE))
        for index in range(experimental.childCount())
    }
    assert ids == {"joint_jerk", "quaternion_angular_speed"}
    assert "DENEYSEL" in _rows(dialog)["joint_jerk"][1]
    # And none of them is in the "all supported research features" preset.
    assert not ids & set(get_preset("research_all").feature_ids)


def test_search_filters_by_name_description_and_array_key(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    dialog._filter("quaternion")
    assert "tracker_joint_orientations" in _visible_ids(dialog)
    assert "segment_ratios" not in _visible_ids(dialog)

    dialog._filter("bone_lengths")  # an array key, not a label
    assert "bone_geometry" in _visible_ids(dialog)

    dialog._filter("")
    assert len(_visible_ids(dialog)) > 20


def test_dialog_summary_counts_features_and_arrays(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    dialog._apply_preset("classical_ml")
    selection = dialog.selected_feature_ids()
    text = dialog._summary.text()
    assert f"{len(selection)} özellik" in text
    assert f"{len(array_keys_for(selection))} dizi" in text
    assert get_preset("classical_ml").label in text


def test_every_row_states_a_shape_and_a_unit(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    for group_index in range(dialog._tree.topLevelItemCount()):
        group = dialog._tree.topLevelItem(group_index)
        for child_index in range(group.childCount()):
            child = group.child(child_index)
            assert child.text(1).startswith("[")
            assert child.toolTip(0)


def test_dialog_paints_in_both_themes(theme) -> None:
    dialog = picker.FeatureSelectionDialog(
        theme, selected=(), spec=MOCK_SKELETON, mapping_active=False
    )
    dialog.resize(760, 540)
    assert not dialog.grab().isNull()
    dialog._apply_preset("research_all")
    assert not dialog.grab().isNull()


# ---------------------------------------------------------- the page


@pytest.fixture
def export_page(qt_app, workspace, session, dataset_root, isolated_user_state):
    from tests.conftest import authenticate_state

    _record_and_label(workspace, session, frames=30)
    config = AppConfig(dataset_root=dataset_root, backend="mock")
    state = AppState(config)
    authenticate_state(state, workspace)
    page = ExportPage(state)
    page.on_activated()
    return page


def test_page_starts_with_the_canonical_selection(export_page) -> None:
    options = export_page._current_options()
    assert options.resolved_feature_ids() == ("canonical_pose", "joint_confidences")
    assert options.store_confidences


def test_page_preview_reports_the_feature_selection(export_page) -> None:
    export_page._feature_ids = order_features(["joint_angles", "joint_velocity"])
    export_page._refresh_feature_summary()
    export_page._refresh_preview()

    joined = " ".join(
        f"{key.text()}={value.text()}" for key, value in export_page._preview._rows
    )
    assert "Seçili özellik" in joined
    assert "Tahmini boyut" in joined
    assert "MB" in joined
    assert "Filtrelenen kayıt" in joined


def test_page_selection_reaches_export_options(export_page) -> None:
    export_page._feature_ids = order_features(
        ["joint_angles", "summary_vector", "bone_geometry"]
    )
    options = export_page._current_options()
    resolved = options.resolved_feature_ids()
    assert "summary_vector" in resolved
    assert "bone_geometry" in resolved
    assert options.feature_preset is None or isinstance(options.feature_preset, str)


def test_page_records_a_preset_by_name_when_the_selection_matches(
    export_page,
) -> None:
    preset = get_preset("kinematics_research")
    export_page._feature_ids = order_features(preset.feature_ids)
    assert export_page._current_options().feature_preset == "kinematics_research"


def test_deselecting_confidences_flows_into_the_legacy_flag(export_page) -> None:
    export_page._feature_ids = order_features(["joint_angles"])
    assert not export_page._current_options().store_confidences
    export_page._feature_ids = order_features(["joint_confidences"])
    assert export_page._current_options().store_confidences


def test_page_persists_the_selection_to_user_state(
    export_page, isolated_user_state
) -> None:
    export_page._feature_ids = order_features(["joint_angles", "joint_velocity"])
    export_page._remember_features()
    assert isolated_user_state.is_file()
    text = isolated_user_state.read_text(encoding="utf-8")
    assert "joint_angles" in text
    assert "export_feature_ids" in text


def test_page_warns_about_a_selected_feature_it_cannot_produce(export_page) -> None:
    export_page._feature_ids = order_features(["tracker_joint_orientations"])
    # Ask for a mapped export, which makes that feature meaningless.
    for index in range(export_page._skeleton_selector.count()):
        if export_page._skeleton_selector.itemData(index) == "rehab24_6_mocap":
            export_page._skeleton_selector.setCurrentIndex(index)
            break
    export_page._refresh_feature_summary()
    note = export_page._feature_note.text()
    if export_page._skeleton_selector.currentData() == "rehab24_6_mocap":
        assert "üretilemeyecek" in note
    else:  # no mapping offered for this project's skeleton
        assert "Oluşacak dizi anahtarları" in note


def test_page_paints_with_a_rich_selection(export_page) -> None:
    export_page._feature_ids = order_features(
        [definition.feature_id for definition in __import__(
            "kinecapture.features.registry", fromlist=["FEATURES"]
        ).FEATURES]
    )
    export_page._refresh_feature_summary()
    export_page._refresh_preview()
    export_page.resize(1366, 768)
    assert not export_page.grab().isNull()


def test_summary_label_names_the_preset(qt_app) -> None:
    label = picker.FeatureSummaryLabel(get_theme("dark"))
    label.set_selection(get_preset("classical_ml").feature_ids)
    assert get_preset("classical_ml").label in label._label.text()
    label.set_selection(["joint_angles"])
    assert "özel seçim" in label._label.text()


def test_feature_row_summary_shows_shape_dtype_and_unit() -> None:
    text = picker.summarise(get_feature("joint_velocity"))
    assert "[T, J, 3]" in text
    assert "float32" in text
    assert "length_unit/second" in text
