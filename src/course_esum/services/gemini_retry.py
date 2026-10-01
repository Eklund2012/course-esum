"""
gemini_retry.py
~~~~~~~~~~~~~~~
Exponential backoff with full jitter for all Gemini API call sites.

Retry policy
------------
Retryable status codes : 429, 500, 502, 503, 504
                         + network-level errors (httpx.TransportError)
Fail-fast codes         : all other ClientErrors (400, 401, 403, 404, ...)

Backoff formula (full jitter - avoids thundering herds)
--------------------------------------------------------
  cap   = min(base_delay_ms * 2**attempt, max_delay_ms)   [ms]
  sleep = random(0, cap) / 1000                           [seconds]

If the server returns a ``Retry-After`` header on a 429 response its
value (integer seconds) is used instead, bounded by ``max_delay_ms``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

import httpx
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retryable HTTP status codes
# ---------------------------------------------------------------------------
RETRYABLE_CODES: frozenset[int] = frozenset({
    429,  # Too Many Requests / Rate Limit
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable / Overloaded
    504,  # Gateway Timeout
})

# ---------------------------------------------------------------------------
# Public exception raised when retries are exhausted
# ---------------------------------------------------------------------------

class GeminiRateLimitError(RuntimeError):
    """Raised after all retry attempts for a Gemini API call are exhausted."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class GeminiRetryConfig:
    """Tunable parameters for the retry wrapper."""

    max_retries: int = 4          # total attempts = max_retries + 1
    base_delay_ms: int = 500      # initial backoff window in milliseconds
    max_delay_ms: int = 30_000    # absolute ceiling for any sleep in milliseconds

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay_ms <= 0:
            raise ValueError("base_delay_ms must be > 0")
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be >= base_delay_ms")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* should trigger a retry attempt."""
    if isinstance(exc, genai_errors.APIError):
        return exc.code in RETRYABLE_CODES
    # Network-level transient failures (connection refused, timeout, etc.)
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _extract_retry_after_secs(exc: BaseException, max_delay_ms: int) -> float | None:
    """
    Parse the ``Retry-After`` header (integer seconds) from a 429 APIError.

    Returns the delay in *seconds* (bounded by *max_delay_ms*), or ``None``
    if the header is absent or cannot be parsed safely.
    """
    try:
        response = getattr(exc, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", {})
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is None:
            return None
        # Only handle the integer-seconds form; ignore HTTP-date strings
        value_secs = int(raw.strip())
        if value_secs <= 0:
            return None
        # Bound by max_delay_ms
        bounded = min(value_secs * 1000, max_delay_ms) / 1000.0
        return bounded
    except (AttributeError, ValueError, TypeError):
        # Malformed header - fall back to jitter calculation
        return None


def _compute_sleep_secs(
    attempt: int,
    cfg: GeminiRetryConfig,
    exc: BaseException,
) -> float:
    """
    Compute how long to sleep before the next attempt (in seconds).

    Uses ``Retry-After`` when available on 429 responses, otherwise applies
    full-jitter exponential backoff.
    """
    # Honour Retry-After on 429 errors
    if isinstance(exc, genai_errors.APIError) and exc.code == 429:
        retry_after = _extract_retry_after_secs(exc, cfg.max_delay_ms)
        if retry_after is not None:
            logger.debug("Honouring Retry-After header: sleeping %.2fs", retry_after)
            return retry_after

    # Full-jitter backoff
    cap_ms = min(cfg.base_delay_ms * (2 ** attempt), cfg.max_delay_ms)
    sleep_ms = random.uniform(0, cap_ms)
    return sleep_ms / 1000.0


# ---------------------------------------------------------------------------
# Synchronous wrapper
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


def with_gemini_retry(
    fn: Callable[..., _T],
    /,
    *args: Any,
    cfg: GeminiRetryConfig,
    **kwargs: Any,
) -> _T:
    """
    Call fn(*args, **kwargs) with exponential-backoff retry semantics.

    Non-retryable errors are re-raised immediately.
    After cfg.max_retries failed attempts a GeminiRateLimitError is raised,
    chaining the last exception as its cause.
    """
    last_exc: BaseException | None = None

    for attempt in range(cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except BaseException as exc:
            last_exc = exc

            if not _is_retryable(exc):
                logger.warning(
                    "Gemini non-retryable error (attempt %d/%d): %s",
                    attempt + 1,
                    cfg.max_retries + 1,
                    exc,
                )
                raise  # fail-fast

            if attempt >= cfg.max_retries:
                break  # exhausted - fall through to raise below

            sleep_secs = _compute_sleep_secs(attempt, cfg, exc)
            logger.warning(
                "Gemini transient error (attempt %d/%d), retrying in %.2fs: %s",
                attempt + 1,
                cfg.max_retries + 1,
                sleep_secs,
                exc,
            )
            time.sleep(sleep_secs)

    raise GeminiRateLimitError(
        f"Gemini API call failed after {cfg.max_retries + 1} attempt(s): {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Asynchronous wrapper
# ---------------------------------------------------------------------------

async def async_with_gemini_retry(
    fn: Callable[..., _T],
    /,
    *args: Any,
    cfg: GeminiRetryConfig,
    **kwargs: Any,
) -> _T:
    """
    Async version of with_gemini_retry.

    Uses asyncio.sleep so as not to block the event loop during backoff.
    fn is called directly (not awaited) since the google-genai SDK's
    generate_content is synchronous even when used inside async contexts.
    """
    last_exc: BaseException | None = None

    for attempt in range(cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except BaseException as exc:
            last_exc = exc

            if not _is_retryable(exc):
                logger.warning(
                    "Gemini non-retryable error (attempt %d/%d): %s",
                    attempt + 1,
                    cfg.max_retries + 1,
                    exc,
                )
                raise  # fail-fast

            if attempt >= cfg.max_retries:
                break

            sleep_secs = _compute_sleep_secs(attempt, cfg, exc)
            logger.warning(
                "Gemini transient error (attempt %d/%d), retrying in %.2fs: %s",
                attempt + 1,
                cfg.max_retries + 1,
                sleep_secs,
                exc,
            )
            await asyncio.sleep(sleep_secs)

    raise GeminiRateLimitError(
        f"Gemini API call failed after {cfg.max_retries + 1} attempt(s): {last_exc}"
    ) from last_exc
