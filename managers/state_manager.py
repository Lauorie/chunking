"""
Document splitting state management.

This module provides state management for document splitting operations.
"""

import logging
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, Heading

logger = logging.getLogger(__name__)


class DocumentSplitState:
    """
    Manages state during document splitting operations.
    
    This class tracks chunks, headers, and current block accumulation
    during the document splitting process.
    """
    
    def __init__(self):
        """Initialize the document split state."""
        self.chunks: List[str] = []
        self.headers: Dict[int, Tuple["BlockToken", int]] = {}  # level -> (block, size)
        self.current_blocks: List[str] = []
        self.current_size: int = 0
        
        logger.debug("DocumentSplitState initialized")
    
    def add_block(self, content: str, size: int) -> None:
        """
        Add a block to the current chunk.
        
        Args:
            content: Block content to add
            size: Size of the block in tokens
        """
        self.current_blocks.append(content)
        self.current_size += size + 2  # +2 for paragraph separation
        
        logger.debug(f"Added block: {size} tokens, total: {self.current_size}")
    
    def flush_chunk(self) -> None:
        """Flush the current chunk to the chunks list."""
        if self.current_blocks:
            chunk_content = "\n\n".join(self.current_blocks).strip()
            if chunk_content:  # Only add non-empty chunks
                self.chunks.append(chunk_content)
                logger.debug(f"Flushed chunk: {len(chunk_content)} chars, {self.current_size} tokens")
            
            self.current_blocks = []
            self.current_size = 0
    
    def update_headers(self, heading: "Heading", size: int) -> None:
        """
        Update headers tracking with new heading.
        
        Args:
            heading: The heading block
            size: Size of the heading in tokens
        """
        self.headers[heading.level] = (heading, size)
        
        # Remove deeper level headers
        levels_to_remove = [level for level in self.headers.keys() if level > heading.level]
        for level in levels_to_remove:
            del self.headers[level]
        
        logger.debug(f"Updated headers: level {heading.level}, removed levels {levels_to_remove}")
    
    def get_header_content(self, renderer, max_size: int) -> Tuple[List[str], int]:
        """
        Get header content that fits within max_size.
        
        Args:
            renderer: Function to render blocks to text
            max_size: Maximum size allowed for headers
            
        Returns:
            Tuple of (header_content_list, total_header_size)
        """
        header_content = []
        header_size = 0
        
        for level in sorted(self.headers.keys()):
            header_block, cached_size = self.headers[level]
            
            # Use cached size if available, otherwise render and calculate
            try:
                header_text = renderer(header_block)
                header_tokens = cached_size if cached_size > 0 else len(header_text) // 3
            except Exception as e:
                logger.warning(f"Failed to render header at level {level}: {e}")
                continue
            
            if header_size + header_tokens + 2 <= max_size:
                header_content.append(header_text)
                header_size += header_tokens + 2  # +2 for separation
            else:
                break
        
        logger.debug(f"Generated headers: {len(header_content)} headers, {header_size} tokens")
        return header_content, header_size
    
    def calculate_header_size(self) -> int:
        """
        Calculate total size of current headers.
        
        Returns:
            Total size of all current headers
        """
        total_size = 0
        for level in sorted(self.headers.keys()):
            _, size = self.headers[level]
            total_size += size + 2  # +2 for separation
        
        return total_size
    
    def get_header_blocks(self) -> List["BlockToken"]:
        """
        Get list of current header blocks.
        
        Returns:
            List of header blocks in order
        """
        header_blocks = []
        for level in sorted(self.headers.keys()):
            block, _ = self.headers[level]
            header_blocks.append(block)
        
        return header_blocks
    
    def can_fit_block(self, block_size: int, max_chunk_size: int) -> bool:
        """
        Check if a block can fit in the current chunk.
        
        Args:
            block_size: Size of the block to check
            max_chunk_size: Maximum allowed chunk size
            
        Returns:
            True if the block can fit
        """
        return self.current_size + block_size <= max_chunk_size
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get current state statistics.
        
        Returns:
            Dictionary with state statistics
        """
        return {
            'total_chunks': len(self.chunks),
            'current_blocks': len(self.current_blocks),
            'current_size': self.current_size,
            'header_levels': len(self.headers),
            'avg_chunk_size': sum(len(chunk) for chunk in self.chunks) // max(1, len(self.chunks))
        }
    
    def reset(self) -> None:
        """Reset the state for processing a new document."""
        stats = self.get_stats()
        
        self.chunks = []
        self.headers = {}
        self.current_blocks = []
        self.current_size = 0
        
        logger.debug(f"State reset. Previous stats: {stats}") 