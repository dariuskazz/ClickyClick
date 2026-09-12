"""Non-root evdev event source enabled by ClickyClick's one-time uaccess setup."""

import glob
import os
import threading
import time

import evdev
from evdev import ecodes as e


class InputAccessRequired(RuntimeError):
    pass


def _classify(device):
    keys = device.capabilities().get(e.EV_KEY, [])
    if e.BTN_LEFT in keys:
        return "mouse"
    if e.KEY_A in keys and e.KEY_ENTER in keys:
        return "kbd"
    return None


class EvdevInputSource:
    """Observe physical input without root after the system uaccess rule is installed."""

    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._devices = {}
        self._monitor = threading.Thread(target=self._monitor_devices, daemon=True)
        self._scan(require_device=True)
        self._monitor.start()

    def _scan(self, require_device=False):
        opened = 0
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in self._devices or not os.access(path, os.R_OK):
                continue
            try:
                device = evdev.InputDevice(path)
                tag = _classify(device)
            except OSError:
                continue
            if tag is None:
                device.close()
                continue
            self._devices[path] = device
            threading.Thread(target=self._stream, args=(path, device, tag), daemon=True).start()
            opened += 1
        if require_device and not self._devices:
            raise InputAccessRequired(
                "One-time input access setup is required for system-wide recording on Wayland."
            )
        return opened

    def _monitor_devices(self):
        while not self._stop.wait(1):
            self._scan()

    def _stream(self, path, device, tag):
        try:
            for event in device.read_loop():
                if self._stop.is_set():
                    return
                if event.type == e.EV_KEY:
                    self._emit(tag, event.code, event.value)
        except OSError:
            pass
        finally:
            self._devices.pop(path, None)
            try:
                device.close()
            except OSError:
                pass

    def _emit(self, tag, code, value):
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(tag, code, value)
            except Exception:
                continue

    def subscribe(self, callback):
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def close(self):
        self._stop.set()
        for device in list(self._devices.values()):
            try:
                device.close()
            except OSError:
                pass
        self._devices.clear()
