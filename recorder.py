"""Macro recording: builds a Step list from real mouse/keyboard actions,
fed from the shared raw-input event stream (see privileged_input.py).

Mouse position is never reconstructed from raw relative deltas -- that
would drift. Instead, whenever a click happens, or periodically between
events, the main thread is asked for the current pointer position (via
get_pointer_pos, e.g. Tk's winfo_pointerxy) and that's what gets recorded.

Recording stops on a dedicated key (F9) rather than a clickable UI button:
a click on a "Stop Recording" button is, at the raw-device level,
indistinguishable from any other click, and would corrupt the last
recorded step. The F9 press itself is filtered out of the result.
"""

import queue
import threading
import time

from evdev import ecodes as e

from macro import BUTTON_NAMES, Step

STOP_KEY_NAME = "KEY_F9"
POSITION_SAMPLE_INTERVAL = 0.075


class MacroRecorder:
    def __init__(self, source, get_pointer_pos):
        self._source = source
        self._get_pointer_pos = get_pointer_pos
        self._stop_flag = threading.Event()
        self._raw_events = queue.Queue()
        self._sample_thread = None
        self.steps = []
        self._last_step_time = None
        self._pending_press = {}

    def start(self):
        self._last_step_time = time.monotonic()
        self._stop_flag.clear()
        self.steps = []
        self._pending_press = {}
        self._source.subscribe(self._on_event)
        self._sample_thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._sample_thread.start()

    def _on_event(self, tag, code, value):
        if self._stop_flag.is_set():
            return
        self._raw_events.put((tag, code, value))

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
                item = self._raw_events.get_nowait()
                if item is None:
                    x, y = self._get_pointer_pos()
                    self.steps.append(Step(type="move", delay_ms=self._delay_since_last_step(), x=x, y=y))
                    continue
                self._handle_event(*item)
        except queue.Empty:
            pass
        return self._stop_flag.is_set()

    def _handle_event(self, tag, code, value):
        if code == e.ecodes[STOP_KEY_NAME]:
            if value == 1:
                self._stop_flag.set()
            return
        if tag == "mouse":
            if code not in BUTTON_NAMES:
                return
            button = BUTTON_NAMES[code]
            if value == 1:
                self._pending_press[button] = self._get_pointer_pos()
            elif value == 0 and button in self._pending_press:
                x, y = self._pending_press.pop(button)
                self.steps.append(
                    Step(type="click", delay_ms=self._delay_since_last_step(), x=x, y=y, button=button)
                )
            return
        if value == 1:
            self.steps.append(Step(type="key_down", delay_ms=self._delay_since_last_step(), key=e.KEY[code]))
        elif value == 0:
            self.steps.append(Step(type="key_up", delay_ms=self._delay_since_last_step(), key=e.KEY[code]))
        # value == 2 is autorepeat (key held down) -- not a distinct press/release

    def stop(self):
        self._stop_flag.set()

    def close(self):
        self._stop_flag.set()
        self._source.unsubscribe(self._on_event)
