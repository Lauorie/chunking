"""
HTML splitting strategy.

This module handles the splitting of HTML blocks.
"""

import logging
from typing import List, TYPE_CHECKING

from .base_strategy import BlockSplitStrategy

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, HtmlBlock

logger = logging.getLogger(__name__)


class HtmlSplitStrategy(BlockSplitStrategy):
    """Strategy for splitting HTML blocks."""
    
    def can_handle(self, block: "BlockToken") -> bool:
        """Check if this is an HTML block."""
        from mistletoe.block_token import HtmlBlock
        return isinstance(block, HtmlBlock)
    
    def split_block(self, block: "HtmlBlock") -> List["BlockToken"]:
        """
        Split an HTML block into smaller blocks.
        
        Args:
            block: The HTML block to split
            
        Returns:
            List of split blocks
        """
        try:
            # For now, use simple approach
            html_text = self.render_block(block)
            html_tokens = self.get_token_count(html_text)
            
            if html_tokens <= self.chunk_size:
                return [block]
            
            # Try to extract text content and create paragraphs
            return self._extract_html_content(block)
            
        except Exception as e:
            logger.error(f"HTML splitting failed: {e}")
            return [block]
    
    def _extract_html_content(self, html_block: "HtmlBlock") -> List["BlockToken"]:
        """Extract content from HTML block and create paragraphs."""
        try:
            from mistletoe.block_token import Document
            
            # Simple approach: try to extract text content
            html_content = getattr(html_block, 'content', '')
            
            if not html_content:
                return [html_block]
            
            # Remove HTML tags (simple regex approach)
            import re
            text_content = re.sub(r'<[^>]+>', ' ', html_content)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            if text_content:
                # Create document from extracted text
                doc = Document(text_content)
                return doc.children if doc.children else [html_block]
            
            return [html_block]
            
        except Exception as e:
            logger.error(f"Failed to extract HTML content: {e}")
            return [html_block] 