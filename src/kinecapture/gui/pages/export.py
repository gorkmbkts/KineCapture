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

from kinecapture.core.errors import ExportCancelled, ExportError, KineCaptureError
from kinecapture.core.jsonio import read_json
from kinecapture.export.release import (
    ExportOptions,
    ExportResult,
    ReleaseBuilder,
    list_releases,
    next_release_name,
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
from kinecapture.visualization.mapping import available_mappings
from kinecapture.visualization.skeleton_spec import REHAB24_6_MOCAP

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

        self._store_confidence = QCheckBox("Eklem güven değerlerini yaz")
        self._store_confidence.setChecked(True)
        card.add_widget(self._store_confidence)

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
        self._refresh_preview()

    def _current_options(self) -> ExportOptions:
        target = self._skeleton_selector.currentData()
        return ExportOptions(
            include_synthetic=self._include_synthetic.isChecked(),
            include_unready=self._include_unready.isChecked(),
            include_excluded_samples=self._include_excluded.isChecked(),
            min_frames_per_sample=self._min_frames.value(),
            target_skeleton_format=None if target == _NATIVE else target,
            store_confidences=self._store_confidence.isChecked(),
            store_error_target_arrays=self._store_targets.isChecked(),
            notes=self._notes.toPlainText().strip(),
        )

    def _refresh_preview(self) -> None:
        workspace = self.state.workspace
        index = self.state.index
        if workspace is None or index is None:
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

        self._preview.set_items(
            [
                ("Sonraki sürüm", next_release_name(workspace.releases_dir)),
                ("Uygun kayıt", str(len(rows))),
                ("Örnek (hareket)", str(samples)),
                ("Hata aralığı", str(intervals)),
                ("Katılımcı", str(len(participants))),
                ("Sentetik kayıt", str(synthetic)),
                ("Hedef klasör", str(workspace.releases_dir)),
            ]
        )
        if samples == 0:
            self._preview_chip.set_status(
                "Örnek yok", icon="warning", colour=self.theme.warning
            )
        elif len(participants) < 2:
            self._preview_chip.set_status(
                "Tek katılımcı", icon="warning", colour=self.theme.warning
            )
        else:
            self._preview_chip.set_status(
                f"{samples} örnek", icon="check", colour=self.theme.success
            )
        self._build_button.setEnabled(samples > 0 and self._thread is None)

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
