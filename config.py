"""
Configuration module for chunking functionality.

This module contains all configuration constants, default values, and
environment-specific settings for the chunking system.
"""

import os
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ChunkingConfig:
    """Configuration class for chunking operations."""
    
    # Default chunking parameters
    default_chunk_size: int = 1024
    default_chunk_overlap: int = 20
    default_metadata_format_len: int = 2
    min_effective_chunk_size: int = 50
    max_header_to_row_ratio: float = 2.0
    default_convert_table_ratio: float = 0.5
    
    # Table processing
    table_border_tokens: int = 2
    table_cell_separator_tokens: int = 2
    
    # List processing  
    list_overhead_tokens: int = 3
    list_item_overhead_tokens: int = 2
    
    # Sentence separators for different languages
    sentence_separators: List[str] = None
    
    # HTML tags to process
    html_tags: List[str] = None
    
    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Performance settings
    max_retries: int = 3
    retry_delay: float = 0.1
    
    def __post_init__(self):
        """Initialize default values after object creation."""
        if self.sentence_separators is None:
            self.sentence_separators = [ "。", "？", "！", "；", "……", "…", "》", "】",
            "）", "?", "!", ";", "…", ")", "]", "}", ".", "\n\n"]
            
        if self.html_tags is None:
            self.html_tags = [
                "p", "h1", "h2", "h3", "h4", "h5", "h6", 
                "li", "b", "i", "u", "section"
            ]


# Environment-specific configuration
def get_config() -> ChunkingConfig:
    """
    Get configuration based on environment variables.
    
    Returns:
        ChunkingConfig: Configuration object with environment-specific values
    """
    return ChunkingConfig(
        default_chunk_size=int(os.getenv("CHUNKING_DEFAULT_CHUNK_SIZE", 1024)),
        default_chunk_overlap=int(os.getenv("CHUNKING_DEFAULT_OVERLAP", 20)),
        min_effective_chunk_size=int(os.getenv("CHUNKING_MIN_EFFECTIVE_SIZE", 50)),
        max_header_to_row_ratio=float(os.getenv("CHUNKING_MAX_HEADER_RATIO", 2.0)),
        default_convert_table_ratio=float(os.getenv("CHUNKING_TABLE_RATIO", 0.5)),
        log_level=os.getenv("CHUNKING_LOG_LEVEL", "INFO"),
        max_retries=int(os.getenv("CHUNKING_MAX_RETRIES", 3)),
        retry_delay=float(os.getenv("CHUNKING_RETRY_DELAY", 0.1)),
    )


# Global configuration instance
CONFIG = get_config() 