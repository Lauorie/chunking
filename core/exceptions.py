"""
Exception classes for chunking operations.

This module contains all custom exceptions used throughout the chunking system.
"""


class SplitException(Exception):
    """Exception raised when text splitting fails."""
    pass


class ChunkingError(Exception):
    """Base exception for chunking operations."""
    pass


class InvalidConfigurationError(ChunkingError):
    """Exception raised when configuration is invalid."""
    pass


class TokenizationError(ChunkingError):
    """Exception raised when tokenization fails."""
    pass


class HtmlProcessingError(ChunkingError):
    """Exception raised when HTML processing fails."""
    pass


class DocumentParsingError(ChunkingError):
    """Exception raised when document parsing fails."""
    pass


class RenderingError(ChunkingError):
    """Exception raised when block rendering fails."""
    pass 