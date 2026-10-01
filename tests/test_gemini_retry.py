"""
tests/test_gemini_retry.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the Gemini retry/backoff module.

All tests mock time.sleep / asyncio.sleep to run instantly and never hit
the real Gemini API.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, call
from typing import Any

import pytest
import httpx
from google.genai import errors as genai_errors

from course_esum.services.gemini_retry import (
    RETRYABLE_CODES,
    GeminiRateLimitError,
    GeminiRetryConfig,
    _extract_retry_after_secs,
    _is_retryable,
    async_with_gemini_retry,
    with_gemini_retry,
)


# ---------------------------------------------------------------------------
# Helpers to construct fake google.genai errors
# ---------------------------------------------------------------------------

def _make_api_error(
    code: int,
    retry_after: str | None = None,
) -> genai_errors.APIError:
    """Build a minimal APIError with an optional Retry-After header."""
    response_json: dict[str, Any] = {"error": {"code": code, "message": "test", "status": "TEST"}}
    # Build a mock httpx.Response so .response attribute is present
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = code
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    mock_response.headers = headers

    if 400 <= code < 500:
        err = genai_errors.ClientError(code, response_json, mock_response)
    else:
        err = genai_errors.ServerError(code, response_json, mock_response)
    return err


_FAST_CFG = GeminiRetryConfig(max_retries=3, base_delay_ms=1, max_delay_ms=10)


# ---------------------------------------------------------------------------
# 1. Retries on 429, succeeds on 3rd attempt
# ---------------------------------------------------------------------------

def test_retries_on_429():
    """ClientError(429) is retryable; should succeed after two failures."""
    err = _make_api_error(429)
    call_count = 0

    def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise err
        return "ok"

    with patch("course_esum.services.gemini_retry.time.sleep"):
        result = with_gemini_retry(flaky, cfg=_FAST_CFG)

    assert result == "ok"
    assert call_count == 3


# ---------------------------------------------------------------------------
# 2. Retries on 503, succeeds on 2nd attempt
# ---------------------------------------------------------------------------

def test_retries_on_503():
    """ServerError(503) is retryable; should succeed after one failure."""
    err = _make_api_error(503)
    call_count = 0

    def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise err
        return "ok"

    with patch("course_esum.services.gemini_retry.time.sleep"):
        result = with_gemini_retry(flaky, cfg=_FAST_CFG)

    assert result == "ok"
    assert call_count == 2


# ---------------------------------------------------------------------------
# 3. 502 and 504 are in RETRYABLE_CODES
# ---------------------------------------------------------------------------

def test_retryable_codes_include_502_and_504():
    assert 502 in RETRYABLE_CODES
    assert 504 in RETRYABLE_CODES


# ---------------------------------------------------------------------------
# 4. Fail-fast on 401 — no retry
# ---------------------------------------------------------------------------

def test_fails_immediately_on_401():
    """ClientError(401) must propagate after exactly one call, no retry."""
    err = _make_api_error(401)
    call_count = 0

    def always_fails(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise err

    with patch("course_esum.services.gemini_retry.time.sleep") as mock_sleep:
        with pytest.raises(genai_errors.ClientError):
            with_gemini_retry(always_fails, cfg=_FAST_CFG)

    assert call_count == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Retry-After header is honoured on 429
# ---------------------------------------------------------------------------

def test_respects_retry_after_header():
    """A valid Retry-After: 2 should produce a sleep of ~2 s (bounded)."""
    cfg = GeminiRetryConfig(max_retries=1, base_delay_ms=1, max_delay_ms=30_000)
    err = _make_api_error(429, retry_after="2")
    call_count = 0

    def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise err
        return "done"

    sleep_calls: list[float] = []

    def capture_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    with patch("course_esum.services.gemini_retry.time.sleep", side_effect=capture_sleep):
        result = with_gemini_retry(flaky, cfg=cfg)

    assert result == "done"
    assert len(sleep_calls) == 1
    # Retry-After: 2 -> bounded sleep of 2.0 s
    assert abs(sleep_calls[0] - 2.0) < 0.01


# ---------------------------------------------------------------------------
# 6. Retry-After header is bounded by max_delay_ms
# ---------------------------------------------------------------------------

def test_retry_after_bounded_by_max_delay():
    """A Retry-After value exceeding max_delay_ms is capped."""
    max_delay_ms = 5_000  # 5 s
    err = _make_api_error(429, retry_after="60")  # server asks for 60 s
    result = _extract_retry_after_secs(err, max_delay_ms)
    assert result is not None
    assert result == max_delay_ms / 1000.0  # 5.0 s


# ---------------------------------------------------------------------------
# 7. Malformed Retry-After header falls back gracefully
# ---------------------------------------------------------------------------

def test_malformed_retry_after_falls_back():
    """A non-integer Retry-After value should return None (jitter fallback)."""
    err = _make_api_error(429, retry_after="Wed, 01 Oct 2026 21:00:00 GMT")
    result = _extract_retry_after_secs(err, 30_000)
    assert result is None


# ---------------------------------------------------------------------------
# 8. GeminiRateLimitError raised and chains the last exception
# ---------------------------------------------------------------------------

def test_exhausts_max_retries():
    """After max_retries attempts, GeminiRateLimitError is raised with __cause__."""
    err = _make_api_error(503)
    call_count = 0

    def always_fails(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise err

    with patch("course_esum.services.gemini_retry.time.sleep"):
        with pytest.raises(GeminiRateLimitError) as exc_info:
            with_gemini_retry(always_fails, cfg=_FAST_CFG)

    # max_retries=3 -> 4 total attempts
    assert call_count == _FAST_CFG.max_retries + 1
    # Exception chaining preserved
    assert exc_info.value.__cause__ is err


# ---------------------------------------------------------------------------
# 9. Jitter sleep is always within [0, max_delay_ms] bounds
# ---------------------------------------------------------------------------

def test_jitter_within_bounds():
    """Sleep values from the jitter algorithm must never exceed max_delay_ms."""
    from course_esum.services.gemini_retry import _compute_sleep_secs
    cfg = GeminiRetryConfig(max_retries=10, base_delay_ms=100, max_delay_ms=5_000)
    err = _make_api_error(503)

    for attempt in range(11):
        sleep = _compute_sleep_secs(attempt, cfg, err)
        assert 0.0 <= sleep <= cfg.max_delay_ms / 1000.0, (
            f"Sleep {sleep:.3f}s out of bounds on attempt {attempt}"
        )


# ---------------------------------------------------------------------------
# 10. Async wrapper retries correctly
# ---------------------------------------------------------------------------

def test_async_retries_on_429():
    """async_with_gemini_retry should retry transient errors asynchronously."""
    err = _make_api_error(429)
    call_count = 0

    def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise err
        return "async-ok"

    async def _run():
        with patch("course_esum.services.gemini_retry.asyncio.sleep"):
            return await async_with_gemini_retry(flaky, cfg=_FAST_CFG)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result == "async-ok"
    assert call_count == 2


# ---------------------------------------------------------------------------
# 11. Async fail-fast on non-retryable error
# ---------------------------------------------------------------------------

def test_async_fails_immediately_on_403():
    """async_with_gemini_retry must fail-fast on 403 without sleeping."""
    err = _make_api_error(403)
    call_count = 0

    def always_fails(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise err

    async def _run():
        with patch("course_esum.services.gemini_retry.asyncio.sleep") as mock_sleep:
            with pytest.raises(genai_errors.ClientError):
                await async_with_gemini_retry(always_fails, cfg=_FAST_CFG)
            mock_sleep.assert_not_called()

    asyncio.get_event_loop().run_until_complete(_run())
    assert call_count == 1


# ---------------------------------------------------------------------------
# 12. _is_retryable correctly classifies httpx.TransportError
# ---------------------------------------------------------------------------

def test_is_retryable_httpx_transport_error():
    exc = httpx.ConnectError("connection refused")
    assert _is_retryable(exc) is True


def test_is_retryable_non_transport_error():
    assert _is_retryable(ValueError("bad")) is False
