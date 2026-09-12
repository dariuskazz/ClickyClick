"""Password-free X11 output and global input observation via pynput."""

import threading

from evdev import ecodes as e
from pynput import keyboard, mouse

from input_backend import BackendUnavailable


_SPECIAL_KEYS = {
    "alt": e.KEY_LEFTALT,
    "alt_gr": e.KEY_RIGHTALT,
    "backspace": e.KEY_BACKSPACE,
    "caps_lock": e.KEY_CAPSLOCK,
    "cmd": e.KEY_LEFTMETA,
    "cmd_l": e.KEY_LEFTMETA,
    "cmd_r": e.KEY_RIGHTMETA,
    "ctrl": e.KEY_LEFTCTRL,
    "ctrl_l": e.KEY_LEFTCTRL,
    "ctrl_r": e.KEY_RIGHTCTRL,
    "delete": e.KEY_DELETE,
    "down": e.KEY_DOWN,
    "end": e.KEY_END,
    "enter": e.KEY_ENTER,
    "esc": e.KEY_ESC,
    "home": e.KEY_HOME,
    "insert": e.KEY_INSERT,
    "left": e.KEY_LEFT,
    "menu": e.KEY_MENU,
    "page_down": e.KEY_PAGEDOWN,
    "page_up": e.KEY_PAGEUP,
    "right": e.KEY_RIGHT,
    "shift": e.KEY_LEFTSHIFT,
    "shift_l": e.KEY_LEFTSHIFT,
    "shift_r": e.KEY_RIGHTSHIFT,
    "space": e.KEY_SPACE,
    "tab": e.KEY_TAB,
    "up": e.KEY_UP,
}
for _number in range(1, 25):
    _SPECIAL_KEYS[f"f{_number}"] = getattr(e, f"KEY_F{_number}")

_CHAR_KEYS = {chr(ord("a") + i): getattr(e, f"KEY_{chr(ord('A') + i)}") for i in range(26)}
_CHAR_KEYS.update({str(i): getattr(e, f"KEY_{i}") for i in range(10)})
_CHAR_KEYS.update({
    "-": e.KEY_MINUS, "_": e.KEY_MINUS, "=": e.KEY_EQUAL, "+": e.KEY_EQUAL,
    "[": e.KEY_LEFTBRACE, "{": e.KEY_LEFTBRACE, "]": e.KEY_RIGHTBRACE,
    "}": e.KEY_RIGHTBRACE, ";": e.KEY_SEMICOLON, ":": e.KEY_SEMICOLON,
    "'": e.KEY_APOSTROPHE, '"': e.KEY_APOSTROPHE, "`": e.KEY_GRAVE,
    "~": e.KEY_GRAVE, "\\": e.KEY_BACKSLASH, "|": e.KEY_BACKSLASH,
    ",": e.KEY_COMMA, "<": e.KEY_COMMA, ".": e.KEY_DOT, ">": e.KEY_DOT,
    "/": e.KEY_SLASH, "?": e.KEY_SLASH, "!": e.KEY_1, "@": e.KEY_2,
    "#": e.KEY_3, "$": e.KEY_4, "%": e.KEY_5, "^": e.KEY_6,
    "&": e.KEY_7, "*": e.KEY_8, "(": e.KEY_9, ")": e.KEY_0,
})
_EVDEV_CHARS = {
    e.KEY_MINUS: "-", e.KEY_EQUAL: "=", e.KEY_LEFTBRACE: "[",
    e.KEY_RIGHTBRACE: "]", e.KEY_SEMICOLON: ";", e.KEY_APOSTROPHE: "'",
    e.KEY_GRAVE: "`", e.KEY_BACKSLASH: "\\", e.KEY_COMMA: ",",
    e.KEY_DOT: ".", e.KEY_SLASH: "/",
}


def _key_to_evdev(key):
    char = getattr(key, "char", None)
    if char:
        return _CHAR_KEYS.get(char.lower())
    name = getattr(key, "name", None)
    return _SPECIAL_KEYS.get(name)


class X11InputBackend:
    def __init__(self):
        try:
            self._mouse = mouse.Controller()
            self._keyboard = keyboard.Controller()
        except Exception as exc:
            raise BackendUnavailable(f"X11 input backend unavailable: {exc}") from exc

    def move_absolute(self, x, y):
        self._mouse.position = (x, y)

    def click(self, button="left", double=False):
        selected = getattr(mouse.Button, button, mouse.Button.left)
        self._mouse.click(selected, 2 if double else 1)

    def key_down(self, keycode):
        self._keyboard.press(self._from_evdev(keycode))

    def key_up(self, keycode):
        self._keyboard.release(self._from_evdev(keycode))

    @staticmethod
    def _from_evdev(keycode):
        if keycode in _EVDEV_CHARS:
            return _EVDEV_CHARS[keycode]
        name = e.KEY[keycode].replace("KEY_", "").lower()
        if len(name) == 1:
            return name
        aliases = {"leftctrl": "ctrl_l", "rightctrl": "ctrl_r", "leftshift": "shift_l",
                   "rightshift": "shift_r", "leftalt": "alt_l", "rightalt": "alt_gr",
                   "leftmeta": "cmd_l", "rightmeta": "cmd_r", "pagedown": "page_down",
                   "pageup": "page_up"}
        return getattr(keyboard.Key, aliases.get(name, name))

    def close(self):
        pass


class X11InputSource:
    """Shared X11 listener matching the app's existing event-source protocol."""

    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()
        self._pressed = set()
        self._keyboard = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse = mouse.Listener(on_click=self._on_click)
        self._keyboard.start()
        self._mouse.start()
        self._keyboard.wait()
        self._mouse.wait()

    def _emit(self, tag, code, value):
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(tag, code, value)
            except Exception:
                continue

    def _on_press(self, key):
        code = _key_to_evdev(key)
        if code is not None:
            value = 2 if code in self._pressed else 1
            self._pressed.add(code)
            self._emit("kbd", code, value)

    def _on_release(self, key):
        code = _key_to_evdev(key)
        if code is not None:
            self._pressed.discard(code)
            self._emit("kbd", code, 0)

    def _on_click(self, _x, _y, button, pressed):
        mapping = {mouse.Button.left: e.BTN_LEFT, mouse.Button.right: e.BTN_RIGHT,
                   mouse.Button.middle: e.BTN_MIDDLE}
        code = mapping.get(button)
        if code is not None:
            self._emit("mouse", code, 1 if pressed else 0)

    def subscribe(self, callback):
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def close(self):
        for listener in (self._keyboard, self._mouse):
            try:
                listener.stop()
            except (AttributeError, RuntimeError):
                pass
