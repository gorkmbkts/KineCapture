"""Explicit, checksum-verified download of small preview model data (no installs)."""
from pathlib import Path
import argparse
import hashlib
import os
import urllib.request

COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "kinecapture" / "models"

def fetch(directory=DEFAULT_MODEL_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("person_detection_mediapipe", "pose_estimation_mediapipe"):
        file = name + "_2023mar.onnx"
        path = f"models/{name}/{file}"
        pointer = urllib.request.urlopen(f"https://raw.githubusercontent.com/opencv/opencv_zoo/{COMMIT}/{path}", timeout=30).read().decode()
        checksum = pointer.split("oid sha256:")[1].split()[0]
        size = int(pointer.split("size ")[1].split()[0])
        target = directory / file
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == checksum:
            print(file, "already verified")
            continue
        temporary = target.with_suffix(".download")
        with urllib.request.urlopen(f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{COMMIT}/{path}", timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size != size or hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Model checksum mismatch: {file}")
        os.replace(temporary, target)
        print(file, size, checksum)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_MODEL_DIR)
    fetch(parser.parse_args().directory)
