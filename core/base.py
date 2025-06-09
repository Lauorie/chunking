"""
Base classes for text splitters.

This module contains the abstract base classes that define the interface
for metadata-aware text splitters.
"""

from typing import List
from pydantic import BaseModel, Field, field_validator

from ..config import CONFIG


class MetadataAwareTextSplitter(BaseModel):
    """
    Base class for text splitters that are aware of metadata.
    
    This abstract class defines the interface for text splitters that can
    handle metadata along with the main text content.
    """
    
    chunk_overlap: int = Field(
        default=CONFIG.default_chunk_overlap,
        description="The token overlap between chunks.",
        ge=0,
    )
    
    @field_validator('chunk_overlap')
    @classmethod
    def validate_chunk_overlap(cls, v: int) -> int:
        """Validate chunk overlap is non-negative."""
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
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
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclass must implement split_text_metadata_aware")
    
    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks.
        
        Args:
            text: The text to split
            
        Returns:
            List of text chunks
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclass must implement split_text") 