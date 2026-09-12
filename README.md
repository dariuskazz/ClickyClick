# ClickyClick

> **Picking this up after a break?** Check [HANDOFF.md](HANDOFF.md) first — it tracks the current open issue and hard-won lessons from the last debugging session, so they don't get re-learned or undone by accident.

A configurable auto clicker and macro tool for Linux with runtime-selected X11 and Wayland backends. On Wayland, clicks and keystrokes are injected through the `RemoteDesktop` XDG portal using `libei`/EIS, and the global start/stop action uses the standard `GlobalShortcuts` portal. On X11, ClickyClick uses the X server through `pynput`. Normal operation never launches `pkexec`, never changes group membership, requires no logout, and asks for no administrator password.

This isn't the first thing that was tried. `uinput` (what `ydotool` uses) creates a real kernel-level virtual mouse, but KWin accepts synthetic *keyboard* input from it while silently dropping synthetic *pointer* input (clicks and motion) — confirmed by hand, not assumed. X11-style injection (`xdotool`/`pynput`, XTest) is blocked outright on Wayland. The portal's own plain D-Bus methods (`NotifyPointerButton` etc.) also silently no-op on this KWin version. Negotiating a proper portal session and injecting through the real EIS protocol is the one path that actually works.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

The first launch asks the compositor for permission (a real consent dialog) to inject pointer and keyboard input. Approval is remembered — a restore token is saved to `~/.config/clickyclick/restore_token` — so this normally only happens once.

**If no dialog appears and the app reports it couldn't set up a session:** some KDE versions (observed on `xdg-desktop-portal-kde` 6.7.4) have a permission-checking bug ("MegaAuth") that blocks the RemoteDesktop consent dialog before it can show. You'll see this in `journalctl --user` as:

```
MegaAuth: Failed to lookup permissions: "No entry for remote-desktop"
```

Run the included one-time fix:

```bash
./venv/bin/python fix_kde_portal_permission.py
```

This writes the same `kde-authorized`/`remote-desktop` permission-store entry that clicking "Allow" would (see [KDE's own docs on portal pre-authorization](https://develop.kde.org/docs/administration/portal-permissions/)) — the documented mechanism for pre-approving a portal request, used here because the bug prevents the interactive version of it from ever appearing. Harmless to run even if you don't hit the bug. If `xdg-desktop-portal-kde` was already running, restart it afterward so it picks up the change: `pkill -f xdg-desktop-portal-kde` (it restarts automatically on the next request).

## Run

```bash
./run.sh
```

Or symlink `clickyclick.desktop` into `~/.local/share/applications/` to launch it from your application menu — `ln -s "$(pwd)/clickyclick.desktop" ~/.local/share/applications/clickyclick.desktop`. Symlink rather than copy: a copy silently stops matching this file (name, icon, anything else) the moment either one changes, and KDE's app menu caches whatever it last read regardless — if you edit this file after installing it, refresh that cache with `kbuildsycoca6 --noincremental` (no logout needed).

## Features

- Interval in hours/minutes/seconds/milliseconds
- Left/right/middle button, single/double click
- Click at the current cursor position, or a fixed position (pick it with a 3-second countdown, or type coordinates)
- Repeat forever or a fixed number of times
- One Start/Stop button — the same action starts and stops (also `F6` or `Esc` while the window has focus)
- A configurable global hotkey that works regardless of which window has focus (see below)
- Record, save, and play back macros — sequences of clicks, moves, and keystrokes (see below)
- A separate configurable global macro hotkey: choose a saved macro, then use the same shortcut to start and stop it
- An always-visible **Stop All** button and in-window **Esc** emergency stop

## Global hotkey

Configured from **Settings → Hotkey**. On Wayland, the desktop's standard shortcut dialog assigns the key and the portal delivers it regardless of focus. On X11, ClickyClick captures and listens for the combination directly through the X server. Neither path needs administrator privileges.

## Macros

Configured from **Settings → Macros**. "Record New…" captures real mouse clicks, movement, and keystrokes as you perform them, until you press **F9** to stop (a dedicated key rather than a clickable button, since a click on a "Stop" button would itself be indistinguishable from any other recorded click). Recorded macros are saved as JSON under `~/.config/clickyclick/macros/` and can be played back with a configurable loop count.

System-wide recording is password-free on X11. On Wayland, the first recording asks to install a small persistent udev `uaccess` rule. This produces one administrator confirmation, applies immediately without logout, and gives the active local desktop session access to keyboard and mouse event devices. Later launches do not ask again. The application itself always remains unprivileged.

To control playback globally, select a saved macro in **Settings → Macros**, click **Use Selected Macro**, then click **Set Toggle Hotkey…**. Pressing that shortcut starts the chosen macro; pressing it again stops it. Macro playback can also be stopped from the Macros tab, with the main-window **Stop All** button, or with **Esc** while ClickyClick is focused.

Raw input access is powerful: any application running as your active desktop user can use the resulting device ACLs, not only ClickyClick. Remove `/etc/udev/rules.d/70-clickyclick-input.rules` as administrator and reload udev rules to revoke it.

## Compatibility

| Session | Clicking/playback | Global hotkey | Passive recording |
|---|---|---|---|
| X11 (any desktop/window manager) | Yes | Yes | Yes |
| Wayland with RemoteDesktop + GlobalShortcuts portals | Yes | Yes | Yes, after one-time input-access setup |
| Wayland missing either required portal | Capability is reported unavailable | Capability is reported unavailable | No |

KDE Plasma and current GNOME versions are the primary portal targets. COSMIC and other compositors become supported automatically as their portal backends expose the required standard output and shortcut interfaces; recording is independent of the compositor after one-time setup.
