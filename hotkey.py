"""In-app global hotkey: captured and detected entirely within this
process from a shared raw-input event stream (see privileged_input.py),
not registered with the compositor or KDE's shortcut system at all.

This is deliberately NOT the GlobalShortcuts XDG portal: that requires
KDE's own native "assign a key" dialog and registers a persistent,
app-identified shortcut that shows up in KDE's own Shortcuts settings and
outlives this process. Reading the keyboard directly instead means the
whole thing lives only in this process's memory for as long as it runs --
closing ClickyClick (or killing it) leaves nothing behind to revert, and
the key is assigned through this app's own UI, never KDE's.
"""

import threading

from evdev import ecodes as e

MODIFIER_GROUPS = {
    "Ctrl": {e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL},
    "Shift": {e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT},
    "Alt": {e.KEY_LEFTALT, e.KEY_RIGHTALT},
    "Super": {e.KEY_LEFTMETA, e.KEY_RIGHTMETA},
}
ALL_MODIFIER_CODES = set().union(*MODIFIER_GROUPS.values())
MODIFIER_ORDER = ("Ctrl", "Shift", "Alt", "Super")


class HotkeyError(RuntimeError):
    pass


def format_combo(modifiers, key_code):
    parts = [mod for mod in MODIFIER_ORDER if mod in modifiers]
    parts.append(e.KEY[key_code].replace("KEY_", ""))
    return "+".join(parts)


def _held_modifier_names(held_codes):
    return {mod for mod, codes in MODIFIER_GROUPS.items() if codes & held_codes}


class HotkeyCapture:
    """Records the next non-modifier key (plus whatever modifiers are held
    at that moment) pressed on a keyboard -- the "click here, then press
    your desired combo" step of the in-app hotkey picker."""

    def __init__(self, source):
        self._source = source
        self._held_modifiers = set()
        self.result = None
        self._stop_flag = threading.Event()

    def start(self):
        self._source.subscribe(self._on_event)

    def _on_event(self, tag, code, value):
        if self._stop_flag.is_set() or tag != "kbd":
            return
        if code in ALL_MODIFIER_CODES:
            if value == 1:
                self._held_modifiers.add(code)
            elif value == 0:
                self._held_modifiers.discard(code)
            return
        if value == 1:
            self.result = (frozenset(_held_modifier_names(self._held_modifiers)), code)
            self._stop_flag.set()

    def cancel(self):
        self.close()

    def close(self):
        self._stop_flag.set()
        self._source.unsubscribe(self._on_event)


class HotkeyListener:
    """Watches for one specific combination and calls on_triggered() (from
    the shared source's own background thread -- route it through a
    thread-safe queue, same as this app's other background work) whenever
    it's pressed. Purely in-process: stop()/close() (or the process simply
    exiting) is the entire teardown, since nothing was ever registered
    anywhere else."""

    def __init__(self, source, modifiers, key_code, on_triggered):
        self._source = source
        self._modifiers = frozenset(modifiers)
        self._key_code = key_code
        self._on_triggered = on_triggered
        self._held_modifiers = set()

    def start(self):
        self._source.subscribe(self._on_event)

    def _on_event(self, tag, code, value):
        if tag != "kbd":
            return
        if code in ALL_MODIFIER_CODES:
            if value == 1:
                self._held_modifiers.add(code)
            elif value == 0:
                self._held_modifiers.discard(code)
            return
        if code == self._key_code and value == 1:
            if _held_modifier_names(self._held_modifiers) == self._modifiers:
                self._on_triggered()

    def stop(self):
        self._source.unsubscribe(self._on_event)

    def close(self):
        self.stop()
