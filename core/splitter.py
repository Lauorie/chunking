"""
This module contains the main AstMarkdownSplitter class that uses
different strategies to handle various block types.
"""

import logging
import warnings
from typing import Any, Callable, List, Sequence, Optional, ClassVar
from collections import deque

import mistletoe
import mistletoe.markdown_renderer
from mistletoe.block_token import Document, Heading, ThematicBreak, Paragraph, Table, List as ListBlock, HtmlBlock
from pydantic import Field, PrivateAttr, field_validator

from .base import MetadataAwareTextSplitter
from .exceptions import InvalidConfigurationError, TokenizationError, DocumentParsingError, ChunkingError
from ..strategies import ParagraphSplitStrategy, TableSplitStrategy, ListSplitStrategy, HtmlSplitStrategy, CodeSplitStrategy
from ..managers import CacheManager, DocumentSplitState
from ..config import CONFIG
from ..utils import timer, metrics, validate_input

logger = logging.getLogger(__name__)


class AstMarkdownSplitter(MetadataAwareTextSplitter):
    """   
    This splitter uses Abstract Syntax Tree parsing to intelligently split
    Markdown documents while preserving structure and meaning. It uses
    different strategies for different block types.
    """
    
    chunk_size: int = Field(
        default=CONFIG.default_chunk_size,
        description="The token chunk size for each chunk.",
        gt=0,
    )
    convert_table_ratio: float = Field(
        default=0.5,
        description="The ratio of the max_chunk_size to convert table to paragraph.",
        gt=0,
        le=1.0,
    )
    enable_first_line_as_title: bool = Field(
        default=True,
        description="Whether to enable the first line as title.",
    )

    SEPS: ClassVar[List[str]] = CONFIG.sentence_separators

    _tokenizer: Callable[[str], Sequence] = PrivateAttr()
    _renderer: Optional[mistletoe.markdown_renderer.MarkdownRenderer] = PrivateAttr(default=None)
    
    # Managers and strategies
    _cache_manager: CacheManager = PrivateAttr(default=None)
    _strategies: List = PrivateAttr(default_factory=list)

    def __init__(
        self,
        chunk_size: int = CONFIG.default_chunk_size,
        chunk_overlap: int = CONFIG.default_chunk_overlap,
        tokenizer: Optional[Callable[[str], Sequence]] = None,
        *args: Any,
        **kwargs: Any,
    ):
        """
        Initialize the AstMarkdownSplitter.
        
        Args:
            chunk_size: Maximum size of each chunk in tokens
            chunk_overlap: Number of tokens to overlap between chunks
            tokenizer: Custom tokenizer function. If None, uses character-based tokenization
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Raises:
            InvalidConfigurationError: If chunk_overlap is larger than chunk_size
        """
        if chunk_overlap > chunk_size:
            error_msg = (
                f"Chunk overlap ({chunk_overlap}) cannot be larger than "
                f"chunk size ({chunk_size})"
            )
            logger.error(error_msg)
            raise InvalidConfigurationError(error_msg)
        
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            *args,
            **kwargs,
        )

        self._tokenizer = tokenizer if tokenizer else lambda x: x
        
        # Initialize managers and strategies
        self._cache_manager = CacheManager()
        self._initialize_strategies()
        
        logger.info(f"Initialized AstMarkdownSplitter with chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")

    def _initialize_strategies(self):
        """Initialize splitting strategies for different block types."""
        self._strategies = [
            ParagraphSplitStrategy(self._tokenizer, self._render_block, self.chunk_size),
            TableSplitStrategy(self._tokenizer, self._render_block, self.chunk_size),
            ListSplitStrategy(self._tokenizer, self._render_block, self.chunk_size),
            HtmlSplitStrategy(self._tokenizer, self._render_block, self.chunk_size),
            CodeSplitStrategy(self._tokenizer, self._render_block, self.chunk_size),
        ]

    @field_validator('chunk_size')
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk size is positive."""
        if v <= 0:
            raise ValueError("chunk_size must be positive")
        return v

    @field_validator('convert_table_ratio')
    @classmethod
    def validate_convert_table_ratio(cls, v: float) -> float:
        """Validate convert table ratio is between 0 and 1."""
        if not 0 < v <= 1.0:
            raise ValueError("convert_table_ratio must be between 0 and 1")
        return v

    def split_text_metadata_aware(self, text: str, metadata_str: str) -> List[str]:
        """
        Split text with metadata awareness.
        
        Args:
            text: The text to split
            metadata_str: The metadata string that will be included with each chunk
            
        Returns:
            List of text chunks
            
        Raises:
            ValueError: If metadata is too long relative to chunk size
            TokenizationError: If tokenization fails
        """
        # Validate inputs
        validated_text, validated_metadata = validate_input(text, metadata_str)
        
        with timer("Metadata-aware text splitting"):
            try:
                metadata_len = self._cache_manager.get_token_count(validated_metadata, self._tokenizer)
                metadata_len += CONFIG.default_metadata_format_len
            except Exception as e:
                metrics.record_error("tokenization")
                logger.error(f"Tokenization failed for metadata: {e}")
                raise TokenizationError(f"Failed to tokenize metadata: {e}") from e

            effective_chunk_size = self.chunk_size - metadata_len
            if effective_chunk_size <= 0:
                error_msg = (
                    f"Metadata length ({metadata_len}) is longer than chunk size "
                    f"({self.chunk_size}). Consider increasing the chunk size or "
                    "decreasing the size of your metadata."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            chunks = self._split_text(validated_text, effective_chunk_size)
            
            # Record metrics
            metrics.record_chunks_generated(len(chunks))
            metrics.record_chars_processed(len(validated_text))
            
            logger.debug(f"Split text into {len(chunks)} chunks with metadata awareness")
            return chunks

    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks.
        
        Args:
            text: The text to split
            
        Returns:
            List of text chunks
            
        Raises:
            TypeError: If text is not a string
            ChunkingError: If splitting fails
        """
        # Validate input
        validated_text, _ = validate_input(text)
        
        with timer("Text splitting"):
            try:
                chunks = self._split_text(validated_text, self.chunk_size)
                
                # Record metrics
                metrics.record_chunks_generated(len(chunks))
                metrics.record_chars_processed(len(validated_text))
                
                logger.debug(f"Split text into {len(chunks)} chunks")
                return chunks
            except Exception as e:
                metrics.record_error("splitting")
                logger.critical(f"Unexpected error in text splitting: {e}")
                raise ChunkingError(f"Unexpected text splitting failure: {e}") from e

    def _split_text(self, text: str, chunk_size: int) -> List[str]:
        """
        Internal method to split text into chunks.
        
        Args:
            text: The text to split
            chunk_size: Maximum size of each chunk
            
        Returns:
            List of text chunks
            
        Raises:
            ChunkingError: If document parsing or splitting fails
        """
        text = text.strip()
        if not text:
            logger.warning("Empty text provided for splitting")
            return []

        # Clear caches for new document
        self._cache_manager.clear_all()

        try:
            with mistletoe.markdown_renderer.MarkdownRenderer() as self._renderer:
                doc = mistletoe.Document(text)

                if self.enable_first_line_as_title and doc.children:
                    # when paragraph is the first block, convert it to heading
                    if isinstance(doc.children[0], Paragraph):
                        first_block = doc.children[0]
                        heading = Heading((1, "", ""))
                        heading.children = first_block.children
                        doc.children[0] = heading

                # Use deque for efficient pop from left
                doc.children = deque(doc.children)
                return self._split_document(doc, chunk_size)
        except Exception as e:
            metrics.record_error("parsing")
            logger.critical(f"Unexpected error in document processing: {e}")
            raise DocumentParsingError(f"Unexpected document processing failure: {e}") from e

    def _render_block(self, token) -> str:
        """
        Render a block token to string.
        
        Args:
            token: The block token to render
            
        Returns:
            Rendered string representation
        """
        try:
            if self._renderer is None:
                raise Exception("Renderer not initialized")
                
            # Handle different renderer versions
            renderer_method = self._renderer.render_map[token.__class__.__name__]
            try:
                # Try with max_line_length parameter
                rendered_lines = renderer_method(token, max_line_length=None)
            except TypeError:
                # Fallback for older renderer versions that don't support max_line_length
                rendered_lines = renderer_method(token)
            s = "\n".join(rendered_lines)

            if isinstance(token, Table):
                # replace multiple spaces with single space
                import re
                s = re.sub(r" +", " ", s)
                # replace | --- | with | - | to reduce the size
                s = re.sub(r"(-+)|(\| -+ \|)", lambda x: "-" if x.group(1) else "| - |", s)

            return s
        except Exception as e:
            logger.error(f"Failed to render block {token.__class__.__name__}: {e}")
            raise

    def _split_block(self, block, max_chunk_size: int) -> List:
        """
        Split a block using appropriate strategy.
        
        Args:
            block: The block to split
            max_chunk_size: Maximum size for each chunk
            
        Returns:
            List of split blocks
        """
        # Find appropriate strategy
        for strategy in self._strategies:
            if strategy.can_handle(block):
                try:
                    return strategy.split_block(block)
                except Exception as e:
                    logger.warning(f"Strategy {strategy.__class__.__name__} failed: {e}")
                    continue
        
        # No strategy could handle this block type
        logger.warning(f"No strategy available for block type: {block.__class__.__name__}")
        return [block]

    def _is_empty(self, token) -> bool:
        """
        Check if a block token is empty.
        
        Args:
            token: The block token to check
            
        Returns:
            True if the token is empty, False otherwise
        """
        if isinstance(token, ThematicBreak):
            return True
        return not hasattr(token, 'children') or len(token.children) == 0

    def _split_document(self, doc: Document, max_chunk_size: int) -> List[str]:
        """
        Split a document into chunks using simplified logic.
        
        Args:
            doc: The document to split
            max_chunk_size: Maximum size for each chunk
            
        Returns:
            List of text chunks
        """
        state = DocumentSplitState()
        children_to_process = doc.children

        while children_to_process:
            child = children_to_process.popleft()

            # Skip empty blocks
            if self._is_empty(child):
                continue

            # Handle headings specially
            if isinstance(child, Heading):
                # Get heading content and size
                block_content = self._cache_manager.get_rendered_content(child, self._render_block)
                block_size = self._cache_manager.get_token_count(block_content, self._tokenizer)
                
                # Update headers tracking
                state.update_headers(child, block_size)
                state.add_block(block_content, block_size)
                continue

            # Get block content and size
            try:
                block_content = self._cache_manager.get_rendered_content(child, self._render_block)
                block_size = self._cache_manager.get_token_count(block_content, self._tokenizer)
            except Exception as e:
                logger.warning(f"Failed to process block {child.__class__.__name__}: {e}")
                continue

            # Check if block fits in current chunk
            if state.can_fit_block(block_size, max_chunk_size):
                state.add_block(block_content, block_size)
            else:
                # Check if block needs splitting
                if block_size > max_chunk_size:
                    # Try to split the block
                    split_blocks = self._split_block(child, max_chunk_size)
                    if len(split_blocks) > 1:
                        # Add split blocks back to processing queue
                        children_to_process.extendleft(reversed(split_blocks))
                        continue
                    else:
                        # Block couldn't be split, ALWAYS force split if oversized
                        logger.warning(f"Oversized chunk ({block_size} tokens), force splitting")
                        # Force split by sentences/lines with strict token control
                        split_text = self._force_split_large_text(block_content, max_chunk_size)
                        state.flush_chunk()
                        state.chunks.extend(split_text)
                        continue

                # Flush current chunk and start new one
                state.flush_chunk()
                
                # Add headers to new chunk if they fit
                header_content, header_size = state.get_header_content(self._render_block, max_chunk_size - block_size)
                for header in header_content:
                    state.add_block(header, 0)  # Size already counted in header_size
                
                # Add the current block
                state.add_block(block_content, block_size)

        # Flush the last chunk
        state.flush_chunk()

        # Final validation: ensure NO chunk exceeds max_chunk_size
        validated_chunks = []
        for chunk in state.chunks:
            chunk_tokens = self._cache_manager.get_token_count(chunk, self._tokenizer)
            if chunk_tokens > max_chunk_size:
                logger.warning(f"Final validation: splitting oversized chunk ({chunk_tokens} tokens)")
                validated_chunks.extend(self._force_split_large_text(chunk, max_chunk_size))
            else:
                validated_chunks.append(chunk)

        return validated_chunks

    def _force_split_large_text(self, text: str, max_chunk_size: int) -> List[str]:
        """
        Force split extremely large text ensuring each chunk is ≤ max_chunk_size tokens.
        
        Args:
            text: The text to split
            max_chunk_size: Maximum size for each chunk (in tokens)
            
        Returns:
            List of text chunks, each guaranteed to be ≤ max_chunk_size tokens
        """
        chunks = []
        
        # First try splitting by sentences
        sentences = []
        for sep in ['. ', '。', '！', '!', '？', '?', '\n\n', '\n']:
            if sep in text:
                sentences = text.split(sep)
                break
        
        if not sentences:
            # If no sentence separators, split by lines
            sentences = text.split('\n')
        
        current_chunk = ""
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            # Add separator back
            sentence_with_sep = sentence.strip() + ('\n' if '\n' in text else ' ')
            sentence_size = self._cache_manager.get_token_count(sentence_with_sep, self._tokenizer)
            
            # If single sentence is too large, force split by tokens
            if sentence_size > max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # Split sentence into token-precise chunks
                chunks.extend(self._split_by_tokens(sentence, max_chunk_size))
                continue
            
            # Check if adding this sentence would exceed limit
            if current_chunk:
                combined_size = self._cache_manager.get_token_count(current_chunk + sentence_with_sep, self._tokenizer)
                if combined_size > max_chunk_size:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence_with_sep
                else:
                    current_chunk += sentence_with_sep
            else:
                current_chunk = sentence_with_sep
        
        # Add remaining chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks

    def _split_by_tokens(self, text: str, max_chunk_size: int) -> List[str]:
        """
        Split text by tokens ensuring each chunk is ≤ max_chunk_size tokens.
        
        Args:
            text: The text to split
            max_chunk_size: Maximum size for each chunk (in tokens)
            
        Returns:
            List of text chunks, each guaranteed to be ≤ max_chunk_size tokens
        """
        chunks = []
        
        # Try to split by words first
        words = text.split()
        if not words:
            return []
        
        current_chunk = ""
        for word in words:
            # Test adding this word
            test_chunk = current_chunk + (" " if current_chunk else "") + word
            test_size = self._cache_manager.get_token_count(test_chunk, self._tokenizer)
            
            if test_size <= max_chunk_size:
                current_chunk = test_chunk
            else:
                # Current chunk is full, save it and start new one
                if current_chunk:
                    chunks.append(current_chunk)
                
                # Check if single word is too large
                word_size = self._cache_manager.get_token_count(word, self._tokenizer)
                if word_size > max_chunk_size:
                    # Split word by characters with token validation
                    chunks.extend(self._split_by_chars_with_tokens(word, max_chunk_size))
                    current_chunk = ""
                else:
                    current_chunk = word
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _split_by_chars_with_tokens(self, text: str, max_chunk_size: int) -> List[str]:
        """
        Split text by characters while validating with tokenizer.
        
        Args:
            text: The text to split
            max_chunk_size: Maximum size for each chunk (in tokens)
            
        Returns:
            List of text chunks, each guaranteed to be ≤ max_chunk_size tokens
        """
        chunks = []
        
        # Start with conservative character estimate and adjust
        start = 0
        while start < len(text):
            # Start with estimated chunk size (conservative: 3 chars per token)
            estimated_chars = max_chunk_size * 3
            end = min(start + estimated_chars, len(text))
            
            # Find the largest valid chunk size using binary search approach
            chunk = text[start:end]
            chunk_tokens = self._cache_manager.get_token_count(chunk, self._tokenizer)
            
            # If chunk is too large, shrink it
            while chunk_tokens > max_chunk_size and end > start + 1:
                # Reduce by ~10% each time
                reduction = max(1, (end - start) // 10)
                end -= reduction
                chunk = text[start:end]
                chunk_tokens = self._cache_manager.get_token_count(chunk, self._tokenizer)
            
            # If chunk is small enough, try to grow it
            while chunk_tokens <= max_chunk_size and end < len(text):
                # Try to add more characters
                next_end = min(end + max(1, (end - start) // 20), len(text))
                next_chunk = text[start:next_end]
                next_tokens = self._cache_manager.get_token_count(next_chunk, self._tokenizer)
                
                if next_tokens <= max_chunk_size:
                    end = next_end
                    chunk = next_chunk
                    chunk_tokens = next_tokens
                else:
                    break
            
            # Ensure we make progress
            if end <= start:
                end = start + 1
                chunk = text[start:end]
            
            chunks.append(chunk)
            start = end
        
        return chunks 