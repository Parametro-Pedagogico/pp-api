"""Rate limit em memória para discovery (por IP e hash de e-mail)."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from threading import Lock

from app.core.config import settings

_lock = Lock()
_buckets: dict[str, list[float]] = defaultdict(list)


def _prune(key: str, now: float, window: float) -> None:
    cutoff = now - window
    _buckets[key] = [t for t in _buckets[key] if t > cutoff]
    if not _buckets[key]:
        del _buckets[key]


def check_rate_limit(*, ip: str | None, email_normalized: str) -> bool:
    """Retorna True se permitido; False se excedeu limite."""
    now = time.monotonic()
    window = float(settings.discovery_rate_limit_window_seconds)
    limit = settings.discovery_rate_limit_per_ip
    email_hash = hashlib.sha256(email_normalized.encode()).hexdigest()[:32]

    keys = [f"ip:{ip or 'unknown'}", f"em:{email_hash}"]
    with _lock:
        for key in keys:
            _prune(key, now, window)
            if len(_buckets[key]) >= limit:
                return False
        for key in keys:
            _buckets[key].append(now)
    return True


_used_discovery_jti: dict[str, float] = {}


def mark_discovery_jti_used(jti: str) -> bool:
    """Marca JTI como usado. Retorna False se já estava usado (replay)."""
    now = time.monotonic()
    ttl = float(settings.discovery_challenge_ttl_minutes * 60 + 30)
    with _lock:
        cutoff = now - ttl
        expired = [k for k, t in _used_discovery_jti.items() if t <= cutoff]
        for k in expired:
            del _used_discovery_jti[k]
        if jti in _used_discovery_jti:
            return False
        _used_discovery_jti[jti] = now
    return True
