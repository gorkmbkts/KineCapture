"""Bounded latest-frame worker. User callbacks and inference never run in grab()."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class LatestWorker:
    def __init__(self, process: Callable, *, fps: float = 15.0):
        self.process = process
        self.fps = fps
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pending = None
        self.result = None
        self.submitted = self.dropped = self.completed = 0
        self.error = ""
        self.last_ms = 0.0
        self._thread = threading.Thread(target=self._run, name="kinecapture-preview", daemon=True)
        self._thread.start()

    def offer(self, packet: Any) -> bool:
        if self._stop.is_set() or not self._lock.acquire(blocking=False):
            self.dropped += 1
            return False
        try:
            self.submitted += 1
            self.dropped += int(self._pending is not None)
            self._pending = packet
        finally:
            self._lock.release()
        self._wake.set()
        return True

    def _run(self):
        while not self._stop.is_set():
            if not self._wake.wait(0.1):
                continue
            with self._lock:
                packet, self._pending = self._pending, None
                self._wake.clear()
            if packet is None:
                continue
            started = time.perf_counter()
            try:
                result = self.process(packet)
                if not self._stop.is_set():
                    self.result = result
                self.completed += 1
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
            self.last_ms = (time.perf_counter() - started) * 1000
            self._stop.wait(max(0.0, 1 / self.fps - self.last_ms / 1000))

    def close(self, timeout: float = 2.0) -> bool:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout)
        return not self._thread.is_alive()
