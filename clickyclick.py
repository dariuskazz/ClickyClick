#!/usr/bin/env python3
import getpass
import json
import queue
import signal
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from evdev import ecodes as e

from hotkey import HotkeyCapture, HotkeyError, HotkeyListener, HotkeyPermissionError, format_combo, list_keyboards
from input_backend import BackendUnavailable, InputBackend
from macro import Macro, MacroError, MacroPlayer
from recorder import MacroRecorder, RecorderError, RecorderPermissionError, list_candidate_devices

BACKEND_ERROR_MSG_TEMPLATE = (
    "Couldn't set up a RemoteDesktop session with the compositor:\n\n"
    "{error}\n\n"
    "If a consent dialog appeared, it needs to be approved. If none "
    "appeared at all, your KDE version may need the one-time permission-"
    "store fix described in this project's README (a known bug in KDE's "
    "portal permission checking for non-Flatpak apps).\n\n"
    "Relaunch ClickyClick after resolving this."
)

ABOUT_URL = "https://www.erased.no"

HOTKEY_CONFIG_PATH = Path.home() / ".config" / "clickyclick" / "hotkey.json"


class ClickyClickApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ClickyClick")
        self.root.resizable(False, False)

        self._stop_event = threading.Event()
        self._click_thread = None
        self._ui_queue = queue.Queue()
        self._running = False

        self._macro_stop_event = threading.Event()
        self._macro_thread = None
        self._macro_running = False
        self._recorder = None
        self._recording = False
        self._pending_macro_name = None

        self._settings_win = None

        # Installed before backend/UI setup so the global-hotkey signal is
        # handled from the earliest possible moment after launch.
        self._install_signal_handlers()

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.backend = None
        self._backend_error = None
        try:
            self.backend = InputBackend()
        except BackendUnavailable as exc:
            self._backend_error = str(exc)

        self.hotkey_listener = None
        self.hotkey_combo = None  # (frozenset of modifier names, evdev key code)
        self._hotkey_capture = None
        self._load_and_start_hotkey()

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

    # ---------- main window UI ----------
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
        self.toggle_btn = ttk.Button(btn_frame, text="Start", command=self._toggle_start_stop)
        self.toggle_btn.grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(btn_frame, text="Settings…", command=self._open_settings).grid(row=0, column=1, padx=4, sticky="ew")
        btn_frame.columnconfigure((0, 1), weight=1)

        # In-window convenience bindings; the same physical action (button or
        # key) both starts and stops. The global hotkey configured in
        # Settings does the same thing regardless of window focus.
        self.root.bind("<F6>", lambda ev: self._toggle_start_stop())
        self.root.bind("<Escape>", lambda ev: self._toggle_start_stop())

    # ---------- signal / hotkey plumbing ----------
    def _install_signal_handlers(self):
        # SIGTERM is deliberately left at its default disposition (terminate
        # the process) so a plain `kill`/`pkill` still quits the app normally.
        signal.signal(signal.SIGUSR1, lambda signum, frame: self._ui_queue.put(("toggle", None)))

    def _load_and_start_hotkey(self):
        try:
            data = json.loads(HOTKEY_CONFIG_PATH.read_text())
            combo = (frozenset(data["modifiers"]), data["key_code"])
        except (OSError, ValueError, KeyError):
            return
        try:
            self._start_hotkey_listener(combo)
        except HotkeyError:
            pass  # e.g. input-group permission revoked since last run; Settings shows "Not set"

    def _start_hotkey_listener(self, combo):
        """combo: (frozenset of modifier names, evdev key code). Raises
        HotkeyError if no keyboard device could be opened."""
        if self.hotkey_listener is not None:
            self.hotkey_listener.close()
            self.hotkey_listener = None
        keyboards = list_keyboards()
        if not keyboards:
            raise HotkeyError("no keyboard input device found")
        modifiers, key_code = combo
        listener = HotkeyListener(
            keyboards[0], modifiers, key_code, on_triggered=self._on_hotkey_triggered
        )
        for extra in keyboards[1:]:
            extra.close()
        listener.start()
        self.hotkey_listener = listener
        self.hotkey_combo = combo

    def _on_hotkey_triggered(self):
        # Called from the listener's own background thread -- route through
        # the same thread-safe queue as every other cross-thread signal.
        self._ui_queue.put(("toggle", None))

    @staticmethod
    def _save_hotkey_combo(combo):
        modifiers, key_code = combo
        HOTKEY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        HOTKEY_CONFIG_PATH.write_text(json.dumps({"modifiers": sorted(modifiers), "key_code": key_code}))

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

    # ---------- start / stop (Simple Click) ----------
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
        if self._macro_running:
            messagebox.showerror("Busy", "Stop the running macro before starting Simple Click.")
            return
        try:
            cfg = self._validate_and_build_config()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self._stop_event.clear()
        self._running = True
        self.status_var.set("Running")
        self.toggle_btn.config(text="Stop")
        self.count_var.set("Clicks: 0")

        self._click_thread = threading.Thread(target=self._click_loop, args=(cfg,), daemon=True)
        self._click_thread.start()

    def _on_stop_clicked(self):
        if not self._running:
            return
        self._stop_event.set()

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

    # ---------- queue pump (main thread; also keeps signals/hotkey responsive) ----------
    def _pump_queue(self):
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "count":
                    self.count_var.set(f"Clicks: {payload}")
                elif kind == "stopped":
                    self._running = False
                    self.status_var.set("Idle")
                    self.toggle_btn.config(text="Start")
                elif kind == "toggle":
                    self._toggle_start_stop()
                elif kind == "macro_step":
                    if self._settings_open():
                        self._macro_status_var.set(f"Playing… {payload} step(s) done.")
                elif kind == "macro_stopped":
                    self._macro_running = False
                    if self._settings_open():
                        self._play_btn.config(state="normal")
                        self._stop_macro_btn.config(state="disabled")
                        self._macro_status_var.set(f"Stopped after {payload} step(s).")
        except queue.Empty:
            pass
        self.root.after(50, self._pump_queue)

    # ---------- Settings window ----------
    def _settings_open(self):
        return self._settings_win is not None and self._settings_win.winfo_exists()

    def _open_settings(self):
        if self._settings_open():
            self._settings_win.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("ClickyClick Settings")
        win.resizable(False, False)
        self._settings_win = win

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        hotkey_tab = ttk.Frame(notebook, padding=12)
        notebook.add(hotkey_tab, text="Hotkey")
        self._build_hotkey_tab(hotkey_tab)

        macros_tab = ttk.Frame(notebook, padding=12)
        notebook.add(macros_tab, text="Macros")
        self._build_macros_tab(macros_tab)

        about_tab = ttk.Frame(notebook, padding=12)
        notebook.add(about_tab, text="About")
        self._build_about_tab(about_tab)

    # ---- Hotkey tab ----
    def _build_hotkey_tab(self, parent):
        ttk.Label(parent, text="Global start/stop shortcut", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self._hotkey_status_var = tk.StringVar()
        self._refresh_hotkey_status()
        ttk.Label(parent, textvariable=self._hotkey_status_var, wraplength=320, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 10)
        )
        self._set_hotkey_btn = ttk.Button(parent, text="Set Hotkey…", command=self._on_set_hotkey)
        self._set_hotkey_btn.grid(row=2, column=0, sticky="w")
        ttk.Label(
            parent,
            text="Works even while another window (e.g. a game) has focus. Assigned and "
            "detected entirely within this app -- nothing is registered with KDE, so "
            "closing ClickyClick leaves no shortcut behind.",
            foreground="#666666",
            wraplength=320,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _refresh_hotkey_status(self):
        if self.hotkey_combo:
            self._hotkey_status_var.set(f"Currently set to: {format_combo(*self.hotkey_combo)}")
        else:
            self._hotkey_status_var.set("Not set.")

    def _on_set_hotkey(self):
        try:
            keyboards = list_keyboards()
        except HotkeyPermissionError as exc:
            self._offer_input_group_fix(str(exc))
            return
        except HotkeyError as exc:
            messagebox.showerror("Can't set hotkey", str(exc))
            return
        if not keyboards:
            messagebox.showerror("Can't set hotkey", "No keyboard input device found.")
            return
        for extra in keyboards[1:]:
            extra.close()
        self._set_hotkey_btn.config(state="disabled")
        self._hotkey_status_var.set("Press your desired key combination… (Esc to cancel)")
        self._hotkey_capture = HotkeyCapture(keyboards[0])
        self._hotkey_capture.start()
        self._poll_hotkey_capture()

    def _poll_hotkey_capture(self):
        capture = self._hotkey_capture
        if capture is None:
            return
        result = capture.result
        if result is None:
            if self._settings_open():
                self.root.after(100, self._poll_hotkey_capture)
            else:
                capture.cancel()
                self._hotkey_capture = None
            return
        self._hotkey_capture = None
        capture.close()
        modifiers, key_code = result
        if key_code == e.KEY_ESC and not modifiers:
            self._hotkey_status_var.set("Cancelled.")
        else:
            try:
                self._start_hotkey_listener(result)
            except HotkeyError as exc:
                messagebox.showerror("Can't set hotkey", str(exc))
            else:
                self._save_hotkey_combo(result)
        if self._settings_open():
            self._set_hotkey_btn.config(state="normal")
            self._refresh_hotkey_status()

    # ---- Macros tab ----
    def _build_macros_tab(self, parent):
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=0, column=0, sticky="nsew")
        self._macro_listbox = tk.Listbox(list_frame, height=8, width=32, exportselection=False)
        self._macro_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, command=self._macro_listbox.yview)
        scrollbar.pack(side="left", fill="y")
        self._macro_listbox.config(yscrollcommand=scrollbar.set)
        self._refresh_macro_list()

        btns = ttk.Frame(parent)
        btns.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._record_btn = ttk.Button(btns, text="Record New…", command=self._on_record_macro)
        self._record_btn.grid(row=0, column=0, padx=2, sticky="ew")
        self._play_btn = ttk.Button(btns, text="Play", command=self._on_play_macro)
        self._play_btn.grid(row=0, column=1, padx=2, sticky="ew")
        self._stop_macro_btn = ttk.Button(btns, text="Stop", command=self._on_stop_macro, state="disabled")
        self._stop_macro_btn.grid(row=0, column=2, padx=2, sticky="ew")
        ttk.Button(btns, text="Delete", command=self._on_delete_macro).grid(row=0, column=3, padx=2, sticky="ew")
        btns.columnconfigure((0, 1, 2, 3), weight=1)

        if self._recording:
            self._record_btn.config(state="disabled")
            self._play_btn.config(state="disabled")
        if self._macro_running:
            self._play_btn.config(state="disabled")
            self._stop_macro_btn.config(state="normal")

        loop_frame = ttk.Frame(parent)
        loop_frame.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(loop_frame, text="Loop count (0 = forever):").pack(side="left")
        self.macro_loop_count = tk.StringVar(value="0")
        ttk.Entry(loop_frame, textvariable=self.macro_loop_count, width=6).pack(side="left", padx=6)

        self._macro_status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self._macro_status_var, foreground="#0a7a4a", wraplength=320).grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )

    def _refresh_macro_list(self):
        self._macro_listbox.delete(0, "end")
        for name in Macro.list_names():
            self._macro_listbox.insert("end", name)

    def _on_record_macro(self):
        name = simpledialog.askstring("Record Macro", "Name for this macro:", parent=self._settings_win)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if Macro.exists(name):
            if not messagebox.askyesno("Overwrite?", f"A macro named {name!r} already exists. Overwrite it?"):
                return
        try:
            mice, keyboards = list_candidate_devices()
        except RecorderPermissionError as exc:
            self._offer_input_group_fix(str(exc))
            return
        except RecorderError as exc:
            messagebox.showerror("Can't record", str(exc))
            return
        if not mice or not keyboards:
            messagebox.showerror("Can't record", "No mouse and/or keyboard input device found to record from.")
            return

        self._recorder = MacroRecorder(mice[0], keyboards[0], self.root.winfo_pointerxy)
        self._recorder.start()
        self._recording = True
        self._pending_macro_name = name
        self._record_btn.config(state="disabled")
        self._play_btn.config(state="disabled")
        self._macro_status_var.set(f"Recording from {mice[0].name!r} / {keyboards[0].name!r}… press F9 to stop.")
        self._poll_recorder()

    def _poll_recorder(self):
        if self._recorder is None:
            return
        stopped = self._recorder.poll()
        if self._settings_open():
            self._macro_status_var.set(f"Recording… {len(self._recorder.steps)} step(s) captured. Press F9 to stop.")
        if stopped:
            self._finish_recording()
            return
        self.root.after(100, self._poll_recorder)

    def _finish_recording(self):
        steps = self._recorder.steps
        self._recorder.close()
        self._recorder = None
        self._recording = False
        name = self._pending_macro_name
        self._pending_macro_name = None
        macro = Macro(name=name, steps=steps, loop_count=0)
        macro.save()
        if self._settings_open():
            self._record_btn.config(state="normal")
            self._play_btn.config(state="normal")
            self._macro_status_var.set(f"Saved {name!r} with {len(steps)} step(s).")
            self._refresh_macro_list()

    def _on_play_macro(self):
        sel = self._macro_listbox.curselection()
        if not sel:
            messagebox.showerror("No macro selected", "Select a macro to play.")
            return
        name = self._macro_listbox.get(sel[0])
        try:
            macro = Macro.load(name)
        except MacroError as exc:
            messagebox.showerror("Can't load macro", str(exc))
            return
        try:
            macro.loop_count = int(self.macro_loop_count.get() or 0)
        except ValueError:
            messagebox.showerror("Invalid loop count", "Loop count must be a whole number.")
            return
        if macro.loop_count < 0:
            messagebox.showerror("Invalid loop count", "Loop count can't be negative.")
            return
        if self.backend is None:
            self._show_backend_error()
            return
        if self._running:
            messagebox.showerror("Busy", "Stop Simple Click before playing a macro.")
            return
        if self._macro_running:
            return

        self._macro_stop_event.clear()
        self._macro_running = True
        self._play_btn.config(state="disabled")
        self._stop_macro_btn.config(state="normal")
        self._macro_status_var.set(f"Playing {name!r}…")

        player = MacroPlayer(self.backend, self._macro_stop_event, self._ui_queue)
        self._macro_thread = threading.Thread(target=player.play, args=(macro,), daemon=True)
        self._macro_thread.start()

    def _on_stop_macro(self):
        self._macro_stop_event.set()

    def _on_delete_macro(self):
        sel = self._macro_listbox.curselection()
        if not sel:
            return
        name = self._macro_listbox.get(sel[0])
        if messagebox.askyesno("Delete macro", f"Delete {name!r}?"):
            Macro.delete(name)
            self._refresh_macro_list()

    # ---- About tab ----
    def _build_about_tab(self, parent):
        ttk.Label(parent, text="ClickyClick", font=("", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="Made by Darius Kazlauskas").grid(row=1, column=0, sticky="w", pady=(8, 2))
        link = ttk.Label(parent, text="www.erased.no", foreground="#3366cc", cursor="hand2")
        link.grid(row=2, column=0, sticky="w")
        link.bind("<Button-1>", lambda ev: webbrowser.open(ABOUT_URL))

    # ---------- dialogs ----------
    def _show_backend_error(self):
        messagebox.showerror(
            "ClickyClick — setup needed", BACKEND_ERROR_MSG_TEMPLATE.format(error=self._backend_error)
        )

    def _offer_input_group_fix(self, detail):
        """Offer to run `usermod -aG input <user>` via a graphical polkit
        prompt (pkexec) instead of just telling the user to type it into a
        terminal themselves. The actual privilege escalation and password
        entry happens in pkexec's own native dialog -- this app never sees
        the password, only whether pkexec's child process succeeded."""
        proceed = messagebox.askyesno(
            "Permission needed",
            "ClickyClick needs to read your keyboard/mouse for hotkeys and "
            "macro recording, which requires your user to be in the "
            "'input' group (a one-time system change).\n\n"
            "Add your user to the 'input' group now? A password prompt "
            "will appear.\n\n"
            f"({detail})",
        )
        if not proceed:
            return
        try:
            result = subprocess.run(
                ["pkexec", "usermod", "-aG", "input", getpass.getuser()],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            messagebox.showerror(
                "Can't run pkexec",
                "pkexec isn't available on this system. Run this yourself "
                "in a terminal:\n\n  sudo usermod -aG input $USER",
            )
            return
        except subprocess.TimeoutExpired:
            messagebox.showerror("Timed out", "The permission prompt timed out or wasn't answered.")
            return
        if result.returncode == 0:
            messagebox.showinfo(
                "Done",
                "Your user was added to the 'input' group.\n\n"
                "Log out and log back in for this to take effect, then try again.",
            )
        else:
            messagebox.showerror(
                "Couldn't add to group",
                "The password prompt was cancelled or failed.\n\n"
                + (result.stderr.strip() or "Run this yourself in a terminal:\n\n  sudo usermod -aG input $USER"),
            )

    def on_close(self):
        self._stop_event.set()
        self._macro_stop_event.set()
        if self._recorder is not None:
            self._recorder.close()
        if self._click_thread and self._click_thread.is_alive():
            self._click_thread.join(timeout=0.5)
        if self._macro_thread and self._macro_thread.is_alive():
            self._macro_thread.join(timeout=0.5)
        if self._hotkey_capture is not None:
            self._hotkey_capture.cancel()
        if self.hotkey_listener is not None:
            self.hotkey_listener.close()
        if self.backend:
            self.backend.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ClickyClickApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
