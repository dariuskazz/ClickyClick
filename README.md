# ClickyClick

A configurable auto clicker and macro tool for Linux with runtime-selected X11 and Wayland backends. On Wayland, clicks and keystrokes are injected through the `RemoteDesktop` XDG portal using `libei`/EIS, and the global start/stop action uses the standard `GlobalShortcuts` portal. On X11, ClickyClick uses the X server through `pynput`. After the optional one-time Wayland recording setup, normal operation needs no administrator password or logout.

## Setup

### Ubuntu, Debian, Linux Mint, and Pop!_OS

Install the common dependencies:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-tk python3-gi xdg-desktop-portal
```

On KDE Plasma also install:

```bash
sudo apt install xdg-desktop-portal-kde
```

On GNOME also install:

```bash
sudo apt install xdg-desktop-portal-gnome
```

Linux Mint Cinnamon normally uses `xdg-desktop-portal-xapp`; Pop!_OS COSMIC
normally provides `xdg-desktop-portal-cosmic`. Keep the portal backend supplied
by the desktop rather than replacing it with a backend for a different desktop.

### Fedora

```bash
sudo dnf install git python3 python3-pip python3-tkinter python3-gobject xdg-desktop-portal
```

Install the matching desktop backend:

```bash
# KDE Plasma
sudo dnf install xdg-desktop-portal-kde

# GNOME
sudo dnf install xdg-desktop-portal-gnome
```

### Arch Linux and Manjaro

```bash
sudo pacman -S --needed git python python-pip tk python-gobject libei xdg-desktop-portal
```

Install the matching backend:

```bash
# KDE Plasma
sudo pacman -S --needed xdg-desktop-portal-kde

# GNOME
sudo pacman -S --needed xdg-desktop-portal-gnome

# Sway and other wlroots desktops
sudo pacman -S --needed xdg-desktop-portal-wlr
```

### openSUSE Tumbleweed and Leap

```bash
sudo zypper install git python3 python3-pip python3-tk python3-gobject xdg-desktop-portal
```

For KDE Plasma, also install the KDE portal package when it is available for
your openSUSE release:

```bash
sudo zypper install xdg-desktop-portal-kde
```

### Download and install ClickyClick

The following steps are the same on every distribution:

```bash
git clone https://github.com/dariuskazz/ClickyClick.git
cd ClickyClick
./install.sh
```

The installer creates a Python virtual environment, installs the dependencies,
and adds ClickyClick to the current user's application menu. It does not need
administrator access.

Run it:

```bash
./run.sh
```

### First Wayland launch

1. Approve the desktop's RemoteDesktop consent dialog. This is desktop consent,
   not an administrator-password request. ClickyClick stores the returned
   restore token for later launches.
2. Assign the simple-click and macro shortcuts when the desktop's Global
   Shortcuts dialog appears.
3. The first time you record a macro, approve the one-time input-access setup.
   It applies immediately, requires no logout, and is not requested on later
   launches.

X11 sessions do not need portal approval or the input-access installation.

### Updating

From the ClickyClick directory:

```bash
git pull --ff-only
./venv/bin/pip install -r requirements.txt
```

Run `./install.sh` again after moving the downloaded folder so the application
menu entry receives the new path.

### Distribution notes

- The commands above target currently supported releases. Older releases may
  use versioned Python package names or portal versions without RemoteDesktop
  or GlobalShortcuts support.
- Native COSMIC Wayland clicking depends on the COSMIC portal/compositor
  exposing RemoteDesktop input injection. Installation alone cannot add a
  compositor capability that the desktop does not provide.
- Minimal window-manager installations must include a working
  `xdg-desktop-portal` backend for Wayland. X11 window managers do not require
  a portal for ClickyClick.

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

## Features

- Interval in hours/minutes/seconds/milliseconds
- Left/right/middle button, single/double click
- Click at the current cursor position, or a fixed position (pick it with a 3-second countdown, or type coordinates)
- Repeat forever or a fixed number of times
- One Start/Stop button for simple clicking (`F6` while focused); `Esc` is the emergency Stop All key
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

## License

ClickyClick is free and open-source software licensed under the
[GNU General Public License version 3](LICENSE) (`GPL-3.0-only`). You may use,
study, modify, and redistribute it under the terms of that license.

Copyright © 2026 Darius Kazlauskas.
