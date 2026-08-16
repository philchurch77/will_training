"""Login throttling for the 4-digit code.

On a home network a session-based lockout was fine. Published to the internet
it is not: a session lockout is bypassed by discarding a cookie, and 10,000
guesses is not many. So the counters live in the cache, keyed by client IP,
with an escalating lockout and a global cap that catches attempts spread
across many addresses.

Deliberately simple - it is a family app, not a bank - but it turns a
brute-force from "half an hour" into "not worth trying".
"""

import time

from django.conf import settings
from django.core.cache import cache

FAIL_KEY = "pin-fails:{ip}"
LOCK_KEY = "pin-locked-until:{ip}"
LEVEL_KEY = "pin-lock-level:{ip}"
GLOBAL_KEY = "pin-fails-global"

# Counters are kept a good while longer than the lockout so that someone who
# waits out a block does not get a completely clean slate.
COUNTER_TTL = 60 * 60 * 24


def client_ip(request):
    """Best-effort client address.

    Behind Render's proxy the real address is the first entry in
    X-Forwarded-For. Only trust that header when we know we are behind a proxy,
    otherwise anyone could spoof it to dodge the throttle.
    """
    behind_proxy = getattr(settings, "SECURE_PROXY_SSL_HEADER", None) is not None
    if behind_proxy:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def seconds_locked(request):
    """How long this address must wait, in seconds. Zero means go ahead."""
    if _global_tripped():
        return _remaining(GLOBAL_KEY + ":until")

    until = cache.get(LOCK_KEY.format(ip=client_ip(request)))
    if not until:
        return 0
    return max(0, int(until - time.time()))


def record_failure(request):
    """Count a wrong code and lock the address if it has had too many.

    Returns the number of seconds it is now locked for, or 0.
    """
    ip = client_ip(request)
    fails = (cache.get(FAIL_KEY.format(ip=ip)) or 0) + 1
    cache.set(FAIL_KEY.format(ip=ip), fails, COUNTER_TTL)

    total = (cache.get(GLOBAL_KEY) or 0) + 1
    cache.set(GLOBAL_KEY, total, settings.PIN_GLOBAL_WINDOW_SECONDS)
    if total >= settings.PIN_GLOBAL_MAX_ATTEMPTS:
        cache.set(
            GLOBAL_KEY + ":until",
            time.time() + settings.PIN_GLOBAL_WINDOW_SECONDS,
            settings.PIN_GLOBAL_WINDOW_SECONDS,
        )

    if fails < settings.PIN_MAX_ATTEMPTS:
        return 0

    # Every further lockout is twice as long as the last, up to the cap.
    level = (cache.get(LEVEL_KEY.format(ip=ip)) or 0) + 1
    cache.set(LEVEL_KEY.format(ip=ip), level, COUNTER_TTL)

    wait = min(
        settings.PIN_LOCKOUT_SECONDS * (2 ** (level - 1)),
        settings.PIN_MAX_LOCKOUT_SECONDS,
    )
    cache.set(LOCK_KEY.format(ip=ip), time.time() + wait, wait)
    cache.set(FAIL_KEY.format(ip=ip), 0, COUNTER_TTL)
    return wait


def clear(request):
    """Forget everything about this address - called after a correct code."""
    ip = client_ip(request)
    cache.delete_many(
        [
            FAIL_KEY.format(ip=ip),
            LOCK_KEY.format(ip=ip),
            LEVEL_KEY.format(ip=ip),
        ]
    )


def _global_tripped():
    return _remaining(GLOBAL_KEY + ":until") > 0


def _remaining(key):
    until = cache.get(key)
    if not until:
        return 0
    return max(0, int(until - time.time()))


def describe(seconds):
    """Wording a nine-year-old can act on."""
    if seconds <= 0:
        return ""
    if seconds < 90:
        return f"Too many tries. Wait {seconds} seconds."
    minutes = round(seconds / 60)
    return f"Too many tries. Wait about {minutes} minutes."
