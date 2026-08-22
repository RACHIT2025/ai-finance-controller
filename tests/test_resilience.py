"""
Unit tests for async retry, circuit breaker, and resilience telemetry.
"""

import asyncio
import pytest
from fincontroller.core.exceptions import CircuitBreakerOpenException
from fincontroller.resilience.circuit_breaker import CircuitBreaker, CircuitState
from fincontroller.resilience.logger import telemetry
from fincontroller.resilience.retry import async_retry


@pytest.mark.asyncio
async def test_async_retry_success_after_failure():
    attempts = 0

    @async_retry(max_retries=3, initial_delay=0.01, backoff_factor=1.0)
    async def flaky_api_call():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Temporary upstream drop")
        return "SUCCESS"

    result = await flaky_api_call()
    assert result == "SUCCESS"
    assert attempts == 3


@pytest.mark.asyncio
async def test_async_retry_exhaustion():
    @async_retry(max_retries=2, initial_delay=0.01)
    async def always_failing():
        raise TimeoutError("Endpoint timeout")

    with pytest.raises(TimeoutError):
        await always_failing()


def test_circuit_breaker_tripping():
    cb = CircuitBreaker("test_service", failure_threshold=2, recovery_timeout_sec=0.1)
    assert cb.state == CircuitState.CLOSED

    @cb
    def failing_func():
        raise RuntimeError("Service unavailable")

    with pytest.raises(RuntimeError):
        failing_func()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    with pytest.raises(RuntimeError):
        failing_func()
    # Tripped to OPEN
    assert cb.state == CircuitState.OPEN

    # Subsequent call immediately fast-fails with CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        failing_func()


def test_telemetry_event_logging():
    telemetry.clear()
    telemetry.push("WARNING", "TEST_COMP", "Test warning event", {"key": "val"})
    events = telemetry.get_recent(5)
    assert len(events) == 1
    assert events[0]["component"] == "TEST_COMP"
    assert events[0]["level"] == "WARNING"
