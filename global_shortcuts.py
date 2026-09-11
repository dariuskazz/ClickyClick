"""Global (works-while-unfocused) hotkey support via the GlobalShortcuts XDG
portal.

Unlike a Tkinter key binding, a shortcut bound through this portal is
delivered by the compositor regardless of which window has focus -- the
actual fix for "the stop key doesn't do anything while some other window is
focused", which no in-app-only binding can solve.

The user assigns the physical key through KDE's own native configuration
dialog (shown once, the first time `bind()` is called, or again if
`reconfigure()` is invoked) rather than a custom key-recorder built into
this app -- reusing the same infrastructure KDE's own global shortcuts use,
so it's just as reliable and rebindable from one place.

Delivery of the `Activated` signal requires the GLib main context to be
iterated periodically -- this module does not do that itself, since this
app's event loop is Tkinter's, not GLib's. Call `pump()` on a short
`root.after()` interval (alongside whatever else already polls on a timer)
to actually receive activations.
"""

import uuid

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

_BUS = "org.freedesktop.portal.Desktop"
_PATH = "/org/freedesktop/portal/desktop"
_IFACE = "org.freedesktop.portal.GlobalShortcuts"
_SESSION_IFACE = "org.freedesktop.portal.Session"
_REQUEST_IFACE = "org.freedesktop.portal.Request"

DEFAULT_TIMEOUT = 60.0
"""Generous, since BindShortcuts waits on a human seeing and answering
KDE's own assign-a-key dialog."""


class GlobalShortcutsError(RuntimeError):
    pass


class GlobalShortcuts:
    def __init__(self):
        self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._sender_token = self._connection.get_unique_name()[1:].replace(".", "_")
        self._session_handle = None
        self._on_activated = None
        self._activated_sub = None

    # ---------- low-level request/response plumbing ----------
    def _request(self, method, signature, args, options, timeout=DEFAULT_TIMEOUT):
        token = "cc_" + uuid.uuid4().hex[:8]
        request_path = f"/org/freedesktop/portal/desktop/request/{self._sender_token}/{token}"
        opts = dict(options)
        opts["handle_token"] = GLib.Variant("s", token)

        loop = GLib.MainLoop()
        result = {}

        def on_response(_c, _s, _p, _i, _sig, params, *_a):
            if result:
                return
            result["code"], result["results"] = params.unpack()
            loop.quit()

        sub = self._connection.signal_subscribe(
            _BUS, _REQUEST_IFACE, "Response", request_path, None,
            Gio.DBusSignalFlags.NONE, on_response, None,
        )
        try:
            self._connection.call_sync(
                _BUS, _PATH, _IFACE, method,
                GLib.Variant(signature, (*args, opts)),
                None, Gio.DBusCallFlags.NONE, int(timeout * 1000), None,
            )
            if not result:
                timed_out = []
                timeout_id = GLib.timeout_add(
                    int(timeout * 1000),
                    lambda: (timed_out.append(True), loop.quit(), False)[-1],
                )
                loop.run()
                if not timed_out:
                    GLib.source_remove(timeout_id)
        except GLib.Error as exc:
            raise GlobalShortcutsError(f"{method} failed: {exc}") from exc
        finally:
            self._connection.signal_unsubscribe(sub)
        if not result:
            raise GlobalShortcutsError(f"{method} did not respond within {timeout:g}s")
        return result["code"], result["results"]

    # ---------- public API ----------
    def bind(self, shortcuts, on_activated, timeout=DEFAULT_TIMEOUT):
        """shortcuts: list of (shortcut_id, description).
        on_activated: callable(shortcut_id) invoked (on whatever thread calls
        pump()) whenever the user presses their assigned key for one of them.

        Returns {shortcut_id: trigger_description} for whatever got bound --
        reuses an existing session's shortcuts from a previous run of this
        app if there is one, only showing KDE's assign-a-key dialog when
        nothing is bound yet.
        """
        code, results = self._request(
            "CreateSession", "(a{sv})", (),
            {"session_handle_token": GLib.Variant("s", "cc_sess_" + uuid.uuid4().hex[:8])},
            timeout=timeout,
        )
        if code != 0:
            raise GlobalShortcutsError("CreateSession was not approved")
        self._session_handle = results["session_handle"]

        code, results = self._request(
            "ListShortcuts", "(oa{sv})", (self._session_handle,), {}, timeout=timeout
        )
        existing = results.get("shortcuts", []) if code == 0 else []
        if not existing:
            packed = [
                (shortcut_id, {"description": GLib.Variant("s", description)})
                for shortcut_id, description in shortcuts
            ]
            code, results = self._request(
                "BindShortcuts", "(oa(sa{sv})sa{sv})",
                (self._session_handle, packed, ""), {},
                timeout=timeout,
            )
            if code != 0:
                raise GlobalShortcutsError("BindShortcuts was not approved")
            existing = results.get("shortcuts", [])

        self._on_activated = on_activated
        self._activated_sub = self._connection.signal_subscribe(
            _BUS, _IFACE, "Activated", self._session_handle, None,
            Gio.DBusSignalFlags.NONE, self._handle_activated, None,
        )
        return {shortcut_id: opts.get("trigger_description", "(unassigned)") for shortcut_id, opts in existing}

    def _handle_activated(self, _c, _s, _p, _i, _sig, params, *_a):
        _session_handle, shortcut_id, _timestamp, _options = params.unpack()
        if self._on_activated is not None:
            self._on_activated(shortcut_id)

    def list_shortcuts(self, timeout=DEFAULT_TIMEOUT):
        """Re-query the session's current bindings -- e.g. after reconfigure()
        to pick up whatever the user just chose (ConfigureShortcuts has no
        completion signal of its own to wait on instead)."""
        if self._session_handle is None:
            raise GlobalShortcutsError("not bound yet")
        code, results = self._request(
            "ListShortcuts", "(oa{sv})", (self._session_handle,), {}, timeout=timeout
        )
        if code != 0:
            raise GlobalShortcutsError("ListShortcuts failed")
        return {shortcut_id: opts.get("trigger_description", "(unassigned)") for shortcut_id, opts in results.get("shortcuts", [])}

    def reconfigure(self, timeout=DEFAULT_TIMEOUT):
        """Show KDE's native shortcut-configuration UI for this session."""
        if self._session_handle is None:
            raise GlobalShortcutsError("not bound yet")
        try:
            self._connection.call_sync(
                _BUS, _PATH, _IFACE, "ConfigureShortcuts",
                GLib.Variant("(osa{sv})", (self._session_handle, "", {})),
                None, Gio.DBusCallFlags.NONE, int(timeout * 1000), None,
            )
        except GLib.Error as exc:
            raise GlobalShortcutsError(f"ConfigureShortcuts failed: {exc}") from exc

    @staticmethod
    def pump():
        """Process any pending GLib/D-Bus work (signal delivery included).

        Call periodically (e.g. from a root.after() timer) for as long as
        Activated events need to be received -- GLib's main context is
        never otherwise iterated by an app whose event loop is Tkinter's.
        """
        context = GLib.MainContext.default()
        while context.iteration(False):
            pass

    def close(self):
        if self._activated_sub is not None:
            self._connection.signal_unsubscribe(self._activated_sub)
            self._activated_sub = None
        if self._session_handle is not None:
            try:
                self._connection.call_sync(
                    _BUS, self._session_handle, _SESSION_IFACE, "Close",
                    None, None, Gio.DBusCallFlags.NONE, -1, None,
                )
            except GLib.Error:
                pass
            self._session_handle = None
