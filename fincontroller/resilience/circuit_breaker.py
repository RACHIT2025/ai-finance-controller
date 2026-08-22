"""
Circuit Breaker Implementation for Upstream APIs and External LLM Services.
"""

from datetime import datetime, timedelta
from enum import Enum
import functools
from typing import Any, Callable, Optional
from fincontroller.core.exceptions import CircuitBreakerOpenException
from fincontroller.resilience.logger import telemetry


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, blocks calls immediately
    HALF_OPEN = "HALF_OPEN"# Testing recovery


class CircuitBreaker:
    """Protects system from cascading failures when upstream services fail."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_sec: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout_sec)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None

    def record_success(self) -> None:
        if self.state != CircuitState.CLOSED:
            telemetry.push(
                level="INFO",
                component="CIRCUIT_BREAKER",
                message=f"Circuit Breaker '{self.name}' recovered: transitioning to CLOSED.",
                metadata={"circuit": self.name, "state": "CLOSED"},
            )
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    def record_failure(self, error: Exception) -> None:
        from datetime import timezone
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            telemetry.push(
                level="ERROR",
                component="CIRCUIT_BREAKER",
                message=f"Circuit Breaker '{self.name}' tripped OPEN after {self.failure_count} consecutive failures.",
                metadata={"circuit": self.name, "state": "OPEN", "error": str(error)},
            )

    def allow_request(self) -> bool:
        from datetime import timezone
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (datetime.now(timezone.utc) - self.last_failure_time) > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                telemetry.push(
                    level="WARNING",
                    component="CIRCUIT_BREAKER",
                    message=f"Circuit Breaker '{self.name}' testing recovery in HALF_OPEN state.",
                    metadata={"circuit": self.name, "state": "HALF_OPEN"},
                )
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def __call__(self, func: Callable):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            if not self.allow_request():
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN. Fast-failing upstream call."
                )
            try:
                res = func(*args, **kwargs)
                self.record_success()
                return res
            except Exception as e:
                self.record_failure(e)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            if not self.allow_request():
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN. Fast-failing upstream call."
                )
            try:
                res = await func(*args, **kwargs)
                self.record_success()
                return res
            except Exception as e:
                self.record_failure(e)
                raise

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
