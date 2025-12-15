from time import time
from typing import Any, Dict, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: int = 900):
        self.ttl = ttl_seconds
        self.store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str):
        now = time()
        item = self.store.get(key)
        if not item:
            return None
        ts, val = item
        if now - ts > self.ttl:
            self.store.pop(key, None)
            return None
        return val

    def set(self, key: str, val: Any):
        self.store[key] = (time(), val)

