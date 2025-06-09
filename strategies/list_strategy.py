"""
List splitting strategy.

This module handles the splitting of list blocks.
"""

import logging
from typing import List, TYPE_CHECKING

from .base_strategy import BlockSplitStrategy

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, List as ListBlock

logger = logging.getLogger(__name__)


class ListSplitStrategy(BlockSplitStrategy):
    """Strategy for splitting list blocks."""
    
    def can_handle(self, block: "BlockToken") -> bool:
        """Check if this is a list block."""
        from mistletoe.block_token import List as ListBlock
        return isinstance(block, ListBlock)
    
    def split_block(self, block: "ListBlock") -> List["BlockToken"]:
        """
        Split a list block into smaller lists.
        
        Args:
            block: The list block to split
            
        Returns:
            List of split list blocks
        """
        try:
            if not hasattr(block, 'children') or not block.children:
                logger.warning("List block has no children, returning as is")
                return [block]
            
            # Check if list is small enough to keep as is
            list_text = self.render_block(block)
            list_tokens = self.get_token_count(list_text)
            
            if list_tokens <= self.chunk_size:
                return [block]
            
            # Split list by items
            return self._split_list_by_items(block)
            
        except Exception as e:
            logger.error(f"List splitting failed: {e}")
            return [block]
    
    def _split_list_by_items(self, list_block: "ListBlock") -> List["BlockToken"]:
        """Split list by grouping items that fit within chunk size."""
        try:
            from mistletoe.block_token import List as ListBlock
            
            result_lists = []
            current_items = []
            current_size = 0
            
            # Estimate overhead for list structure
            list_overhead = 50  # Conservative estimate
            
            for item in list_block.children:
                if item is None:
                    continue
                    
                try:
                    item_text = self.render_block(item)
                    item_tokens = self.get_token_count(item_text)
                except Exception as e:
                    logger.warning(f"Failed to render list item: {e}")
                    continue
                
                # Check if adding this item would exceed chunk size
                if current_size + item_tokens + list_overhead > self.chunk_size and current_items:
                    # Create new list with current items
                    new_list = self._create_list_with_items(list_block, current_items)
                    if new_list:
                        result_lists.append(new_list)
                    
                    current_items = [item]
                    current_size = item_tokens
                else:
                    current_items.append(item)
                    current_size += item_tokens
            
            # Add remaining items as final list
            if current_items:
                new_list = self._create_list_with_items(list_block, current_items)
                if new_list:
                    result_lists.append(new_list)
            
            return result_lists if result_lists else [list_block]
            
        except Exception as e:
            logger.error(f"Failed to split list by items: {e}")
            return [list_block]
    
    def _create_list_with_items(self, original_list: "ListBlock", items: List) -> "ListBlock":
        """Create a new list with specified items."""
        try:
            from mistletoe.block_token import List as ListBlock
            
            if not items:
                return None
            
            # Create new list with items directly
            new_list = ListBlock(list(items) if items else [])
            
            # Copy properties from original list after creation
            try:
                if hasattr(original_list, 'start'):
                    new_list.start = original_list.start
                if hasattr(original_list, 'loose'):
                    new_list.loose = original_list.loose
                if hasattr(original_list, 'tight'):
                    new_list.tight = original_list.tight
            except Exception as e:
                logger.warning(f"Failed to copy list properties: {e}")
            
            return new_list
            
        except Exception as e:
            logger.error(f"Failed to create list with items: {e}")
            return None 