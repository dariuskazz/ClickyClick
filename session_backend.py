"""Runtime selection for X11 and Wayland input backends."""

import os

from input_backend import InputBackend as PortalInputBackend


def session_type(environ=None):
    env = os.environ if environ is None else environ
    declared = env.get("XDG_SESSION_TYPE", "").lower()
    if declared in ("x11", "wayland"):
        return declared
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "unknown"


def create_output_backend():
    kind = session_type()
    if kind == "x11":
        from x11_backend import X11InputBackend

        return X11InputBackend()
    if kind == "wayland":
        return PortalInputBackend()
    raise RuntimeError("No X11 or Wayland graphical session was detected.")


def supports_raw_recording():
    return session_type() == "x11"


def create_input_source():
    if session_type() == "x11":
        from x11_backend import X11InputSource

        return X11InputSource()
    if session_type() == "wayland":
        from evdev_input import EvdevInputSource

        return EvdevInputSource()
    raise RuntimeError("No graphical session was detected for input recording.")
