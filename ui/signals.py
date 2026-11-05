"""
ui/signals.py
connect_alive(): connect a widget to an app-wide signal (window resized,
theme changed) and automatically DISCONNECT it when the widget is deleted.

Why: on logout the dashboard is deleted. Without this, those app-wide signals
would still try to redraw the deleted pages and print
"RuntimeError: Internal C++ object already deleted".
"""


def connect_alive(signal, owner, fn):
    """Like signal.connect(fn), but stops as soon as `owner` (a widget) is deleted."""

    def slot(*args):
        try:
            fn(*args)
        except RuntimeError:              # owner is already gone
            disconnect()

    def disconnect(*_):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass                          # already disconnected

    signal.connect(slot)
    owner.destroyed.connect(disconnect)
