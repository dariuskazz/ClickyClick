#!/usr/bin/env python3
"""One-time workaround for a KDE portal bug that blocks ClickyClick entirely.

KDE's xdg-desktop-portal-kde (observed on 6.7.4) added a permission-checking
layer ("MegaAuth") that, for a non-Flatpak client's first RemoteDesktop
request, fails its own permission lookup instead of falling through to the
normal consent dialog -- so the dialog never appears and the request just
hangs. The portal's own log shows this as:

    MegaAuth: Failed to lookup permissions: "No entry for remote-desktop"

This script writes the permission entry directly -- the same effect
"Allow" in a working dialog would have. Run it once:

    ./venv/bin/python fix_kde_portal_permission.py

Then (re)launch ClickyClick. If your KDE version doesn't hit this bug,
running this script is harmless but unnecessary -- the normal consent
dialog will just work on its own.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS = "org.freedesktop.impl.portal.PermissionStore"
PATH = "/org/freedesktop/impl/portal/PermissionStore"
IFACE = "org.freedesktop.impl.portal.PermissionStore"
TABLE = "xdp-kde-remotedesktop"
RESOURCE_ID = "remote-desktop"


def main():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    try:
        reply = connection.call_sync(
            BUS,
            PATH,
            IFACE,
            "Lookup",
            GLib.Variant("(ss)", (TABLE, RESOURCE_ID)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        print(f"Entry already exists: {reply.unpack()}")
        print("Nothing to do.")
        return
    except GLib.Error as exc:
        print(f"No existing entry ({exc.message}) -- writing one now.")

    connection.call_sync(
        BUS,
        PATH,
        IFACE,
        "Set",
        GLib.Variant(
            "(sbsa{sas}v)",
            (TABLE, True, RESOURCE_ID, {"": ["yes"], "*": ["yes"]}, GLib.Variant("b", True)),
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    print("Permission entry written.")
    print(
        "If xdg-desktop-portal-kde was already running before this, restart it "
        "so it picks up the change:\n"
        "  pkill -f xdg-desktop-portal-kde\n"
        "(it restarts automatically on the next request)."
    )


if __name__ == "__main__":
    main()
