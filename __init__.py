"""
Production-grade chunking library for intelligent text splitting.

This library provides AST-based Markdown text splitting with advanced features
including metadata awareness, table processing, and HTML handling.
"""

__version__ = "1.0.0"
__author__ = "Chunking Library Team"
__description__ = "Production-grade intelligent text chunking library"

# Import from new modular structure
try:
    # Try importing from new refactored modules first
    from .core.base import MetadataAwareTextSplitter
    from .core.splitter import AstMarkdownSplitter
    from .core.exceptions import (
        SplitException,
        ChunkingError,
        InvalidConfigurationError,
        TokenizationError,
        HtmlProcessingError,
        DocumentParsingError,
        RenderingError,
    )
    from .managers.cache_manager import CacheManager
    from .strategies import (
        BlockSplitStrategy,
        ParagraphSplitStrategy,
        TableSplitStrategy,
        ListSplitStrategy,
        HtmlSplitStrategy,
        CodeSplitStrategy,
    )
    
    # Flag to indicate we're using the new modular structure
    _USING_REFACTORED_MODULES = True
    
except ImportError:
    # Fallback to original chunking.py for backward compatibility
    try:
        from .chunking import (
            AstMarkdownSplitter,
            MetadataAwareTextSplitter,
            SplitException,
            ChunkingError,
            InvalidConfigurationError,
            TokenizationError,
        )
        _USING_REFACTORED_MODULES = False
    except ImportError:
        # If neither works, raise a clear error
        raise ImportError(
            "Could not import chunking modules. Please ensure the chunking library is properly installed."
        )

# Always import config and utils (these are stable)
from .config import (
    ChunkingConfig,
    get_config,
    CONFIG,
)

from .utils import (
    setup_logging,
    retry_on_exception,
    timer,
    validate_input,
    estimate_tokens,
    format_chunk_stats,
    ChunkingMetrics,
    metrics,
)

# Public API - core classes
__all__ = [
    # Main classes
    "AstMarkdownSplitter",
    "MetadataAwareTextSplitter",
    
    # Exceptions
    "SplitException",
    "ChunkingError", 
    "InvalidConfigurationError",
    "TokenizationError",
    
    # Configuration
    "ChunkingConfig",
    "get_config",
    "CONFIG",
    
    # Utilities
    "setup_logging",
    "retry_on_exception", 
    "timer",
    "validate_input",
    "estimate_tokens",
    "format_chunk_stats",
    "ChunkingMetrics",
    "metrics",
    
    # Metadata
    "__version__",
    "__author__",
    "__description__",
]

# Add refactored modules to public API if available
if _USING_REFACTORED_MODULES:
    __all__.extend([
        # Additional exceptions from refactored modules
        "HtmlProcessingError",
        "DocumentParsingError", 
        "RenderingError",
        
        # Managers and strategies (advanced API)
        "CacheManager",
        "BlockSplitStrategy",
        "ParagraphSplitStrategy",
        "TableSplitStrategy", 
        "ListSplitStrategy",
        "HtmlSplitStrategy",
        "CodeSplitStrategy",
    ])

# Initialize logging on import
setup_logging()

# Optional: Print which modules are being used (for debugging)
import logging
logger = logging.getLogger(__name__)
if _USING_REFACTORED_MODULES:
    logger.debug("Using refactored modular chunking structure")
else:
    logger.debug("Using legacy chunking.py structure") 