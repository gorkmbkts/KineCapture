# KineCapture Studio

Working title for a Windows desktop application that captures, reviews and
annotates 3D human motion recorded with a **Stereolabs ZED 2i** camera, so the
resulting datasets can feed a machine-learning pipeline later.

**Current stage: scaffold.** This repository is an architecture skeleton with a
working mock capture path. It is not yet a data-collection tool. Read
[What works today](#what-works-today) and
[What is not implemented yet](#what-is-not-implemented-yet) before relying on
anything here.

Project context, long-term goals and permanent decisions live in
[`MEMORY.md`](MEMORY.md). Read it before making changes.

---

## What works today

Verified by running the code (see [Verification status](#verification-status)):

* The package imports and the application starts **without** the ZED SDK.
* `--diagnose` prints a real environment report (OS, Python, PySide6, NumPy,
  PyYAML, `pyzed`, ZED backend, mock backend).
* A deterministic **mock camera backend** produces synthetic RGB frames and one
  moving synthetic skeleton - same seed, same bytes, every run.
* A **PySide6 main window** with backend selection, connect/disconnect,
  start/stop preview, live RGB preview, live 2D skeleton preview, capture state,
  frame index, measured vs. target FPS, dropped-frame counter and a status bar.
* A **capture service** between GUI and backend: bounded frame buffer, real
  drop counting, idempotent stop/shutdown, and no blocking loop on the Qt main
  thread (a `QTimer` polls the service).
* A tested **capture state machine** (`DISCONNECTED / READY / PREVIEWING /
  RECORDING / STOPPING / ERROR`) that raises on invalid transitions.
* **Session and annotation skeletons**: versioned schemas, atomic JSON writes,
  refusal to overwrite existing recordings, annotations kept as sidecar files.
* A test suite that needs neither hardware nor the ZED SDK.

## What is not implemented yet

Listed explicitly so nothing here looks finished when it is not:

* **The ZED backend.** `camera/zed.py` contains no capture or body-tracking
  calls. It only reports availability and fails loudly if used. No `pyzed` API
  was written from memory - see [ZED integration status](#zed-integration-status).
* **Recording.** `SessionWriter` creates the folder layout and writes
  `session.json`; `write_frame()` raises `NotImplementedError`. The recording
  buttons in the GUI are visible but disabled on purpose.
* **Depth capture and depth view.**
* **Playback, frame stepping and the annotation timeline UI.**
* **Dataset validation and export**, including any KineSynthV3 joint mapping.
* **Multi-person handling** beyond carrying a list of bodies through the pipeline.
* **ZED skeleton topologies** (BODY_18 / BODY_34 / BODY_38). Only the 16-joint
  mock skeleton is registered; ZED joint orders must be read from a verified
  local SDK, never reproduced from memory.
* **Packaging and distribution.**

---

## Requirements

* Windows (the platform target; the code itself avoids OS-specific paths)
* Anaconda or Miniconda on `PATH`
* Python 3.10 - pinned in `environment.yml`, see the note under
  [ZED integration status](#zed-integration-status)
* PySide6, NumPy, PyYAML (installed by the editable install)
* pytest, pytest-qt (dev extra)
* **The ZED SDK is a separate, out-of-band dependency.** It is not installed by
  pip and is not required to run the mock backend, the tests or `--diagnose`.

## Setup (Windows)

Everything runs in a **project-specific Conda environment** named
`KineCaptureStudio`. Never install this project into `base`, `Kinesynth` or any
other existing environment.

```powershell
# from the project root
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```

`setup_env.ps1`:

1. creates `KineCaptureStudio` from `environment.yml` if it does not exist, and
   marks it as this project's environment;
2. refuses to modify an existing environment of the same name that it does not
   own - pass `-EnvName KineCaptureStudio-ZED2i` (and update `environment.yml`,
   this README and the scripts) or `-AdoptExisting` if you are sure;
3. installs the project editable with dev extras;
4. prints `sys.executable` and the installed package versions so you can see
   which interpreter actually ran.

The equivalent manual commands:

```powershell
conda env create -f environment.yml
conda run -n KineCaptureStudio python -m pip install -e ".[dev]"
```

## Running

```powershell
# mock backend GUI
powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1

# environment report, no GUI
powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1 -Diagnose

# tests
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

Equivalent direct commands:

```powershell
conda run -n KineCaptureStudio python -m kinecapture --backend mock
conda run -n KineCaptureStudio python -m kinecapture --diagnose
conda run -n KineCaptureStudio python -m pytest
```

If you chose a different environment name, use that real name everywhere.

## Configuration

`configs/default.yaml` holds the starting defaults: app name, default backend,
target preview FPS, mock frame size and seed, log level, and the output and log
directories. Runtime data never lives inside the source tree - the defaults
point at `~/KineCaptureStudio/data` and `~/KineCaptureStudio/logs`, and those
paths (plus `logs/`, `data/`, `*.svo`) are git-ignored.

Override the file with `--config path\to\file.yaml`; override single values with
`--backend` and `--log-level`.

## Project layout

```text
src/kinecapture/
├── core/           config, logging, diagnostics, capture state machine
├── domain/         enums and dataclasses (no Qt, no pyzed)
├── camera/         backend contract, mock backend, ZED adapter stub
├── services/       capture service - the GUI/backend boundary
├── recording/      session folder layout and atomic metadata writing
├── annotations/    annotation sidecar store
├── visualization/  skeleton topology (SkeletonSpec)
└── gui/            PySide6 main window and widgets
tests/              hardware-free unit tests
scripts/            PowerShell entry points (project environment only)
configs/            default.yaml
```

Architectural rules that must survive future changes:

* the GUI never imports `pyzed` and never calls a backend directly;
* `pyzed` is imported lazily, inside the ZED backend, never at module import;
* raw data and display-only transforms stay separate - the skeleton view's axis
  flip and scaling never touch stored coordinates;
* annotations are sidecar files and never modify a raw recording;
* every recording and annotation file carries a schema version;
* nothing blocks the Qt main thread.

## ZED integration status

**Not implemented.** This is deliberate, not an oversight.

The ZED SDK version, its Python binding and the exact body format have not been
verified on the target machine yet. Writing plausible-looking `pyzed.sl` calls
from memory would produce code that looks finished and fails on first contact
with real hardware. Instead:

* `camera/zed.py` imports `pyzed` lazily and only inside its own functions;
* `is_available()` returns a machine-readable reason (`pyzed_missing` or
  `not_implemented`) plus a message a user can act on;
* `connect()`, `start_preview()` and `grab_frame()` raise
  `CameraUnavailableError` rather than returning fake data;
* `--diagnose` shows this state honestly.

The Python 3.10 pin in `environment.yml` is an **assumption** based on the ZED
SDK 4.x Python binding supporting CPython 3.8-3.11. It has not been checked
against a local SDK installation. Verify it before treating it as final.

To install the binding once the SDK is present, run Stereolabs'
`get_python_api.py` **inside the project environment**:

```powershell
conda run -n KineCaptureStudio python "C:\Program Files (x86)\ZED SDK\get_python_api.py"
conda run -n KineCaptureStudio python -m kinecapture --diagnose
```

Installing `pyzed` alone does not make the ZED backend work - the adapter still
has to be written.

## Verification status

The scaffold's Python behaviour was verified by execution:

* full test suite: **63 passed**;
* `python -m kinecapture --diagnose`: exit code 0, correctly reporting `pyzed`
  and the ZED backend as unavailable;
* offscreen GUI smoke run: window built, mock backend connected, preview timer
  delivered 29 frames in ~1 s at a 30 FPS target, recording buttons disabled,
  clean shutdown.

The PowerShell scripts were parsed and exercised on PowerShell 7.4 (Linux) with
a stub that emulates `conda run`: `run_app.ps1 -Diagnose`, `run_tests.ps1` and
`run_tests.ps1 -k <expr>` all worked, and `setup_env.ps1` correctly refused to
touch an existing environment it did not own.

What is still **unverified**, because it needs the target machine:

* real Conda environment creation, and therefore `python=3.10` resolution on
  Windows;
* the scripts running against a real `conda` on Windows PowerShell 5.1;
* anything involving the ZED SDK or the camera itself.

Run `scripts\setup_env.ps1` and `scripts\run_tests.ps1` on the Windows machine to
close those gaps, and record the result in `MEMORY.md`.

## Next development step

Verify the real ZED SDK environment and build a single-frame prototype:
confirm the SDK version and the Python version it supports, install `pyzed`
into `KineCaptureStudio`, open the camera once, grab one frame plus one body,
and record the actual joint count, joint order, coordinate system and length
unit in `MEMORY.md`. Only then implement `ZedCameraBackend` and decide the
recording format.

## Relationship to KineSynthV3

This project is intentionally separate from the KineSynthV3 repository. It does
not import KineSynthV3 code, does not assume it is present on the machine, and
does not reference its datasets by path. Compatibility will be provided later by
an explicit, tested, versioned export adapter - not by a code dependency. The
ZED native joint layout must not be assumed to match KineSynthV3's 26-joint
skeleton.
