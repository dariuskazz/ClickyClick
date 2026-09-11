# ClickyClick

A configurable auto clicker and macro tool for Linux, built for Wayland (KDE Plasma). Clicks and keystrokes are injected through the `RemoteDesktop` XDG portal using the real `libei`/EIS protocol — the same mechanism screen-sharing and remote-control tools use, and the compositor's actual sanctioned channel for this on Wayland. The global start/stop hotkey, by contrast, is assigned and detected entirely inside this app by reading a keyboard device directly — nothing is ever registered with KDE's shortcut system, so there's nothing left behind when ClickyClick closes.

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

Configured from **Settings → Hotkey**. Click "Set Hotkey…", then press whatever key or combination (e.g. `Ctrl+F6`) you want — captured directly by this app, no KDE dialog involved. Once set, that combination toggles Start/Stop from anywhere, including while a game or another window has focus.

This is deliberately *not* the `GlobalShortcuts` XDG portal (the usual sanctioned way to do this on Wayland): that requires KDE's own native "assign a key" dialog and registers a persistent, app-identified shortcut that shows up in KDE's own Shortcuts settings and outlives the process. Reading a keyboard device directly instead means the whole thing lives only in this app's memory for as long as it's running — closing or killing ClickyClick leaves nothing registered anywhere to revert. Your chosen combination is remembered locally (`~/.config/clickyclick/hotkey.json`, this app's own preference file — not KDE's) so you don't have to reassign it every launch, but re-detecting it each time is a fresh in-process read, not a standing system registration.

Reading a keyboard device directly needs root (there's no portal for *observing* general input the way RemoteDesktop covers *injecting* it above) — same requirement as macro recording below. This used to be solved by putting your account in the `input` group, but that needs a real logout to take effect for any given process, no matter how it's granted (a hard property of how Linux group membership works, not a bug to route around — a `newgrp`-based attempt to skip it turned out to permanently break the RemoteDesktop session in the same process instead, which is worse). So instead: the first time you use "Set Hotkey…" or "Record New…" in a given run of the app, it starts a tiny, fixed-behavior root helper (`input_reader_helper.py`) via `pkexec` — a native password dialog, same as any other `pkexec` use, your password goes there and never through the app. That one helper is then reused for the rest of the app's run, so this is at most one prompt per launch, covering both features, and it **never** requires a logout, because your own account's credentials never change at all.

## Macros

Configured from **Settings → Macros**. "Record New…" captures real mouse clicks, movement, and keystrokes as you perform them, until you press **F9** to stop (a dedicated key rather than a clickable button, since a click on a "Stop" button would itself be indistinguishable from any other recorded click). Recorded macros are saved as JSON under `~/.config/clickyclick/macros/` and can be played back with a configurable loop count.

Recording reads raw input devices directly, which needs the same root helper as the hotkey above (and shares the same running instance of it, if one's already been started this session).
