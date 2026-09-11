#!/usr/bin/env python3
import queue
import signal
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from clicker_backend import BackendUnavailable, ClickBackend

INPUT_GROUP_FIX_MSG = (
    "Couldn't open the virtual input device.\n\n"
    "This usually means your user isn't in the 'input' group yet, which "
    "the desktop compositor needs in order to read synthetic mouse events "
    "on Wayland.\n\n"
    "Fix (one-time):\n"
    "  sudo usermod -aG input $USER\n\n"
    "Then log out and back in, and relaunch Auto Clicker."
)

HOTKEY_HELP_MSG = (
    "In-app hotkeys (work while this window has focus):\n"
    "  F6   Start / Stop\n"
    "  Esc  Stop\n\n"
    "Global hotkey (works even while another window, e.g. a game, has "
    "focus):\n\n"
    "KDE can bind a key to a system-wide command via Custom Shortcuts; "
    "this app listens for the signal that sends.\n\n"
    "Setup:\n"
    "1. System Settings -> Shortcuts -> Custom Shortcuts\n"
    "2. Edit -> New -> Global Shortcut -> Command/URL\n"
    "3. Name it \"Toggle Auto Clicker\"\n"
    "4. Command:  pkill -USR1 -f autoclicker.py\n"
    "5. On the Trigger tab, set your key (e.g. F6)\n\n"
    "That key then toggles Start/Stop from anywhere."
)


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.resizable(False, False)

        self._stop_event = threading.Event()
        self._click_thread = None
        self._ui_queue = queue.Queue()
        self._running = False

        # Installed before backend/UI setup so the global-hotkey signal is
        # handled from the earliest possible moment after launch.
        self._install_signal_handlers()

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.backend = None
        self._backend_error = None
        try:
            self.backend = ClickBackend(self.screen_w, self.screen_h)
        except BackendUnavailable as exc:
            self._backend_error = str(exc)

        self._build_vars()
        self._build_ui()
        self._pump_queue()

        if self._backend_error:
            self.root.after(200, self._show_backend_error)

    # ---------- state ----------
    def _build_vars(self):
        self.hours = tk.StringVar(value="0")
        self.minutes = tk.StringVar(value="0")
        self.seconds = tk.StringVar(value="0")
        self.millis = tk.StringVar(value="100")

        self.button_var = tk.StringVar(value="left")
        self.click_type_var = tk.StringVar(value="single")

        self.position_mode = tk.StringVar(value="current")
        self.fixed_x = tk.StringVar(value="0")
        self.fixed_y = tk.StringVar(value="0")

        self.repeat_mode = tk.StringVar(value="until_stopped")
        self.repeat_count = tk.StringVar(value="10")

        self.status_var = tk.StringVar(value="Idle")
        self.count_var = tk.StringVar(value="Clicks: 0")
        self.pick_status_var = tk.StringVar(value="")

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        interval_frame = ttk.LabelFrame(main, text="Click Interval")
        interval_frame.grid(row=0, column=0, sticky="ew", **pad)
        for i, (label, var) in enumerate(
            [
                ("Hours", self.hours),
                ("Minutes", self.minutes),
                ("Seconds", self.seconds),
                ("Milliseconds", self.millis),
            ]
        ):
            ttk.Label(interval_frame, text=label).grid(row=0, column=2 * i, padx=(6, 2), pady=6)
            ttk.Entry(interval_frame, textvariable=var, width=6).grid(row=0, column=2 * i + 1, padx=(0, 6))

        options_frame = ttk.LabelFrame(main, text="Click Options")
        options_frame.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(options_frame, text="Button:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        for i, val in enumerate(["left", "right", "middle"]):
            ttk.Radiobutton(options_frame, text=val.capitalize(), value=val, variable=self.button_var).grid(
                row=0, column=i + 1, padx=4
            )
        ttk.Label(options_frame, text="Type:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        for i, val in enumerate(["single", "double"]):
            ttk.Radiobutton(options_frame, text=val.capitalize(), value=val, variable=self.click_type_var).grid(
                row=1, column=i + 1, padx=4, sticky="w"
            )

        pos_frame = ttk.LabelFrame(main, text="Click Location")
        pos_frame.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Radiobutton(
            pos_frame, text="Current cursor position", value="current", variable=self.position_mode
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(pos_frame, text="Fixed position:", value="fixed", variable=self.position_mode).grid(
            row=1, column=0, sticky="w", padx=6, pady=2
        )
        ttk.Entry(pos_frame, textvariable=self.fixed_x, width=6).grid(row=1, column=1)
        ttk.Entry(pos_frame, textvariable=self.fixed_y, width=6).grid(row=1, column=2, padx=4)
        ttk.Button(pos_frame, text="Pick Location", command=self._start_pick_location).grid(row=1, column=3, padx=6)
        ttk.Label(pos_frame, textvariable=self.pick_status_var, foreground="#0a7a4a").grid(
            row=2, column=0, columnspan=4, sticky="w", padx=6
        )

        repeat_frame = ttk.LabelFrame(main, text="Repeat")
        repeat_frame.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Radiobutton(
            repeat_frame, text="Repeat until stopped", value="until_stopped", variable=self.repeat_mode
        ).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(repeat_frame, text="Repeat", value="count", variable=self.repeat_mode).grid(
            row=1, column=0, sticky="w", padx=6, pady=2
        )
        ttk.Entry(repeat_frame, textvariable=self.repeat_count, width=6).grid(row=1, column=1)
        ttk.Label(repeat_frame, text="times").grid(row=1, column=2, sticky="w")

        status_frame = ttk.Frame(main)
        status_frame.grid(row=4, column=0, sticky="ew", **pad)
        ttk.Label(status_frame, textvariable=self.status_var, font=("", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self.count_var).grid(row=0, column=1, sticky="e", padx=12)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, sticky="ew", **pad)
        self.start_btn = ttk.Button(btn_frame, text="Start (F6)", command=self._on_start_clicked)
        self.start_btn.grid(row=0, column=0, padx=4, sticky="ew")
        self.stop_btn = ttk.Button(btn_frame, text="Stop (Esc)", command=self._on_stop_clicked, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(btn_frame, text="Global Hotkey Setup…", command=self._show_hotkey_help).grid(
            row=0, column=2, padx=4, sticky="ew"
        )
        btn_frame.columnconfigure((0, 1, 2), weight=1)

        self.root.bind("<F6>", lambda ev: self._toggle_start_stop())
        self.root.bind("<Escape>", lambda ev: self._on_stop_clicked())

    # ---------- signal / hotkey plumbing ----------
    def _install_signal_handlers(self):
        # SIGTERM is deliberately left at its default disposition (terminate
        # the process) so a plain `kill`/`pkill` still quits the app normally.
        signal.signal(signal.SIGUSR1, lambda signum, frame: self._ui_queue.put(("toggle", None)))

    # ---------- pick location ----------
    def _start_pick_location(self):
        self._pick_countdown(3)

    def _pick_countdown(self, seconds_left):
        if seconds_left <= 0:
            x, y = self.root.winfo_pointerxy()
            self.fixed_x.set(str(x))
            self.fixed_y.set(str(y))
            self.pick_status_var.set(f"Captured: ({x}, {y})")
            return
        self.pick_status_var.set(f"Move mouse to target… capturing in {seconds_left}")
        self.root.after(1000, self._pick_countdown, seconds_left - 1)

    # ---------- start / stop ----------
    def _toggle_start_stop(self):
        if self._running:
            self._on_stop_clicked()
        else:
            self._on_start_clicked()

    def _validate_and_build_config(self):
        try:
            h = int(self.hours.get() or 0)
            m = int(self.minutes.get() or 0)
            s = int(self.seconds.get() or 0)
            ms = int(self.millis.get() or 0)
        except ValueError:
            raise ValueError("Interval fields must be whole numbers.")
        if min(h, m, s, ms) < 0:
            raise ValueError("Interval fields can't be negative.")
        interval = h * 3600 + m * 60 + s + ms / 1000.0
        if interval <= 0:
            raise ValueError("Interval must be greater than zero.")

        cfg = {
            "interval": interval,
            "button": self.button_var.get(),
            "double": self.click_type_var.get() == "double",
            "position_mode": self.position_mode.get(),
            "repeat_mode": self.repeat_mode.get(),
        }

        if cfg["position_mode"] == "fixed":
            try:
                x, y = int(self.fixed_x.get()), int(self.fixed_y.get())
            except ValueError:
                raise ValueError("Fixed position X/Y must be whole numbers.")
            if not (0 <= x < self.screen_w and 0 <= y < self.screen_h):
                raise ValueError(f"Fixed position must be within 0..{self.screen_w - 1}, 0..{self.screen_h - 1}.")
            cfg["x"], cfg["y"] = x, y

        if cfg["repeat_mode"] == "count":
            try:
                cfg["repeat_count"] = int(self.repeat_count.get())
            except ValueError:
                raise ValueError("Repeat count must be a whole number.")
            if cfg["repeat_count"] <= 0:
                raise ValueError("Repeat count must be greater than zero.")

        return cfg

    def _on_start_clicked(self):
        if self._running:
            return
        if self.backend is None:
            self._show_backend_error()
            return
        try:
            cfg = self._validate_and_build_config()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        if not self._diagnostic_check():
            proceed = messagebox.askyesno(
                "Input device check",
                "The virtual mouse doesn't seem to be moving the cursor. "
                "This usually means your user isn't in the 'input' group "
                "yet (needed on Wayland).\n\n"
                "Fix: sudo usermod -aG input $USER, then log out and back in.\n\n"
                "Start anyway?",
            )
            if not proceed:
                return

        if cfg["position_mode"] == "fixed":
            cfg["x"], cfg["y"] = self._prepare_fixed_target(cfg["x"], cfg["y"])

        self._stop_event.clear()
        self._running = True
        self.status_var.set("Running")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.count_var.set("Clicks: 0")

        self._click_thread = threading.Thread(target=self._click_loop, args=(cfg,), daemon=True)
        self._click_thread.start()

    def _on_stop_clicked(self):
        if not self._running:
            return
        self._stop_event.set()

    def _diagnostic_check(self):
        before = self.root.winfo_pointerxy()
        dx = 12 if before[0] < self.screen_w - 20 else -12
        dy = 12 if before[1] < self.screen_h - 20 else -12
        self.backend.move_relative(dx, dy)
        time.sleep(0.08)
        mid = self.root.winfo_pointerxy()
        self.backend.move_relative(-dx, -dy)
        time.sleep(0.05)
        return mid != before

    def _prepare_fixed_target(self, x, y):
        self.backend.move_absolute(x, y)
        time.sleep(0.08)
        actual_x, actual_y = self.root.winfo_pointerxy()
        err_x, err_y = actual_x - x, actual_y - y
        corrected_x = max(0, min(self.screen_w - 1, x - err_x))
        corrected_y = max(0, min(self.screen_h - 1, y - err_y))
        return corrected_x, corrected_y

    # ---------- click loop (background thread) ----------
    def _click_loop(self, cfg):
        count = 0
        while not self._stop_event.is_set():
            if cfg["position_mode"] == "fixed":
                self.backend.move_absolute(cfg["x"], cfg["y"])
            self.backend.click(cfg["button"], double=cfg["double"])
            count += 1
            self._ui_queue.put(("count", count))
            if cfg["repeat_mode"] == "count" and count >= cfg["repeat_count"]:
                break
            if self._stop_event.wait(cfg["interval"]):
                break
        self._ui_queue.put(("stopped", None))

    # ---------- queue pump (main thread; also keeps signals responsive) ----------
    def _pump_queue(self):
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "count":
                    self.count_var.set(f"Clicks: {payload}")
                elif kind == "stopped":
                    self._running = False
                    self.status_var.set("Idle")
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                elif kind == "toggle":
                    self._toggle_start_stop()
        except queue.Empty:
            pass
        self.root.after(50, self._pump_queue)

    # ---------- dialogs ----------
    def _show_backend_error(self):
        messagebox.showerror("Auto Clicker — setup needed", INPUT_GROUP_FIX_MSG)

    def _show_hotkey_help(self):
        messagebox.showinfo("Global Hotkey Setup", HOTKEY_HELP_MSG)

    def on_close(self):
        self._stop_event.set()
        if self._click_thread and self._click_thread.is_alive():
            self._click_thread.join(timeout=0.5)
        if self.backend:
            self.backend.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
