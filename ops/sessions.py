"""Single-terminal badge session with activity-based expiry."""
import threading
import time
from uuid import uuid4


class Session:
    def __init__(self, timeout=120, clock=time.monotonic):
        self.timeout = timeout
        self.clock = clock
        self.lock = threading.Lock()
        self.user = None
        self.last_activity = 0
        self.generation = 0
        self.instance = str(uuid4())

    def start(self, user):
        with self.lock:
            self.user = user
            self.last_activity = self.clock()
            self.generation += 1
            return self.generation

    def end(self, expected=None):
        with self.lock:
            if expected is None or expected == self.generation:
                self.user = None
                self.generation += 1

    def current(self, activity=False):
        with self.lock:
            return self._current(activity)

    def _current(self, activity=False):
        now = self.clock()
        if self.user and now - self.last_activity >= self.timeout:
            self.user = None
            self.generation += 1
        if self.user and activity:
            self.last_activity = now
        return self.user

    def snapshot(self):
        with self.lock:
            return self._current(), self.generation
