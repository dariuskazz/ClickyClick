"""Global start/stop shortcut through the standard desktop portal."""

import uuid

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"
REGISTRY_IFACE = "org.freedesktop.host.portal.Registry"
APP_ID = "clickyclick"


class GlobalShortcutsError(RuntimeError):
    pass


class PortalGlobalShortcuts:
    def __init__(self):
        self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        try:
            self._connection.call_sync(
                BUS, PATH, REGISTRY_IFACE, "Register",
                GLib.Variant("(sa{sv})", (APP_ID, {})), None,
                Gio.DBusCallFlags.NONE, 5000, None,
            )
        except GLib.Error:
            # Packaged/sandboxed processes already have an identity and reject
            # host registration. CreateSession below is the authoritative check.
            pass
        self._sender = self._connection.get_unique_name()[1:].replace(".", "_")
        self._session = None
        self._subscription = None
        self._callback = None

    def _request(self, method, signature, args, options, timeout=60):
        token = "cc_" + uuid.uuid4().hex
        request_path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{token}"
        options = dict(options)
        options["handle_token"] = GLib.Variant("s", token)
        loop = GLib.MainLoop()
        response = {}

        def receive(_conn, _sender, _path, _iface, _signal, params, *_args):
            response["value"] = params.unpack()
            loop.quit()

        subscription = self._connection.signal_subscribe(
            BUS, REQUEST_IFACE, "Response", request_path, None,
            Gio.DBusSignalFlags.NONE, receive, None,
        )
        timeout_id = 0
        try:
            self._connection.call_sync(
                BUS, PATH, IFACE, method,
                GLib.Variant(signature, (*args, options)), None,
                Gio.DBusCallFlags.NONE, timeout * 1000, None,
            )
            if not response:
                timeout_id = GLib.timeout_add_seconds(timeout, lambda: (loop.quit(), False)[1])
                loop.run()
        except GLib.Error as exc:
            raise GlobalShortcutsError(f"{method} failed: {exc.message}") from exc
        finally:
            if timeout_id:
                try:
                    GLib.source_remove(timeout_id)
                except GLib.Error:
                    pass
            self._connection.signal_unsubscribe(subscription)
        if not response:
            raise GlobalShortcutsError(f"{method} timed out")
        return response["value"]

    def bind(self, callback):
        code, results = self._request(
            "CreateSession", "(a{sv})", (),
            {"session_handle_token": GLib.Variant("s", "cc_session_" + uuid.uuid4().hex)},
        )
        if code != 0:
            raise GlobalShortcutsError("Global shortcut session was not approved")
        self._session = results["session_handle"]

        code, listed = self._request("ListShortcuts", "(oa{sv})", (self._session,), {})
        shortcuts = listed.get("shortcuts", []) if code == 0 else []
        required = {"toggle_clicks", "toggle_macro"}
        if not required.issubset({shortcut_id for shortcut_id, _opts in shortcuts}):
            requested = [("toggle_clicks", {
                "description": GLib.Variant("s", "Start or stop ClickyClick"),
                "preferred_trigger": GLib.Variant("s", "F6"),
            }), ("toggle_macro", {
                "description": GLib.Variant("s", "Start or stop the selected ClickyClick macro"),
                "preferred_trigger": GLib.Variant("s", "F8"),
            })]
            code, bound = self._request(
                "BindShortcuts", "(oa(sa{sv})sa{sv})", (self._session, requested, ""), {}
            )
            if code != 0:
                raise GlobalShortcutsError("Global shortcut was not approved")
            shortcuts = bound.get("shortcuts", [])

        self._callback = callback
        self._subscription = self._connection.signal_subscribe(
            BUS, IFACE, "Activated", self._session, None,
            Gio.DBusSignalFlags.NONE, self._activated, None,
        )
        return {shortcut_id: opts.get("trigger_description", "Assigned")
                for shortcut_id, opts in shortcuts}

    def _activated(self, _conn, _sender, _path, _iface, _signal, params, *_args):
        _session, shortcut_id, _timestamp, _options = params.unpack()
        if self._callback:
            self._callback(shortcut_id)

    @staticmethod
    def pump():
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def configure(self):
        if not self._session:
            raise GlobalShortcutsError("Global shortcut session is not active")
        self._connection.call_sync(
            BUS, PATH, IFACE, "ConfigureShortcuts",
            GLib.Variant("(osa{sv})", (self._session, "", {})), None,
            Gio.DBusCallFlags.NONE, -1, None,
        )

    def close(self):
        if self._subscription is not None:
            self._connection.signal_unsubscribe(self._subscription)
            self._subscription = None
        if self._session:
            try:
                self._connection.call_sync(
                    BUS, self._session, SESSION_IFACE, "Close", None, None,
                    Gio.DBusCallFlags.NONE, -1, None,
                )
            except GLib.Error:
                pass
            self._session = None
