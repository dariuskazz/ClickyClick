"""Pointer + keyboard input backend for Linux Wayland, via the RemoteDesktop
XDG portal and the real EIS protocol (``libei``) -- not ``/dev/uinput``.

Why not uinput: confirmed by hand on this system that KWin accepts synthetic
*keyboard* input from a uinput device but silently drops synthetic *pointer*
input (both clicks and motion) from one, even with correct permissions --
likely a deliberate Wayland security boundary around cursor control, since a
fake pointer can click "Yes" on a consent dialog in a way a fake keyboard
can't as directly. The portal's own plain D-Bus methods
(``NotifyPointerButton`` etc.) were tried too and also silently no-op on
this KWin version. Negotiating the portal session properly and then
injecting through the real EIS protocol is the one path that actually
reaches the compositor's input pipeline.

The first run raises a real consent dialog (or, if this exact system has hit
the KDE "MegaAuth" permission-lookup bug -- see the project README -- may
need a one-time manual fix first). Approval is remembered via a restore
token saved to disk, so normal use after that is silent.
"""

import select
import time
from pathlib import Path

from evdev import ecodes as e
from libei import ei
from libei.portal import DeviceType, PersistMode, PortalError, RemoteDesktopSession

RESTORE_TOKEN_PATH = Path.home() / ".config" / "clickyclick" / "restore_token"

BUTTONS = {
    "left": e.BTN_LEFT,
    "right": e.BTN_RIGHT,
    "middle": e.BTN_MIDDLE,
}

DOUBLE_CLICK_GAP = 0.09
PRESS_RELEASE_GAP = 0.02
DEVICE_WAIT_TIMEOUT = 10.0
DEVICE_SETTLE_SECONDS = 1.5
"""How long to keep draining EIS events after both required devices have
resumed. The compositor resumes multiple devices (absolute pointer, relative
pointer, keyboard) as a burst; stopping the instant the two this backend
needs are in hand -- while the burst is still arriving -- has been observed
to leave the connection in a state where every subsequent event is silently
dropped. Draining a little longer avoids that."""


class BackendUnavailable(RuntimeError):
    pass


class InputBackend:
    def __init__(self):
        restore_token = self._load_restore_token()
        try:
            self._session = RemoteDesktopSession.negotiate(
                devices=DeviceType.POINTER | DeviceType.KEYBOARD,
                persist_mode=PersistMode.UNTIL_REVOKED,
                restore_token=restore_token,
            )
        except PortalError as exc:
            raise BackendUnavailable(str(exc)) from exc
        self._save_restore_token(self._session.restore_token)

        self._sender = ei.Sender.create_for_fd(self._session.eis_fd, name="clickyclick")
        self._pointer = None
        self._keyboard = None
        try:
            self._wait_for_devices()
        except Exception as exc:
            self.close()
            raise BackendUnavailable(f"EIS device negotiation failed: {exc}") from exc
        if self._pointer is None or self._keyboard is None:
            self.close()
            raise BackendUnavailable(
                "compositor did not resume an absolute-pointer and keyboard EIS device"
            )
        self.regions = self._pointer.regions

    # ---------- setup ----------
    @staticmethod
    def _load_restore_token():
        try:
            token = RESTORE_TOKEN_PATH.read_text().strip()
        except OSError:
            return None
        return token or None

    @staticmethod
    def _save_restore_token(token):
        if not token:
            return
        RESTORE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESTORE_TOKEN_PATH.write_text(token)

    def _wait_for_devices(self):
        deadline = time.monotonic() + DEVICE_WAIT_TIMEOUT
        settle_deadline = None
        while time.monotonic() < deadline:
            if self._pointer and self._keyboard and settle_deadline is None:
                settle_deadline = time.monotonic() + DEVICE_SETTLE_SECONDS
            if settle_deadline is not None and time.monotonic() > settle_deadline:
                return
            select.select([self._sender.fd], [], [], 1)
            self._sender.dispatch()
            for event in self._sender.events:
                if event.event_type == ei.EventType.SEAT_ADDED:
                    event.seat.bind(
                        (
                            ei.DeviceCapability.POINTER_ABSOLUTE,
                            ei.DeviceCapability.BUTTON,
                            ei.DeviceCapability.KEYBOARD,
                        )
                    )
                elif event.event_type == ei.EventType.DEVICE_RESUMED:
                    caps = event.device.capabilities
                    if ei.DeviceCapability.POINTER_ABSOLUTE in caps and self._pointer is None:
                        self._pointer = event.device
                    elif ei.DeviceCapability.KEYBOARD in caps and self._keyboard is None:
                        self._keyboard = event.device

    # ---------- pointer ----------
    def move_absolute(self, x, y):
        self._pointer.start_emulating()
        self._pointer.pointer_motion_absolute(x, y).frame()
        self._pointer.stop_emulating()

    def click(self, button="left", double=False):
        code = BUTTONS.get(button, BUTTONS["left"])
        self._press(code)
        if double:
            time.sleep(DOUBLE_CLICK_GAP)
            self._press(code)

    def _press(self, code):
        self._pointer.start_emulating()
        self._pointer.button(code, True).frame()
        time.sleep(PRESS_RELEASE_GAP)
        self._pointer.button(code, False).frame()
        self._pointer.stop_emulating()

    # ---------- keyboard ----------
    def key_down(self, keycode):
        self._keyboard.start_emulating()
        self._keyboard.keyboard_key(keycode, True).frame()

    def key_up(self, keycode):
        self._keyboard.keyboard_key(keycode, False).frame()
        self._keyboard.stop_emulating()

    def key_tap(self, keycode, hold=PRESS_RELEASE_GAP):
        self.key_down(keycode)
        time.sleep(hold)
        self.key_up(keycode)

    # ---------- teardown ----------
    def close(self):
        if self._sender is not None:
            try:
                self._sender.disconnect()
            except Exception:
                pass
            self._sender = None
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
