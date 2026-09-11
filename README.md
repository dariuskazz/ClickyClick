# ClickyClick

A configurable auto clicker for Linux, built for Wayland (KDE Plasma). Clicks and keystrokes are injected through the `RemoteDesktop` XDG portal using the real `libei`/EIS protocol — the same mechanism screen-sharing and remote-control tools use, and the compositor's actual sanctioned channel for this on Wayland.

This isn't the first thing that was tried. `uinput` (what `ydotool` uses) creates a real kernel-level virtual mouse, but KWin accepts synthetic *keyboard* input from it while silently dropping synthetic *pointer* input (clicks and motion) — confirmed by hand, not assumed. X11-style injection (`xdotool`/`pynput`, XTest) is blocked outright on Wayland. The portal's own plain D-Bus methods (`NotifyPointerButton` etc.) also silently no-op on this KWin version. Negotiating a proper portal session and injecting through the real EIS protocol is the one path that actually works.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

The first launch asks the compositor for permission (a real consent dialog) to inject pointer and keyboard input. Approval is remembered — a restore token is saved to `~/.config/clickyclick/restore_token` — so this only happens once.

**If no dialog appears and the app reports it couldn't set up a session:** some KDE versions (observed on `xdg-desktop-portal-kde` 6.7.4) have a permission-checking bug that blocks the dialog before it can show. You'll see this in `journalctl --user` as `MegaAuth: Failed to lookup permissions: "No entry for remote-desktop"`. Run the included one-time fix:

```bash
./venv/bin/python fix_kde_portal_permission.py
```

This writes the permission entry directly — the same effect clicking "Allow" would have if the dialog worked. Harmless to run even if you don't hit the bug.

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
- `F6` start/stop and `Esc` stop while the window has focus

## Global hotkey

Wayland only lets the compositor itself own global key grabs, so this app listens for `SIGUSR1` to toggle start/stop instead of grabbing a hotkey directly. To trigger it from anywhere (e.g. while a game has focus), add a KDE Custom Shortcut:

1. System Settings → Shortcuts → Custom Shortcuts
2. Edit → New → Global Shortcut → Command/URL
3. Command: `pkill -USR1 -f clickyclick.py`
4. Set your trigger key on the Trigger tab

(Also shown in-app via the "Global Hotkey Setup…" button.)
