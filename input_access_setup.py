"""Install the persistent active-session input ACL in one authenticated action."""

import shutil
import subprocess

from evdev_input import EvdevInputSource, InputAccessRequired

RULE_PATH = "/etc/udev/rules.d/70-clickyclick-input.rules"
RULE = """# ClickyClick: active local session access; installed with user approval.
SUBSYSTEM==\"input\", KERNEL==\"event*\", ENV{ID_INPUT_KEYBOARD}==\"1\", TAG+=\"uaccess\"
SUBSYSTEM==\"input\", KERNEL==\"event*\", ENV{ID_INPUT_MOUSE}==\"1\", TAG+=\"uaccess\"
SUBSYSTEM==\"input\", KERNEL==\"event*\", ENV{ID_INPUT_TOUCHPAD}==\"1\", TAG+=\"uaccess\"
"""


class InputSetupError(RuntimeError):
    pass


def access_is_ready():
    try:
        source = EvdevInputSource()
    except InputAccessRequired:
        return False
    source.close()
    return True


def install_input_access():
    pkexec = shutil.which("pkexec")
    if not pkexec:
        raise InputSetupError("pkexec is not installed; install the packaged ClickyClick input-access rule instead.")
    command = (
        "umask 022; "
        f"printf '%s' \"$1\" > {RULE_PATH}; "
        "/usr/bin/udevadm control --reload-rules; "
        "/usr/bin/udevadm trigger --subsystem-match=input --action=change"
    )
    result = subprocess.run(
        [pkexec, "/bin/sh", "-c", command, "clickyclick-setup", RULE],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "authorization was cancelled or setup failed"
        raise InputSetupError(detail)

    # logind applies TAG+=uaccess asynchronously after the udev change event.
    for _attempt in range(30):
        if access_is_ready():
            return
        import time
        time.sleep(0.1)
    raise InputSetupError("The rule was installed, but input access was not applied to this active session.")
