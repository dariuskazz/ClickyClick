# Roadmap

## Shipped

- Auto-click: interval, button/type, fixed or cursor position, repeat count
- Click/keyboard injection via the RemoteDesktop portal + real EIS protocol (the only mechanism that works on this Wayland/KWin setup — see README)
- In-app global hotkey (no KDE registration, nothing left behind on close)
- Macro recording and playback (mouse + keyboard, save/load/delete)
- Root-helper permission model for hotkey/macro input reading — no logout ever required (see README's "Global hotkey" section)
- Custom app icon, wired into the window, taskbar, and app launcher

## Not done

- **Macro library management beyond delete.** No rename or duplicate for a saved macro — only Record New / Play / Delete exist (`clickyclick.py`'s Macros tab). Renaming today means re-recording under a new name.
- **Desktop icon bug.** Open, actively being debugged — see [HANDOFF.md](HANDOFF.md), don't re-attempt already-ruled-out fixes listed there.

No other features are currently planned — add to this list when something new comes up rather than letting it live only in chat history.
