"""Settings and diagnostics.

Preferences and capture provenance are edited in separate cards because they
behave differently: a preference takes effect immediately and applies to the
application, while a capture setting is copied into each take at record time
and therefore only affects *future* recordings. Saying so on screen prevents
the reasonable but wrong assumption that changing the resolution here rewrites
what a past take says about itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from kinecapture.core.config import USER_STATE_PATH
from kinecapture.core.diagnostics import collect_diagnostics
from kinecapture.core.errors import KineCaptureError
from kinecapture.core.logging import log_file_path
from kinecapture.domain.enums import BackendKind, HealthLevel
from kinecapture.gui.pages.base import Page, scrollable
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme, available_themes
from kinecapture.gui.widgets.common import (
    Card,
    FieldRow,
    KeyValueList,
    StatusChip,
    make_button,
    make_label,
)

_RESOLUTIONS = ("HD720", "HD1080", "HD1200", "HD2K", "SVGA", "VGA", "AUTO")
_DEPTH_MODES = (
    "NEURAL_LIGHT",
    "NEURAL",
    "NEURAL_PLUS",
    "ULTRA",
    "QUALITY",
    "PERFORMANCE",
)
_BODY_FORMATS = ("BODY_18", "BODY_34", "BODY_38")
_BODY_MODELS = ("HUMAN_BODY_FAST", "HUMAN_BODY_MEDIUM", "HUMAN_BODY_ACCURATE")


class SettingsPage(Page):
    """Preferences, capture defaults, label schema editing and diagnostics."""

    title = "Ayarlar ve Tanılama"
    description = "Uygulama tercihleri, yakalama profili ve ortam kontrolü."
    icon = "settings"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme

        save_button = make_button(
            "Ayarları kaydet", variant="primary", icon="check", theme=theme
        )
        save_button.clicked.connect(self._save)
        self.header.add_action(save_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scrollable(self._build_left(theme)))
        splitter.addWidget(scrollable(self._build_right(theme)))
        splitter.setSizes([620, 620])
        self.content.addWidget(splitter, 1)

        self._load()

    # --------------------------------------------------------------- layout
    def _build_left(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        prefs = Card(
            "Uygulama tercihleri",
            subtitle="Hemen etkili olur; kayıtlı verileri etkilemez.",
            theme=theme,
            icon="settings",
        )
        self._theme_selector = QComboBox()
        for name in available_themes():
            self._theme_selector.addItem("Koyu" if name == "dark" else "Açık", name)
        self._theme_selector.currentIndexChanged.connect(self._theme_selected)
        prefs.add_widget(FieldRow("Tema", self._theme_selector, theme=theme))

        self._backend_selector = QComboBox()
        for kind in BackendKind:
            label = "Sentetik (donanımsız)" if kind is BackendKind.MOCK else "ZED 2i"
            self._backend_selector.addItem(label, kind.value)
        prefs.add_widget(FieldRow("Varsayılan backend", self._backend_selector, theme=theme))

        self._preview_fps = QDoubleSpinBox()
        self._preview_fps.setRange(1.0, 120.0)
        self._preview_fps.setSuffix(" FPS")
        prefs.add_widget(
            FieldRow(
                "Önizleme sınırı",
                self._preview_fps,
                theme=theme,
                help_text=(
                    "Yalnızca ekran tazeleme hızını sınırlar. Kayıt kameranın "
                    "kendi hızında sürer."
                ),
            )
        )

        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        prefs.add_widget(FieldRow("Log seviyesi", self._log_level, theme=theme))

        self._autosave = QCheckBox("Etiketleri otomatik kaydet")
        prefs.add_widget(self._autosave)
        self._autosave_delay = QSpinBox()
        self._autosave_delay.setRange(0, 10000)
        self._autosave_delay.setSuffix(" ms")
        prefs.add_widget(
            FieldRow("Otomatik kayıt gecikmesi", self._autosave_delay, theme=theme)
        )

        root_row = QHBoxLayout()
        self._dataset_root = QLineEdit()
        root_row.addWidget(self._dataset_root, 1)
        browse = make_button("Seç", icon="folder-open", theme=theme)
        browse.clicked.connect(self._browse_root)
        root_row.addWidget(browse)
        root_container = QWidget()
        root_container.setLayout(root_row)
        prefs.add_widget(FieldRow("Dataset kök klasörü", root_container, theme=theme))
        layout.addWidget(prefs)

        capture = Card(
            "Yakalama profili",
            subtitle=(
                "Bu değerler her yeni kaydın içine provenance olarak yazılır. "
                "Değiştirmek geçmiş kayıtları DEĞİŞTİRMEZ."
            ),
            theme=theme,
            icon="camera",
        )
        self._resolution = QComboBox()
        self._resolution.addItems(_RESOLUTIONS)
        capture.add_widget(FieldRow("Çözünürlük", self._resolution, theme=theme))

        self._fps = QSpinBox()
        self._fps.setRange(1, 120)
        capture.add_widget(FieldRow("Hedef FPS", self._fps, theme=theme))

        self._depth_enabled = QCheckBox("Derinlik etkin")
        capture.add_widget(self._depth_enabled)
        self._depth_mode = QComboBox()
        self._depth_mode.addItems(_DEPTH_MODES)
        capture.add_widget(FieldRow("Derinlik modu", self._depth_mode, theme=theme))

        self._body_tracking = QCheckBox("Vücut takibi etkin")
        capture.add_widget(self._body_tracking)
        self._body_format = QComboBox()
        self._body_format.addItems(_BODY_FORMATS)
        capture.add_widget(
            FieldRow(
                "Body formatı",
                self._body_format,
                theme=theme,
                help_text="Eklem sırası yerel ZED SDK'dan okunur ve kayda yazılır.",
            )
        )
        self._body_model = QComboBox()
        self._body_model.addItems(_BODY_MODELS)
        capture.add_widget(FieldRow("Takip modeli", self._body_model, theme=theme))
        self._body_fitting = QCheckBox("Body fitting")
        capture.add_widget(self._body_fitting)

        self._detection_confidence = QSpinBox()
        self._detection_confidence.setRange(0, 100)
        capture.add_widget(
            FieldRow("Algılama güven eşiği", self._detection_confidence, theme=theme)
        )

        # The old "store depth frames" checkbox was removed: it wrote a value
        # nothing ever read, and its tooltip claimed the SVO2 could regenerate
        # depth. Measured on this machine, it cannot - replaying a fresh SVO2
        # returns a different depth map from the one the camera produced. So
        # the archive is mandatory and the only remaining choice is how it is
        # encoded.
        self._archive_note = make_label(
            "Ham RGB-D arşivi ZORUNLUDUR ve kapatılamaz. SVO2 stereo "
            "görüntüleri saklar; derinlik yeniden oynatmada YENİDEN HESAPLANIR "
            "ve ölçülen derinlikle aynı değildir, bu yüzden ölçülen derinlik "
            "ayrıca arşivlenir.",
            role="muted",
        )
        self._archive_note.setWordWrap(True)
        capture.add_widget(self._archive_note)

        self._depth_archive = QComboBox()
        self._depth_archive.addItem(
            "Kayıpsız float32  (~3.5 GB/dk, ölçülen)", "float32_lossless"
        )
        self._depth_archive.addItem(
            "Nicemlenmiş uint16, 0.25 mm  (~1.6 GB/dk, KAYIPLI)",
            "uint16_quantised",
        )
        self._depth_archive.setToolTip(
            "Nicemlenmiş profil ölçülen 0.13 mm hata ve 16.4 m menzil sınırı "
            "getirir; sürüm dosyasında kayıplı olarak işaretlenir."
        )
        capture.add_widget(
            FieldRow("Derinlik arşivi", self._depth_archive, theme=theme)
        )

        self._native_compression = QComboBox()
        for value, label in (
            ("H264", "H264  (kayıplı, ~96 MB/dk - ölçüldü)"),
            ("H264_LOSSLESS", "H264 kayıpsız  (~1.1 GB/dk - ölçüldü)"),
            ("LOSSLESS", "Kayıpsız  (~3.0 GB/dk - ölçüldü)"),
        ):
            self._native_compression.addItem(label, value)
        self._native_compression.setToolTip(
            "SVO2 sıkıştırması. Varsayılan H264 KAYIPLIDIR; sürüm dosyasında "
            "böyle yazılır."
        )
        capture.add_widget(
            FieldRow("SVO2 sıkıştırması", self._native_compression, theme=theme)
        )

        self._min_free_minutes = QSpinBox()
        self._min_free_minutes.setRange(0, 240)
        self._min_free_minutes.setSuffix(" dk")
        self._min_free_minutes.setToolTip(
            "Diskte bu kadar kayıt için yer yoksa kayıt başlamaz. Çözünürlük "
            "veya FPS sessizce düşürülmez."
        )
        capture.add_widget(
            FieldRow(
                "En az boş disk", self._min_free_minutes, theme=theme,
                help_text="0 = kontrol kapalı (önerilmez).",
            )
        )

        self._native_recording = QCheckBox(
            "Native SVO2 kaydı yaz (ham stereo görüntü)"
        )
        self._native_recording.setToolTip(
            "Gerçek kamerada zorunludur: kapatılırsa kayıt başlamaz."
        )
        capture.add_widget(self._native_recording)

        self._proxy_width = QSpinBox()
        self._proxy_width.setRange(160, 1920)
        self._proxy_width.setSuffix(" px")
        capture.add_widget(
            FieldRow(
                "Proxy video genişliği",
                self._proxy_width,
                theme=theme,
                help_text="İnceleme için kullanılan küçültülmüş kopyanın genişliği.",
            )
        )
        layout.addWidget(capture)

        mock = Card(
            "Sentetik backend",
            subtitle="Donanımsız geliştirme ve otomatik test içindir.",
            theme=theme,
            icon="flask",
        )
        size_row = QHBoxLayout()
        self._mock_width = QSpinBox()
        self._mock_width.setRange(64, 3840)
        size_row.addWidget(FieldRow("Genişlik", self._mock_width, theme=theme))
        self._mock_height = QSpinBox()
        self._mock_height.setRange(64, 2160)
        size_row.addWidget(FieldRow("Yükseklik", self._mock_height, theme=theme))
        self._mock_fps = QDoubleSpinBox()
        self._mock_fps.setRange(1.0, 120.0)
        size_row.addWidget(FieldRow("FPS", self._mock_fps, theme=theme))
        size_container = QWidget()
        size_container.setLayout(size_row)
        mock.add_widget(size_container)

        seed_row = QHBoxLayout()
        self._mock_seed = QSpinBox()
        self._mock_seed.setRange(0, 999999)
        seed_row.addWidget(
            FieldRow(
                "Seed",
                self._mock_seed,
                theme=theme,
                help_text="Aynı seed aynı kareleri üretir.",
            )
        )
        self._mock_bodies = QSpinBox()
        self._mock_bodies.setRange(1, 6)
        seed_row.addWidget(FieldRow("Gövde sayısı", self._mock_bodies, theme=theme))
        seed_container = QWidget()
        seed_container.setLayout(seed_row)
        mock.add_widget(seed_container)

        self._mock_depth = QCheckBox("Sentetik derinlik üret")
        mock.add_widget(self._mock_depth)

        scenario_row = QHBoxLayout()
        self._mock_tracking_loss = QSpinBox()
        self._mock_tracking_loss.setRange(0, 10000)
        self._mock_tracking_loss.setSpecialValueText("kapalı")
        scenario_row.addWidget(
            FieldRow(
                "Takip kaybı periyodu",
                self._mock_tracking_loss,
                theme=theme,
                help_text="Kare cinsinden. Kalite panelini denemek için.",
            )
        )
        self._mock_low_confidence = QSpinBox()
        self._mock_low_confidence.setRange(0, 10000)
        self._mock_low_confidence.setSpecialValueText("kapalı")
        scenario_row.addWidget(
            FieldRow("Düşük güven periyodu", self._mock_low_confidence, theme=theme)
        )
        scenario_container = QWidget()
        scenario_container.setLayout(scenario_row)
        mock.add_widget(scenario_container)
        layout.addWidget(mock)
        layout.addStretch(1)
        return wrapper

    def _build_right(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        diagnostics = Card(
            "Ortam tanılaması",
            subtitle="Rapor kişisel veri içermez; destek için kopyalanabilir.",
            theme=theme,
            icon="shield",
        )
        self._health_chip = StatusChip("Çalıştırılmadı", theme=theme, icon="info")
        diagnostics.add_header_widget(self._health_chip)
        self._report_view = QPlainTextEdit()
        self._report_view.setReadOnly(True)
        self._report_view.setMinimumHeight(300)
        diagnostics.add_widget(self._report_view, 1)

        row = QHBoxLayout()
        run = make_button("Tanıyı çalıştır", variant="primary", icon="refresh", theme=theme)
        run.clicked.connect(self._run_diagnostics)
        row.addWidget(run)
        copy = make_button("Kopyala", icon="list", theme=theme)
        copy.clicked.connect(self._copy_report)
        row.addWidget(copy)
        row.addStretch(1)
        row_container = QWidget()
        row_container.setLayout(row)
        diagnostics.add_widget(row_container)
        layout.addWidget(diagnostics, 1)

        schema_card = Card(
            "Etiket şeması",
            subtitle=(
                "Hata ontolojisi burada tanımlanır. Kod içinde uydurulmuş hata "
                "sınıfı yoktur."
            ),
            theme=theme,
            icon="list",
        )
        lists = QHBoxLayout()
        exercise_column = QVBoxLayout()
        exercise_column.addWidget(make_label("Egzersizler", role="caption"))
        self._exercise_list = QListWidget()
        exercise_column.addWidget(self._exercise_list)
        exercise_input = QHBoxLayout()
        self._exercise_input = QLineEdit()
        self._exercise_input.setPlaceholderText("Yeni egzersiz adı")
        exercise_input.addWidget(self._exercise_input)
        add_exercise = make_button("Ekle", icon="add", theme=theme)
        add_exercise.clicked.connect(self._add_exercise)
        exercise_input.addWidget(add_exercise)
        exercise_column.addLayout(exercise_input)
        exercise_container = QWidget()
        exercise_container.setLayout(exercise_column)
        lists.addWidget(exercise_container)

        error_column = QVBoxLayout()
        error_column.addWidget(make_label("Hata türleri", role="caption"))
        self._error_list = QListWidget()
        error_column.addWidget(self._error_list)
        error_input = QHBoxLayout()
        self._error_input = QLineEdit()
        self._error_input.setPlaceholderText("Yeni hata türü adı")
        error_input.addWidget(self._error_input)
        add_error = make_button("Ekle", icon="add", theme=theme)
        add_error.clicked.connect(self._add_error_type)
        error_input.addWidget(add_error)
        error_column.addLayout(error_input)
        error_container = QWidget()
        error_container.setLayout(error_column)
        lists.addWidget(error_container)

        lists_container = QWidget()
        lists_container.setLayout(lists)
        schema_card.add_widget(lists_container, 1)
        layout.addWidget(schema_card, 1)

        paths = Card("Dosya konumları", theme=theme, icon="folder-open")
        self._paths = KeyValueList(theme)
        paths.add_widget(self._paths)
        layout.addWidget(paths)
        return wrapper

    # ----------------------------------------------------------------- data
    def on_activated(self) -> None:
        self._load()
        self._reload_schema()
        self._refresh_paths()

    def _load(self) -> None:
        config = self.state.config
        self._theme_selector.blockSignals(True)
        self._theme_selector.setCurrentIndex(
            self._theme_selector.findData(config.theme)
        )
        self._theme_selector.blockSignals(False)
        self._backend_selector.setCurrentIndex(
            self._backend_selector.findData(config.backend.value)
        )
        self._preview_fps.setValue(config.preview_fps)
        self._log_level.setCurrentText(config.log_level)
        self._autosave.setChecked(config.autosave_enabled)
        self._autosave_delay.setValue(config.autosave_delay_ms)
        self._dataset_root.setText(str(config.dataset_root))

        capture = config.capture
        self._resolution.setCurrentText(capture.resolution)
        self._fps.setValue(capture.fps)
        self._depth_enabled.setChecked(capture.enable_depth)
        self._depth_mode.setCurrentText(capture.depth_mode)
        self._body_tracking.setChecked(capture.enable_body_tracking)
        self._body_format.setCurrentText(capture.body_format)
        self._body_model.setCurrentText(capture.body_tracking_model)
        self._body_fitting.setChecked(capture.enable_body_fitting)
        self._detection_confidence.setValue(capture.detection_confidence)
        self._native_recording.setChecked(capture.store_native_recording)
        archive_index = self._depth_archive.findData(capture.depth_archive)
        self._depth_archive.setCurrentIndex(max(0, archive_index))
        compression_index = self._native_compression.findData(
            capture.native_compression
        )
        self._native_compression.setCurrentIndex(max(0, compression_index))
        self._min_free_minutes.setValue(int(capture.min_free_disk_minutes))
        self._proxy_width.setValue(capture.proxy_video_width)

        mock = config.mock
        self._mock_width.setValue(mock.width)
        self._mock_height.setValue(mock.height)
        self._mock_fps.setValue(mock.fps)
        self._mock_seed.setValue(mock.seed)
        self._mock_bodies.setValue(mock.num_bodies)
        self._mock_depth.setChecked(mock.enable_depth)
        self._mock_tracking_loss.setValue(mock.tracking_loss_every)
        self._mock_low_confidence.setValue(mock.low_confidence_every)

    def _save(self) -> None:
        config = self.state.config
        config.backend = BackendKind(self._backend_selector.currentData())
        config.preview_fps = self._preview_fps.value()
        config.log_level = self._log_level.currentText()
        config.autosave_enabled = self._autosave.isChecked()
        config.autosave_delay_ms = self._autosave_delay.value()
        config.dataset_root = Path(self._dataset_root.text()).expanduser()

        capture = config.capture
        capture.resolution = self._resolution.currentText()
        capture.fps = self._fps.value()
        capture.enable_depth = self._depth_enabled.isChecked()
        capture.depth_mode = self._depth_mode.currentText()
        capture.enable_body_tracking = self._body_tracking.isChecked()
        capture.body_format = self._body_format.currentText()
        capture.body_tracking_model = self._body_model.currentText()
        capture.enable_body_fitting = self._body_fitting.isChecked()
        capture.detection_confidence = self._detection_confidence.value()
        capture.store_native_recording = self._native_recording.isChecked()
        capture.depth_archive = str(self._depth_archive.currentData())
        capture.native_compression = str(self._native_compression.currentData())
        capture.min_free_disk_minutes = float(self._min_free_minutes.value())
        capture.proxy_video_width = self._proxy_width.value()

        mock = config.mock
        mock.width = self._mock_width.value()
        mock.height = self._mock_height.value()
        mock.fps = self._mock_fps.value()
        mock.seed = self._mock_seed.value()
        mock.num_bodies = self._mock_bodies.value()
        mock.enable_depth = self._mock_depth.isChecked()
        mock.tracking_loss_every = self._mock_tracking_loss.value()
        mock.low_confidence_every = self._mock_low_confidence.value()

        self.state.save_preferences()
        # The backend object caches the capture profile, so rebuild it rather
        # than letting a stale profile keep driving the camera.
        self.state.release_capture_service()
        self.state.notify("Ayarlar kaydedildi. Yakalama profili sonraki kayıtlara uygulanır.")
        self._refresh_paths()

    def _theme_selected(self) -> None:
        self.state.set_theme(self._theme_selector.currentData())

    def _browse_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Dataset kök klasörü", self._dataset_root.text()
        )
        if directory:
            self._dataset_root.setText(directory)

    # ------------------------------------------------------------- schema
    def _reload_schema(self) -> None:
        workspace = self.state.workspace
        self._exercise_list.clear()
        self._error_list.clear()
        enabled = workspace is not None
        self._exercise_input.setEnabled(enabled)
        self._error_input.setEnabled(enabled)
        if workspace is None:
            self._exercise_list.addItem(
                QListWidgetItem("Etiket şeması için bir proje açın.")
            )
            return
        schema = workspace.label_schema
        for option in schema.exercises:
            self._exercise_list.addItem(f"{option.label}   [{option.code}]")
        for option in schema.error_types:
            self._error_list.addItem(f"{option.label}   [{option.code}]")
        if not schema.exercises:
            self._exercise_list.addItem(
                QListWidgetItem("Tanımlı egzersiz yok. Aşağıdan ekleyin.")
            )
        if not schema.error_types:
            self._error_list.addItem(
                QListWidgetItem(
                    "Tanımlı hata türü yok. Ontoloji araştırmacı tarafından tanımlanır."
                )
            )

    def _add_exercise(self) -> None:
        workspace = self.state.workspace
        name = self._exercise_input.text().strip()
        if workspace is None or not name:
            return
        schema = workspace.label_schema
        try:
            schema.add_exercise(name)
        except KineCaptureError as exc:
            QMessageBox.warning(self, "Eklenemedi", exc.user_text())
            return
        workspace.save_label_schema(schema)
        self._exercise_input.clear()
        self._reload_schema()
        self.state.notify(f"Egzersiz eklendi: {name}")

    def _add_error_type(self) -> None:
        workspace = self.state.workspace
        name = self._error_input.text().strip()
        if workspace is None or not name:
            return
        schema = workspace.label_schema
        try:
            schema.add_error_type(name)
        except KineCaptureError as exc:
            QMessageBox.warning(self, "Eklenemedi", exc.user_text())
            return
        workspace.save_label_schema(schema)
        self._error_input.clear()
        self._reload_schema()
        self.state.notify(f"Hata türü eklendi: {name}")

    # -------------------------------------------------------- diagnostics
    def _run_diagnostics(self) -> None:
        report = collect_diagnostics(
            dataset_root=self.state.config.dataset_root,
            backend=self.state.config.backend,
        )
        self._report = report
        self._report_view.setPlainText(report.as_text())
        self._health_chip.set_health(report.level)
        if report.level is HealthLevel.BLOCKED:
            self.state.notify("Tanı engel bildirdi; ayrıntı raporda.", 6000)

    def _copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        if not hasattr(self, "_report"):
            self._run_diagnostics()
        QApplication.clipboard().setText(self._report.as_text())
        self.state.notify("Rapor panoya kopyalandı.")

    def _refresh_paths(self) -> None:
        workspace = self.state.workspace
        self._paths.set_items(
            [
                ("Kullanıcı ayarları", str(USER_STATE_PATH)),
                ("Log dosyası", str(log_file_path() or "-")),
                ("Dataset kökü", str(self.state.config.dataset_root)),
                ("Açık proje", str(workspace.root) if workspace else "-"),
                (
                    "Sürümler",
                    str(workspace.releases_dir) if workspace else "-",
                ),
            ]
        )


__all__ = ["SettingsPage"]
