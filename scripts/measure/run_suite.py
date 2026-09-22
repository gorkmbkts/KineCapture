"""The whole suite, file by file - the project's own rule, because the
one-process run does not finish."""
import json, subprocess, sys, time
from pathlib import Path

REPO = Path(r"C:\Users\gorke\Desktop\KineCapture")
PY_EXE = r"C:\Users\gorke\anaconda3\envs\KineSynth\python.exe"
OUT = Path(sys.argv[1])
OUT.parent.mkdir(parents=True, exist_ok=True)
LOGS = OUT.parent / f"{OUT.stem}_logs"
LOGS.mkdir(parents=True, exist_ok=True)
files = sorted(p.name for p in (REPO / "tests").glob("test_*.py"))
results, started = [], time.perf_counter()
for index, name in enumerate(files, start=1):
    begin = time.perf_counter()
    proc = subprocess.run(
        [PY_EXE, "-m", "pytest", f"tests/{name}", "-q", "-o", "addopts=", "-ra"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    log = LOGS / f"{Path(name).stem}.txt"
    log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    tail = [l for l in (proc.stdout or "").splitlines() if l.strip()][-1:] or [""]
    row = {
        "file": name, "code": proc.returncode,
        "seconds": round(time.perf_counter() - begin, 1), "tail": tail[-1][:200],
        "log": str(log),
    }
    results.append(row)
    print(f"[{index}/{len(files)}] {name:44} {'OK ' if proc.returncode == 0 else 'FAIL'} "
          f"{row['seconds']:6.1f}s  {row['tail'][:70]}", flush=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
green = sum(1 for r in results if r["code"] == 0)
print(f"\n{green}/{len(results)} files green in {round(time.perf_counter()-started)}s")
for r in results:
    if r["code"]:
        print("  FAILED", r["file"], "|", r["tail"])
sys.exit(0 if green == len(results) else 1)
