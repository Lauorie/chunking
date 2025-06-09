"""
Code block splitting strategy.

This module handles the splitting of code blocks.
"""

import logging
import re
from typing import List, TYPE_CHECKING

from .base_strategy import BlockSplitStrategy

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, BlockCode

logger = logging.getLogger(__name__)


class CodeSplitStrategy(BlockSplitStrategy):
    """Strategy for splitting code blocks."""
    
    def can_handle(self, block: "BlockToken") -> bool:
        """Check if this is a code block."""
        from mistletoe.block_token import BlockCode
        return isinstance(block, BlockCode)
    
    def split_block(self, block: "BlockCode") -> List["BlockToken"]:
        """
        Split a code block into smaller blocks.
        
        Args:
            block: The code block to split
            
        Returns:
            List of split blocks
        """
        try:
            # Get code content and size
            code_text = self.render_block(block)
            code_tokens = self.get_token_count(code_text)
            
            if code_tokens <= self.chunk_size:
                return [block]
            
            # For large code blocks, try to split by logical units
            return self._split_code_block(block)
            
        except Exception as e:
            logger.error(f"Code block splitting failed: {e}")
            return [block]
    
    def _split_code_block(self, code_block: "BlockCode") -> List["BlockToken"]:
        """Split code block into smaller parts."""
        try:
            from mistletoe.block_token import BlockCode, Document
            
            # Get code content
            if hasattr(code_block, 'content'):
                content = code_block.content
            elif hasattr(code_block, 'children') and code_block.children:
                # Extract text from children
                content = '\n'.join(str(child) for child in code_block.children)
            else:
                logger.warning("Code block has no content")
                return [code_block]
            
            # Get language info
            language = getattr(code_block, 'language', '') or ''
            
            # Split by logical units (functions, classes, etc.) for programming languages
            if self._is_programming_language(language):
                split_blocks = self._split_by_logical_units(content, language, code_block)
                if len(split_blocks) > 1:
                    return split_blocks
            
            # Fall back to line-based splitting
            return self._split_by_lines(content, language, code_block)
            
        except Exception as e:
            logger.error(f"Failed to split code block: {e}")
            return [code_block]
    
    def _is_programming_language(self, language: str) -> bool:
        """Check if this is a programming language that can be split logically."""
        programming_languages = {
            'python', 'java', 'javascript', 'typescript', 'c', 'cpp', 'c++',
            'csharp', 'c#', 'go', 'rust', 'php', 'ruby', 'swift', 'kotlin'
        }
        return language.lower() in programming_languages
    
    def _split_by_logical_units(self, content: str, language: str, original_block: "BlockCode") -> List["BlockToken"]:
        """Split code by logical units like functions or classes."""
        try:
            from mistletoe.block_token import BlockCode
            
            lines = content.split('\n')
            chunks = []
            current_chunk = []
            current_size = 0
            
            # Simple heuristic: split on function/class definitions
            function_patterns = {
                'python': [r'^def ', r'^class ', r'^async def '],
                'javascript': [r'^function ', r'^class ', r'^const .* = \(', r'^async function '],
                'java': [r'^(public|private|protected).*\{', r'^class ', r'^interface '],
                'c': [r'^\w+.*\{', r'^struct ', r'^typedef '],
                'cpp': [r'^\w+.*\{', r'^class ', r'^struct '],
            }
            
            patterns = function_patterns.get(language.lower(), [r'^\w+.*\{'])
            
            for line in lines:
                line_tokens = self.get_token_count(line)
                
                # Check if this line starts a new logical unit
                is_new_unit = any(re.match(pattern, line.strip()) for pattern in patterns)
                
                # If this would make chunk too large, or it's a new unit, flush current chunk
                if ((current_size + line_tokens > self.chunk_size and current_chunk) or 
                    (is_new_unit and current_chunk)):
                    
                    chunk_content = '\n'.join(current_chunk)
                    new_block = self._create_code_block(chunk_content, language, original_block)
                    if new_block:
                        chunks.append(new_block)
                    
                    current_chunk = [line]
                    current_size = line_tokens
                else:
                    current_chunk.append(line)
                    current_size += line_tokens
            
            # Add the last chunk
            if current_chunk:
                chunk_content = '\n'.join(current_chunk)
                new_block = self._create_code_block(chunk_content, language, original_block)
                if new_block:
                    chunks.append(new_block)
            
            return chunks if chunks else [original_block]
            
        except Exception as e:
            logger.error(f"Failed to split by logical units: {e}")
            return [original_block]
    
    def _split_by_lines(self, content: str, language: str, original_block: "BlockCode") -> List["BlockToken"]:
        """Split code block by lines when logical splitting fails."""
        try:
            from mistletoe.block_token import BlockCode
            
            lines = content.split('\n')
            chunks = []
            current_chunk = []
            current_size = 0
            
            for line in lines:
                line_tokens = self.get_token_count(line)
                
                # If adding this line would exceed chunk size, flush current chunk
                if current_size + line_tokens > self.chunk_size and current_chunk:
                    chunk_content = '\n'.join(current_chunk)
                    new_block = self._create_code_block(chunk_content, language, original_block)
                    if new_block:
                        chunks.append(new_block)
                    
                    current_chunk = [line]
                    current_size = line_tokens
                else:
                    current_chunk.append(line)
                    current_size += line_tokens
            
            # Add the last chunk
            if current_chunk:
                chunk_content = '\n'.join(current_chunk)
                new_block = self._create_code_block(chunk_content, language, original_block)
                if new_block:
                    chunks.append(new_block)
            
            return chunks if chunks else [original_block]
            
        except Exception as e:
            logger.error(f"Failed to split by lines: {e}")
            return [original_block]
    
    def _create_code_block(self, content: str, language: str, original_block: "BlockCode") -> "BlockCode":
        """Create a new code block with specified content."""
        try:
            from mistletoe.block_token import BlockCode
            
            if not content.strip():
                return None
            
            # Create new code block
            new_block = BlockCode(content)
            
            # Copy properties from original block
            if hasattr(original_block, 'language'):
                new_block.language = original_block.language
            elif language:
                new_block.language = language
            
            return new_block
            
        except Exception as e:
            logger.error(f"Failed to create code block: {e}")
            return None 