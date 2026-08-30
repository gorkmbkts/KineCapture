"""Export screen: build a versioned dataset release without blocking the UI.

The build runs on a worker thread. Progress and cancellation cross the thread
boundary through Qt signals, so the window stays responsive and Cancel takes
effect at the next sample boundary. A cancelled or failed export removes its
staging directory and publishes nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.config import save_user_state
from kinecapture.domain.activity import evaluate_continuous
from kinecapture.core.errors import ExportCancelled, ExportError, KineCaptureError
from kinecapture.core.jsonio import read_json
from kinecapture.export.release import (
    ExportOptions,
    ExportResult,
    ReleaseBuilder,
    list_releases,
    next_release_name,
)
from kinecapture.features.registry import (
    DEFAULT_FEATURE_IDS,
    applicability,
    array_keys_for,
    estimate_bytes_per_frame,
    get_feature,
    match_preset,
    order_features,
)
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
from kinecapture.gui.widgets.feature_picker import (
    FeatureSelectionDialog,
    FeatureSummaryLabel,
)
from kinecapture.visualization.mapping import available_mappings
from kinecapture.visualization.skeleton_spec import SkeletonSpec, try_get_skeleton_spec

_NATIVE = "__native__"


class _ExportWorker(QObject):
    """Runs :class:`ReleaseBuilder` on a worker thread."""

    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(object)

    def __init__(self, builder: ReleaseBuilder, rows) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._builder = builder
        self._rows = rows
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def report(done: int, total: int, message: str) -> bool:
            self.progress.emit(done, total, message)
            return not self._cancelled

        try:
            result = self._builder.build(rows=self._rows, progress=report)
        except ExportCancelled as exc:
            self.failed.emit(exc)
        except KineCaptureError as exc:
            self.failed.emit(exc)
        except Exception as exc:  # a worker crash must reach the GUI as an error
            self.failed.emit(
                ExportError(
                    f"Dışa aktarma beklenmedik şekilde durdu: {exc}",
                    code="export_crashed",
                    remedy="Ayrıntı için log dosyasına bakın.",
                )
            )
        else:
            self.finished.emit(result)


class ExportPage(Page):
    """Release options, progress, and the list of published releases."""

    navigate_requested = Signal(str)

    title = "Export"
    description = (
        "Sürümlenmiş dataset yayını: canonical skeleton, manifest, "
        "spec, label mapping, fingerprint ve doğrulama raporu."
    )
    icon = "export"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ExportWorker] = None
        # Restored from the user's preferences; unknown ids from an older
        # version are dropped by the registry rather than carried forward.
        # With no stored preference the screen opens on the canonical default,
        # which is the release this application produced before features
        # existed - a first run must not quietly change the export contract.
        stored = list(state.config.export_feature_ids or ())
        self._feature_ids: tuple[str, ...] = order_features(
            stored or DEFAULT_FEATURE_IDS
        )

        self._empty = EmptyState(
            "Önce bir proje açın",
            "Dataset sürümleri açık projeye aittir.",
            theme=theme,
            icon="project",
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        body = QHBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.space_md)
        body.addWidget(self._build_options(theme), 2)
        body.addWidget(self._build_releases(theme), 3)
        self.content.addWidget(self._body, 1)

        state.project_changed.connect(lambda _: self._reload())
        state.dataset_changed.connect(self._refresh_preview)
        self._set_empty(True)

    # --------------------------------------------------------------- layout
    def _build_options(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        card = Card("Sürüm seçenekleri", theme=theme, icon="settings")

        self._skeleton_selector = QComboBox()
        self._skeleton_selector.currentIndexChanged.connect(self._skeleton_changed)
        card.add_widget(
            FieldRow(
                "İskelet biçimi",
                self._skeleton_selector,
                theme=theme,
                help_text=(
                    "Varsayılan: yakalamanın kendi (native) eklem sırası. "
                    "Eşleştirme yalnızca tanımlı ve doğrulanmış olduğunda sunulur."
                ),
            )
        )
        self._mapping_note = make_label("", role="muted")
        self._mapping_note.setWordWrap(True)
        card.add_widget(self._mapping_note)

        # --- which dataset(s) this release contains -------------------
        self._movement_mode = QCheckBox("Hareket örnekleri (mevcut biçim)")
        self._movement_mode.setChecked(True)
        self._movement_mode.setToolTip(
            "Etiketli her tekrar ayrı bir örnek. Varsayılan; eski sürümlerle "
            "aynı sözleşme."
        )
        self._movement_mode.toggled.connect(self._refresh_preview)
        card.add_widget(self._movement_mode)

        self._continuous_mode = QCheckBox("Sürekli aktivite (kaydın tamamı)")
        self._continuous_mode.setToolTip(
            "Bir örnek = bir kayıt. Egzersiz dışı zaman, geçişler ve "
            "başlangıç/bitiş anları kare bazında etiketlenir.\n\n"
            "Aktivite etiketleme inceleme ekranından kaldırıldı. Bu seçenek "
            "yalnızca daha önce aktivite etiketi girilmiş kayıtları olan "
            "projelerde açılabilir; mevcut veri silinmez veya dönüştürülmez."
        )
        self._continuous_mode.toggled.connect(self._refresh_preview)
        card.add_widget(self._continuous_mode)

        self._require_coverage = QCheckBox(
            "Sürekli export için tam etiket kapsamı şart"
        )
        self._require_coverage.setToolTip(
            "Açıkken, zaman çizelgesinde etiketlenmemiş kare kalan kayıtlar "
            "sürüme girmez. Kapalıyken girerler ve etiketsiz kareler "
            "activity_label_mask ile işaretlenir."
        )
        self._require_coverage.toggled.connect(self._refresh_preview)
        card.add_widget(self._require_coverage)

        self._continuous_note = make_label("", role="muted")
        self._continuous_note.setWordWrap(True)
        card.add_widget(self._continuous_note)

        self._include_synthetic = QCheckBox("Sentetik kayıtları dahil et")
        self._include_synthetic.setToolTip(
            "Sentetik veriler gerçek ölçüm değildir ve manifestte öyle işaretlenir."
        )
        self._include_synthetic.toggled.connect(self._refresh_preview)
        card.add_widget(self._include_synthetic)

        self._include_unready = QCheckBox("Etiketi eksik hareketleri dahil et")
        self._include_unready.setToolTip(
            "Kapalıyken sürüm, ekranda \u201chazır\u201d görünen hareketlerle "
            "birebir aynıdır."
        )
        self._include_unready.toggled.connect(self._refresh_preview)
        card.add_widget(self._include_unready)

        self._include_excluded = QCheckBox("Dışlanmış hareketleri dahil et")
        self._include_excluded.toggled.connect(self._refresh_preview)
        card.add_widget(self._include_excluded)

        self._store_targets = QCheckBox(
            "Kare başına hata hedefi dizisi yaz (error_multi_hot)"
        )
        self._store_targets.setChecked(True)
        self._store_targets.setToolTip(
            "Zamansal yerelleştirme eğitimi için [T, sınıf] hedef dizisi. "
            "Kapatılırsa yalnız aralık listesi yazılır."
        )
        card.add_widget(self._store_targets)

        self._min_frames = QSpinBox()
        self._min_frames.setRange(2, 500)
        self._min_frames.setValue(4)
        self._min_frames.valueChanged.connect(lambda _: self._refresh_preview())
        card.add_widget(
            FieldRow("En az kare / örnek", self._min_frames, theme=theme)
        )

        self._notes = QPlainTextEdit()
        self._notes.setMaximumHeight(56)
        self._notes.setPlaceholderText("Bu sürümle ilgili not (manifeste yazılır)")
        card.add_widget(FieldRow("Sürüm notu", self._notes, theme=theme))
        layout.addWidget(card)

        features = Card(
            "Veri ve özellik seçimi",
            subtitle=(
                "Canonical iskelet her sürümde yazılır. Seçilenler onun yanına "
                "ayrı dizilerle eklenir."
            ),
            theme=theme,
            icon="dataset",
        )
        self._feature_summary = FeatureSummaryLabel(theme)
        self._feature_summary.edit_requested.connect(self._edit_features)
        features.add_widget(self._feature_summary)
        self._feature_note = make_label("", role="muted")
        self._feature_note.setWordWrap(True)
        features.add_widget(self._feature_note)
        layout.addWidget(features)

        preview_card = Card("Önizleme", theme=theme, icon="eye")
        self._preview_chip = StatusChip("-", theme=theme, icon="info")
        preview_card.add_header_widget(self._preview_chip)
        self._preview = KeyValueList(theme)
        preview_card.add_widget(self._preview)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        preview_card.add_widget(self._progress)
        self._progress_label = make_label("", role="muted")
        self._progress_label.setWordWrap(True)
        preview_card.add_widget(self._progress_label)

        buttons = QHBoxLayout()
        self._build_button = make_button(
            "Sürüm oluştur", variant="primary", icon="export", theme=theme
        )
        self._build_button.clicked.connect(self._start_export)
        buttons.addWidget(self._build_button)
        self._cancel_button = make_button("İptal", variant="danger", theme=theme)
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._cancel_export)
        buttons.addWidget(self._cancel_button)
        buttons.addStretch(1)
        container = QWidget()
        container.setLayout(buttons)
        preview_card.add_widget(container)
        layout.addWidget(preview_card)
        layout.addStretch(1)
        return wrapper

    def _build_releases(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        card = Card(
            "Yayımlanmış sürümler",
            subtitle="Önceki sürümler asla değiştirilmez.",
            theme=theme,
            icon="dataset",
        )
        self._release_table = QTableWidget(0, 5)
        self._release_table.setHorizontalHeaderLabels(
            ["Sürüm", "Tarih", "Örnek", "Doğrulama", "Fingerprint"]
        )
        self._release_table.verticalHeader().setVisible(False)
        self._release_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._release_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._release_table.currentCellChanged.connect(
            lambda *_: self._release_selected()
        )
        header = self._release_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        card.add_widget(self._release_table, 1)

        row = QHBoxLayout()
        open_folder = make_button("Klasörü aç", icon="folder-open", theme=theme)
        open_folder.clicked.connect(self._open_release_folder)
        row.addWidget(open_folder)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        layout.addWidget(card, 2)

        detail = Card("Sürüm ayrıntısı", theme=theme, icon="info")
        self._release_details = KeyValueList(theme)
        detail.add_widget(self._release_details)
        self._release_warnings = QPlainTextEdit()
        self._release_warnings.setReadOnly(True)
        self._release_warnings.setMaximumHeight(120)
        detail.add_widget(self._release_warnings)
        layout.addWidget(detail, 1)
        return wrapper

    # ----------------------------------------------------------------- data
    def _set_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._body.setVisible(not empty)

    def on_activated(self) -> None:
        self._reload()

    def can_leave(self) -> bool:
        if self._thread is not None and self._thread.isRunning():
            self.state.notify(
                "Dışa aktarma sürüyor. Bitmesini bekleyin veya iptal edin.", 6000
            )
            return False
        return True

    def _reload(self) -> None:
        if self.state.workspace is None:
            self._set_empty(True)
            return
        self._set_empty(False)
        self._populate_skeleton_choices()
        self._refresh_feature_summary()
        self._refresh_preview()
        self._refresh_releases()

    def _populate_skeleton_choices(self) -> None:
        """Only offer targets that a defined mapping can actually reach."""
        index = self.state.index
        formats = set()
        if index is not None:
            for row in index.rows:
                if row.take.skeleton_format:
                    formats.add(row.take.skeleton_format)

        self._skeleton_selector.blockSignals(True)
        self._skeleton_selector.clear()
        self._skeleton_selector.addItem(
            "Native (kaydın kendi eklem sırası)", _NATIVE
        )
        for mapping in available_mappings():
            if mapping.source_format not in formats:
                continue
            status = "tam" if mapping.status == "complete" else "kısmi"
            self._skeleton_selector.addItem(
                f"{mapping.target_format}  ({status}: "
                f"{mapping.mapped_count}/{mapping.target_spec.num_joints})",
                mapping.target_format,
            )
        self._skeleton_selector.blockSignals(False)
        self._skeleton_changed()

    def _skeleton_changed(self) -> None:
        target = self._skeleton_selector.currentData()
        if target == _NATIVE or target is None:
            self._mapping_note.setText(
                "Ham eklem sırası korunur. KineSynthV3 uyumu için hedef biçim seçin."
            )
            self._mapping_note.setStyleSheet("")
            self._refresh_preview()
            return
        mapping = next(
            (m for m in available_mappings() if m.target_format == target), None
        )
        if mapping is None:
            self._mapping_note.setText(
                f"'{target}' için tanımlı eklem eşleştirmesi yok: not available yet."
            )
            self._mapping_note.setStyleSheet(f"color: {self.theme.warning};")
        elif mapping.status == "partial":
            self._mapping_note.setText(
                f"KISMİ EŞLEŞTİRME ({mapping.mapping_id} v{mapping.version}): "
                f"{mapping.mapped_count}/{mapping.target_spec.num_joints} eklem "
                f"eşleşiyor. Eşleşmeyenler NaN yazılır ve manifestte listelenir: "
                f"{', '.join(mapping.unmapped_target_joints)}."
            )
            self._mapping_note.setStyleSheet(f"color: {self.theme.warning};")
        else:
            self._mapping_note.setText(
                f"Tam eşleştirme: {mapping.mapping_id} v{mapping.version}."
            )
            self._mapping_note.setStyleSheet(f"color: {self.theme.success};")
        # A mapping can make a native-only feature unavailable, so the summary
        # has to be recomputed here, not only when the dialog closes.
        self._refresh_feature_summary()
        self._refresh_preview()

    def _current_options(self) -> ExportOptions:
        target = self._skeleton_selector.currentData()
        selection = self._effective_feature_ids()
        return ExportOptions(
            include_synthetic=self._include_synthetic.isChecked(),
            include_unready=self._include_unready.isChecked(),
            include_excluded_samples=self._include_excluded.isChecked(),
            min_frames_per_sample=self._min_frames.value(),
            target_skeleton_format=None if target == _NATIVE else target,
            # Confidences are a normal registry feature; this flag stays only so
            # the two cannot disagree about the array.
            store_confidences="joint_confidences" in selection,
            store_error_target_arrays=self._store_targets.isChecked(),
            feature_ids=selection,
            feature_preset=match_preset(selection),
            export_movement_samples=self._movement_mode.isChecked(),
            export_continuous=self._continuous_mode.isChecked(),
            require_full_activity_coverage=self._require_coverage.isChecked(),
            notes=self._notes.toPlainText().strip(),
        )

    # --------------------------------------------------------- feature pick
    def _output_spec(self) -> Optional[SkeletonSpec]:
        """The skeleton a release would actually be written in."""
        target = self._skeleton_selector.currentData()
        if target and target != _NATIVE:
            return try_get_skeleton_spec(target)
        index = self.state.index
        if index is None:
            return None
        for row in index.rows:
            spec = try_get_skeleton_spec(row.take.skeleton_format)
            if spec is not None:
                return spec
        return None

    def _available_sources(self) -> Optional[tuple[str, ...]]:
        """Optional tracker fields present in the takes, if that is knowable.

        Answering it needs the pose streams, which is too expensive for a
        preview, so the dialog is told ``None`` and reports availability from
        the skeleton and mapping alone. What the takes really contain is
        reported per feature in the release itself.
        """
        return None

    def _effective_feature_ids(self) -> tuple[str, ...]:
        return order_features(self._feature_ids)

    def _edit_features(self) -> None:
        dialog = FeatureSelectionDialog(
            self.theme,
            selected=self._feature_ids,
            spec=self._output_spec(),
            mapping_active=self._skeleton_selector.currentData() not in (None, _NATIVE),
            available_sources=self._available_sources(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._feature_ids = dialog.selected_feature_ids()
        self._remember_features()
        self._refresh_feature_summary()
        self._refresh_preview()

    def _remember_features(self) -> None:
        """Persist the selection through the normal user-state path.

        Tests redirect ``USER_STATE_PATH``, so this never touches the real
        user's settings file during a test run.
        """
        self.state.config.export_feature_ids = list(self._feature_ids)
        try:
            save_user_state(self.state.config)
        except KineCaptureError as exc:  # a preference must never block export
            self.state.notify(exc.message, 4000)

    def _refresh_feature_summary(self) -> None:
        selection = self._effective_feature_ids()
        self._feature_summary.set_selection(selection)
        spec = self._output_spec()
        blocked: list[str] = []
        if spec is not None:
            mapping_active = self._skeleton_selector.currentData() not in (
                None,
                _NATIVE,
            )
            for feature_id in selection:
                definition = get_feature(feature_id)
                verdict = applicability(
                    definition, spec, mapping_active=mapping_active
                )
                if not verdict.supported:
                    blocked.append(f"{definition.label}: {verdict.reason}")
        keys = array_keys_for(selection)
        lines = [
            f"Oluşacak dizi anahtarları: {', '.join(keys[:8])}"
            + (f" (+{len(keys) - 8})" if len(keys) > 8 else ""),
        ]
        if blocked:
            lines.append("Seçili ama bu yapılandırmada üretilemeyecek: " + "; ".join(blocked))
        self._feature_note.setText("\n".join(lines))

    def _refresh_continuous_availability(self) -> int:
        """Enable the continuous option only where activity data exists.

        Authoring activity labels was retired from the review screen, so a
        project recorded since then has nothing for this exporter to read and
        the option would silently produce an entirely unlabelled dataset.
        Existing intervals are untouched on disk and remain exportable.
        """
        workspace = self.state.workspace
        index = self.state.index
        if workspace is None or index is None:
            return 0
        with_activity = sum(
            1 for row in index.rows if workspace.load_activity_intervals(row.take)
        )
        available = with_activity > 0
        for widget in (self._continuous_mode, self._require_coverage):
            widget.setEnabled(available)
        if not available and self._continuous_mode.isChecked():
            self._continuous_mode.blockSignals(True)
            self._continuous_mode.setChecked(False)
            self._continuous_mode.blockSignals(False)
        self._continuous_note.setText(
            f"Sürekli aktivite: {with_activity} kayıtta eski aktivite etiketi var."
            if available
            else "Sürekli aktivite export'u kapalı: bu projede aktivite etiketi "
            "olan kayıt yok. Aktivite etiketleme kaldırıldı; mevcut veriler "
            "olduğu gibi korunur."
        )
        return with_activity

    def _refresh_preview(self) -> None:
        workspace = self.state.workspace
        index = self.state.index
        if workspace is None or index is None:
            return
        self._refresh_continuous_availability()
        if not (self._movement_mode.isChecked() or self._continuous_mode.isChecked()):
            self._preview_chip.set_status(
                "Biçim seçilmedi", icon="warning", colour=self.theme.warning
            )
            self._build_button.setEnabled(False)
            return
        builder = ReleaseBuilder(workspace, index, self._current_options())
        rows = builder.select_rows()
        selected = [builder._selected_samples(row) for row in rows]
        samples = sum(len(group) for group in selected)
        intervals = sum(
            len(sample.error_intervals) for group in selected for sample in group
        )
        participants = {row.take.participant_id for row in rows}
        synthetic = sum(1 for row in rows if row.take.is_synthetic)
        rejected = len(index.rows) - len(rows)
        frames = sum(
            max(0, sample.end_frame - sample.start_frame + 1)
            for group in selected
            for sample in group
        )

        continuous_ready = 0
        if self._continuous_mode.isChecked():
            for row in rows:
                readiness, _coverage = evaluate_continuous(
                    workspace.load_activity_intervals(row.take),
                    row.take.metrics.frames_written,
                    known_exercises=workspace.label_schema.exercise_codes(),
                    require_full_coverage=self._require_coverage.isChecked(),
                )
                continuous_ready += int(readiness.is_ready)

        selection = self._effective_feature_ids()
        keys = array_keys_for(selection)
        spec = self._output_spec()
        unsupported = 0
        if spec is not None:
            mapping_active = self._skeleton_selector.currentData() not in (
                None,
                _NATIVE,
            )
            unsupported = sum(
                1
                for feature_id in selection
                if not applicability(
                    get_feature(feature_id), spec, mapping_active=mapping_active
                ).supported
            )
            estimate = estimate_bytes_per_frame(
                selection,
                num_joints=spec.num_joints,
                num_bones=len(spec.edges),
            ) * frames
            size_text = f"~{estimate / (1024 * 1024):.1f} MB (sıkıştırma öncesi)"
        else:
            size_text = "-"

        self._preview.set_items(
            [
                ("Sonraki sürüm", next_release_name(workspace.releases_dir)),
                ("Uygun kayıt", str(len(rows))),
                ("Filtrelenen kayıt", str(max(0, rejected))),
                ("Örnek (hareket)", str(samples) if self._movement_mode.isChecked() else "-"),
                (
                    "Örnek (sürekli)",
                    str(continuous_ready) if self._continuous_mode.isChecked() else "-",
                ),
                ("Hata aralığı", str(intervals)),
                ("Katılımcı", str(len(participants))),
                ("Sentetik kayıt", str(synthetic)),
                ("Seçili özellik", f"{len(selection)} özellik · {len(keys)} dizi"),
                (
                    "Üretilemeyecek özellik",
                    str(unsupported) if unsupported else "yok",
                ),
                ("Tahmini boyut", size_text),
                ("Hedef klasör", str(workspace.releases_dir)),
            ]
        )
        total_examples = (samples if self._movement_mode.isChecked() else 0) + (
            continuous_ready if self._continuous_mode.isChecked() else 0
        )
        if total_examples == 0:
            self._preview_chip.set_status(
                "Örnek yok", icon="warning", colour=self.theme.warning
            )
        elif len(participants) < 2:
            self._preview_chip.set_status(
                "Tek katılımcı", icon="warning", colour=self.theme.warning
            )
        else:
            self._preview_chip.set_status(
                f"{total_examples} örnek", icon="check", colour=self.theme.success
            )
        self._build_button.setEnabled(total_examples > 0 and self._thread is None)

    def _refresh_releases(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        releases = list_releases(workspace.releases_dir)
        self._release_table.setRowCount(len(releases))
        for position, path in enumerate(reversed(releases)):
            manifest_path = path / "manifest.json"
            validation_path = path / "validation_report.json"
            fingerprint_path = path / "dataset_fingerprint.json"
            created, samples, verdict, fingerprint = "-", "-", "-", "-"
            try:
                manifest = read_json(manifest_path)
                created = str(manifest.get("created_at", ""))[:16].replace("T", " ")
                samples = str(manifest.get("counts", {}).get("samples", "-"))
            except KineCaptureError:
                created = "manifest okunamadı"
            try:
                report = read_json(validation_path)
                verdict = "Geçti" if report.get("passed") else "HATA"
            except KineCaptureError:
                verdict = "-"
            try:
                fingerprint = str(read_json(fingerprint_path).get("fingerprint", ""))[:26]
            except KineCaptureError:
                fingerprint = "-"

            for column, text in enumerate(
                [path.name, created, samples, verdict, fingerprint]
            ):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                if column == 3 and verdict == "HATA":
                    item.setForeground(Qt.GlobalColor.red)
                self._release_table.setItem(position, column, item)
        if releases:
            self._release_table.selectRow(0)

    def _release_selected(self) -> None:
        item = self._release_table.currentItem()
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        try:
            manifest = read_json(path / "manifest.json")
            report = read_json(path / "validation_report.json")
            fingerprint = read_json(path / "dataset_fingerprint.json")
            excluded = read_json(path / "excluded.json")
        except KineCaptureError as exc:
            self._release_details.set_items([("Hata", exc.message)])
            return

        counts = manifest.get("counts", {})
        config = manifest.get("export_config", {}).get("options", {})
        self._release_details.set_items(
            [
                ("Sürüm", manifest.get("release_name", path.name)),
                ("Oluşturma", str(manifest.get("created_at", ""))[:19].replace("T", " ")),
                ("Uygulama", manifest.get("app_version", "-")),
                (
                    "İçerik",
                    f"{counts.get('samples', 0)} örnek · "
                    f"{counts.get('participants', 0)} katılımcı · "
                    f"{counts.get('takes', 0)} kayıt",
                ),
                ("Dışlanan", str(excluded.get("count", 0))),
                ("Doğrulama", "Geçti" if report.get("passed") else "HATA"),
                ("Fingerprint", fingerprint.get("fingerprint", "-")),
                (
                    "İskelet hedefi",
                    config.get("target_skeleton_format") or "native",
                ),
                ("Sentetik dahil", str(config.get("include_synthetic", False))),
                ("Normalizasyon", manifest.get("array_contract", {}).get("normalisation", "-")),
            ]
        )
        warnings = list(report.get("warnings") or [])
        errors = list(report.get("errors") or [])
        lines = [f"UYARI: {w}" for w in warnings] + [
            f"HATA: {e}" for e in errors
        ]
        self._release_warnings.setPlainText(
            "\n".join(lines) or "Uyarı veya hata yok."
        )

    # -------------------------------------------------------------- actions
    def _start_export(self) -> None:
        workspace = self.state.workspace
        index = self.state.index
        if workspace is None or index is None or self._thread is not None:
            return

        builder = ReleaseBuilder(workspace, index, self._current_options())
        rows = builder.select_rows()
        if not rows:
            self.state.notify("Dışa aktarılacak kayıt yok.", 5000)
            return

        self._progress.setVisible(True)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._build_button.setEnabled(False)
        self._cancel_button.setEnabled(True)

        self._thread = QThread(self)
        self._worker = _ExportWorker(builder, rows)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)
        self._progress_label.setText(f"{done}/{total}  ·  {message}")

    def _on_finished(self, result: ExportResult) -> None:
        self._teardown_thread()
        self._progress_label.setText(
            f"{result.release_name} oluşturuldu: {result.sample_count} örnek, "
            f"{result.excluded_count} dışlandı."
        )
        verdict = "doğrulama geçti" if result.validation_passed else "DOĞRULAMA HATASI"
        self.state.notify(f"{result.release_name} yayımlandı ({verdict}).", 8000)
        if result.warnings:
            self._release_warnings.setPlainText(
                "\n".join(f"UYARI: {w}" for w in result.warnings)
            )
        self._refresh_releases()

    def _on_failed(self, error: KineCaptureError) -> None:
        self._teardown_thread()
        if isinstance(error, ExportCancelled):
            self._progress_label.setText(
                "İptal edildi. Hazırlanan geçici dosyalar silindi; "
                "hiçbir sürüm yayımlanmadı."
            )
            self.state.notify("Dışa aktarma iptal edildi.", 5000)
        else:
            self._progress_label.setText(error.user_text())
            self.state.report_error(error)

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._progress.setVisible(False)
        self._cancel_button.setEnabled(False)
        self._refresh_preview()

    def _cancel_export(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._progress_label.setText("İptal ediliyor...")

    def _open_release_folder(self) -> None:
        item = self._release_table.currentItem()
        workspace = self.state.workspace
        if workspace is None:
            return
        path = (
            Path(item.data(Qt.ItemDataRole.UserRole))
            if item is not None
            else workspace.releases_dir
        )
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self.state.notify(f"Klasör açılamadı: {exc}", 5000)


__all__ = ["ExportPage"]
