import os
import time
import asyncio
from collections import deque
from fastapi import Request

# Default rate limit
DEFAULT_RATE = 10
# Window in seconds (1 minute)
WINDOW_SECONDS = 60

_rate_limit_per_min = None

# Map identifier -> deque of timestamps (float seconds)
_timestamps = {}
_lock = asyncio.Lock()


def get_rate_limit() -> int:
    global _rate_limit_per_min
    if _rate_limit_per_min is not None:
        return _rate_limit_per_min
    v = os.getenv("CREATE_PER_MIN")
    if not v:
        _rate_limit_per_min = DEFAULT_RATE
        return _rate_limit_per_min
    try:
        n = int(v)
        if n < 1:
            n = DEFAULT_RATE
    except Exception:
        n = DEFAULT_RATE
    _rate_limit_per_min = n
    return _rate_limit_per_min


def get_ip_address(request: Request) -> str:
    # Check X-Real-IP, then X-Forwarded-For, then client.host
    ip = request.headers.get("X-Real-IP")
    if not ip:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # X-Forwarded-For may contain a list
            ip = xff.split(",")[0].strip()
    if not ip:
        # request.client may be None in some tests
        client = request.client
        if client:
            ip = client.host
        else:
            ip = ""
    # strip port if present
    if ":" in ip:
        ip = ip.split(":")[0]
    return ip


async def check_and_record_rate_limit(request: Request = None, identifier: str = None) -> bool:
    """Returns True if request is allowed, False if rate-limited.

    Accepts an optional composite `identifier`. If not provided, will fall back to IP extracted from `request`.
    Honors DISABLE_RATE_LIMIT=1 to bypass checks.
    """
    # allow disabling rate limit via env
    if os.getenv("DISABLE_RATE_LIMIT") == "1":
        return True

    if identifier is None:
        if request is None:
            identifier = ""  # fallback empty identifier
        else:
            identifier = get_ip_address(request)

    now = time.time()
    limit = get_rate_limit()

    async with _lock:
        dq = _timestamps.get(identifier)
        if dq is None:
            dq = deque()
            _timestamps[identifier] = dq
        # remove old timestamps
        while dq and (now - dq[0]) > WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= limit:
            # rate limited
            return False
        dq.append(now)
        return True
