# ClickyClick SteamOS Game Mode implementation plan

## Goal

Run ClickyClick from SteamOS Game Mode on supported handhelds, configure it
with a controller, record actions while the game is visible, and start or stop
clicking and macros without returning to system settings.

The first supported device families are:

1. Steam Deck LCD and OLED.
2. Lenovo Legion Go S running the official SteamOS image.

Other SteamOS handhelds use capability detection and generic/experimental
support. The app must not claim that every game accepts synthetic input or that
using automation is permitted by every game's rules.

## Design principles

- Detect controls and capabilities, not only product names.
- Use plain control names first and manufacturer labels second, for example
  `back-left upper button (L4)`.
- Let the user press a combination instead of requiring them to understand
  controller terminology.
- Never depend on Steam or Quick Access buttons for safety controls because
  SteamOS can intercept them.
- Recording, playback and stopping must work while the game is visible.
- Emergency Stop All must release every simulated button, key and mouse button.
- No password, logout or system-settings visit during normal operation.
- SteamOS support remains experimental until verified on physical hardware.

## Architecture

Split the SteamOS edition into four components:

1. **Controller UI** — a 1280x800 controller- and touchscreen-friendly screen.
2. **Background engine** — owns click/macro state when the UI is not visible.
3. **Device adapter** — normalizes Steam Input, SDL and evdev events into named
   controls.
4. **Gamescope output backend** — safely injects mouse, keyboard or controller
   events into the active game and reports when that is unavailable.

The existing desktop UI and X11/Wayland backends remain available. SteamOS
support is selected at runtime rather than maintained as a permanent code fork.

## Phase 1: detection and diagnostics

- Detect SteamOS using `/etc/os-release`.
- distinguish Game Mode, Desktop Mode and ordinary Linux sessions.
- Detect Gamescope and record the active display/input environment.
- Enumerate connected controllers through SDL 3.
- Read Steam Input type when available:
  - Steam Deck controller.
  - Generic SteamOS handheld controller.
- Record vendor ID, product ID and SDL GUID only for local device matching.
- Detect capabilities: face buttons, shoulders, triggers, rear buttons,
  touchpads, touchscreen, sticks, gyro and rumble.
- Add a diagnostics page with **Copy report** and no personal identifiers.

Acceptance criteria:

- Correctly identifies Steam Deck, Legion Go S or Generic handheld.
- Continues with a generic profile when the model is unknown.
- Hot-plugging an external controller refreshes the device list.

## Phase 2: understandable controller setup

- Add a controller-first settings screen with focus navigation and large touch
  targets.
- Replace bare labels such as `L4` or `Y1` with physical descriptions:
  - Steam Deck: back-left upper/lower and back-right upper/lower buttons.
  - Legion Go S: left rear (Y1) and right rear (Y2) buttons.
- Implement **Press the buttons you want to use** capture.
- Show detected combinations using both plain and technical names.
- Show a diagram of the detected handheld with pressed controls highlighted.
- Warn about duplicate, single-button and SteamOS-reserved combinations.

Default Steam Deck bindings:

- Hold back-left upper + back-right upper for two seconds: start/stop recording.
- Back-left lower + back-right lower: start/stop selected macro.
- Back-left upper + back-right lower: start/stop auto clicker.
- Hold back-left lower + back-right upper for two seconds: emergency Stop All.

Default Legion Go S bindings:

- Hold left rear + right rear + Y for two seconds: start/stop recording.
- Left rear + right rear + X: start/stop selected macro.
- Left rear + right rear + A: start/stop auto clicker.
- Hold left rear + right rear + B for two seconds: emergency Stop All.

Every binding is editable. Recording and emergency actions require a hold.

## Phase 3: background recording while seeing the game

- Add **Arm recording and return to game**.
- Start a configurable five-second countdown.
- Hide the UI and return focus to the previously active game.
- Record normalized controller, mouse and keyboard events in the background.
- Stop and save with the configured controller combination.
- Provide audible signals for countdown, start, save, playback and failure.
- Use a non-interactive notification when SteamOS exposes a suitable mechanism.
- Store pointer positions relative to the game surface, not only absolute screen
  coordinates.
- Save the device capability profile with the macro and warn when replayed on a
  substantially different layout.

Acceptance criteria:

- The game remains visible for the complete recording.
- Switching to the UI does not terminate the background engine.
- Suspend, controller disconnect or engine failure stops safely.

## Phase 4: Gamescope playback backend

- Prototype Gamescope/XWayland injection for mouse and keyboard games.
- Prototype virtual controller output for controller-native games.
- Select the least privileged working backend automatically.
- Never modify SteamOS's read-only partition as part of ordinary startup.
- If a one-time host helper is unavoidable, make installation explicit,
  removable and resilient to SteamOS updates.
- Track every pressed output so Stop All and process shutdown can release it.
- Detect games/backends that reject output and show a clear compatibility
  result.

Compatibility levels shown to the user:

- Controller playback supported.
- Mouse/keyboard playback supported.
- Auto click only.
- Unsupported in this game/session.

## Phase 5: Steam library and packaging

- Package as a Flatpak suitable for installation from Desktop Mode.
- Provide a script that adds ClickyClick as a non-Steam library application.
- Include a controller layout for navigation and safe default shortcuts.
- Preserve user macros and settings across updates.
- Do not require disabling SteamOS read-only mode.
- Publish SteamOS builds separately from stable desktop releases until the
  physical-device test matrix passes.

## Phase 6: testing matrix

Required physical testing:

| Device | Modes | Controls |
|---|---|---|
| Steam Deck LCD | Game/Desktop | built-in, Bluetooth controller |
| Steam Deck OLED | Game/Desktop | built-in, Bluetooth controller |
| Legion Go S SteamOS | Game/Desktop | built-in, Bluetooth controller |
| Unknown AMD handheld | Game/Desktop | generic fallback |

For each configuration test:

- Install/update/uninstall.
- Detection and control naming.
- UI navigation at 1280x800 and 1920x1200.
- Shortcut capture, conflicts and persistence.
- Record while the game remains visible.
- Finite and infinite macro playback.
- Auto-click start/stop.
- Emergency stop during every operation.
- Suspend/resume and controller disconnect.
- Mouse/keyboard, native Linux and Proton games.
- A game that rejects automation, verifying a clear safe failure.

## Delivery milestones

1. `0.1-steamos`: detection, diagnostics and controller navigation.
2. `0.2-steamos`: in-app controller binding and emergency stop.
3. `0.3-steamos`: background recording workflow.
4. `0.4-steamos`: Gamescope mouse/keyboard playback.
5. `0.5-steamos`: virtual-controller playback and Flatpak prototype.
6. `1.1-steamos-preview`: physical-device beta release.

No SteamOS release should replace desktop ClickyClick 1.0 until regression and
physical-device testing are complete.
