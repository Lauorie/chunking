# TextChunker

A production-ready utility for splitting text into semantically meaningful chunks based on sentence terminators while controlling token length.

## Overview

TextChunker solves the common problem of breaking long texts into smaller, coherent chunks for processing with token-limited systems like language models. It intelligently splits text at natural sentence boundaries (periods, question marks, etc.) while ensuring chunks stay within specified token length limits.

## Features

- Semantically coherent text chunking that preserves sentence boundaries
- Customizable sentence terminators for multiple languages 
- Configurable minimum and maximum token lengths
- Efficient tokenization using tiktoken
- Robust error handling for production use
- Type hints for better IDE support and static analysis
- Well-documented code with comprehensive docstrings

## Installation

```bash
# Install required dependencies
pip install tiktoken
```

## Usage

### Basic Usage

```python
from text_chunker import TextChunker

# Initialize with default settings
chunker = TextChunker()

# Split text into chunks
text = """This is a long piece of text that needs to be split into smaller chunks. 
Each chunk should ideally be a complete sentence or a group of related sentences.
The algorithm will try to keep the chunks between the specified minimum and maximum lengths."""

chunks = chunker.split_text(text)
for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}: {chunk}")
```

### Customizing Behavior

```python
# Configure with custom parameters
chunker = TextChunker(
    encoding_name="cl100k_base",  # Tiktoken encoding to use
    terminators={".", "?", "!", ";", "\n\n"},  # Custom sentence terminators
    min_length=100,  # Minimum chunk size in tokens
    max_length=300   # Maximum chunk size in tokens
)

chunks = chunker.split_text(text)
```

### Legacy Function

For backward compatibility, you can use the functional interface:

```python
from text_chunker import split_chunks

terminators = [".", "?", "!", ";"]
chunks = split_chunks(text, terminators, min_length=100, max_length=300)
```

## Parameters

- **encoding_name**: The name of the tiktoken encoding to use (default: "cl100k_base")
- **terminators**: Set of characters that mark sentence boundaries
- **min_length**: Minimum token length for a chunk (default: 128)
- **max_length**: Maximum token length for a chunk (default: 512)

## Handling Different Languages

TextChunker works with multiple languages. The default terminators include common punctuation for both English and Asian languages:

```python
DEFAULT_TERMINATORS = {
    "。", "？", "！", "；", "……", "…", "》", "】", "）",
    "?", "!", ";", "…", '"', ")", "]", "}", ".", "\n\n"
}
```

## Error Handling

TextChunker includes robust error handling for production environments:

```python
try:
    chunks = chunker.split_text(text)
except ValueError as e:
    print(f"Configuration error: {e}")
except RuntimeError as e:
    print(f"Runtime error during text splitting: {e}")
```

## Performance Considerations

- For very large texts, consider processing in batches
- The tokenizer initialization is relatively expensive, so reuse the TextChunker instance when processing multiple texts

## Example: Processing a Large Document

```python
chunker = TextChunker(min_length=200, max_length=800)

with open("large_document.txt", "r") as f:
    text = f.read()

chunks = chunker.split_text(text)
print(f"Split document into {len(chunks)} chunks")

# Process each chunk independently
for chunk in chunks:
    # Your processing logic here
    process_chunk(chunk)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
