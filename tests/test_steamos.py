import tempfile
import time
import unittest
from pathlib import Path

from evdev import ecodes as e

from controller_bindings import BindingStore, ChordCapture, ChordListener, ControllerBinding
from steamos import control_name, detect_environment


class FakeSource:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def unsubscribe(self, callback):
        self.callbacks.remove(callback)

    def emit(self, code, value):
        for callback in list(self.callbacks):
            callback("gamepad", code, value)


class SteamEnvironmentTests(unittest.TestCase):
    def test_detects_game_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "os-release"
            release.write_text('ID="steamos"\nID_LIKE="arch"\n')
            result = detect_environment(
                {"SteamGamepadUI": "1", "XDG_SESSION_TYPE": "wayland"}, release
            )
        self.assertTrue(result.is_steamos)
        self.assertTrue(result.is_game_mode)
        self.assertEqual(result.description, "SteamOS Game Mode")

    def test_non_steamos_gamescope_is_not_misidentified(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "os-release"
            release.write_text('ID="arch"\n')
            result = detect_environment({"GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0"}, release)
        self.assertFalse(result.is_steamos)
        self.assertFalse(result.is_game_mode)


class BindingTests(unittest.TestCase):
    def test_plain_language_names(self):
        self.assertEqual(control_name(e.BTN_TRIGGER_HAPPY1, "steam_deck"), "back-left upper button (L4)")
        self.assertEqual(control_name(e.BTN_TRIGGER_HAPPY1, "legion_go_s"), "left rear button (Y1)")

    def test_capture_finishes_after_all_buttons_are_released(self):
        source = FakeSource()
        capture = ChordCapture(source)
        capture.start()
        source.emit(e.BTN_TL, 1)
        source.emit(e.BTN_TR, 1)
        source.emit(e.BTN_TL, 0)
        self.assertIsNone(capture.result)
        source.emit(e.BTN_TR, 0)
        self.assertEqual(capture.result, frozenset({e.BTN_TL, e.BTN_TR}))
        capture.close()

    def test_listener_fires_once_per_press(self):
        source = FakeSource()
        hits = []
        listener = ChordListener(
            source, ControllerBinding(frozenset({e.BTN_TL, e.BTN_TR})),
            lambda: hits.append(True),
        )
        listener.start()
        for _ in range(2):
            source.emit(e.BTN_TL, 1)
            source.emit(e.BTN_TR, 1)
            source.emit(e.BTN_TR, 0)
            source.emit(e.BTN_TL, 0)
        listener.close()
        self.assertEqual(hits, [True, True])

    def test_hold_listener_does_not_fire_after_early_release(self):
        source = FakeSource()
        hits = []
        listener = ChordListener(
            source, ControllerBinding(frozenset({e.BTN_TL, e.BTN_TR}), 0.04),
            lambda: hits.append(True),
        )
        listener.start()
        source.emit(e.BTN_TL, 1)
        source.emit(e.BTN_TR, 1)
        source.emit(e.BTN_TR, 0)
        time.sleep(0.06)
        listener.close()
        self.assertEqual(hits, [])

    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BindingStore(Path(directory) / "bindings.json")
            expected = {"record": ControllerBinding(frozenset({e.BTN_TL, e.BTN_TR}), 2)}
            store.save(expected)
            self.assertEqual(store.load(), expected)


if __name__ == "__main__":
    unittest.main()
