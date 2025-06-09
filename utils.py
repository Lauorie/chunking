"""
Utility functions for chunking operations.

This module provides helper functions, decorators, and utilities
to support the chunking functionality.
"""

import time
import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union
from contextlib import contextmanager

from .config import CONFIG

logger = logging.getLogger(__name__)

T = TypeVar('T')


def setup_logging(level: Optional[str] = None, format_string: Optional[str] = None) -> None:
    """
    Set up logging configuration for the chunking module.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
    """
    log_level = level or CONFIG.log_level
    log_format = format_string or CONFIG.log_format
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        force=True
    )
    
    logger.info(f"Logging configured with level: {log_level}")


def retry_on_exception(
    max_retries: int = None,
    delay: float = None,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator to retry function execution on specified exceptions.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
        exceptions: Tuple of exception types to catch and retry on
        
    Returns:
        Decorated function with retry logic
    """
    _max_retries = max_retries or CONFIG.max_retries
    _delay = delay or CONFIG.retry_delay
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < _max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {_delay} seconds..."
                        )
                        time.sleep(_delay)
                    else:
                        logger.error(
                            f"All {_max_retries + 1} attempts failed for {func.__name__}"
                        )
            
            # Re-raise the last exception if all retries failed
            raise last_exception
            
        return wrapper
    return decorator


@contextmanager
def timer(operation_name: str = "Operation"):
    """
    Context manager to measure execution time.
    
    Args:
        operation_name: Name of the operation being timed
        
    Yields:
        None
        
    Example:
        with timer("Text processing"):
            # Some time-consuming operation
            process_text(text)
    """
    start_time = time.time()
    logger.debug(f"{operation_name} started")
    
    try:
        yield
    finally:
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"{operation_name} completed in {duration:.2f} seconds")


def validate_input(
    text: Any,
    metadata: Any = None,
    allow_empty: bool = False
) -> tuple[str, Optional[str]]:
    """
    Validate and sanitize input for chunking operations.
    
    Args:
        text: Input text to validate
        metadata: Optional metadata to validate
        allow_empty: Whether to allow empty text
        
    Returns:
        Tuple of (validated_text, validated_metadata)
        
    Raises:
        TypeError: If input types are incorrect
        ValueError: If input values are invalid
    """
    # Validate text
    if not isinstance(text, str):
        raise TypeError(f"Text must be a string, got {type(text)}")
    
    if not allow_empty and not text.strip():
        raise ValueError("Text cannot be empty")
    
    # Validate metadata
    validated_metadata = None
    if metadata is not None:
        if not isinstance(metadata, str):
            raise TypeError(f"Metadata must be a string, got {type(metadata)}")
        validated_metadata = metadata
    
    return text, validated_metadata


def estimate_tokens(text: str, tokenizer: Optional[Callable] = None) -> int:
    """
    Estimate the number of tokens in a text.
    
    Args:
        text: Text to estimate tokens for
        tokenizer: Optional custom tokenizer function
        
    Returns:
        Estimated number of tokens
    """
    if tokenizer:
        try:
            return len(tokenizer(text))
        except Exception as e:
            logger.warning(f"Custom tokenizer failed: {e}. Using fallback.")
    
    # Fallback to character-based estimation
    return len(text)


def format_chunk_stats(chunks: list) -> str:
    """
    Format statistics about generated chunks.
    
    Args:
        chunks: List of text chunks
        
    Returns:
        Formatted statistics string
    """
    if not chunks:
        return "No chunks generated"
    
    total_chunks = len(chunks)
    chunk_lengths = [len(chunk) for chunk in chunks]
    
    stats = {
        "total_chunks": total_chunks,
        "total_chars": sum(chunk_lengths),
        "avg_chunk_length": sum(chunk_lengths) / total_chunks,
        "min_chunk_length": min(chunk_lengths),
        "max_chunk_length": max(chunk_lengths),
    }
    
    return (
        f"Chunks: {stats['total_chunks']}, "
        f"Total chars: {stats['total_chars']}, "
        f"Avg length: {stats['avg_chunk_length']:.1f}, "
        f"Range: {stats['min_chunk_length']}-{stats['max_chunk_length']}"
    )


def safe_divide(a: Union[int, float], b: Union[int, float], default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default value on division by zero.
    
    Args:
        a: Numerator
        b: Denominator
        default: Value to return if division by zero
        
    Returns:
        Result of division or default value
    """
    try:
        return a / b if b != 0 else default
    except (TypeError, ZeroDivisionError):
        return default


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


class ChunkingMetrics:
    """Class to collect and track chunking performance metrics."""
    
    def __init__(self):
        """Initialize metrics collection."""
        self.reset()
    
    def reset(self) -> None:
        """Reset all metrics to initial state."""
        self._processing_times = []
        self._chunk_counts = []
        self._error_counts = {"tokenization": 0, "parsing": 0, "splitting": 0, "other": 0}
        self._total_chars_processed = 0
    
    def record_processing_time(self, duration: float) -> None:
        """Record processing time for an operation."""
        self._processing_times.append(duration)
    
    def record_chunks_generated(self, count: int) -> None:
        """Record number of chunks generated."""
        self._chunk_counts.append(count)
    
    def record_error(self, error_type: str) -> None:
        """Record an error occurrence."""
        if error_type in self._error_counts:
            self._error_counts[error_type] += 1
        else:
            self._error_counts["other"] += 1
    
    def record_chars_processed(self, count: int) -> None:
        """Record number of characters processed."""
        self._total_chars_processed += count
    
    def get_summary(self) -> dict:
        """
        Get summary of collected metrics.
        
        Returns:
            Dictionary containing metric summaries
        """
        total_operations = len(self._processing_times)
        
        if total_operations == 0:
            return {"message": "No operations recorded"}
        
        avg_processing_time = sum(self._processing_times) / total_operations
        total_chunks = sum(self._chunk_counts)
        avg_chunks_per_operation = total_chunks / total_operations if total_operations > 0 else 0
        
        return {
            "total_operations": total_operations,
            "avg_processing_time": round(avg_processing_time, 3),
            "total_chunks_generated": total_chunks,
            "avg_chunks_per_operation": round(avg_chunks_per_operation, 1),
            "total_chars_processed": self._total_chars_processed,
            "error_counts": self._error_counts.copy(),
            "throughput_chars_per_second": safe_divide(
                self._total_chars_processed, 
                sum(self._processing_times)
            )
        }


# Global metrics instance
metrics = ChunkingMetrics() 