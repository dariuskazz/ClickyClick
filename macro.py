"""Macro data model (a named, ordered sequence of steps) and playback.

A Step's delay_ms is the time to wait *before* executing it -- this encodes
the natural rhythm captured while recording, and is what gets hand-tuned
when editing a macro manually.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from evdev import ecodes as e

MACROS_DIR = Path.home() / ".config" / "clickyclick" / "macros"

STEP_TYPES = ("move", "click", "key_down", "key_up")
BUTTON_NAMES = {
    e.BTN_LEFT: "left",
    e.BTN_RIGHT: "right",
    e.BTN_MIDDLE: "middle",
}


@dataclass
class Step:
    type: str
    delay_ms: int
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[str] = None
    double: bool = False
    key: Optional[str] = None

    def __post_init__(self):
        if self.type not in STEP_TYPES:
            raise ValueError(f"unknown step type: {self.type!r}")
        if self.delay_ms < 0:
            raise ValueError("delay_ms can't be negative")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            type=data["type"],
            delay_ms=data["delay_ms"],
            x=data.get("x"),
            y=data.get("y"),
            button=data.get("button"),
            double=data.get("double", False),
            key=data.get("key"),
        )

    def describe(self):
        if self.type == "move":
            return f"Move to ({self.x}, {self.y})"
        if self.type == "click":
            where = f" at ({self.x}, {self.y})" if self.x is not None else ""
            kind = "Double-click" if self.double else "Click"
            return f"{kind} {self.button or 'left'}{where}"
        if self.type == "key_down":
            return f"Key down: {self.key}"
        if self.type == "key_up":
            return f"Key up: {self.key}"
        return self.type


class MacroError(RuntimeError):
    pass


@dataclass
class Macro:
    name: str
    steps: list
    loop_count: int = 0  # 0 = forever

    def to_dict(self):
        return {"name": self.name, "loop_count": self.loop_count, "steps": [s.to_dict() for s in self.steps]}

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            loop_count=data.get("loop_count", 0),
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
        )

    def save(self):
        MACROS_DIR.mkdir(parents=True, exist_ok=True)
        path = MACROS_DIR / f"{self.name}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, name):
        path = MACROS_DIR / f"{name}.json"
        try:
            return cls.from_dict(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError) as exc:
            raise MacroError(f"couldn't load macro {name!r}: {exc}") from exc

    @staticmethod
    def list_names():
        if not MACROS_DIR.exists():
            return []
        return sorted(p.stem for p in MACROS_DIR.glob("*.json"))

    @staticmethod
    def delete(name):
        (MACROS_DIR / f"{name}.json").unlink(missing_ok=True)

    @staticmethod
    def exists(name):
        return (MACROS_DIR / f"{name}.json").exists()


class MacroPlayer:
    """Plays a Macro's steps in a loop, mirroring ClickyClickApp's own
    interruptible click-loop pattern: a threading.Event for cancellation,
    a queue.Queue for status back to the main thread."""

    def __init__(self, backend, stop_event, ui_queue):
        self.backend = backend
        self._stop_event = stop_event
        self._ui_queue = ui_queue

    def play(self, macro):
        loops_done = 0
        step_count = 0
        while not self._stop_event.is_set():
            for step in macro.steps:
                if self._stop_event.wait(step.delay_ms / 1000.0):
                    self._ui_queue.put(("macro_stopped", step_count))
                    return
                self._run_step(step)
                step_count += 1
                self._ui_queue.put(("macro_step", step_count))
            loops_done += 1
            if macro.loop_count and loops_done >= macro.loop_count:
                break
        self._ui_queue.put(("macro_stopped", step_count))

    def _run_step(self, step):
        if step.type == "move":
            self.backend.move_absolute(step.x, step.y)
        elif step.type == "click":
            if step.x is not None and step.y is not None:
                self.backend.move_absolute(step.x, step.y)
            self.backend.click(step.button or "left", double=step.double)
        elif step.type == "key_down":
            self.backend.key_down(e.ecodes[step.key])
        elif step.type == "key_up":
            self.backend.key_up(e.ecodes[step.key])
