from collections import defaultdict, deque
from time import monotonic
from threading import Lock
from fastapi import HTTPException, Request

_lock = Lock()
_hits = defaultdict(deque)


def check(request: Request, bucket: str, limit: int = 20, window: int = 60):
    ip = request.client.host if request.client else 'unknown'
    key = f'{bucket}:{ip}'
    now = monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, 'Слишком много запросов. Попробуйте позже.')
        q.append(now)
