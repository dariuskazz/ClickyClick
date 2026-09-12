"""SteamOS/Game Mode and handheld-controller discovery."""

from dataclasses import dataclass
from pathlib import Path
import os

import evdev
from evdev import ecodes as e


@dataclass(frozen=True)
class SteamEnvironment:
    is_steamos: bool
    is_game_mode: bool
    session: str

    @property
    def description(self):
        if self.is_steamos and self.is_game_mode:
            return "SteamOS Game Mode"
        if self.is_steamos:
            return "SteamOS Desktop Mode"
        return "Standard Linux desktop"


@dataclass(frozen=True)
class ControllerInfo:
    path: str
    name: str
    profile: str
    vendor: int
    product: int
    button_count: int
    button_codes: tuple
    has_touchpad: bool
    has_gyro: bool

    @property
    def description(self):
        labels = {
            "steam_deck": "Steam Deck controller",
            "legion_go_s": "Lenovo Legion Go S controller",
            "steamos_handheld": "SteamOS handheld controller",
            "generic": "Generic game controller",
        }
        return labels[self.profile]


def _os_release(path=Path("/etc/os-release")):
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def detect_environment(environ=None, os_release_path=Path("/etc/os-release")):
    env = os.environ if environ is None else environ
    release = _os_release(os_release_path)
    identifiers = " ".join((release.get("ID", ""), release.get("ID_LIKE", ""))).lower()
    is_steamos = "steamos" in identifiers
    game_markers = (
        env.get("SteamGamepadUI") == "1",
        bool(env.get("GAMESCOPE_WAYLAND_DISPLAY")),
        env.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope",
    )
    is_game_mode = is_steamos and any(game_markers)
    return SteamEnvironment(is_steamos, is_game_mode, env.get("XDG_SESSION_TYPE", "unknown"))


def _profile(name, vendor, product):
    label = name.lower()
    if "steam deck" in label or (vendor == 0x28DE and product in {0x1205, 0x1142}):
        return "steam_deck"
    if "legion go s" in label:
        return "legion_go_s"
    if "steamos" in label and ("handheld" in label or "controller" in label):
        return "steamos_handheld"
    return "generic"


def _is_gamepad(capabilities):
    keys = set(capabilities.get(e.EV_KEY, []))
    return bool(keys & {e.BTN_GAMEPAD, e.BTN_SOUTH, e.BTN_EAST}) and e.EV_ABS in capabilities


def controller_from_device(device):
    capabilities = device.capabilities()
    if not _is_gamepad(capabilities):
        return None
    keys = set(capabilities.get(e.EV_KEY, []))
    abs_codes = {item[0] if isinstance(item, tuple) else item for item in capabilities.get(e.EV_ABS, [])}
    info = device.info
    return ControllerInfo(
        path=device.path,
        name=device.name or "Unknown controller",
        profile=_profile(device.name or "", info.vendor, info.product),
        vendor=info.vendor,
        product=info.product,
        button_count=len(keys),
        button_codes=tuple(sorted(keys)),
        has_touchpad=bool(abs_codes & {e.ABS_MT_POSITION_X, e.ABS_MT_POSITION_Y}),
        has_gyro=any(word in (device.name or "").lower() for word in ("motion", "gyro", "imu")),
    )


def list_controllers(paths=None):
    controllers = []
    for path in paths or evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            controller = controller_from_device(device)
            device.close()
        except OSError:
            continue
        if controller is not None:
            controllers.append(controller)
    return controllers


def profile_control_names(profile):
    common = {
        e.BTN_SOUTH: "A face button",
        e.BTN_EAST: "B face button",
        e.BTN_WEST: "X face button",
        e.BTN_NORTH: "Y face button",
        e.BTN_TL: "left shoulder button (L1/LB)",
        e.BTN_TR: "right shoulder button (R1/RB)",
        e.BTN_TL2: "left trigger (L2/LT)",
        e.BTN_TR2: "right trigger (R2/RT)",
        e.BTN_SELECT: "View button",
        e.BTN_START: "Menu button",
    }
    if profile == "steam_deck":
        common.update({
            e.BTN_TRIGGER_HAPPY1: "back-left upper button (L4)",
            e.BTN_TRIGGER_HAPPY2: "back-left lower button (L5)",
            e.BTN_TRIGGER_HAPPY3: "back-right upper button (R4)",
            e.BTN_TRIGGER_HAPPY4: "back-right lower button (R5)",
        })
    elif profile == "legion_go_s":
        common.update({
            e.BTN_TRIGGER_HAPPY1: "left rear button (Y1)",
            e.BTN_TRIGGER_HAPPY2: "right rear button (Y2)",
        })
    return common


def control_name(code, profile="generic"):
    names = profile_control_names(profile)
    if code in names:
        return names[code]
    kernel_name = e.BTN.get(code, e.KEY.get(code, f"button {code}"))
    if isinstance(kernel_name, (tuple, list)):
        kernel_name = kernel_name[0]
    return kernel_name.replace("BTN_", "").replace("KEY_", "").replace("_", " ").title()
