from typing import Iterable, Set
from modules.shared.cache import TTLCache


# Keep seen hashes per session id; default TTL ~ 2 hours
_SESSION = TTLCache(ttl_seconds=7200)


def get_seen(session_id: str) -> Set[str]:
    val = _SESSION.get(session_id) or set()
    if not isinstance(val, set):
        val = set()
    return set(val)


def add_seen(session_id: str, hashes: Iterable[str]) -> None:
    current = get_seen(session_id)
    current.update(hashes)
    _SESSION.set(session_id, current)

