"""IP-based sign-in throttling shared by every sign-in form.

All sign-in pages use the same attempt bucket so moving between the general
page and the older staff or customer pages cannot reset the budget.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

LOGIN_ATTEMPT_LIMIT = 8
LOGIN_ATTEMPT_WINDOW = 15 * 60

_CACHE_KEY = "signin-attempts:{ip}"


def client_ip(request):
    """Identify the sign-in client for rate limiting.

    ``X-Forwarded-For`` is easy to spoof, so it is only trusted when the site is
    explicitly deployed behind a proxy that overwrites the header.
    """

    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _attempt_key(request):
    return _CACHE_KEY.format(ip=client_ip(request))


def login_blocked(request):
    try:
        return int(cache.get(_attempt_key(request), 0)) >= LOGIN_ATTEMPT_LIMIT
    except (TypeError, ValueError):
        return False


def record_login_failure(request):
    key = _attempt_key(request)
    try:
        if cache.add(key, 1, LOGIN_ATTEMPT_WINDOW):
            return
        cache.incr(key)
    except (TypeError, ValueError):
        cache.set(key, 1, LOGIN_ATTEMPT_WINDOW)
    except Exception:
        pass


def clear_login_failures(request):
    try:
        cache.delete(_attempt_key(request))
    except Exception:
        pass
