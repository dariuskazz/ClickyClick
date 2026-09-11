"""In-app global hotkey: captured and detected entirely within this
process by reading a keyboard device directly via evdev, not registered
with the compositor or KDE's shortcut system at all.

This is deliberately NOT the GlobalShortcuts XDG portal: that requires
KDE's own native "assign a key" dialog and registers a persistent,
app-identified shortcut that shows up in KDE's own Shortcuts settings and
outlives this process. Reading the keyboard directly instead means the
whole thing lives only in this process's memory for as long as it runs --
closing ClickyClick (or killing it) leaves nothing behind to revert, and
the key is assigned through this app's own UI, never KDE's.

Needs the running user in the `input` group to read the raw device -- the
same one-time requirement already noted in the README for macro recording.
"""

import glob
import threading

import evdev
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


class HotkeyPermissionError(HotkeyError):
    """Specifically: no permission to read /dev/input/event*. Distinct from
    the base class so a caller can offer to fix this one automatically
    (add the user to the `input` group) rather than just explain it -- see
    ClickyClickApp._offer_input_group_fix."""


def list_keyboards():
    """Return evdev.InputDevice candidates classified as keyboards.
    Raises HotkeyPermissionError if the running user can't read
    /dev/input/event* -- see the README's `input`-group step.

    Deliberately globs for device paths directly rather than using
    evdev.list_devices(): that function silently drops any path the
    calling user can't access (it defaults to requiring both read *and*
    write, via a plain os.access() check) before returning -- so on a
    system missing the input-group setup, it always returns an empty
    list, and a PermissionError from InputDevice() never has a chance to
    happen at all. That turned "no permission" into a misleading "no
    keyboard found" in practice; opening every path ourselves is what
    actually lets the permission error surface."""
    keyboards = []
    paths = glob.glob("/dev/input/event*")
    for path in paths:
        try:
            dev = evdev.InputDevice(path)
        except PermissionError as exc:
            raise HotkeyPermissionError(
                "no permission to read input devices -- run "
                "'sudo usermod -aG input $USER', then log out and back in "
                f"({exc})"
            ) from exc
        except OSError:
            continue
        caps = dev.capabilities().get(e.EV_KEY, [])
        if e.KEY_A in caps and e.KEY_ENTER in caps:
            keyboards.append(dev)
        else:
            dev.close()
    return keyboards


def format_combo(modifiers, key_code):
    parts = [mod for mod in MODIFIER_ORDER if mod in modifiers]
    parts.append(e.KEY[key_code].replace("KEY_", ""))
    return "+".join(parts)


def _held_modifier_names(held_codes):
    return {mod for mod, codes in MODIFIER_GROUPS.items() if codes & held_codes}


class HotkeyCapture:
    """Records the next non-modifier key (plus whatever modifiers are held
    at that moment) pressed on a keyboard device -- the "click here, then
    press your desired combo" step of the in-app hotkey picker."""

    def __init__(self, keyboard_device):
        self._device = keyboard_device
        self._held_modifiers = set()
        self.result = None
        self._stop_flag = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        try:
            for event in self._device.read_loop():
                if self._stop_flag.is_set():
                    return
                if event.type != e.EV_KEY:
                    continue
                if event.code in ALL_MODIFIER_CODES:
                    if event.value == 1:
                        self._held_modifiers.add(event.code)
                    elif event.value == 0:
                        self._held_modifiers.discard(event.code)
                    continue
                if event.value == 1:
                    self.result = (frozenset(_held_modifier_names(self._held_modifiers)), event.code)
                    self._stop_flag.set()
                    return
        except OSError:
            return

    def cancel(self):
        self.close()

    def close(self):
        self._stop_flag.set()
        self._device.close()


class HotkeyListener:
    """Watches a keyboard device for one specific combination and calls
    on_triggered() (from its own background thread -- route it through a
    thread-safe queue, same as this app's other background work) whenever
    it's pressed. Purely in-process: stop()/close() (or the process simply
    exiting) is the entire teardown, since nothing was ever registered
    anywhere else."""

    def __init__(self, keyboard_device, modifiers, key_code, on_triggered):
        self._device = keyboard_device
        self._modifiers = frozenset(modifiers)
        self._key_code = key_code
        self._on_triggered = on_triggered
        self._held_modifiers = set()
        self._stop_flag = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        try:
            for event in self._device.read_loop():
                if self._stop_flag.is_set():
                    return
                if event.type != e.EV_KEY:
                    continue
                if event.code in ALL_MODIFIER_CODES:
                    if event.value == 1:
                        self._held_modifiers.add(event.code)
                    elif event.value == 0:
                        self._held_modifiers.discard(event.code)
                    continue
                if event.code == self._key_code and event.value == 1:
                    if _held_modifier_names(self._held_modifiers) == self._modifiers:
                        self._on_triggered()
        except OSError:
            return

    def stop(self):
        self._stop_flag.set()

    def close(self):
        self.stop()
        self._device.close()
