"""Raw mouse/keyboard capture for building a macro by recording real
actions, reading hardware input devices directly via evdev.

This is the read counterpart to input_backend.py's write side, and
deliberately uses a different mechanism: the portal only grants *injecting*
input (RemoteDesktop), not *observing* it, and the portal built for
observing input (InputCapture) is edge-triggered/exclusive-diversion only
-- built for "move the pointer to a screen edge to switch to another
machine", not "record everything for a while". Reading real devices is the
one way to get this, and it needs the running user in the `input` group
(the same one-time system requirement noted in the README) -- independent
of playback, which goes through the portal instead.

Recording stops on a dedicated key (F9) rather than a clickable UI button:
a click on a "Stop Recording" button is, at the raw-device level,
indistinguishable from any other click, and would corrupt the last
recorded step. The F9 press itself is filtered out of the result.
"""

import glob
import queue
import threading
import time

import evdev
from evdev import ecodes as e

from macro import BUTTON_NAMES, Step

STOP_KEY_NAME = "KEY_F9"
POSITION_SAMPLE_INTERVAL = 0.075


class RecorderError(RuntimeError):
    pass


def list_candidate_devices():
    """Return (mice, keyboards): evdev.InputDevice lists, classified by
    capability. Raises RecorderError (wrapping the PermissionError) if the
    running user can't read /dev/input/event* -- see the README's
    `input`-group setup step.

    Deliberately globs for device paths directly rather than using
    evdev.list_devices(): that function silently drops any path the
    calling user can't access (it defaults to requiring both read *and*
    write, via a plain os.access() check) before returning -- so on a
    system missing the input-group setup, it always returns an empty
    list, and a PermissionError from InputDevice() never has a chance to
    happen at all. That turned "no permission" into a misleading "no mouse
    or keyboard found" in practice; opening every path ourselves is what
    actually lets the permission error surface."""
    mice, keyboards = [], []
    paths = glob.glob("/dev/input/event*")
    for path in paths:
        try:
            dev = evdev.InputDevice(path)
        except PermissionError as exc:
            raise RecorderError(
                "no permission to read input devices -- run "
                "'sudo usermod -aG input $USER', then log out and back in "
                f"({exc})"
            ) from exc
        except OSError:
            continue
        caps = dev.capabilities().get(e.EV_KEY, [])
        if e.BTN_LEFT in caps:
            mice.append(dev)
        elif e.KEY_A in caps and e.KEY_ENTER in caps:
            keyboards.append(dev)
        else:
            dev.close()
    return mice, keyboards


class MacroRecorder:
    def __init__(self, mouse_device, keyboard_device, get_pointer_pos):
        self._mouse = mouse_device
        self._keyboard = keyboard_device
        self._get_pointer_pos = get_pointer_pos
        self._stop_flag = threading.Event()
        self._raw_events = queue.Queue()
        self._threads = []
        self.steps = []
        self._last_step_time = None
        self._pending_press = {}

    def start(self):
        self._last_step_time = time.monotonic()
        self._stop_flag.clear()
        self.steps = []
        self._pending_press = {}
        self._threads = [
            threading.Thread(target=self._read_loop, args=(self._mouse,), daemon=True),
            threading.Thread(target=self._read_loop, args=(self._keyboard,), daemon=True),
            threading.Thread(target=self._sample_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def _read_loop(self, device):
        try:
            for event in device.read_loop():
                if self._stop_flag.is_set():
                    return
                self._raw_events.put(event)
        except OSError:
            return

    def _sample_loop(self):
        while not self._stop_flag.is_set():
            time.sleep(POSITION_SAMPLE_INTERVAL)
            self._raw_events.put(None)  # sentinel: "sample the pointer now"

    def _delay_since_last_step(self):
        now = time.monotonic()
        delay_ms = max(0, int((now - self._last_step_time) * 1000))
        self._last_step_time = now
        return delay_ms

    def poll(self):
        """Drain queued raw events into self.steps. Call periodically from
        the main thread -- get_pointer_pos must run there."""
        try:
            while True:
                event = self._raw_events.get_nowait()
                if event is None:
                    x, y = self._get_pointer_pos()
                    self.steps.append(Step(type="move", delay_ms=self._delay_since_last_step(), x=x, y=y))
                    continue
                self._handle_event(event)
        except queue.Empty:
            pass
        return self._stop_flag.is_set()

    def _handle_event(self, event):
        if event.type != e.EV_KEY:
            return
        if event.code == e.ecodes[STOP_KEY_NAME]:
            if event.value == 1:
                self._stop_flag.set()
            return
        if event.code in BUTTON_NAMES:
            button = BUTTON_NAMES[event.code]
            if event.value == 1:
                self._pending_press[button] = self._get_pointer_pos()
            elif event.value == 0 and button in self._pending_press:
                x, y = self._pending_press.pop(button)
                self.steps.append(
                    Step(type="click", delay_ms=self._delay_since_last_step(), x=x, y=y, button=button)
                )
            return
        if event.value == 1:
            self.steps.append(Step(type="key_down", delay_ms=self._delay_since_last_step(), key=e.KEY[event.code]))
        elif event.value == 0:
            self.steps.append(Step(type="key_up", delay_ms=self._delay_since_last_step(), key=e.KEY[event.code]))
        # value == 2 is autorepeat (key held down) -- not a distinct press/release

    def stop(self):
        self._stop_flag.set()

    def close(self):
        self._stop_flag.set()
        self._mouse.close()
        self._keyboard.close()
