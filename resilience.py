"""
Shared retry and circuit-breaker helpers.

The production setup uses `tenacity` and `circuitbreaker`, but tests and
lightweight environments should still import cleanly even when those optional
dependencies are not installed yet.
"""

from __future__ import annotations

import functools
import logging
import time
from collections import deque

try:
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )
except ImportError:  # pragma: no cover - dependency shim
    def retry(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def wait_exponential(*args, **kwargs):
        return None

    def stop_after_attempt(*args, **kwargs):
        return None

    def retry_if_exception_type(*args, **kwargs):
        return None

    def before_sleep_log(*args, **kwargs):
        return None

try:
    from circuitbreaker import CircuitBreakerError
except ImportError:  # pragma: no cover - dependency shim
    class CircuitBreakerError(RuntimeError):
        """Fallback error raised when the local circuit breaker is open."""


def api_circuit_breaker(
    name: str,
    *,
    logger: logging.Logger | None = None,
    failure_threshold: int = 3,
    failure_window_seconds: int = 300,
    recovery_timeout: int = 600,
):
    """
    Simple in-process circuit breaker with timing semantics tuned for APIs.

    After `failure_threshold` raised exceptions inside `failure_window_seconds`,
    the circuit opens for `recovery_timeout` seconds.
    """

    log = logger or logging.getLogger(f"circuit.{name}")
    failures = deque()
    open_until = 0.0

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal open_until
            now = time.time()

            if open_until:
                if now < open_until:
                    remaining = int(open_until - now)
                    raise CircuitBreakerError(
                        f"Circuit open for {name}; retry in {remaining}s"
                    )
                log.info("Circuit closed for %s", name)
                open_until = 0.0

            try:
                result = func(*args, **kwargs)
            except Exception:
                now = time.time()
                while failures and (now - failures[0]) > failure_window_seconds:
                    failures.popleft()
                failures.append(now)
                if len(failures) >= failure_threshold:
                    open_until = now + recovery_timeout
                    failures.clear()
                    log.warning(
                        "Circuit opened for %s after %d failures; pausing calls for %ss",
                        name,
                        failure_threshold,
                        recovery_timeout,
                    )
                raise

            if failures:
                failures.clear()
            return result

        return wrapper

    return decorator
