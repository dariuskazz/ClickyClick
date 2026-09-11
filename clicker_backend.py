"""Virtual-pointer click backend for Linux, built on uinput (kernel-level input).

Works on both X11 and Wayland because it injects events below the display
server, the same way a real mouse would. XTest-style injection (what tools
like xdotool/pynput use) is blocked by modern Wayland compositors, so this
is the mechanism that actually works here.

Requires the running user to have read/write access to /dev/uinput, AND to
be a member of the `input` group so the compositor can read the resulting
/dev/input/eventN device node. See BackendUnavailable / the diagnostic
check in autoclicker.py for the runtime check.
"""

import time

from evdev import UInput, AbsInfo, ecodes as e

DOUBLE_CLICK_GAP = 0.09
PRESS_RELEASE_GAP = 0.012

BUTTONS = {
    "left": e.BTN_LEFT,
    "right": e.BTN_RIGHT,
    "middle": e.BTN_MIDDLE,
}


class BackendUnavailable(RuntimeError):
    pass


class ClickBackend:
    def __init__(self, screen_width, screen_height):
        capabilities = {
            e.EV_KEY: list(BUTTONS.values()),
            e.EV_REL: [e.REL_X, e.REL_Y],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=max(screen_width - 1, 1), fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=max(screen_height - 1, 1), fuzz=0, flat=0, resolution=0)),
            ],
        }
        try:
            self._ui = UInput(capabilities, name="auto-clicker-virtual-pointer")
        except (PermissionError, OSError) as exc:
            raise BackendUnavailable(str(exc)) from exc
        # Give udev/libinput a moment to enumerate the new device before use.
        time.sleep(0.3)

    def move_absolute(self, x, y):
        self._ui.write(e.EV_ABS, e.ABS_X, int(x))
        self._ui.write(e.EV_ABS, e.ABS_Y, int(y))
        self._ui.syn()

    def move_relative(self, dx, dy):
        if dx:
            self._ui.write(e.EV_REL, e.REL_X, int(dx))
        if dy:
            self._ui.write(e.EV_REL, e.REL_Y, int(dy))
        self._ui.syn()

    def click(self, button="left", double=False):
        code = BUTTONS.get(button, e.BTN_LEFT)
        self._press(code)
        if double:
            time.sleep(DOUBLE_CLICK_GAP)
            self._press(code)

    def _press(self, code):
        self._ui.write(e.EV_KEY, code, 1)
        self._ui.syn()
        time.sleep(PRESS_RELEASE_GAP)
        self._ui.write(e.EV_KEY, code, 0)
        self._ui.syn()

    def close(self):
        self._ui.close()
