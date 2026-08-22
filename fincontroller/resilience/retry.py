"""
Asynchronous Retry Manager with Exponential Backoff and Full Jitter.
"""

import asyncio
import functools
import random
from typing import Any, Callable, Tuple, Type
from fincontroller.resilience.logger import get_logger, telemetry

logger = get_logger("resilience.retry")


def async_retry(
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator for retrying async operations with exponential backoff and jitter.
    Logs retry events to the visible telemetry buffer.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_err = None

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt == max_retries:
                        telemetry.push(
                            level="ERROR",
                            component="RETRY_EXHAUSTED",
                            message=f"Function {func.__name__} failed permanently after {max_retries} attempts: {str(e)}",
                            metadata={"function": func.__name__, "attempts": attempt, "error": str(e)},
                        )
                        raise

                    actual_delay = delay * (random.uniform(0.8, 1.2) if jitter else 1.0)
                    telemetry.push(
                        level="WARNING",
                        component="RETRY_BACKOFF",
                        message=f"Attempt {attempt}/{max_retries} failed for {func.__name__} ({str(e)}). Retrying in {actual_delay:.2f}s...",
                        metadata={"function": func.__name__, "attempt": attempt, "delay": round(actual_delay, 2)},
                    )
                    await asyncio.sleep(actual_delay)
                    delay *= backoff_factor

            raise last_err
        return wrapper
    return decorator
