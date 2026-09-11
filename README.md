# ClickyClick

A configurable auto clicker and macro tool for Linux, built for Wayland (KDE Plasma). Clicks and keystrokes are injected through the `RemoteDesktop` XDG portal using the real `libei`/EIS protocol — the same mechanism screen-sharing and remote-control tools use, and the compositor's actual sanctioned channel for this on Wayland. The global start/stop hotkey goes through the separate `GlobalShortcuts` portal, so it works via KDE's own native shortcut system rather than a hand-rolled key grab.

This isn't the first thing that was tried. `uinput` (what `ydotool` uses) creates a real kernel-level virtual mouse, but KWin accepts synthetic *keyboard* input from it while silently dropping synthetic *pointer* input (clicks and motion) — confirmed by hand, not assumed. X11-style injection (`xdotool`/`pynput`, XTest) is blocked outright on Wayland. The portal's own plain D-Bus methods (`NotifyPointerButton` etc.) also silently no-op on this KWin version. Negotiating a proper portal session and injecting through the real EIS protocol is the one path that actually works.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

The first launch asks the compositor for permission (a real consent dialog) to inject pointer and keyboard input, and a separate one to register the global hotkey. Approval is remembered — a restore token is saved to `~/.config/clickyclick/restore_token` for the click/keyboard permission — so this normally only happens once.

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

Or install `clickyclick.desktop` to `~/.local/share/applications/` to launch it from your application menu.

## Features

- Interval in hours/minutes/seconds/milliseconds
- Left/right/middle button, single/double click
- Click at the current cursor position, or a fixed position (pick it with a 3-second countdown, or type coordinates)
- Repeat forever or a fixed number of times
- One Start/Stop button — the same action starts and stops (also `F6` or `Esc` while the window has focus)
- A configurable global hotkey that works regardless of which window has focus (see below)
- Record, save, and play back macros — sequences of clicks, moves, and keystrokes (see below)

## Global hotkey

Configured from **Settings → Hotkey**. Clicking "Change Hotkey…" opens KDE's own native shortcut-assignment dialog (via the `GlobalShortcuts` portal) rather than a custom key-recorder built into this app — the same infrastructure KDE's own global shortcuts use, so it's reliable and rebindable from one place. Once assigned, that key toggles Start/Stop from anywhere, including while a game or another window has focus.

## Macros

Configured from **Settings → Macros**. "Record New…" captures real mouse clicks, movement, and keystrokes as you perform them, until you press **F9** to stop (a dedicated key rather than a clickable button, since a click on a "Stop" button would itself be indistinguishable from any other recorded click). Recorded macros are saved as JSON under `~/.config/clickyclick/macros/` and can be played back with a configurable loop count.

Recording reads raw input devices directly (there's no portal for *observing* general input the way there is for injecting it), which needs your user in the `input` group:

```bash
sudo usermod -aG input $USER
```

Log out and back in for it to take effect. This is independent of the click/keyboard injection permission above — recording and playback use different mechanisms.
