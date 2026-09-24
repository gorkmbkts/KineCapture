"""After installing: the zero state, then one whole chain, on the installed Python.

Run with the **installed** interpreter, as a throwaway user - the caller
redirects ``LOCALAPPDATA``, ``APPDATA``, ``USERPROFILE``, ``TEMP``::

    <kurulum>\\env\\python.exe -B scripts\\release\\smoke_installed.py --tests <depo>\\tests --report sonuc.json

1. **Zero state** - the configuration the application itself loads points
   into the redirected user; there is no identity database yet; opening the
   session gives the first-run form (no seed) or exactly the seeded owner;
   the project list is empty.
2. **Chain on the mock backend** - project, participant, session, a mock
   recording, offline processing twice (in this process, and as the Studio's
   child process ``python -B -m kinecapture.processing``), labelling
   (movements, an error interval with joint roles), the canonical export and
   the independent oracle over it, checksums included.
3. **ZED** - pyzed imports against the SDK and reports its version; a camera
   that is attached is listed by serial number, never opened.

``tests/release_chain.py`` and ``tests/release_oracle.py`` come from the
repository (``--tests``); they need only numpy and kinecapture.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tests", required=True, help="deponun tests klasörü")
    parser.add_argument("--report", required=True)
    parser.add_argument("--expect-owner", default="", help="tohumla gelmesi gereken kullanıcı adı")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(args.tests).resolve()))
    result: dict = {"python": sys.executable, "steps": {}, "ok": False}
    started = time.perf_counter()
    try:
        _run(result, args)
        result["ok"] = all(step.get("ok") for step in result["steps"].values())
    except Exception as exc:  # noqa: BLE001 - reported in the file, not lost
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    result["seconds"] = round(time.perf_counter() - started, 1)
    Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "traceback"}, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 1


def _run(result: dict, args) -> None:  # noqa: ANN001
    import kinecapture
    from kinecapture.core.config import AppConfig, load_config
    from kinecapture.studio.services.session import SessionService

    steps = result["steps"]
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    profile = Path(os.environ["USERPROFILE"]).resolve()
    install_env = Path(sys.prefix).resolve()
    steps["package"] = {
        "ok": Path(kinecapture.__file__).resolve().is_relative_to(install_env),
        "file": kinecapture.__file__, "version": kinecapture.APP_VERSION,
    }

    # 1. zero state -------------------------------------------------------
    config = load_config()
    identity = Path(config.identity_db_path).resolve()
    dataset_root = Path(config.dataset_root).resolve()
    existed_before = identity.exists()
    session = SessionService.open(config)
    users = session.identity.repository.user_count()
    zero = {
        "identity_db": str(identity),
        "identity_in_redirected_user": identity.is_relative_to(local),
        "dataset_root_in_redirected_user": dataset_root.is_relative_to(profile),
        "identity_db_existed_before": existed_before,
        "needs_initial_setup": session.needs_initial_setup,
        "users": users,
        "projects_on_disk": sorted(p.name for p in (dataset_root / "projects").glob("*")) if (dataset_root / "projects").exists() else [],
        "startup_notice": session.startup_notice.outcome.value if session.startup_notice else None,
    }
    if args.expect_owner:
        owner = session.identity.repository.get_user_by_normalized_username(args.expect_owner)
        zero["owner_present"] = owner is not None and owner.is_owner
        zero_ok = users == 1 and zero["owner_present"] and not session.needs_initial_setup
    else:
        zero_ok = users == 0 and session.needs_initial_setup
    zero["ok"] = bool(
        zero_ok and not existed_before and zero["identity_in_redirected_user"]
        and zero["dataset_root_in_redirected_user"] and not zero["projects_on_disk"]
    )
    steps["zero_state"] = zero

    # 2. the chain ----------------------------------------------------------
    import numpy as np
    import release_chain as chain
    import release_oracle as oracle

    from kinecapture.core.jsonio import write_json
    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.export.canonical import build_release
    from kinecapture.processing import ProcessingConfig
    from kinecapture.processing.annotations import JointStatus, RolesOrigin
    from kinecapture.processing.sources import SyntheticSource

    workspace = ProjectWorkspace.create(dataset_root, "Kurulum Doğrulaması (ğüşıöç)")
    schema = workspace.label_schema
    squat = schema.ensure_exercise("Squat").code
    valgus = schema.ensure_error_type("Diz içe çöküyor").code
    workspace.save_label_schema(schema)
    schema = workspace.label_schema

    runs = []
    session_a = chain.new_session(workspace)
    take, paths = chain.record(workspace, session_a, frames=40, seed=31)
    run_a = chain.process(paths, take, body_format="BODY_18")
    runs.append(run_a)

    # The Studio's route: the processing module as a child of this Python.
    session_b = chain.new_session(workspace)
    take, paths = chain.record(workspace, session_b, frames=40, seed=32)
    config_b = ProcessingConfig(body_format="BODY_34", store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config_b.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(paths.raw_dir / "subject_anchors.json", [{
        "camera_timestamp_ns": packet.camera_timestamp_ns,
        "source_resolution": list(packet.resolution),
        "point_xy": np.nanmean(points, axis=0).tolist(),
        "bbox_xyxy": np.r_[np.nanmin(points, axis=0), np.nanmax(points, axis=0)].tolist(),
    }])
    source.close()
    child = subprocess.run(
        [sys.executable, "-B", "-m", "kinecapture.processing", str(paths.root),
         "--body-format", "BODY_34", "--no-depth", "--no-proxy"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    # The module prints where it published; a glob would silently miss a
    # version whose path is past MAX_PATH.
    summary = {}
    for line in reversed(child.stdout.strip().splitlines()):
        try:
            summary = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    output = Path(summary["output"]) if summary.get("output") else None
    steps["child_processing"] = {
        "ok": child.returncode == 0 and summary.get("state") == "complete" and output is not None,
        "exit_code": child.returncode, "state": summary.get("state"), "frames": summary.get("frames"),
        "run": output.name if output else None, "stderr_tail": child.stderr[-600:],
    }
    if output is not None:
        runs.append(output)

    for run in runs:
        with chain.Labeller(run, schema) as labeller:
            labeller.choose_athlete()
            first = labeller.movement(2, 12, squat, note="kurulum doğrulaması")
            labeller.error(first, 4, 9, valgus, roles=("left_knee",),
                           status=JointStatus.SELECTED, origin=RolesOrigin.REVIEWED)
            labeller.movement(20, 39, squat)

    releases = dataset_root / "releases"
    report = build_release(runs, releases, workspace.label_schema, operator="kurulum-dogrulama")
    problems = oracle.verify(
        report.release_dir, runs, chain.schema_file(workspace), project=chain.project_file(workspace)
    )
    problems += oracle.verify_checksums(report.release_dir)
    steps["chain"] = {
        "ok": not problems and report.samples == 4,
        "samples": report.samples, "release": str(report.release_dir), "oracle_problems": problems[:20],
    }

    # 3. ZED --------------------------------------------------------------
    from kinecapture.camera import zed

    version = zed.sdk_version()
    devices = zed.list_devices()
    steps["zed"] = {
        "ok": version is not None,
        "sdk_version": version,
        "import_error": zed.pyzed_import_error(),
        "sdk_bin": str(zed.sdk_bin_directory()),
        "devices": [{"serial": d["serial_number"], "model": d["model"], "state": d["state"]} for d in devices],
    }


if __name__ == "__main__":
    raise SystemExit(main())
