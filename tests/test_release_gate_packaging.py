"""Release gate A4: the code has to run from somewhere that is not this folder.

An installed KineCapture runs from a relocated conda environment, from a
read-only installation folder, through ``pythonw.exe`` with no console, on a
machine that may not have the ZED SDK. Each test here pins down one thing that
works from a checkout by accident and would break in that setting.

Every child process gets its own ``USERPROFILE`` and ``LOCALAPPDATA`` under
``tmp_path``: nothing here reads or writes the real user's data.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kinecapture.core.config import default_config_path, load_config
from kinecapture.dataset.summary_index import TakeSummary
from kinecapture.studio.services.processing import JobState, ProcessingService

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "kinecapture"


def _isolated_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """A child environment whose home and app-data folders are throwaway."""
    home = tmp_path / "home"
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        USERPROFILE=str(home),
        HOME=str(home),
        LOCALAPPDATA=str(home / "AppData" / "Local"),
        QT_QPA_PLATFORM="offscreen",
    )
    env.pop("PYTHONPATH", None)
    env.update(extra)
    return env


# ------------------------------------------------------------ configuration
def test_the_default_configuration_is_package_data() -> None:
    path = default_config_path()
    assert path.is_file()
    import kinecapture

    assert Path(kinecapture.__file__).parent in path.parents
    config = load_config(include_user_state=False)
    assert config.capture.fps == 60 and config.capture.body_format == "BODY_38"


def test_no_module_walks_up_out_of_the_package() -> None:
    """``Path(__file__).parents[N]`` past the package is a checkout assumption."""
    offenders = []
    pattern = re.compile(r"__file__\)\.resolve\(\)\.parents\[(\d+)\]")
    for path in PACKAGE.rglob("*.py"):
        depth = len(path.relative_to(PACKAGE).parts) - 1  # folders below kinecapture/
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            if int(match.group(1)) > depth:
                offenders.append(f"{path.relative_to(ROOT)}: parents[{match.group(1)}]")
    assert offenders == []


def test_no_machine_specific_path_is_compiled_in() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in PACKAGE.rglob("*")
        if path.is_file()
        and path.suffix in (".py", ".json", ".yaml", ".tmpl", ".txt", ".md")
        and re.search(r"(?i)c:[\\/]+users[\\/]+|gorke", path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []


# ----------------------------------------------------------- child processes
def _take(directory: Path) -> TakeSummary:
    return TakeSummary(
        take_id="take_gate",
        participant_id="P0001",
        session_id="ses_gate",
        directory=str(directory),
        state="complete",
    )


class _ChattyService(ProcessingService):
    """A processing child that writes a megabyte to stderr before exiting.

    The ZED SDK prints progress while it optimises a model, and a child's
    Python warnings land on stderr as well. Nothing reads those pipes while the
    child runs, so once the pipe buffer is full the child blocks on its next
    write - and a job that cannot exit shows as "running" for ever.
    """

    def _command(self, take, parameters):  # noqa: ANN001, ANN202
        return [
            sys.executable, "-c",
            "import sys; sys.stderr.write('x' * 1_000_000); sys.stderr.flush();"
            "sys.stdout.write('y' * 200_000); sys.stdout.flush()",
        ]


def test_a_chatty_processing_child_does_not_hang(tmp_path) -> None:
    service = _ChattyService(log_dir=tmp_path / "logs")
    job = service.start(_take(tmp_path))
    deadline = time.time() + 60
    while job.process.poll() is None and time.time() < deadline:
        service.poll()
        time.sleep(0.05)
    try:
        assert job.process.poll() is not None, "the child blocked on a full pipe"
    finally:
        if job.process.poll() is None:
            job.process.kill()
    service.poll()
    assert job.progress.state is JobState.COMPLETE
    logs = list((tmp_path / "logs").glob("*.log"))
    assert logs and logs[0].stat().st_size >= 1_000_000, "the child's output went nowhere"


def test_a_failed_child_says_why_from_its_log(tmp_path) -> None:
    class Failing(ProcessingService):
        def _command(self, take, parameters):  # noqa: ANN001, ANN202
            return [sys.executable, "-c", "import sys; sys.stderr.write('patladı: disk dolu'); sys.exit(3)"]

    service = Failing(log_dir=tmp_path / "logs")
    job = service.start(_take(tmp_path))
    job.process.wait(timeout=60)
    service.poll()
    assert job.progress.state is JobState.FAILED
    assert "disk dolu" in job.progress.error


def test_the_childs_turkish_message_reaches_the_screen_intact(tmp_path) -> None:
    """Redirected to a file the child wrote cp1254 and the log was read as
    UTF-8: the ASCII half of the message survived, "patladı" did not."""

    class Failing(ProcessingService):
        def _command(self, take, parameters):  # noqa: ANN001, ANN202
            return [sys.executable, "-c",
                    "import sys; print('işlem başladı'); sys.stderr.write('patladı: ğüşıöç ĞÜŞİÖÇ'); sys.exit(3)"]

    service = Failing(log_dir=tmp_path / "logs")
    job = service.start(_take(tmp_path))
    job.process.wait(timeout=60)
    service.poll()
    assert job.progress.state is JobState.FAILED
    assert "patladı: ğüşıöç ĞÜŞİÖÇ" in job.progress.error
    assert "�" not in job.progress.error


def test_processing_children_never_open_a_console(tmp_path, monkeypatch) -> None:
    captured: dict = {}

    class FakePopen:
        def __init__(self, command, **kwargs):  # noqa: ANN001, ANN003
            captured.update(kwargs, command=command)
            self.pid = 0
            self.returncode = 0

        def poll(self):  # noqa: ANN201
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    service = ProcessingService(log_dir=tmp_path / "logs")
    service.start(_take(tmp_path))
    if os.name == "nt":
        assert captured["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert captured["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    assert captured["command"][0] == sys.executable
    assert captured["stdout"] not in (None, subprocess.PIPE)
    # Not wherever the shortcut happened to start the application.
    assert Path(captured["cwd"]) != Path.cwd() or Path.cwd() == tmp_path


_CONSOLELESS_PARENT = """
import json, sys, time
from pathlib import Path
from kinecapture.dataset.summary_index import TakeSummary
from kinecapture.studio.services.processing import ProcessingService

out = Path(sys.argv[1])

class Child(ProcessingService):
    def _command(self, take, parameters):
        # The real module entry point, asked only for its usage line: enough
        # to prove the interpreter, the import path and the output file.
        return [self._python, "-B", "-m", "kinecapture.processing", "--help"]

service = Child(log_dir=out.parent / "logs")
job = service.start(TakeSummary(take_id="t", participant_id="P", session_id="S",
                                directory=str(out.parent), state="complete"))
deadline = time.time() + 60
while job.process.poll() is None and time.time() < deadline:
    time.sleep(0.05)
out.write_text(json.dumps({
    "parent": sys.executable, "stdout_is_none": sys.stdout is None,
    "child_code": job.process.poll(), "child_command": job.process.args,
    "log": job.log_path.read_text(encoding="utf-8", errors="replace"),
}), encoding="utf-8")
"""


@pytest.mark.slow
@pytest.mark.skipif(os.name != "nt", reason="pythonw.exe is a Windows launcher")
def test_a_consoleless_parent_starts_processing_with_its_own_interpreter(tmp_path) -> None:
    """The shortcut runs pythonw; the processing child must run under it too."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = tmp_path / "parent.py"
    script.write_text(_CONSOLELESS_PARENT, encoding="utf-8")
    result = tmp_path / "result.json"
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
    startupinfo.hStdInput = startupinfo.hStdOutput = startupinfo.hStdError = 0
    subprocess.run(
        [str(pythonw), str(script), str(result)],
        env=_isolated_env(tmp_path), cwd=str(tmp_path), startupinfo=startupinfo, timeout=120,
    )
    report = json.loads(result.read_text(encoding="utf-8"))
    assert report["stdout_is_none"] is True
    assert Path(report["child_command"][0]).name.lower() == "pythonw.exe"
    assert report["child_code"] == 0
    assert "Verileri Hesapla" in report["log"], "the child's output reached its log"


# ------------------------------------------------------------- self-check
def _self_check(
    tmp_path: Path,
    *arguments: str,
    interpreter: str = sys.executable,
    capture: bool = True,
    **env: str,
):
    report = tmp_path / "self_check.json"
    startupinfo = None
    if not capture and os.name == "nt":
        # A shortcut starts pythonw with no standard handles at all. Left to
        # itself the child would inherit the test runner's, so they are set
        # explicitly to nothing - which is what Explorer does.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
        startupinfo.hStdInput = startupinfo.hStdOutput = startupinfo.hStdError = 0
    completed = subprocess.run(
        [interpreter, "-B", "-m", "kinecapture", "--self-check", "--report", str(report), *arguments],
        env=_isolated_env(tmp_path, **env),
        cwd=str(tmp_path),
        capture_output=capture,
        startupinfo=startupinfo,
        timeout=300,
    )
    payload = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    return completed, payload


@pytest.mark.slow
def test_the_self_check_passes_headless(tmp_path) -> None:
    completed, report = _self_check(tmp_path)
    assert report is not None, completed.stderr.decode("utf-8", "replace")
    failed = {k: v for k, v in report["checks"].items() if not v["ok"] and v.get("required", True)}
    assert completed.returncode == 0 and report["ok"], failed
    for name in ("config", "resources", "qt", "window", "user_dirs"):
        assert report["checks"][name]["ok"], (name, report["checks"][name])
    # It looked, and it wrote nothing into the user's real folders.
    assert not (tmp_path / "home" / "AppData" / "Local" / "KineCapture" / "identity.sqlite3").exists()


@pytest.mark.slow
@pytest.mark.skipif(os.name != "nt", reason="pythonw.exe is a Windows launcher")
def test_the_self_check_runs_without_a_console(tmp_path) -> None:
    """``pythonw.exe``: no console, ``sys.stdout`` and ``sys.stderr`` are None."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    assert pythonw.is_file()
    completed, report = _self_check(tmp_path, interpreter=str(pythonw), capture=False)
    assert report is not None, "nothing was written - the report is the only output pythonw has"
    assert report["console"] is False
    assert completed.returncode == 0, report
    log = tmp_path / "home" / "KineCapture" / "logs" / "kinecapture.log"
    assert log.is_file() and "self-check" in log.read_text(encoding="utf-8")


@pytest.mark.slow
def test_without_the_zed_sdk_the_application_still_opens(tmp_path) -> None:
    """``pyzed`` missing: everything but the camera works, and it says so."""
    blocker = tmp_path / "block"
    (blocker / "pyzed").mkdir(parents=True)
    # A package that fails to import, first on the path: the same outcome as
    # an SDK that was never installed.
    (blocker / "pyzed" / "__init__.py").write_text(
        "raise ImportError('ZED SDK yok (test)')\n", encoding="utf-8"
    )
    completed, report = _self_check(tmp_path, PYTHONPATH=str(blocker))
    assert report is not None
    assert report["checks"]["zed"]["ok"] is False
    assert "ZED" in report["checks"]["zed"]["detail"]
    assert report["checks"]["window"]["ok"]
    assert completed.returncode == 0, "no camera is not a broken installation"

    completed, report = _self_check(tmp_path, "--expect-zed-sdk", "5.4.1", PYTHONPATH=str(blocker))
    assert completed.returncode != 0
    assert report["checks"]["zed"]["required"] is True


# ------------------------------------------------------------- deletion
def test_a_project_delete_can_never_take_the_installation(tmp_path) -> None:
    from kinecapture.dataset.deletion import inspect_target

    import kinecapture

    prefix = Path(sys.prefix).resolve()
    package_home = Path(kinecapture.__file__).resolve().parent.parent
    for target in (prefix, prefix.parent, package_home):
        report = inspect_target(recorded_path=target, project_id="prj_x", dataset_root=tmp_path)
        assert not report.ok, target
        # A folder directly under a drive root (a release environment in
        # C:\KCBuild\env, say) is refused by the depth rule before the
        # installation rule is reached - found running this file against the
        # installed wheel, 24 September 2026. Either way it is a refusal.
        expected = {"delete_target_is_source_root"}
        if len(target.parts) <= 2:
            expected.add("delete_target_too_shallow")
        assert report.code in expected, (target, report.code)
