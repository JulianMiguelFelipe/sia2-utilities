"""connect_alive(): connect an app-wide signal to a widget safely.

App-wide signals (theme changed, window rescaled) outlive the pages listening to
them. After a page is deleted (for example on logout) calling into its widgets
would crash, so the slot disconnects itself when its owner widget is destroyed.
"""


def connect_alive(signal, owner, fn):
    def slot(*args):
        try:
            fn(*args)
        except RuntimeError:
            disconnect()

    def disconnect(*_):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    signal.connect(slot)
    owner.destroyed.connect(disconnect)
