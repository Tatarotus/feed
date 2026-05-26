import logging
from typing import List

logger = logging.getLogger("pipeline.processing.chunker")

def chunk_text(
    text: str,
    chunk_size: int = 500,  # size in tokens (words)
    overlap: int = 50,      # overlap in tokens
    min_chunk_len: int = 15 # discard tiny fragments (e.g. less than 15 words)
) -> List[str]:
    """
    Splits long normalized text into uniform overlapping chunks.
    Uses simple whitespace tokenization for speed, predictability, and safety.
    """
    if not text:
        return []

    # Tokenize simply by whitespace
    words = text.split()
    total_words = len(words)

    # If the text is shorter than our minimum chunk length, discard or return as one chunk
    if total_words < min_chunk_len:
        return []

    # If text is smaller than chunk size, return as a single chunk
    if total_words <= chunk_size:
        return [" ".join(words)]

    chunks = []
    i = 0
    while i < total_words:
        # Create sliding window slice
        chunk_words = words[i : i + chunk_size]
        
        # Guard against trailing microscopic chunks at the tail end
        if len(chunk_words) < min_chunk_len:
            break
            
        chunks.append(" ".join(chunk_words))
        
        # Advance index by step size (chunk_size minus the overlap)
        i += (chunk_size - overlap)

    logger.debug(f"Chunked text of {total_words} words into {len(chunks)} overlapping segments.")
    return chunks
