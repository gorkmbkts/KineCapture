"""Command line entry point.

```powershell
python -m kinecapture                    # open the GUI
python -m kinecapture --backend zed      # preselect a backend
python -m kinecapture --diagnose         # environment report, no GUI
python -m kinecapture --list-devices     # ZED cameras, no GUI
python -m kinecapture --self-test        # headless end-to-end on synthetic data
```

Error handling policy: the user sees a short, actionable message on stderr; the
traceback goes to the log file only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.config import AppConfig, load_config
from kinecapture.core.errors import KineCaptureError
from kinecapture.core.logging import (
    get_logger,
    install_excepthook,
    log_file_path,
    setup_logging,
)
from kinecapture.domain.enums import BackendKind, HealthLevel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kinecapture",
        description=f"{APP_NAME} - ZED 2i yakalama, inceleme, etiketleme ve dataset export",
    )
    parser.add_argument(
        "--backend",
        choices=[kind.value for kind in BackendKind],
        default=None,
        help="kullanılacak kamera backend'i (varsayılan: ayar dosyasındaki değer)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML ayar dosyası yolu (varsayılan: configs/default.yaml)",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="dataset kök klasörünü bu çalıştırma için geçersiz kıl",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="yapılandırılmış log seviyesini geçersiz kıl",
    )
    parser.add_argument(
        "--theme",
        choices=["dark", "light"],
        default=None,
        help="tema seçimi",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="ortam raporunu yazdır ve GUI açmadan çık",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="bağlı ZED kameraları listele ve çık",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "sentetik backend ile uçtan uca akışı GUI'siz çalıştır "
            "(geçici klasöre yazar, sonra siler)"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"{APP_NAME} {APP_VERSION}"
    )
    return parser


def _apply_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    if args.backend:
        config.backend = BackendKind(args.backend)
    if args.log_level:
        config.log_level = args.log_level
    if args.theme:
        config.theme = args.theme
    if args.dataset_root:
        config.dataset_root = Path(args.dataset_root).expanduser()
    return config


def run_diagnostics(config: AppConfig) -> int:
    """Print the environment report. Returns a process exit code."""
    from kinecapture.core.diagnostics import collect_diagnostics

    report = collect_diagnostics(
        dataset_root=config.dataset_root, backend=config.backend
    )
    print(report.as_text())
    if report.level is HealthLevel.BLOCKED:
        print(
            "\nEn az bir engel var. Yukarıdaki [STOP] satırlarını giderin.",
            file=sys.stderr,
        )
        return 1
    if report.level is HealthLevel.WARNING:
        print("\nUyarılar var; uygulama çalışır fakat bazı özellikler sınırlı olabilir.")
    else:
        print("\nOrtam hazır.")
    return 0


def list_devices() -> int:
    """List attached ZED cameras."""
    from kinecapture.camera.zed import is_pyzed_available, pyzed_import_error
    from kinecapture.camera.zed import list_devices as enumerate_devices
    from kinecapture.camera.zed import sdk_version

    if not is_pyzed_available():
        print(
            "ZED Python modülü (pyzed) bu ortamda yok.\n"
            f"Ayrıntı: {pyzed_import_error()}\n"
            "ZED SDK kurulumundaki get_python_api.py betiğini KineSynth "
            "environment içinde çalıştırın.",
            file=sys.stderr,
        )
        return 1
    print(f"ZED SDK {sdk_version()}")
    devices = enumerate_devices()
    if not devices:
        print("Bağlı kamera bulunamadı.")
        return 1
    for device in devices:
        print(
            f"  id={device['id']}  model={device['model']}  "
            f"serial={device['serial_number']}  state={device['state']}"
        )
    return 0


def run_self_test(config: AppConfig) -> int:
    """Headless end-to-end run on synthetic data, in a temporary directory."""
    import shutil
    import tempfile
    import time

    from kinecapture.annotations.repository import AnnotationRepository
    from kinecapture.camera.mock import MockCameraBackend
    from kinecapture.capture.service import CaptureService
    from kinecapture.core.jsonio import read_json_mapping
    from kinecapture.dataset.index import DatasetIndex
    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.domain.activity import ActivityState
    from kinecapture.domain.enums import Correctness, TakeQuality
    from kinecapture.export.release import ExportOptions, ReleaseBuilder
    from kinecapture.playback.take_reader import load_take
    from kinecapture.recording.rgbd_archive import RgbdArchiveReader

    root = Path(tempfile.mkdtemp(prefix="kinecapture_selftest_"))
    print(f"Geçici çalışma alanı: {root}")
    try:
        workspace = ProjectWorkspace.create(root, "Self Test")
        schema = workspace.label_schema
        schema.add_exercise("Squat")
        workspace.save_label_schema(schema)
        participant = workspace.create_participant()
        session = workspace.create_session(
            participant.participant_id, operator="self-test"
        )
        print(f"  proje/katılımcı/oturum   : OK ({participant.code})")

        backend = MockCameraBackend(width=320, height=180, fps=30, seed=1234)
        service = CaptureService(backend)
        service.connect()
        service.start_preview()
        take = service.start_recording(workspace, session, exercise="squat")
        deadline = time.time() + 5.0
        while service.recorded_frame_count < 60 and time.time() < deadline:
            time.sleep(0.01)
        take = service.stop_recording()
        service.shutdown()
        if take is None or take.metrics.frames_written < 10:
            print("  kayıt                     : BAŞARISIZ", file=sys.stderr)
            return 1
        print(
            f"  kayıt                     : OK "
            f"({take.metrics.frames_written} kare, {take.metrics.duration_s:.1f} sn)"
        )

        take.quality = TakeQuality.GOOD
        workspace.save_take(take)
        loaded = load_take(workspace, take)
        print(
            f"  playback                  : OK "
            f"({loaded.frame_count} kare, video={loaded.has_video})"
        )

        # Two movement samples: one clean, one whose error is localised, so the
        # self-test exercises both label levels rather than only the easy path.
        schema = workspace.label_schema
        error_class = schema.add_error_type("Diz içe çöküyor")
        workspace.save_label_schema(schema)

        repository = AnnotationRepository(
            workspace, take, frame_count=loaded.frame_count
        )
        midpoint = loaded.frame_count // 2
        good = repository.create_sample(1, midpoint - 2)
        repository.label_sample(
            good.sample_id, exercise="squat", correctness=Correctness.CORRECT
        )
        bad = repository.create_sample(midpoint, max(midpoint + 3, loaded.frame_count - 2))
        repository.label_sample(
            bad.sample_id, exercise="squat", correctness=Correctness.INCORRECT
        )
        repository.create_error_interval(
            bad.sample_id,
            bad.start_frame + 2,
            bad.start_frame + 6,
            error_code=error_class.code,
        )
        repository.save()
        if repository.ready_count != 2:
            print(
                f"  etiketleme                : BAŞARISIZ "
                f"({repository.ready_count}/2 hazır)",
                file=sys.stderr,
            )
            return 1
        print(
            "  hareket/hata etiketleme   : OK "
            "(2 hareket, 1 zamansal hata aralığı)"
        )

        # --- the activity strip over the whole take -------------------
        frames = loaded.frame_count
        activity = repository.activity_from_samples()
        created = len(activity)
        gaps = repository.unlabelled_activity_gaps()
        if gaps:
            repository.create_activity_interval(
                gaps[0][0], gaps[0][1], state=ActivityState.BACKGROUND
            )
            created += 1
        repository.save()
        readiness, coverage = repository.continuous_readiness()
        if not readiness.is_ready:
            print(
                f"  aktivite etiketleme       : BAŞARISIZ ({readiness.value})",
                file=sys.stderr,
            )
            return 1
        print(
            f"  aktivite etiketleme       : OK ({created} aralık, kapsam "
            f"%{coverage.ratio * 100:.0f}, {coverage.unlabelled_frames} kare "
            "etiketsiz)"
        )

        # --- the immutable raw archive --------------------------------
        paths = workspace.take_paths(take)
        archive = RgbdArchiveReader(paths.rgbd_dir)
        problems = archive.verify()
        stored = archive.positions()
        if problems or len(stored["depth"]) != take.metrics.frames_written:
            print(
                f"  ham RGB-D arşivi          : BAŞARISIZ "
                f"({len(problems)} sorun, {len(stored['depth'])}/"
                f"{take.metrics.frames_written} derinlik karesi)",
                file=sys.stderr,
            )
            return 1
        manifest = read_json_mapping(paths.raw_manifest)
        codec = manifest["rgbd_archive"]["depth"]["codec"]
        print(
            f"  ham RGB-D arşivi          : OK ({len(stored['depth'])} derinlik, "
            f"{len(stored['color'])} renk karesi, {codec})"
        )

        index = DatasetIndex(workspace).refresh()
        summary = index.summary()
        print(
            f"  dataset index             : OK "
            f"({summary.takes} kayıt, {summary.ready_samples} hazır hareket, "
            f"{summary.error_intervals} hata aralığı)"
        )

        # A feature-carrying selection, so the self test proves the whole
        # export path rather than only its canonical core.
        builder = ReleaseBuilder(
            workspace,
            index,
            ExportOptions(
                include_synthetic=True,
                export_continuous=True,
                feature_ids=(
                    "validity_masks",
                    "joint_velocity",
                    "joint_angles",
                    "summary_vector",
                ),
            ),
        )
        result = builder.build()
        print(
            f"  export                    : OK ({result.release_name}, "
            f"{result.sample_count} hareket örneği, {result.continuous_count} "
            f"sürekli örnek, {result.error_interval_count} hata aralığı, "
            f"doğrulama={'geçti' if result.validation_passed else 'HATA'})"
        )
        for name in (
            "manifest.json",
            "skeleton_spec.json",
            "label_mapping.json",
            "feature_spec.json",
            "activity_spec.json",
            "dataset_fingerprint.json",
            "validation_report.json",
        ):
            if not (result.path / name).is_file():
                print(f"  eksik sürüm dosyası: {name}", file=sys.stderr)
                return 1
        print(
            "  sürüm dosyaları           : OK (manifest, skeleton spec, "
            "feature spec, activity spec, mapping, fingerprint, rapor)"
        )
        print("\nUçtan uca sentetik akış başarıyla tamamlandı.")
        return 0
    except Exception as exc:
        get_logger(__name__).exception("Self test failed")
        print(f"\nSelf test başarısız: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_gui(config: AppConfig) -> int:
    """Start the Qt application. Returns a process exit code."""
    logger = get_logger(__name__)
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        logger.debug("PySide6 import failed", exc_info=True)
        print(
            "PySide6 bu ortamda bulunamadı.\n"
            "Bağımlılıkları KineSynth environment içine kurun:\n"
            '  conda run -n KineSynth python -m pip install -e ".[dev]"\n'
            f"(ayrıntı: {exc})",
            file=sys.stderr,
        )
        return 1

    from kinecapture.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(config.app_name)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("KineCapture")

    window = MainWindow(config)
    window.show()
    return int(app.exec())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except KineCaptureError as exc:
        print(f"Ayar hatası: {exc.message} {exc.remedy}".strip(), file=sys.stderr)
        return 2

    config = _apply_overrides(config, args)
    logger = setup_logging(config.log_level, config.log_dir)
    install_excepthook()
    logger.debug("Etkin ayarlar: %s", config.to_dict())

    try:
        if args.list_devices:
            return list_devices()
        if args.diagnose:
            return run_diagnostics(config)
        if args.self_test:
            return run_self_test(config)
        return run_gui(config)
    except KeyboardInterrupt:
        print("Kesildi.", file=sys.stderr)
        return 130
    except KineCaptureError as exc:
        logger.exception("Uygulama hatası")
        print(f"{exc.message} {exc.remedy}".strip(), file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Beklenmeyen hata")
        print(
            f"{APP_NAME} devam edemedi: {exc}\n"
            f"Teknik ayrıntılar log dosyasına yazıldı: {log_file_path() or config.log_dir}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
