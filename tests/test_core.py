import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

import macro
from input_backend import InputBackend
from input_access_setup import RULE, install_input_access
from macro import Macro, MacroError, Step
from session_backend import session_type
os.environ.setdefault("PYNPUT_BACKEND", "dummy")
from x11_backend import X11InputBackend, _key_to_evdev
from pynput.keyboard import Key, KeyCode
from evdev import ecodes as e


class SessionDetectionTests(unittest.TestCase):
    def test_declared_session_wins(self):
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"}), "x11")

    def test_falls_back_to_wayland_display(self):
        self.assertEqual(session_type({"WAYLAND_DISPLAY": "wayland-0"}), "wayland")

    def test_falls_back_to_x_display(self):
        self.assertEqual(session_type({"DISPLAY": ":0"}), "x11")

    def test_unknown_without_display(self):
        self.assertEqual(session_type({}), "unknown")


class MacroStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.macros_dir = Path(self.temporary.name) / "macros"
        self.patch = mock.patch.object(macro, "MACROS_DIR", self.macros_dir)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def test_rejects_path_traversal(self):
        for name in ("../outside", "folder/name", "folder\\name", "..", ""):
            with self.subTest(name=name), self.assertRaises(MacroError):
                Macro(name, []).save()

    def test_round_trip_and_private_permissions(self):
        Macro("Example", [Step("click", 10, x=2, y=3, button="left")]).save()
        loaded = Macro.load("Example")
        self.assertEqual(loaded.name, "Example")
        self.assertEqual(loaded.steps[0].x, 2)
        self.assertEqual(stat.S_IMODE(self.macros_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.macros_dir / "Example.json").stat().st_mode), 0o600)

    def test_rejects_malformed_steps(self):
        with self.assertRaises(ValueError):
            Step("click", 0, x=None, y=1)
        with self.assertRaises(ValueError):
            Step("click", 0, x=1, y=1, button="sideways")
        with self.assertRaises(ValueError):
            Step("key_down", 0, key=None)


class TokenStorageTests(unittest.TestCase):
    def test_token_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "restore_token"
            with mock.patch("input_backend.RESTORE_TOKEN_PATH", path):
                InputBackend._save_restore_token("secret")
            self.assertEqual(path.read_text(), "secret")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)


class X11KeyConversionTests(unittest.TestCase):
    def test_capture_key_conversion(self):
        self.assertEqual(_key_to_evdev(KeyCode.from_char("A")), e.KEY_A)
        self.assertEqual(_key_to_evdev(SimpleNamespace(char=None, name="f9")), e.KEY_F9)
        self.assertEqual(_key_to_evdev(KeyCode.from_char("?")), e.KEY_SLASH)

    def test_playback_key_conversion(self):
        self.assertEqual(X11InputBackend._from_evdev(e.KEY_A), "a")
        self.assertEqual(X11InputBackend._from_evdev(e.KEY_SLASH), "/")
        self.assertEqual(X11InputBackend._from_evdev(e.KEY_LEFTCTRL), Key.ctrl_l)


class OneTimeSetupTests(unittest.TestCase):
    @mock.patch("input_access_setup.access_is_ready", return_value=True)
    @mock.patch("input_access_setup.shutil.which", return_value="/usr/bin/pkexec")
    @mock.patch("input_access_setup.subprocess.run")
    def test_setup_uses_one_authenticated_process(self, run, _which, _ready):
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        install_input_access()
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/pkexec")
        self.assertEqual(command[-1], RULE)


if __name__ == "__main__":
    unittest.main()
