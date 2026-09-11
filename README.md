# Auto Clicker

A configurable auto clicker for Linux, built for Wayland (KDE Plasma). Clicks are injected at the kernel level via `uinput`, since X11-style synthetic input (`xdotool`/`pynput`/XTest) is blocked by modern Wayland compositors.

## Setup

Requires your user to be in the `input` group, so the compositor can read events from the virtual input device this app creates:

```bash
sudo usermod -aG input $USER
```

Log out and back in for it to take effect. Then:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

Or install `autoclicker.desktop` to `~/.local/share/applications/` to launch it from your application menu.

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
3. Command: `pkill -USR1 -f autoclicker.py`
4. Set your trigger key on the Trigger tab

(Also shown in-app via the "Global Hotkey Setup…" button.)
