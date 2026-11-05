"""Background threads so the window never freezes."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_running = set()          # keep tasks alive until their result is delivered


class _Signals(QObject):
    """Done / error signals."""
    done = Signal(object)
    error = Signal(object)


class _Runnable(QRunnable):
    """Runs the job in the background."""

    def __init__(self, fn, args):
        """Store the job."""
        super().__init__()
        self.fn = fn
        self.args = args
        self.signals = _Signals()

    def run(self):
        """Run the job."""
        try:
            result = self.fn(*self.args)
        except Exception as err:         # handed back to the UI to show
            self.signals.error.emit(err)
        else:
            self.signals.done.emit(result)


class _Task(QObject):
    """Gets the result on the UI thread."""

    def __init__(self, fn, args, on_done, on_error):
        """Connect the signals."""
        super().__init__()
        self.on_done = on_done
        self.on_error = on_error
        self.runnable = _Runnable(fn, args)
        self.runnable.setAutoDelete(False)
        self.runnable.signals.done.connect(self._finished)
        self.runnable.signals.error.connect(self._failed)

    @Slot(object)
    def _finished(self, result):
        """Job done."""
        self._deliver(self.on_done, result)

    @Slot(object)
    def _failed(self, err):
        """Job failed."""
        self._deliver(self.on_error, err)

    def _deliver(self, callback, value):
        """Call back the page."""
        try:
            if callback:
                callback(value)
        except RuntimeError:
            pass                 # the page was closed (e.g. logged out) while working
        finally:
            _running.discard(self)


def run_in_background(fn, *args, on_done=None, on_error=None):
    """Run fn in the background."""
    task = _Task(fn, args, on_done, on_error)
    _running.add(task)
    QThreadPool.globalInstance().start(task.runnable)
