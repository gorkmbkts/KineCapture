"""Release gate A3, GUI: the real Studio window against a project at scale.

    python scripts/measure/scale_gui.py <out.json> --project <project_root>
        [--platform windows] [--cycles 10] [--timeline-frames 3000]
        [--timeline-segments 600] [--skip-export-check]

``<project_root>`` is a project written by ``scale_dataset.py`` into a temp
folder. The window is the product's own ``StudioWindow`` with its own
viewmodels and thread pool; only its preferences, identity database and logs
are sandboxed, so nothing of the user's is read or written.

What is measured, per screen:

* **fill time** - from the navigation to the moment the screen's data is on
  it (its viewmodel idle and its rows the expected count);
* **GUI thread blocking** - a 5 ms timer on the GUI thread; a tick that comes
  late by more than its interval is time the event loop could not run. The
  acceptance line is 250 ms;
* **memory** - resident set before, after and at peak (sampled every 100 ms);
* **uncaught exceptions** and logged errors.

Then the leak check: every screen visited ``--cycles`` times over, resident set
and live widget count after each round.

A version with ``--timeline-segments`` repetitions over ``--timeline-frames``
frames is produced first through the real record -> process chain, so the
labelling screen, its timeline, its class pickers and its label summary are
measured on a real version, not a stub.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--platform", default="windows")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--timeline-frames", type=int, default=3000)
    parser.add_argument("--timeline-segments", type=int, default=600)
    parser.add_argument("--skip-export-check", action="store_true")
    parser.add_argument("--check-timeout", type=float, default=1800.0)
    parser.add_argument("--phase-timeout", type=float, default=600.0,
                        help="how long a screen may take to fill (30k runs: the first dataset read is minutes)")
    parser.add_argument("--profile", action="store_true",
                        help="cProfile every phase; top functions go into the report")
    return parser.parse_args()


ARGS = _parse() if __name__ == "__main__" else None
if ARGS is not None:
    os.environ["QT_QPA_PLATFORM"] = ARGS.platform

import psutil  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

BLOCK_LIMIT_MS = 250.0
TICK_MS = 5


class LoopMonitor(QObject):
    """How late the GUI thread's own timer fires: the event loop's stalls.

    A watcher thread also looks at the GUI thread's Python stack whenever it
    has not ticked for 150 ms, so every stall comes with the code that caused
    it rather than only a number.
    """

    def __init__(self) -> None:
        super().__init__()
        import threading

        self._process = psutil.Process()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._last = time.perf_counter()
        self._last_rss_at = 0.0
        self._gui_thread = threading.get_ident()
        self.culprits: dict[str, dict[str, Any]] = {}
        self.reset("idle")
        self._watch = threading.Thread(target=self._watcher, daemon=True)
        self._watch.start()

    def _watcher(self) -> None:
        import traceback as tb

        seen_for: float = -1.0
        while True:
            time.sleep(0.05)
            last = self._last
            if time.perf_counter() - last < 0.15 or last == seen_for:
                continue
            seen_for = last
            frame = sys._current_frames().get(self._gui_thread)
            if frame is None:
                continue
            stack = tb.extract_stack(frame)
            ours = [f for f in stack if "kinecapture" in f.filename or "PySide6" in f.filename]
            key = " <- ".join(
                f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed((ours or stack)[-4:])
            )
            entry = self.culprits.setdefault(key, {"phase": self.phase, "hits": 0})
            entry["hits"] += 1

    def start(self) -> None:
        self._last = time.perf_counter()
        self._timer.start()

    def reset(self, phase: str) -> None:
        self.phase = phase
        self.max_gap_ms = 0.0
        self.stalls: list[float] = []
        self.peak_rss = self._process.memory_info().rss
        self._last = time.perf_counter()

    def _tick(self) -> None:
        now = time.perf_counter()
        late = (now - self._last) * 1000.0 - TICK_MS
        self._last = now
        if late > self.max_gap_ms:
            self.max_gap_ms = late
        if late > BLOCK_LIMIT_MS:
            self.stalls.append(round(late, 1))
        if now - self._last_rss_at > 0.1:
            self._last_rss_at = now
            self.peak_rss = max(self.peak_rss, self._process.memory_info().rss)

    def measure_block(self, action: Callable[[], Any]) -> float:
        """Run ``action`` on the GUI thread and return how long it held it."""
        began = time.perf_counter()
        action()
        held = (time.perf_counter() - began) * 1000.0
        self.max_gap_ms = max(self.max_gap_ms, held)
        if held > BLOCK_LIMIT_MS:
            self.stalls.append(round(held, 1))
        self._last = time.perf_counter()
        return held


class ErrorCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(f"{record.name}: {record.getMessage()}"[:300])


def settle(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.001)


def wait_until(app: QApplication, predicate: Callable[[], bool], timeout: float) -> Optional[float]:
    began = time.perf_counter()
    while time.perf_counter() - began < timeout:
        app.processEvents()
        try:
            if predicate():
                return time.perf_counter() - began
        except Exception:  # noqa: BLE001 - a predicate racing a reload
            pass
        time.sleep(0.002)
    return None


def build_timeline_version(project_root: Path, frames: int, segments: int) -> Path:
    """A real processed version with many labelled repetitions."""
    sys.path.insert(0, str(REPO / "tests"))
    from release_chain import Labeller, new_session, process, record

    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.processing.annotations import (
        AnnotationDocument,
        ErrorInterval,
        JointStatus,
        MovementSample,
        RolesOrigin,
        save_annotations,
    )
    from kinecapture.studio.services.review import ReviewSession

    workspace = ProjectWorkspace.open(project_root)
    schema = workspace.label_schema
    session = new_session(workspace)
    take, paths = record(workspace, session, frames=frames, seed=99)
    run = process(paths, take, body_format="BODY_38")
    with Labeller(run, schema) as labeller:
        labeller.choose_athlete()
    review = ReviewSession.open(run)
    try:
        dataset = review.dataset
        exercises = schema.exercise_codes()
        errors = schema.error_type_codes()
        span = max(2, frames // segments)
        samples = []
        for index in range(segments):
            start = index * span
            end = min(frames - 1, start + span - 2)
            faults = []
            if index % 3 == 0 and end > start:
                faults.append(ErrorInterval(
                    interval_id=f"err_tl{index:05d}",
                    start=dataset.anchor_at(start),
                    end=dataset.anchor_at(end),
                    error_class=errors[index % len(errors)],
                    affected_roles=("left_knee",),
                    joint_status=JointStatus.SELECTED,
                    roles_origin=RolesOrigin.REVIEWED,
                ))
            samples.append(MovementSample(
                sample_id=f"mov_tl{index:05d}",
                start=dataset.anchor_at(start),
                end=dataset.anchor_at(end),
                exercise=exercises[index % len(exercises)],
                errors=tuple(faults),
                reviewed_at="2026-09-23T12:00:00+00:00",
            ))
        document = AnnotationDocument(
            processing_run=review.run_id,
            source_fingerprint=review.source_fingerprint,
            samples=tuple(samples),
            revision=2,
            annotator="scale-test",
        )
        save_annotations(review.take_dir, document)
    finally:
        review.close()
    return run


def main() -> int:
    args = ARGS
    assert args is not None
    from kinecapture.core.config import AppConfig
    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.studio.app import build_window, install_exception_hook
    from kinecapture.studio.views.theming import apply_application_theme

    project_root = args.project.resolve()
    scratch = Path(tempfile.mkdtemp(prefix="kc_gui_scale_"))
    report: dict[str, Any] = {
        "platform": args.platform,
        "project": str(project_root),
        "phases": {},
        "cycles": [],
        "uncaught": [],
    }

    started = time.perf_counter()
    timeline_run = build_timeline_version(project_root, args.timeline_frames, args.timeline_segments)
    report["timeline_version"] = {
        "run": timeline_run.name, "frames": args.timeline_frames,
        "segments": args.timeline_segments, "build_s": round(time.perf_counter() - started, 1),
    }

    app = QApplication.instance() or QApplication([sys.argv[0]])
    config = AppConfig.sandboxed(scratch)
    config.dataset_root = project_root.parents[1]
    apply_application_theme(config.theme)
    errors = ErrorCounter()
    logging.getLogger("kinecapture").addHandler(errors)
    previous_hook = sys.excepthook

    def hook(kind, value, tb):  # noqa: ANN001
        report["uncaught"].append("".join(traceback.format_exception(kind, value, tb))[-1500:])
        previous_hook(kind, value, tb)

    window = build_window(config, state_path=scratch / "window.json")
    install_exception_hook(window)
    sys.excepthook = hook
    window.showMaximized()
    settle(app, 1.0)
    monitor = LoopMonitor()
    monitor.start()

    session = window.viewmodel.session
    assert window.auth_viewmodel.create_owner(
        first_name="Ölçek", last_name="Kullanıcı", title="", username="olcek",
        password="olcek-parola-1", password_confirm="olcek-parola-1",
    )
    settle(app, 0.5)
    workspace = ProjectWorkspace.open(project_root)
    session.identity.register_project(session.user, workspace)
    project_id = workspace.project.project_id
    class _Lazy:
        """A page's viewmodel, which exists only once the page was visited."""

        def __init__(self, key: str) -> None:
            self._key = key

        def __getattr__(self, name: str):  # noqa: ANN204
            viewmodel = window.viewmodel_for.get(self._key)
            if viewmodel is None:
                window.page(self._key)
                viewmodel = window.viewmodel_for[self._key]
            return getattr(viewmodel, name)

    projects_vm, library_vm = _Lazy("projects"), _Lazy("library")
    dataset_vm, processing_vm = _Lazy("dataset"), _Lazy("processing")
    export_vm, review_vm = _Lazy("export"), _Lazy("review")

    from kinecapture.dataset.summary_index import build_index

    index = build_index(project_root)
    expected_versions = len(index.published_runs())
    expected_waiting = len(index.awaiting_processing())
    report["expected"] = {"versions": expected_versions, "waiting": expected_waiting,
                          "takes": len(index)}

    process = psutil.Process()

    def phase(name: str, action: Callable[[], Any], done: Callable[[], bool], timeout: Optional[float] = None) -> None:
        timeout = args.phase_timeout if timeout is None else timeout
        gc.collect()
        rss_before = process.memory_info().rss
        monitor.reset(name)
        profiler = None
        if args.profile:
            import cProfile

            profiler = cProfile.Profile()
            profiler.enable()
        began = time.perf_counter()
        held = monitor.measure_block(action)
        filled = wait_until(app, done, timeout)
        settle(app, 0.3)
        hot: list[str] = []
        if profiler is not None:
            import io
            import pstats

            profiler.disable()
            buffer = io.StringIO()
            stats = pstats.Stats(profiler, stream=buffer)
            stats.sort_stats("tottime").print_stats(12)
            hot = [line.strip() for line in buffer.getvalue().splitlines()
                   if line.strip() and line.strip()[0].isdigit()][:12]
        report["phases"][name] = {
            "fill_s": None if filled is None else round(time.perf_counter() - began - 0.3, 3),
            "completed": filled is not None,
            "action_held_ms": round(held, 1),
            "max_block_ms": round(monitor.max_gap_ms, 1),
            "stalls_over_250ms": len(monitor.stalls),
            "worst_stalls_ms": sorted(monitor.stalls, reverse=True)[:5],
            "rss_before_mb": round(rss_before / 2**20, 1),
            "rss_after_mb": round(process.memory_info().rss / 2**20, 1),
            "rss_peak_mb": round(monitor.peak_rss / 2**20, 1),
            "errors_logged": len(errors.records),
        }
        if hot:
            report["phases"][name]["profile_tottime"] = hot
        print(f"[{name}] { {k: v for k, v in report['phases'][name].items() if k != 'profile_tottime'} }", flush=True)

    # --- Projeler --------------------------------------------------------
    phase(
        "projects_open",
        lambda: (window.viewmodel.navigate("projects"), projects_vm.reload_projects(),
                 projects_vm.open_project(project_id)),
        lambda: session.workspace is not None and not projects_vm.busy.value
        and sum(r.take_count for r in projects_vm.participants.value) == len(index),
    )
    # --- İşlenen Videolar ------------------------------------------------
    phase(
        "library",
        lambda: window.viewmodel.navigate("library"),
        lambda: not library_vm.busy.value and len(library_vm.all_rows) == expected_versions,
    )
    # --- Veri Seti -------------------------------------------------------
    phase(
        "dataset",
        lambda: window.viewmodel.navigate("dataset"),
        lambda: not dataset_vm.busy.value and len(dataset_vm.rows.value) == expected_versions
        and window.page("dataset").model.rowCount() == expected_versions
        and not getattr(window.page("dataset"), "_stats_pending", False),
    )
    keystrokes: list[float] = []

    def search_dataset() -> None:
        page = window.page("dataset")
        for text in ("P", "P0", "P00", "P000", "P0001", ""):
            began = time.perf_counter()
            page.search.setText(text)
            app.processEvents()
            keystrokes.append((time.perf_counter() - began) * 1000.0)

    phase("dataset_search", search_dataset, lambda: not getattr(window.page("dataset"), "_stats_pending", False))
    report["phases"]["dataset_search"]["per_keystroke_ms"] = [round(v, 1) for v in keystrokes]
    totals = dataset_vm.totals.value
    report["dataset_totals"] = {"versions": totals.versions, "movements": totals.movements,
                                "ready": totals.ready_movements, "errors": totals.error_intervals}
    # --- Verileri Hesapla (queue) ---------------------------------------
    phase(
        "processing_queue",
        lambda: window.viewmodel.navigate("processing"),
        lambda: not processing_vm.busy.value and len(processing_vm.waiting.value) == expected_waiting,
    )
    # --- Dışa Aktarım: check every version -------------------------------
    phase(
        "export_page",
        lambda: window.viewmodel.navigate("export"),
        lambda: not library_vm.busy.value,
    )
    if not args.skip_export_check:
        phase(
            "export_check",
            lambda: window.page("export")._check(),
            lambda: not export_vm.busy.value and len(export_vm.rows.value) == expected_versions,
            timeout=args.check_timeout,
        )
        # Coming back to the screen re-reads every checked version's revisions.
        phase("export_leave", lambda: window.viewmodel.navigate("dataset"),
              lambda: not dataset_vm.busy.value)
        phase("export_return", lambda: window.viewmodel.navigate("export"),
              lambda: not library_vm.busy.value)
    # --- Etiketleme --------------------------------------------------------
    phase(
        "review_open",
        lambda: (window.viewmodel.navigate("review"), review_vm.open_version(str(timeline_run))),
        lambda: review_vm.is_open and not review_vm.busy.value,
        timeout=300,
    )
    report["review"] = {"movements": len(review_vm.movements.value),
                        "errors": len(review_vm.errors.value),
                        "exercise_options": len(review_vm.exercise_options.value),
                        "error_options": len(review_vm.error_options.value)}
    review_page = window.page("review")
    phase("label_summary", lambda: review_page._label_icon_pressed(), lambda: True)
    frames = max(1, review_vm.frames.value)

    def scrub() -> None:
        for step in range(40):
            review_vm.seek(int(step * (frames - 1) / 39))
            app.processEvents()

    phase("timeline_scrub", scrub, lambda: True)

    selections: list[float] = []

    def select_many() -> None:
        rows = review_vm.movements.value
        for row in rows[:: max(1, len(rows) // 25)]:
            began = time.perf_counter()
            review_vm.select_movement(row.sample_id)
            app.processEvents()
            selections.append((time.perf_counter() - began) * 1000.0)

    phase("select_movements", select_many, lambda: True)
    report["phases"]["select_movements"]["per_selection_ms"] = {
        "first": round(selections[0], 1) if selections else None,
        "max_after_first": round(max(selections[1:]), 1) if len(selections) > 1 else None,
        "mean_after_first": round(sum(selections[1:]) / max(1, len(selections) - 1), 1),
    }

    edits: list[float] = []

    def edit_labels() -> None:
        rows = review_vm.movements.value
        codes = [code for code, _label in review_vm.exercise_options.value]
        for number, row in enumerate(rows[:: max(1, len(rows) // 10)][:10]):
            began = time.perf_counter()
            review_vm.label_movement(row.sample_id, codes[(number + 1) % len(codes)])
            app.processEvents()
            edits.append((time.perf_counter() - began) * 1000.0)

    phase("label_edits", edit_labels, lambda: True)
    report["phases"]["label_edits"]["per_edit_ms"] = {
        "max": round(max(edits), 1) if edits else None,
        "mean": round(sum(edits) / len(edits), 1) if edits else None,
    }
    review_vm.undo()
    app.processEvents()

    def browse() -> None:
        review_page._browse_classes(fault=True)
        app.processEvents()

    phase("class_browser_open", browse, lambda: True)

    def type_query() -> None:
        from kinecapture.studio.views.labelwindows import ClassBrowser

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, ClassBrowser) and widget.isVisible():
                for character in "diz iç":
                    widget.search.setText(widget.search.text() + character)
                    app.processEvents()
                widget.search.setText("")
                widget.close()

    phase("class_browser_search", type_query, lambda: True)

    # --- Theme toggle: re-polishes every live widget -----------------------
    phase("theme_toggle", lambda: window.viewmodel.toggle_theme(), lambda: True)
    report["phases"]["theme_toggle"]["widgets"] = len(QApplication.allWidgets())
    phase("theme_toggle_back", lambda: window.viewmodel.toggle_theme(), lambda: True)

    # --- Leak check -------------------------------------------------------
    sequence = ["projects", "library", "dataset", "processing", "export", "review"]
    for cycle in range(args.cycles):
        monitor.reset(f"cycle_{cycle}")
        began = time.perf_counter()
        for key in sequence:
            window.viewmodel.navigate(key)
            wait_until(
                app,
                lambda: not (library_vm.busy.value or dataset_vm.busy.value or processing_vm.busy.value),
                300,
            )
            settle(app, 0.1)
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        report["cycles"].append({
            "cycle": cycle,
            "seconds": round(time.perf_counter() - began, 2),
            "rss_mb": round(process.memory_info().rss / 2**20, 1),
            "widgets": len(QApplication.allWidgets()),
            "max_block_ms": round(monitor.max_gap_ms, 1),
            "stalls_over_250ms": len(monitor.stalls),
        })
        print(f"[cycle {cycle}] {report['cycles'][-1]}", flush=True)

    report["stall_culprits"] = sorted(
        ({"where": k, **v} for k, v in monitor.culprits.items()),
        key=lambda item: -item["hits"],
    )[:40]
    report["errors_logged"] = errors.records[:50]
    report["total_s"] = round(time.perf_counter() - started, 1)
    first = report["cycles"][1] if len(report["cycles"]) > 1 else None
    last = report["cycles"][-1] if report["cycles"] else None
    if first and last:
        report["leak"] = {
            "rss_growth_mb_after_warmup": round(last["rss_mb"] - first["rss_mb"], 1),
            "widget_growth_after_warmup": last["widgets"] - first["widgets"],
            "cycles_measured": len(report["cycles"]) - 1,
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.excepthook = previous_hook
    window.close()
    settle(app, 0.5)
    shutil.rmtree(scratch, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
