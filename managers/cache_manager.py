"""
Cache management for chunking operations.

This module provides efficient caching for token counts and rendered content
to improve performance during document processing.
"""

import logging
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching for token counts and rendered content.
    
    This class provides efficient caching mechanisms to avoid repeated
    expensive operations like tokenization and rendering during document
    splitting operations.
    """
    
    def __init__(self, max_cache_size: int = 10000):
        """
        Initialize cache manager.
        
        Args:
            max_cache_size: Maximum number of items to cache before cleanup
        """
        self._token_cache: Dict[str, int] = {}
        self._render_cache: Dict[int, str] = {}  # Using object id as key
        self._max_cache_size = max_cache_size
        
        logger.debug(f"CacheManager initialized with max_size={max_cache_size}")
    
    def get_token_count(self, content: str, tokenizer: Callable) -> int:
        """
        Get cached token count for content.
        
        Args:
            content: Content to tokenize
            tokenizer: Tokenizer function
            
        Returns:
            Number of tokens in content
        """
        if content not in self._token_cache:
            try:
                self._token_cache[content] = len(tokenizer(content))
            except Exception as e:
                logger.warning(f"Tokenization failed, using character-based fallback: {e}")
                # Fallback to conservative character-based estimate
                self._token_cache[content] = max(1, len(content) // 3)
            
            # Check cache size and cleanup if needed
            self._check_and_cleanup_token_cache()
        
        return self._token_cache[content]
    
    def get_rendered_content(self, block: Any, renderer: Callable) -> str:
        """
        Get cached rendered content for block.
        
        Args:
            block: Block to render
            renderer: Renderer function
            
        Returns:
            Rendered string content
        """
        block_id = id(block)
        if block_id not in self._render_cache:
            try:
                self._render_cache[block_id] = renderer(block)
            except Exception as e:
                logger.error(f"Rendering failed for block {block.__class__.__name__}: {e}")
                # Return empty string as fallback
                self._render_cache[block_id] = ""
            
            # Check cache size and cleanup if needed
            self._check_and_cleanup_render_cache()
        
        return self._render_cache[block_id]
    
    def clear_all(self) -> None:
        """Clear all caches to free memory."""
        token_count = len(self._token_cache)
        render_count = len(self._render_cache)
        
        self._token_cache.clear()
        self._render_cache.clear()
        
        logger.debug(f"Cleared caches: {token_count} token entries, {render_count} render entries")
    
    def clear_token_cache(self) -> None:
        """Clear only the token cache."""
        count = len(self._token_cache)
        self._token_cache.clear()
        logger.debug(f"Cleared token cache: {count} entries")
    
    def clear_render_cache(self) -> None:
        """Clear only the render cache."""
        count = len(self._render_cache)
        self._render_cache.clear()
        logger.debug(f"Cleared render cache: {count} entries")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'token_cache_size': len(self._token_cache),
            'render_cache_size': len(self._render_cache),
            'max_cache_size': self._max_cache_size,
            'token_cache_memory_estimate': sum(len(k) + 24 for k in self._token_cache.keys()),  # Rough estimate
            'render_cache_memory_estimate': sum(len(v) + 24 for v in self._render_cache.values())
        }
    
    def _check_and_cleanup_token_cache(self) -> None:
        """Check token cache size and cleanup if needed."""
        if len(self._token_cache) > self._max_cache_size:
            # Keep only the most recent half of entries (simple LRU approximation)
            items = list(self._token_cache.items())
            keep_count = self._max_cache_size // 2
            self._token_cache = dict(items[-keep_count:])
            logger.debug(f"Token cache cleanup: kept {keep_count} entries")
    
    def _check_and_cleanup_render_cache(self) -> None:
        """Check render cache size and cleanup if needed."""
        if len(self._render_cache) > self._max_cache_size:
            # Keep only the most recent half of entries
            items = list(self._render_cache.items())
            keep_count = self._max_cache_size // 2
            self._render_cache = dict(items[-keep_count:])
            logger.debug(f"Render cache cleanup: kept {keep_count} entries")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clear caches."""
        self.clear_all() 