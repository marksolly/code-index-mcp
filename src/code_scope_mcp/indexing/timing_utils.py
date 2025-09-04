"""
Timing utilities for profiling database and other operations.
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional


class TimingProfiler:
    """Utility class for timing operations with database profiling."""

    def __init__(self, logger):
        self.logger = logger

    @contextmanager
    def time_operation(self, operation_name: str, is_db_operation: bool = False):
        """Context manager to time an operation."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            if is_db_operation:
                self.logger.add_db_time(duration)
            self.logger.stop_timing(operation_name, is_db_operation)

    def time_function(self, operation_name: str, is_db_operation: bool = False):
        """Decorator to time a function."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                self.logger.start_timing(operation_name)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.logger.stop_timing(operation_name, is_db_operation)
            return wrapper
        return decorator


def profile_db_operation():
    """Decorator for profiling database operations that uses self.logger."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Any:
            operation_name = f"{func.__name__}"
            logger = getattr(self, 'logger', None)
            if logger and hasattr(logger, 'start_timing'):
                logger.start_timing(operation_name)
            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                # Don't call add_db_time here - stop_timing handles it when is_db_operation=True
                if logger and hasattr(logger, 'stop_timing'):
                    logger.stop_timing(operation_name, is_db_operation=True)
        return wrapper
    return decorator


@contextmanager
def time_block(logger, operation_name: str, is_db_operation: bool = False):
    """Simple context manager for timing blocks of code."""
    logger.start_timing(operation_name)
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        if is_db_operation:
            logger.add_db_time(duration)
        logger.stop_timing(operation_name, is_db_operation)
