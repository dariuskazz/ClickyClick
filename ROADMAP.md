# Roadmap

## Shipped

- Auto-click: interval, button/type, fixed or cursor position, repeat count
- Click/keyboard injection via the RemoteDesktop portal + real EIS protocol (the only mechanism that works on this Wayland/KWin setup — see README)
- Password-free global hotkey: GlobalShortcuts portal on Wayland, X server on X11
- Macro recording and playback (mouse + keyboard, save/load/delete)
- Runtime X11/Wayland backend selection; no logout or administrator password in normal use
- Password-free system-wide recording on X11
- Wayland recording after one persistent udev `uaccess` installation; one authorization, no logout or later prompts
- Separate configurable global macro start/stop shortcut plus always-visible Stop All control
- Private, validated, atomic macro storage and private portal-token storage
- Custom app icon, wired into the window, taskbar, and app launcher

## Not done

- **Macro library management beyond delete.** No rename or duplicate for a saved macro — only Record New / Play / Delete exist (`clickyclick.py`'s Macros tab). Renaming today means re-recording under a new name.
- **Desktop icon bug.** Open, actively being debugged — see [HANDOFF.md](HANDOFF.md), don't re-attempt already-ruled-out fixes listed there.
- **Broader compositor validation.** KDE Wayland and an XWayland-backed X11 smoke test are available locally; GNOME, COSMIC, Sway, Hyprland, and other environments still need release-matrix testing.

No other features are currently planned — add to this list when something new comes up rather than letting it live only in chat history.
