"""Virtual pointer + keyboard backend for Linux, built on uinput (kernel-level input).

Works on both X11 and Wayland because it injects events below the display
server, the same way real hardware would. XTest-style injection (what tools
like xdotool/pynput use) is blocked by modern Wayland compositors, so this
is the mechanism that actually works here.

Requires the running user to have read/write access to /dev/uinput, AND to
be a member of the `input` group so the compositor can read the resulting
/dev/input/eventN device nodes (both the pointer and the keyboard). See
BackendUnavailable / the diagnostic check in clickyclick.py for the runtime
check.
"""

import time

from evdev import UInput, AbsInfo, ecodes as e

DOUBLE_CLICK_GAP = 0.09
PRESS_RELEASE_GAP = 0.012
KEY_HOLD_GAP = 0.02

BUTTONS = {
    "left": e.BTN_LEFT,
    "right": e.BTN_RIGHT,
    "middle": e.BTN_MIDDLE,
}

# All KEY_* codes, so the virtual keyboard can emit anything a real one
# could. Excludes KEY_MAX/KEY_CNT: those are kernel header boundary
# constants that leak into evdev's code->name table, not real keys — trying
# to register KEY_CNT (one past the valid array bound) makes uinput reject
# the whole device with EINVAL.
_NOT_REAL_KEYS = {"KEY_MAX", "KEY_CNT"}
ALL_KEY_CODES = [code for code, name in e.KEY.items() if name not in _NOT_REAL_KEYS]


class BackendUnavailable(RuntimeError):
    pass


class InputBackend:
    def __init__(self, screen_width, screen_height):
        pointer_capabilities = {
            e.EV_KEY: list(BUTTONS.values()),
            e.EV_REL: [e.REL_X, e.REL_Y],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=max(screen_width - 1, 1), fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=max(screen_height - 1, 1), fuzz=0, flat=0, resolution=0)),
            ],
        }
        keyboard_capabilities = {
            e.EV_KEY: ALL_KEY_CODES,
        }
        try:
            self._pointer = UInput(pointer_capabilities, name="clickyclick-virtual-pointer")
            self._keyboard = UInput(keyboard_capabilities, name="clickyclick-virtual-keyboard")
        except (PermissionError, OSError) as exc:
            raise BackendUnavailable(str(exc)) from exc
        # Give udev/libinput a moment to enumerate the new devices before use.
        time.sleep(0.3)

    # ---------- pointer ----------
    def move_absolute(self, x, y):
        self._pointer.write(e.EV_ABS, e.ABS_X, int(x))
        self._pointer.write(e.EV_ABS, e.ABS_Y, int(y))
        self._pointer.syn()

    def move_relative(self, dx, dy):
        if dx:
            self._pointer.write(e.EV_REL, e.REL_X, int(dx))
        if dy:
            self._pointer.write(e.EV_REL, e.REL_Y, int(dy))
        self._pointer.syn()

    def click(self, button="left", double=False):
        code = BUTTONS.get(button, e.BTN_LEFT)
        self._press(code)
        if double:
            time.sleep(DOUBLE_CLICK_GAP)
            self._press(code)

    def _press(self, code):
        self._pointer.write(e.EV_KEY, code, 1)
        self._pointer.syn()
        time.sleep(PRESS_RELEASE_GAP)
        self._pointer.write(e.EV_KEY, code, 0)
        self._pointer.syn()

    # ---------- keyboard ----------
    def key_down(self, keycode):
        self._keyboard.write(e.EV_KEY, keycode, 1)
        self._keyboard.syn()

    def key_up(self, keycode):
        self._keyboard.write(e.EV_KEY, keycode, 0)
        self._keyboard.syn()

    def key_tap(self, keycode, hold=KEY_HOLD_GAP):
        self.key_down(keycode)
        time.sleep(hold)
        self.key_up(keycode)

    def close(self):
        self._pointer.close()
        self._keyboard.close()
