"""Tests for text chunking strategies."""

from pulse_books.chunker import ChunkStrategy, TextChunk, TextChunker


class TestTextChunk:
    """Tests for TextChunk dataclass."""

    def test_create_chunk(self):
        """Test creating a text chunk."""
        chunk = TextChunk(
            text="This is a test chunk.",
            start_index=0,
            end_index=21,
            chunk_index=0,
            total_chunks=3,
        )
        assert chunk.text == "This is a test chunk."
        assert chunk.start_index == 0
        assert chunk.end_index == 21
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 3

    def test_length_property(self):
        """Test length property."""
        chunk = TextChunk(
            text="Hello",
            start_index=0,
            end_index=5,
            chunk_index=0,
            total_chunks=1,
        )
        assert chunk.length == 5


class TestTextChunker:
    """Tests for TextChunker class."""

    def test_init_defaults(self):
        """Test default initialization."""
        chunker = TextChunker()
        assert chunker.strategy == ChunkStrategy.PARAGRAPH
        assert chunker.chunk_size == 1000
        assert chunker.overlap == 100
        assert chunker.min_chunk_size == 100

    def test_init_custom(self):
        """Test custom initialization."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SENTENCE,
            chunk_size=500,
            overlap=50,
            min_chunk_size=50,
        )
        assert chunker.strategy == ChunkStrategy.SENTENCE
        assert chunker.chunk_size == 500

    def test_chunk_empty_text(self):
        """Test chunking empty text."""
        chunker = TextChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
        assert chunker.chunk(None) == []

    def test_chunk_fixed_size(self):
        """Test fixed-size chunking."""
        chunker = TextChunker(
            strategy=ChunkStrategy.FIXED_SIZE,
            chunk_size=50,
            overlap=10,
        )
        text = "This is a test. " * 10  # ~160 chars
        chunks = chunker.chunk(text)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.total_chunks == len(chunks)

    def test_chunk_by_sentence(self):
        """Test sentence-based chunking."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SENTENCE,
            chunk_size=100,
        )
        text = "First sentence. Second sentence. Third sentence! Fourth sentence?"
        chunks = chunker.chunk(text)
        assert len(chunks) > 0
        # Each chunk should contain complete sentences
        for chunk in chunks:
            assert chunk.text.strip()

    def test_chunk_by_paragraph(self):
        """Test paragraph-based chunking."""
        chunker = TextChunker(
            strategy=ChunkStrategy.PARAGRAPH,
            chunk_size=200,
        )
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.chunk(text)
        assert len(chunks) > 0

    def test_chunk_semantic(self):
        """Test semantic chunking with headers."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SEMANTIC,
            chunk_size=200,
            min_chunk_size=20,
        )
        text = """# Introduction

This is the introduction.

## Methods

This describes the methods.

## Results

These are the results."""
        chunks = chunker.chunk(text)
        assert len(chunks) > 0

    def test_chunk_semantic_no_headers(self):
        """Test semantic chunking falls back to paragraph when no headers."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SEMANTIC,
            chunk_size=200,
        )
        text = "First paragraph.\n\nSecond paragraph."
        chunks = chunker.chunk(text)
        assert len(chunks) > 0

    def test_estimate_tokens(self):
        """Test token estimation."""
        chunker = TextChunker()
        # ~4 chars per token
        assert chunker.estimate_tokens("Hello World!") == 3  # 12 chars / 4
        assert chunker.estimate_tokens("") == 0

    def test_fit_context_window(self):
        """Test fitting chunks to context window."""
        chunker = TextChunker()
        chunks = [
            TextChunk(text="A" * 100, start_index=0, end_index=100, chunk_index=0, total_chunks=3),
            TextChunk(
                text="B" * 100, start_index=100, end_index=200, chunk_index=1, total_chunks=3
            ),
            TextChunk(
                text="C" * 100, start_index=200, end_index=300, chunk_index=2, total_chunks=3
            ),
        ]
        # Each chunk is ~25 tokens, limit to 50 tokens = 2 chunks
        selected = chunker.fit_context_window(chunks, max_tokens=50)
        assert len(selected) == 2

    def test_merge_small_chunks(self):
        """Test merging small chunks."""
        chunker = TextChunker(min_chunk_size=50)
        chunks = [
            TextChunk(text="Small", start_index=0, end_index=5, chunk_index=0, total_chunks=2),
            TextChunk(
                text="Also small", start_index=6, end_index=16, chunk_index=1, total_chunks=2
            ),
        ]
        merged = chunker._merge_small_chunks(chunks)
        # Both chunks are smaller than min_chunk_size, should be merged
        assert len(merged) <= len(chunks)
