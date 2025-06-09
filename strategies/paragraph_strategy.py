"""
Paragraph splitting strategy.

This module handles the splitting of paragraph blocks.
"""

import logging
from typing import List, TYPE_CHECKING

from .base_strategy import BlockSplitStrategy
from ..config import CONFIG
from ..core.exceptions import DocumentParsingError

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, Paragraph, Document

logger = logging.getLogger(__name__)


class ParagraphSplitStrategy(BlockSplitStrategy):
    """Strategy for splitting paragraph blocks."""
    
    def can_handle(self, block: "BlockToken") -> bool:
        """Check if this is a paragraph block."""
        from mistletoe.block_token import Paragraph
        return isinstance(block, Paragraph)
    
    def split_block(self, block: "Paragraph") -> List["BlockToken"]:
        """
        Split a paragraph block into smaller blocks.
        
        Args:
            block: The paragraph block to split
            
        Returns:
            List of split paragraph blocks
        """
        text = self.render_block(block)
        lines = text.split('\n')
        
        content_type = self._detect_special_content_type(text, lines)
        
        if content_type != 'normal':
            logger.info(f"Detected {content_type} content with {len(text)} characters, applying forced splitting")
            return self._force_split_by_lines(text, block)
        
        # Normal paragraph processing for non-special content
        return self._split_normal_paragraph(text, block)
    
    def _detect_special_content_type(self, text: str, lines: List[str]) -> str:
        """
        Detect special content types that require forced splitting.
        
        Args:
            text: Full text content
            lines: Lines of the text
            
        Returns:
            Content type: 'code', 'table_like', 'parameter_config', or 'normal'
        """
        # Check if this is actually a code block that mistletoe didn't recognize properly
        if '[code]' in text and '[/code]' in text:
            return 'code'
        
        # Check if this is a table-like content (many lines with | separators)
        table_like_lines = sum(1 for line in lines if '|' in line and len(line.strip()) > 10)
        if table_like_lines > len(lines) * 0.7 and len(lines) > 10:
            return 'table_like'
        
        # Check for parameter configuration content (many lines with parameter descriptions)
        parameter_keywords = ['参数', 'Parameter', 'Config', 'Switch', 'Offset', 'Threshold', '门限', '开关', '配置']
        parameter_lines = sum(1 for line in lines if any(keyword in line for keyword in parameter_keywords))
        if parameter_lines > len(lines) * 0.5 and len(lines) > 15:
            return 'parameter_config'
        
        return 'normal'
    
    def _force_split_by_lines(self, text: str, original_block: "BlockToken") -> List["BlockToken"]:
        """
        Force split content by lines when normal splitting fails.
        
        Args:
            text: Text content to split
            original_block: Original block token
            
        Returns:
            List of split blocks
        """
        lines = text.split('\n')
        current_chunk = []
        current_size = 0
        result_chunks = []
        
        # Split by lines first
        for line in lines:
            try:
                line_tokens = self.get_token_count(line + '\n')
            except (TypeError, ValueError, AttributeError):
                line_tokens = len(line) // 4  # Fallback estimation
            
            if current_size + line_tokens > self.chunk_size and current_chunk:
                # Finalize current chunk
                chunk_text = '\n'.join(current_chunk)
                block = self._create_document_from_text(chunk_text)
                if block:
                    result_chunks.append(block)
                
                current_chunk = [line]
                current_size = line_tokens
            else:
                current_chunk.append(line)
                current_size += line_tokens
        
        # Add the last chunk
        if current_chunk:
            chunk_text = '\n'.join(current_chunk)
            block = self._create_document_from_text(chunk_text)
            if block:
                result_chunks.append(block)
        
        # Process oversized chunks with character-based splitting
        return self._process_oversized_chunks(result_chunks, original_block)
    
    def _split_normal_paragraph(self, text: str, original_block: "BlockToken") -> List["BlockToken"]:
        """
        Split normal paragraph content using sentence-based splitting.
        
        Args:
            text: Text content to split
            original_block: Original block token
            
        Returns:
            List of split blocks
        """
        sentences = self._split_text_into_sentences(text)
        if not sentences:
            return []

        split_idx, tokens = self._find_sentence_split_point(sentences)
        pair = self._create_sentence_pair(sentences, split_idx, text, original_block)
        
        # If pair is empty, it means we need forced splitting
        if not pair:
            return self._force_split_by_lines(text, original_block)
        
        result = []
        for part in pair:
            if part.strip():
                block = self._create_document_from_text(part)
                if block:
                    result.append(block)
                    
        return result if result else [original_block]
    
    def _split_text_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using separators.
        
        Args:
            text: Text to split into sentences
            
        Returns:
            List of sentences
        """
        sentences = [[]]
        for char in text:
            sentences[-1].append(char)
            if char in CONFIG.sentence_separators:
                sentences.append([])

        return ["".join(sentence) for sentence in sentences if sentence]
    
    def _find_sentence_split_point(self, sentences: List[str]) -> tuple[int, List[int]]:
        """
        Find the optimal split point for sentences based on token count.
        
        Args:
            sentences: List of sentences
            
        Returns:
            Tuple of (split_index, token_counts)
        """
        try:
            tokens = [self.get_token_count(sentence) for sentence in sentences]
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Tokenization failed for sentence splitting: {e}")
            return 0, []

        split_idx = 0
        total_size = 0
        for i, token_count in enumerate(tokens):
            if total_size + token_count > self.chunk_size:
                break
            split_idx = i + 1

        return split_idx, tokens
    
    def _create_sentence_pair(
        self, 
        sentences: List[str], 
        split_idx: int, 
        text: str,
        original_block: "BlockToken"
    ) -> List[str]:
        """
        Create a pair of text chunks from sentence split.
        
        Args:
            sentences: List of sentences
            split_idx: Index to split at
            text: Original text
            original_block: Original block token
            
        Returns:
            List of text parts
        """
        if split_idx == 0:
            # First sentence is too long, check if it's a very long content
            first_sentence = sentences[0] if sentences else text
            
            # Enhanced detection for very long content
            if len(first_sentence) > self.chunk_size * 1.5:
                logger.info(f"Detected very long sentence ({len(first_sentence)} chars), forcing split")
                # Return empty to trigger forced splitting
                return []
            else:
                # Normal sentence but too long, split after first sentence
                return [sentences[0], "".join(sentences[1:]) if len(sentences) > 1 else ""]
        else:
            # Normal sentence-based splitting
            return [
                "".join(sentences[:split_idx]),
                "".join(sentences[split_idx:]),
            ]
    
    def _create_document_from_text(self, text: str) -> "BlockToken":
        """
        Create a document block from text content.
        
        Args:
            text: Text to convert to document
            
        Returns:
            First block from created document, or None if creation fails
        """
        try:
            from mistletoe.block_token import Document
            doc = Document(text)
            return doc.children[0] if doc.children else None
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to create document from text: {e}")
            return None
    
    def _process_oversized_chunks(
        self, 
        result_chunks: List["BlockToken"], 
        original_block: "BlockToken"
    ) -> List["BlockToken"]:
        """
        Process chunks that are still too large after initial splitting.
        
        Args:
            result_chunks: List of chunks to process
            original_block: Original block token for fallback
            
        Returns:
            List of processed chunks
        """
        final_result = []
        for chunk in result_chunks:
            try:
                chunk_text = self.render_block(chunk)
                chunk_tokens = self.get_token_count(chunk_text)
                
                if chunk_tokens > self.chunk_size:
                    logger.warning(f"Chunk still too large ({chunk_tokens} tokens), applying character-based split")
                    # Force split by character count with token validation
                    char_limit = max(50, self.chunk_size * 2)  # Conservative character limit
                    
                    for i in range(0, len(chunk_text), char_limit):
                        part = chunk_text[i:i+char_limit].strip()
                        if part:
                            # Validate token count for the character-split part
                            part_tokens = self.get_token_count(part)
                            
                            # If still too large, split further
                            if part_tokens > self.chunk_size:
                                # Ultra-conservative split
                                smaller_limit = max(20, self.chunk_size)  # Even smaller chunks
                                for j in range(0, len(part), smaller_limit):
                                    tiny_part = part[j:j+smaller_limit].strip()
                                    if tiny_part:
                                        block = self._create_document_from_text(tiny_part)
                                        if block:
                                            final_result.append(block)
                            else:
                                block = self._create_document_from_text(part)
                                if block:
                                    final_result.append(block)
                else:
                    final_result.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to check chunk size: {e}")
                final_result.append(chunk)
        
        return final_result if final_result else [original_block] 