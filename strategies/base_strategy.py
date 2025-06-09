"""
Base strategy class for block splitting.

This module defines the interface for block splitting strategies.
"""

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken


class BlockSplitStrategy(ABC):
    """Abstract base class for block splitting strategies."""
    
    def __init__(self, tokenizer, renderer, chunk_size: int):
        """
        Initialize the strategy.
        
        Args:
            tokenizer: Function to count tokens
            renderer: Function to render blocks to text
            chunk_size: Maximum chunk size
        """
        self.tokenizer = tokenizer
        self.renderer = renderer
        self.chunk_size = chunk_size
    
    @abstractmethod
    def can_handle(self, block: "BlockToken") -> bool:
        """
        Check if this strategy can handle the given block type.
        
        Args:
            block: The block to check
            
        Returns:
            True if this strategy can handle the block
        """
        pass
    
    @abstractmethod
    def split_block(self, block: "BlockToken") -> List["BlockToken"]:
        """
        Split a block into smaller blocks.
        
        Args:
            block: The block to split
            
        Returns:
            List of split blocks
        """
        pass
    
    def get_token_count(self, text: str) -> int:
        """
        Get token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        try:
            return len(self.tokenizer(text))
        except Exception:
            # Fallback to character-based estimation
            return max(1, len(text) // 3)
    
    def render_block(self, block: "BlockToken") -> str:
        """
        Render a block to text.
        
        Args:
            block: Block to render
            
        Returns:
            Rendered text
        """
        return self.renderer(block) 