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
        self.scanned = set()
        self.anonymous_return = False
        self.return_scanned = set()
        self.cancelled_scans = set()
        self.scan_token = None

    def start(self, user, scan_token=None):
        with self.lock:
            if scan_token and scan_token in self.cancelled_scans:
                return None
            self.scan_token = scan_token
            self.user = user
            self.anonymous_return = False
            self.return_scanned.clear()
            self.scanned.clear()
            self.last_activity = self.clock()
            self.generation += 1
            return self.generation

    def begin_anonymous_return(self):
        with self.lock:
            self.user = None
            self.scanned.clear()
            self.return_scanned.clear()
            self.scan_token = None
            self.anonymous_return = True
            self.last_activity = self.clock()
            self.generation += 1
            return self.generation

    def returning(self, generation=None, instance=None, activity=False):
        with self.lock:
            self._current(activity)
            return self.anonymous_return and (generation is None or generation == self.generation) and (instance is None or instance == self.instance)

    def active(self, activity=False):
        with self.lock:
            self._current(activity)
            return self.user is not None or self.anonymous_return

    def end(self, expected=None):
        with self.lock:
            if expected is None or expected == self.generation:
                self.user = None
                self.anonymous_return = False
                self.scanned.clear()
                self.return_scanned.clear()
                self.generation += 1

    def current(self, activity=False):
        with self.lock:
            return self._current(activity)

    def _current(self, activity=False):
        now = self.clock()
        if self.user and now - self.last_activity >= self.timeout:
            self.user = None
            self.scanned.clear()
            self.return_scanned.clear()
            self.anonymous_return = False
            self.generation += 1
        if self.anonymous_return and now - self.last_activity >= self.timeout:
            self.anonymous_return = False
            self.return_scanned.clear()
            self.generation += 1
        if (self.user or self.anonymous_return) and activity:
            self.last_activity = now
        return self.user

    def snapshot(self):
        with self.lock:
            return self._current(), self.generation

    def scan_context(self, token=None):
        with self.lock:
            user = self._current(activity=True)
            return (self.generation, self.instance, bool(user), self.anonymous_return, token)

    def record_scan(self, entity_id, context=None):
        with self.lock:
            if context is None:
                context = (self.generation, self.instance, bool(self._current()), self.anonymous_return, None)
            generation, instance, identified, anonymous, token = context
            self._current()
            if (generation != self.generation or instance != self.instance or
                    token in self.cancelled_scans or identified != bool(self.user) or
                    anonymous != self.anonymous_return):
                return False
            if identified:
                self.scanned.add(entity_id)
            elif anonymous and self.anonymous_return:
                self.return_scanned.add(entity_id)
                self.last_activity = self.clock()
            else:
                return False
            return True

    def scans(self,generation):
        with self.lock:
            user=self._current()
            if generation!=self.generation:return set()
            return set(self.scanned) if user else set(self.return_scanned) if self.anonymous_return else set()


    def cancel_scan(self, token):
        with self.lock:
            self.cancelled_scans.add(token)
            # Tokens are unique per request. Bound memory without evicting recent cancels.
            if len(self.cancelled_scans) > 500:
                self.cancelled_scans = {token}
            if self.scan_token == token:
                self.user = None
                self.anonymous_return = False
                self.scanned.clear()
                self.return_scanned.clear()
                self.generation += 1
                self.scan_token = None


class Sessions:
    """Browser-owned terminal sessions; native inventory and ledger remain shared."""
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = {}

    def get(self, client):
        with self.lock:
            if client not in self.clients:
                if len(self.clients) >= 256:
                    self.clients = {key: value for key, value in self.clients.items()
                                    if value.active()}
                if len(self.clients) >= 256:
                    raise ValueError('Too many active terminals; end an unused session')
                self.clients[client] = Session(timeout=120)
            return self.clients[client]

    def revoke_user(self, user):
        with self.lock:
            for value in self.clients.values():
                actor, generation = value.snapshot()
                if actor == user:
                    value.end(generation)
