"""Single-terminal badge session with activity-based expiry."""
import threading
import time


class Session:
    def __init__(self, timeout=120, clock=time.monotonic):
        self.timeout = timeout
        self.clock = clock
        self.lock = threading.Lock()
        self.user = None
        self.last_activity = 0

    def start(self, user):
        with self.lock:
            self.user = user
            self.last_activity = self.clock()

    def end(self):
        with self.lock:
            self.user = None

    def current(self, activity=False):
        with self.lock:
            now = self.clock()
            if self.user and now - self.last_activity >= self.timeout:
                self.user = None
            if self.user and activity:
                self.last_activity = now
            return self.user
