#!/usr/bin/env python3
"""Root-privileged raw input reader, run on demand via `pkexec` (see
privileged_input.py) instead of requiring the user's own account to be in
the `input` group. That group-based approach needed a real logout to take
effect for any given process (a hard POSIX/PAM property, not a workaround-
able one) -- this needs nothing but a single pkexec prompt, and never a
logout, because it never changes this account's own credentials at all.
It just reads hardware devices as root and prints what it sees.

Deliberately as small and fixed-behavior as possible, since it's the one
piece of this app that runs with elevated privilege: no arguments, no
stdin, nothing configurable from outside. It opens every input device,
classifies each as a mouse or keyboard by capability, and prints one line
per key/button event for as long as it's left running -- that's the whole
program.

Line protocol (stdout, line-buffered): "READY" once at startup, once every
device has been opened, then one line per key/button event: "<tag> <code>
<value>", where tag is "kbd" or "mouse", code is the raw evdev key/button
code, and value is 0 (release), 1 (press), or 2 (autorepeat).
"""

import glob
import sys
import threading

import evdev
from evdev import ecodes as e

_print_lock = threading.Lock()


def _classify(dev):
    caps = dev.capabilities().get(e.EV_KEY, [])
    if e.BTN_LEFT in caps:
        return "mouse"
    if e.KEY_A in caps and e.KEY_ENTER in caps:
        return "kbd"
    return None


def _stream(dev, tag):
    try:
        for event in dev.read_loop():
            if event.type != e.EV_KEY:
                continue
            with _print_lock:
                print(tag, event.code, event.value, flush=True)
    except OSError:
        return


def main():
    threads = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        tag = _classify(dev)
        if tag is None:
            dev.close()
            continue
        t = threading.Thread(target=_stream, args=(dev, tag), daemon=True)
        t.start()
        threads.append(t)
    print("READY", flush=True)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
