"""Text chunking strategies for embedding.

Provides various strategies for splitting text into chunks suitable
for embedding generation (book RAG ingestion, §6).

Sentence splitting understands both Western terminators (". ! ?" followed
by whitespace) and Japanese ones (「。」「!」「?」, no whitespace required —
technical books here are mostly Japanese). A terminator inside a closing
quote (「…。」) does not split, so the quote stays attached to its sentence.
"""

import re
from dataclasses import dataclass
from enum import Enum

# Split after ./!/? + whitespace (Western), or after 。/!/? even without
# whitespace (Japanese) unless a closing bracket follows the terminator.
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|(?<=[。!?])(?![」』】)])\s*")

# A chunk ending in a Japanese terminator needs no space before the next
# sentence; a Western sentence does (re-joining what \s+ consumed).
_NO_SPACE_BEFORE_NEXT = ("。", "!", "?", "」", "』")


class ChunkStrategy(Enum):
    """Available chunking strategies."""

    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SEMANTIC = "semantic"


@dataclass
class TextChunk:
    """A chunk of text with metadata."""

    text: str
    start_index: int
    end_index: int
    chunk_index: int
    total_chunks: int

    @property
    def length(self) -> int:
        """Length of the chunk text."""
        return len(self.text)


class TextChunker:
    """Text chunking utility for RAG pipelines.

    Supports multiple chunking strategies with configurable overlap.
    """

    def __init__(
        self,
        strategy: ChunkStrategy = ChunkStrategy.PARAGRAPH,
        chunk_size: int = 1000,
        overlap: int = 100,
        min_chunk_size: int = 100,
    ):
        """Initialize the chunker.

        Args:
            strategy: Chunking strategy to use
            chunk_size: Target size for each chunk (characters)
            overlap: Overlap between consecutive chunks
            min_chunk_size: Minimum chunk size (smaller chunks are merged)
        """
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str) -> list[TextChunk]:
        """Split text into chunks.

        Args:
            text: Text to split

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        if self.strategy == ChunkStrategy.FIXED_SIZE:
            return self._chunk_fixed_size(text)
        elif self.strategy == ChunkStrategy.SENTENCE:
            return self._chunk_by_sentence(text)
        elif self.strategy == ChunkStrategy.PARAGRAPH:
            return self._chunk_by_paragraph(text)
        elif self.strategy == ChunkStrategy.SEMANTIC:
            return self._chunk_semantic(text)
        else:
            return self._chunk_fixed_size(text)

    def _chunk_fixed_size(self, text: str) -> list[TextChunk]:
        """Split text into fixed-size chunks with overlap."""
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at word boundary
            if end < len(text):
                # Look for space within last 50 chars
                space_pos = text.rfind(" ", end - 50, end)
                if space_pos > start:
                    end = space_pos

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        start_index=start,
                        end_index=end,
                        chunk_index=chunk_index,
                        total_chunks=0,  # Updated later
                    )
                )
                chunk_index += 1

            start = end - self.overlap
            if start < 0:
                start = 0
            # Avoid infinite loop
            if end >= len(text):
                break

        # Update total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks

    def _chunk_by_sentence(self, text: str) -> list[TextChunk]:
        """Split text by sentences, merging small chunks.

        Handles Western (. ! ?) and Japanese (。 ! ?) sentence endings;
        see _SENTENCE_SPLIT_PATTERN.
        """
        sentences = _SENTENCE_SPLIT_PATTERN.split(text)

        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_index = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            separator = "" if current_chunk.endswith(_NO_SPACE_BEFORE_NEXT) else " "
            if len(current_chunk) + len(separator) + len(sentence) <= self.chunk_size:
                if current_chunk:
                    current_chunk += separator + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(
                        TextChunk(
                            text=current_chunk,
                            start_index=current_start,
                            end_index=current_start + len(current_chunk),
                            chunk_index=chunk_index,
                            total_chunks=0,
                        )
                    )
                    chunk_index += 1
                    current_start += len(current_chunk) + 1

                # A single sentence longer than chunk_size has no sentence
                # boundary to cut at: last-resort fixed-size split.
                if len(sentence) > self.chunk_size:
                    for sub in self._chunk_fixed_size(sentence):
                        sub.chunk_index = chunk_index
                        chunks.append(sub)
                        chunk_index += 1
                    current_chunk = ""
                else:
                    current_chunk = sentence

        # Add remaining chunk
        if current_chunk:
            chunks.append(
                TextChunk(
                    text=current_chunk,
                    start_index=current_start,
                    end_index=current_start + len(current_chunk),
                    chunk_index=chunk_index,
                    total_chunks=0,
                )
            )

        # Merge small chunks
        chunks = self._merge_small_chunks(chunks)

        # Update total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks

    def _chunk_by_paragraph(self, text: str) -> list[TextChunk]:
        """Split text by paragraphs (double newlines)."""
        paragraphs = re.split(r"\n\n+", text)

        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    chunks.append(
                        TextChunk(
                            text=current_chunk,
                            start_index=current_start,
                            end_index=current_start + len(current_chunk),
                            chunk_index=chunk_index,
                            total_chunks=0,
                        )
                    )
                    chunk_index += 1
                    current_start += len(current_chunk) + 2

                # A single paragraph exceeding chunk_size is split on
                # sentence boundaries (Japanese-aware): book paragraphs
                # routinely exceed 1000 characters, and a fixed-size split
                # would cut mid-sentence — its ASCII-space word-boundary
                # search never hits in Japanese text. A single over-long
                # sentence still ends up fixed-size inside
                # _chunk_by_sentence (last resort).
                if len(para) > self.chunk_size:
                    sub_chunks = self._chunk_by_sentence(para)
                    for sub in sub_chunks:
                        sub.chunk_index = chunk_index
                        chunks.append(sub)
                        chunk_index += 1
                    current_chunk = ""
                else:
                    current_chunk = para

        # Add remaining chunk
        if current_chunk:
            chunks.append(
                TextChunk(
                    text=current_chunk,
                    start_index=current_start,
                    end_index=current_start + len(current_chunk),
                    chunk_index=chunk_index,
                    total_chunks=0,
                )
            )

        # Merge small chunks
        chunks = self._merge_small_chunks(chunks)

        # Update total_chunks and re-index
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _chunk_semantic(self, text: str) -> list[TextChunk]:
        """Semantic chunking based on content structure.

        Tries to identify logical sections (headers, lists, etc.)
        Falls back to paragraph chunking.
        """
        # Look for markdown-style headers
        header_pattern = r"^#{1,6}\s+.+$"

        sections = re.split(r"(^#{1,6}\s+.+$)", text, flags=re.MULTILINE)
        sections = [s.strip() for s in sections if s.strip()]

        if len(sections) <= 1:
            # No headers found, fall back to paragraph chunking
            return self._chunk_by_paragraph(text)

        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_index = 0

        for section in sections:
            if re.match(header_pattern, section):
                # This is a header, start new chunk if current is not empty
                if current_chunk and len(current_chunk) >= self.min_chunk_size:
                    chunks.append(
                        TextChunk(
                            text=current_chunk,
                            start_index=current_start,
                            end_index=current_start + len(current_chunk),
                            chunk_index=chunk_index,
                            total_chunks=0,
                        )
                    )
                    chunk_index += 1
                    current_start += len(current_chunk) + 1
                    current_chunk = section
                else:
                    current_chunk = (
                        (current_chunk + "\n\n" + section)
                        if current_chunk
                        else section
                    )
            else:
                # Regular content
                if len(current_chunk) + len(section) + 2 <= self.chunk_size:
                    current_chunk = (
                        (current_chunk + "\n\n" + section)
                        if current_chunk
                        else section
                    )
                else:
                    if current_chunk:
                        chunks.append(
                            TextChunk(
                                text=current_chunk,
                                start_index=current_start,
                                end_index=current_start + len(current_chunk),
                                chunk_index=chunk_index,
                                total_chunks=0,
                            )
                        )
                        chunk_index += 1
                        current_start += len(current_chunk) + 2
                    current_chunk = section

        if current_chunk:
            chunks.append(
                TextChunk(
                    text=current_chunk,
                    start_index=current_start,
                    end_index=current_start + len(current_chunk),
                    chunk_index=chunk_index,
                    total_chunks=0,
                )
            )

        # Update total_chunks
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _merge_small_chunks(self, chunks: list[TextChunk]) -> list[TextChunk]:
        """Merge chunks that are smaller than min_chunk_size."""
        if not chunks:
            return chunks

        merged = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            if current.length < self.min_chunk_size:
                # Merge with next chunk
                current = TextChunk(
                    text=current.text + "\n\n" + next_chunk.text,
                    start_index=current.start_index,
                    end_index=next_chunk.end_index,
                    chunk_index=current.chunk_index,
                    total_chunks=0,
                )
            else:
                merged.append(current)
                current = next_chunk

        merged.append(current)
        return merged
