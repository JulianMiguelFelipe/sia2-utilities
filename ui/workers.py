"""Background work without freezing the window.

Network calls (TinyURL, Gmail, SMSGate, the photo site) can take seconds. On the
main thread they would freeze the whole window. run_in_background() runs a
function on Qt's thread pool, then calls on_done(result) or on_error(exception)
back on the main thread, where it is safe to update widgets.
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

# Holds every running task so Python can't garbage-collect it before it finishes.
_running = set()


class _Signals(QObject):
    done = Signal(object)
    error = Signal(object)


# Runs on the worker thread. It never touches widgets; it only reports through signals.
class _Runnable(QRunnable):
    def __init__(self, fn, args):
        super().__init__()
        self.fn = fn
        self.args = args
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception as err:
            self.signals.error.emit(err)
        else:
            self.signals.done.emit(result)


# Lives on the main thread. Qt delivers the worker's signals here, so callbacks run safely.
class _Task(QObject):
    def __init__(self, fn, args, on_done, on_error):
        super().__init__()
        self.on_done = on_done
        self.on_error = on_error
        self.runnable = _Runnable(fn, args)
        self.runnable.setAutoDelete(False)
        self.runnable.signals.done.connect(self._finished)
        self.runnable.signals.error.connect(self._failed)

    @Slot(object)
    def _finished(self, result):
        self._deliver(self.on_done, result)

    @Slot(object)
    def _failed(self, err):
        self._deliver(self.on_error, err)

    def _deliver(self, callback, value):
        try:
            if callback:
                callback(value)
        # The page that asked may already be closed (e.g. after logout), so drop the result.
        except RuntimeError:
            pass
        finally:
            _running.discard(self)


# Example: run_in_background(shorten_url, url, on_done=show_link, on_error=show_error)
def run_in_background(fn, *args, on_done=None, on_error=None):
    task = _Task(fn, args, on_done, on_error)
    _running.add(task)
    QThreadPool.globalInstance().start(task.runnable)
