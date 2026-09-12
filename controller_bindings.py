"""Controller chord capture, persistence and activation."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
import time

from steamos import control_name

CONFIG_PATH = Path.home() / ".config" / "clickyclick" / "controller_bindings.json"
ACTIONS = ("record", "macro", "autoclick", "emergency_stop")


@dataclass(frozen=True)
class ControllerBinding:
    buttons: frozenset
    hold_seconds: float = 0.0

    def __post_init__(self):
        if not self.buttons:
            raise ValueError("a controller binding needs at least one button")
        if self.hold_seconds < 0:
            raise ValueError("hold time cannot be negative")

    def describe(self, profile="generic"):
        names = [control_name(code, profile) for code in sorted(self.buttons)]
        text = " + ".join(names)
        return f"Hold {text} for {self.hold_seconds:g} seconds" if self.hold_seconds else text

    def to_dict(self):
        return {"buttons": sorted(self.buttons), "hold_seconds": self.hold_seconds}


class BindingStore:
    def __init__(self, path=CONFIG_PATH):
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            return {action: ControllerBinding(frozenset(value["buttons"]), value.get("hold_seconds", 0))
                    for action, value in data.items() if action in ACTIONS}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def save(self, bindings):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({action: binding.to_dict() for action, binding in bindings.items()}, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, self.path)


class ChordCapture:
    def __init__(self, source):
        self.source = source
        self.pressed = set()
        self.seen = set()
        self.result = None

    def start(self):
        self.source.subscribe(self._event)

    def _event(self, tag, code, value):
        if tag != "gamepad" or self.result is not None:
            return
        if value == 1:
            self.pressed.add(code)
            self.seen.add(code)
        elif value == 0:
            self.pressed.discard(code)
            if self.seen and not self.pressed:
                self.result = frozenset(self.seen)

    def close(self):
        self.source.unsubscribe(self._event)


class ChordListener:
    def __init__(self, source, binding, callback, clock=time.monotonic):
        self.source = source
        self.binding = binding
        self.callback = callback
        self.clock = clock
        self.pressed = set()
        self.started = None
        self.fired = False
        self.timer = None

    def start(self):
        self.source.subscribe(self._event)

    def _event(self, tag, code, value):
        if tag != "gamepad":
            return
        if value == 1:
            self.pressed.add(code)
        elif value == 0:
            self.pressed.discard(code)
        complete = self.binding.buttons.issubset(self.pressed)
        if complete and self.started is None:
            self.started = self.clock()
            if self.binding.hold_seconds == 0:
                self._fire()
            else:
                self.timer = threading.Timer(self.binding.hold_seconds, self._held_long_enough)
                self.timer.daemon = True
                self.timer.start()
        elif not complete:
            self.started = None
            self.fired = False
            if self.timer:
                self.timer.cancel()
                self.timer = None

    def _held_long_enough(self):
        if self.binding.buttons.issubset(self.pressed):
            self._fire()

    def _fire(self):
        if not self.fired:
            self.fired = True
            self.callback()

    def close(self):
        if self.timer:
            self.timer.cancel()
        self.source.unsubscribe(self._event)
