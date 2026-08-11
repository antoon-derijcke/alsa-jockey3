# SPDX-License-Identifier: GPL-2.0-or-later
"""Terminal styling, applied at display time and nowhere else.

Colour and symbols exist for the person watching a run. They must never reach
a file: an escape sequence in stderr.txt or run.json is noise a year from now,
and it defeats grep. So cases write plain text and the runner paints it on the
way to the screen -- one place that knows about terminals, and artifacts that
stay clean.

No dependency. rich would do this and more, but the whole need here is a few
SGR codes and a carriage return, and the suite runs on a Pi 1B where
`pip install` is not free.

Honours NO_COLOR (https://no-color.org) and switches itself off when stdout is
not a terminal, so a piped or redirected run is plain.
"""

import os
import re
import sys

# Escape sequences occupy no columns. Measuring a styled string with len()
# counts them, so a transient line is remembered as wider than it looks and
# the wipe that follows is sized wrong -- harmlessly long here, but it would
# be harmfully short the moment a style got cheaper.
_SGR = re.compile(r"\033\[[0-9;]*m")


def visible_len(text):
    return len(_SGR.sub("", text))


_CODES = {
    "reset": "0", "bold": "1", "dim": "2",
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "grey": "90",
}


def supported(stream=None):
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


class Style:
    """Paints text, or does not, and knows which it is doing."""

    def __init__(self, enabled=None):
        self.enabled = supported() if enabled is None else enabled

    def __call__(self, text, *names):
        if not self.enabled or not names:
            return text
        codes = ";".join(_CODES[n] for n in names if n in _CODES)
        return f"\033[{codes}m{text}\033[0m" if codes else text


# How each kind of line a case emits is dressed. Keyed on the prefix the case
# writes, so cases stay ignorant of terminals: Case.instruct() writes ">> ",
# Case.ask() writes "?? ", Case.fail() writes "FAIL: ", and the meaning is
# recoverable from the text alone when this is read back from a file.
LINE_STYLES = (
    (">> ", ("bold", "cyan"), "▶ "),
    ("?? ", ("bold", "yellow"), "◆ "),
    ("FAIL: ", ("bold", "red"), "✗ "),
)


def decorate(style, line):
    """Style one streamed line according to how the case marked it."""
    for prefix, names, glyph in LINE_STYLES:
        if line.startswith(prefix):
            return style(glyph + line[len(prefix):], *names)
    return style(line, "grey")


class Live:
    """A place on the terminal that a transient line can rewrite.

    A case reports a countdown by ending its line with a carriage return
    rather than a newline. On a terminal that redraws in place; anywhere else
    -- a log file, a pipe, a CI transcript -- each update becomes an ordinary
    line, because a log that has been overwritten is a log that lost its
    history.
    """

    def __init__(self, out=None, enabled=None, indent="      "):
        self.out = out or sys.stdout
        self.enabled = supported(self.out) if enabled is None else enabled
        self.indent = indent
        self._held = 0          # width of the transient line now on screen

    def write(self, text, transient=False):
        if transient and not self.enabled:
            transient = False   # keep it, as its own line
        if transient:
            width = visible_len(text)
            pad = max(0, self._held - width)
            self.out.write("\r" + self.indent + text + " " * pad)
            self.out.flush()
            self._held = width
            return
        if self._held:
            # Wipe whatever the countdown left behind before printing over it.
            self.out.write("\r" + " " * (self._held + len(self.indent)) + "\r")
            self._held = 0
        self.out.write(self.indent + text + "\n")
        self.out.flush()

    def close(self):
        if self._held:
            self.out.write("\n")
            self.out.flush()
            self._held = 0
