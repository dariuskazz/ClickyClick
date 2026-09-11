"""Shared root-privileged raw input event stream, backing both the global
hotkey (hotkey.py) and macro recording (recorder.py).

Reading raw /dev/input/event* devices needs root (there's no portal for
*observing* general input the way RemoteDesktop covers *injecting* it --
see input_backend.py). The previous approach put the user's own account in
the `input` group instead, but that needs a real logout to take effect for
any given process, no matter how it's granted -- a hard POSIX/PAM property
of group membership, not a bug. This instead runs a tiny, fixed-behavior
helper (input_reader_helper.py) as root via `pkexec` on first use, once per
app run, and streams events from it -- one password prompt at most per
launch, and never a logout, because this account's own credentials never
change at all.
"""

import subprocess
import sys
import threading
from pathlib import Path

HELPER_PATH = Path(__file__).resolve().parent / "input_reader_helper.py"


class PrivilegedInputError(RuntimeError):
    pass


class PrivilegedInputSource:
    """Construction blocks until the helper reports readiness (or fails) --
    that's the pkexec password prompt, if one is needed. Share one instance
    across every feature that needs raw input for the life of the app,
    rather than constructing a new one per use: each instance is its own
    pkexec prompt."""

    def __init__(self):
        try:
            self._proc = subprocess.Popen(
                ["pkexec", sys.executable, str(HELPER_PATH)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise PrivilegedInputError("pkexec isn't available on this system") from exc
        ready = self._proc.stdout.readline()
        if ready.strip() != "READY":
            stderr = self._proc.stderr.read().strip()
            raise PrivilegedInputError(
                "couldn't start the input-reading helper -- the pkexec "
                "prompt may have been cancelled"
                + (f": {stderr}" if stderr else "")
            )
        self._subscribers = []
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        for line in self._proc.stdout:
            parts = line.split()
            if len(parts) != 3 or parts[0] not in ("kbd", "mouse"):
                continue
            tag, code, value = parts[0], int(parts[1]), int(parts[2])
            with self._lock:
                subscribers = list(self._subscribers)
            for callback in subscribers:
                callback(tag, code, value)

    def subscribe(self, callback):
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._proc.terminate()
