"""
ui/workers.py
Run slow tasks (sending email/SMS, shortening links) in a background thread
so the window never freezes.

Usage:
    run_in_background(send_email, gmail, to, subject, body,
                      on_done=self.email_sent, on_error=self.email_failed)

on_done(result) and on_error(exception) are always called on the UI thread.
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_running = set()


class _Signals(QObject):
    done = Signal(object)
    error = Signal(object)


class _Runnable(QRunnable):
    """The part that runs in the background thread."""

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


class _Task(QObject):
    """Lives on the UI thread and receives the result from the background thread."""

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
        except RuntimeError:
            pass
        finally:
            _running.discard(self)


def run_in_background(fn, *args, on_done=None, on_error=None):
    task = _Task(fn, args, on_done, on_error)
    _running.add(task)
    QThreadPool.globalInstance().start(task.runnable)
