import tiktoken
from typing import List, Set, Optional, Tuple

class TextChunker:
    """
    A class for splitting text into semantically meaningful chunks based on sentence terminators
    while controlling the token length of each chunk.
    """
    
    # Default terminators for sentence boundaries across multiple languages
    DEFAULT_TERMINATORS = {
        "。", "？", "！", "；", "……", "…", "》", "】", "）",
        "?", "!", ";", "…", """, ")", "]", "}", ".", "\n\n"
    }
    
    def __init__(
        self, 
        encoding_name: str = "cl100k_base",
        terminators: Optional[Set[str]] = None,
        min_length: int = 128,
        max_length: int = 512
    ):
        """
        Initialize the TextChunker.
        
        Args:
            encoding_name: The name of the tiktoken encoding to use
            terminators: Set of characters that mark sentence boundaries
            min_length: Minimum token length for a chunk
            max_length: Maximum token length for a chunk
        """
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            raise ValueError(f"Failed to initialize tokenizer with encoding '{encoding_name}': {e}")
            
        self.terminators = terminators if terminators is not None else self.DEFAULT_TERMINATORS
        self.min_length = min_length
        self.max_length = max_length
        
        if min_length >= max_length:
            raise ValueError(f"min_length ({min_length}) must be less than max_length ({max_length})")
            
        if min_length < 1:
            raise ValueError(f"min_length ({min_length}) must be at least 1")
    
    def split_into_sentences(self, tokens: List[int]) -> List[List[int]]:
        """
        Split tokens into sentences based on terminators.
        
        Args:
            tokens: List of token IDs
            
        Returns:
            List of token lists, each representing a sentence
        """
        sentences = []
        last_idx = 0
        
        for i, token in enumerate(tokens):
            token_text = self.tokenizer.decode([token])
            if token_text in self.terminators:
                if i + 1 > last_idx:  # Ensure sentence is not empty
                    sentences.append(tokens[last_idx:i+1])
                    last_idx = i + 1
        
        # Handle the last sentence which might not have a terminator
        if last_idx < len(tokens):
            sentences.append(tokens[last_idx:])
            
        return sentences
    
    def merge_sentences_into_chunks(self, sentences: List[List[int]]) -> List[str]:
        """
        Merge sentences into chunks while respecting min and max length constraints.
        
        Args:
            sentences: List of token lists representing sentences
            
        Returns:
            List of text chunks
        """
        chunks = []
        current_chunk = []
        
        for sentence in sentences:
            # If current chunk + new sentence is within max_length, add the sentence
            if len(current_chunk) + len(sentence) <= self.max_length:
                current_chunk.extend(sentence)
            else:
                # If current chunk meets min_length, save it and start a new one
                if len(current_chunk) >= self.min_length:
                    chunks.append(self.tokenizer.decode(current_chunk))
                    current_chunk = sentence
                else:
                    # Current chunk is too short, but adding sentence exceeds max_length
                    # Add as many tokens as possible from the sentence
                    space_left = self.max_length - len(current_chunk)
                    current_chunk.extend(sentence[:space_left])
                    chunks.append(self.tokenizer.decode(current_chunk))
                    
                    # Start new chunk with remaining tokens
                    current_chunk = sentence[space_left:]
        
        # Handle the last chunk
        if current_chunk:
            if len(current_chunk) >= self.min_length:
                chunks.append(self.tokenizer.decode(current_chunk))
            elif chunks:  # If last chunk is too short but not empty, try to merge with previous
                last_chunk_tokens = self.tokenizer.encode(chunks[-1], allowed_special=set())
                if len(last_chunk_tokens) + len(current_chunk) <= self.max_length:
                    last_chunk_tokens.extend(current_chunk)
                    chunks[-1] = self.tokenizer.decode(last_chunk_tokens)
                else:
                    # If we can't merge with previous, add it anyway if it's not too small
                    if len(current_chunk) > self.min_length // 2:
                        chunks.append(self.tokenizer.decode(current_chunk))
                    # For extremely small chunks, we could extend this logic to handle them
        
        return chunks
    
    def split_text(self, text: str, allowed_special: Optional[Set[str]] = None) -> List[str]:
        """
        Split text into semantically meaningful chunks.
        
        Args:
            text: The input text to split
            allowed_special: Set of special tokens allowed in the encoding
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
            
        try:
            tokens = self.tokenizer.encode(text, allowed_special=allowed_special or set())
            sentences = self.split_into_sentences(tokens)
            return self.merge_sentences_into_chunks(sentences)
        except Exception as e:
            raise RuntimeError(f"Error splitting text: {e}")


def split_chunks(
    text: str, 
    terminators: List[str], 
    min_length: int = 128, 
    max_length: int = 512
) -> List[str]:
    """
    Legacy function for backwards compatibility.
    
    Args:
        text: The input text to split
        terminators: List of characters that mark sentence boundaries
        min_length: Minimum token length for a chunk
        max_length: Maximum token length for a chunk
        
    Returns:
        List of text chunks
    """
    chunker = TextChunker(
        terminators=set(terminators),
        min_length=min_length,
        max_length=max_length
    )
    return chunker.split_text(text)
