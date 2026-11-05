"""Auto-disconnect app-wide signals when a widget is deleted."""


def connect_alive(signal, owner, fn):
    """Connect, and disconnect when the widget is deleted."""

    def slot(*args):
        """Call fn unless the widget is gone."""
        try:
            fn(*args)
        except RuntimeError:              # owner is already gone
            disconnect()

    def disconnect(*_):
        """Disconnect."""
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass                          # already disconnected

    signal.connect(slot)
    owner.destroyed.connect(disconnect)
