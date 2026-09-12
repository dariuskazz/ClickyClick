# Handoff notes

Status snapshot for whoever (human or AI) picks this project up next. Written
2026-09-12 after a long session that fixed several real bugs but left one
open. Check `git log` for the authoritative history — this file explains the
*why* and the current open thread, not a changelog.

## Open issue: desktop icon still shows something wrong

The user reports the icon still looks wrong specifically as a **desktop icon**
(Folder View widget / pinned desktop shortcut) — small corner artifacts
visible around the rounded square. Not fixed as of this writing.

What's been ruled out, with direct evidence (don't re-check these blindly,
but do re-verify if `assets/icon.png` changes again):

- **The icon file itself is clean.** `assets/icon.png` has `alpha=0` at the
  four corners (checked with `numpy`/`PIL` directly on pixel data, not by
  eyeballing a preview). It was also composited onto a plain background with
  plain PIL, completely outside KDE/Qt, and rendered with correctly
  transparent, clean rounded corners. If the desktop icon still looks wrong,
  it is very unlikely to be this file's pixel content at this point.
- **Sycoca (`kbuildsycoca6 --noincremental`)** was rebuilt — this is what
  indexes `.desktop` files and their `Icon=` field. Confirmed necessary
  (the installed launcher entry was a stale plain *copy* at
  `~/.local/share/applications/clickyclick.desktop`, not synced with the
  repo's `clickyclick.desktop` — now fixed permanently by replacing the copy
  with a symlink to the repo file, so this specific drift can't recur).
- **`~/.cache/plasma_theme_default.kcache`** (Plasma's SVG/theme render
  cache) was stale from earlier in the session and was deleted.
- **`krunner`** runs as its own long-lived daemon (`krunner --daemon`),
  independent from `plasmashell` — restarting plasmashell does **not**
  restart it, and it was still serving an icon it had loaded into memory
  before a fix landed. Killed it (`kquitapp6 krunner`); it respawns
  automatically via D-Bus activation on the next `org.kde.krunner.App.query`
  call. Confirmed fixed for KRunner search specifically (verified via
  `qdbus6 org.kde.krunner /App org.kde.krunner.App.query "ClickyClick"` +
  screenshot, both before and after the restart, showing the stale vs. fresh
  icon).
- **`~/.cache/thumbnails`** (the freedesktop generic thumbnail cache, 120MB)
  was cleared entirely, in case Folder View was thumbnailing the icon file
  like a generic image rather than loading it as an app icon.
- **`plasmashell` itself** was restarted twice (`kquitapp6 plasmashell` +
  relaunch) — each time after clearing one of the caches above.

None of that fixed the desktop-icon-specific complaint. What's **not yet
tried**:

- Never got a clean, unobstructed screenshot of the actual desktop icon
  grid to inspect closely — every attempt was covered by the user's other
  open windows (browser, game, stream chat, editor). Don't minimize/rearrange
  their windows to force a look; ask them for a cropped screenshot of just
  the icon instead, at whatever size it's rendered at (small desktop icons
  can show antialiasing artifacts that a 1024px source doesn't have — worth
  asking what size their desktop icons are set to).
- Never confirmed whether what the user is seeing is actually part of the
  **icon's pixels** at all, versus a Plasma **selection/hover UI
  decoration** drawn around desktop icons (some Breeze-family styles draw
  corner accents on a focused/selected icon). Worth asking the user to click
  empty desktop space to deselect, then re-screenshot, before assuming it's
  still a caching bug.
- Haven't found or ruled out a **Folder View-specific** icon cache distinct
  from krunner/kickoff/sycoca. `plasmashell` restarts should reload its own
  QML `IconItem` cache since Folder View is a plasmoid running inside that
  same process — but if the corner artifact survives a *third* full
  plasmashell restart done right after a fresh icon file write, there may be
  another cache layer specific to the desktop containment that hasn't been
  identified. `find ~/.cache -newer assets/icon.png` right after touching
  the icon is a reasonable way to spot what else gets written/read around
  icon changes.

## Lessons from this session (read before touching the icon again)

- **KDE/Plasma has several independent icon-related caches/processes.** A
  change to `assets/icon.png` or `clickyclick.desktop` is not visible
  anywhere until *all* of the relevant ones are refreshed: `kbuildsycoca6`
  (desktop-file index), `plasma_theme_default.kcache` (theme/SVG render
  cache), `krunner --daemon` (separate process, own in-memory icon cache,
  needs its own restart), `~/.cache/thumbnails` (generic file thumbnails),
  and possibly more for Folder View specifically (see above). When "I fixed
  it" doesn't match what the user sees, suspect a cache before suspecting
  the file — but *verify* the file directly (numpy/PIL pixel check) before
  spending more time on cache-hunting, so effort isn't wasted chasing a
  caching theory when the file itself regressed.
- **Read the user's image-editing instructions literally, don't
  over-engineer.** Earlier in this session, "remove the background
  surrounding it" was misread as "remove the teal square behind the logo
  too," leading to an elaborate (and repeatedly buggy) background-difference
  matte/recompositing pipeline, when the actual ask was the much simpler
  "remove the checkerboard outside the rounded square, and remove the
  CLICKYCLICK text" — i.e. keep the teal square exactly as it was. When a
  request is ambiguous, the *simpler* reading is usually right, especially
  after the user has already said to stop improvising.
- **Verify visual/image-processing claims numerically, not by eye.** Several
  times this session, a rendered PNG was misjudged by looking at it (seeing
  transparency that wasn't there, or missing transparency that was) —
  costing real time. Check `np.array(img)[y, x]` directly instead of trusting
  a quick visual read, especially for anything alpha-channel related.
- **The `newgrp`-based "no logout" self-relaunch mechanism was removed
  entirely** (see git log around "Revert the newgrp self-relaunch") because
  it broke the RemoteDesktop portal session permanently for any process that
  went through it — `newgrp` is setuid, and Linux marks any process
  descended from a setuid re-exec as unreadable via `/proc/<pid>/root` to
  other processes for its whole life, which is exactly what the portal needs
  to read to identify the caller. Do not reintroduce `newgrp`, `sudo`, `su`,
  or any other setuid-re-exec trick to avoid a permission prompt in this
  app — it will silently break clicking again, and the breakage won't show
  up in quick testing since it depends on which code path a given launch
  takes.
- Hotkey/macro raw input reading now goes through a **pkexec-spawned root
  helper** (`input_reader_helper.py` + `privileged_input.py`), not the old
  `input`-group approach — see the README's "Global hotkey" section for why.
