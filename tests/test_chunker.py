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

    def test_chunk_by_sentence_japanese(self):
        """Japanese sentences split on 。/!/? without needing whitespace."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SENTENCE,
            chunk_size=30,
            min_chunk_size=1,
        )
        text = "これは最初の文です。これは二番目の文です。三番目はどうでしょうか?最後の文です!"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        # Sentences stay intact: every chunk ends on a Japanese terminator.
        for chunk in chunks:
            assert chunk.text[-1] in "。!?"
        # Nothing is lost or gained (Japanese chunks re-join without spaces).
        assert "".join(chunk.text for chunk in chunks) == text

    def test_chunk_by_sentence_japanese_no_ascii_space_inserted(self):
        """Merged Japanese sentences are joined without an ASCII space."""
        chunker = TextChunker(strategy=ChunkStrategy.SENTENCE, chunk_size=1000)
        text = "短い文です。もう一つの文です。"
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_chunk_by_sentence_japanese_closing_quote_stays_attached(self):
        """A terminator inside 「…。」 does not split before the closing quote."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SENTENCE,
            chunk_size=25,
            min_chunk_size=1,
        )
        text = "彼は「もう帰ろう。」と言った。それから静かに部屋を出て行った。"
        chunks = chunker.chunk(text)
        for chunk in chunks:
            assert not chunk.text.startswith("」")

    def test_chunk_by_sentence_mixed_japanese_and_english(self):
        """Western '. ' splits still work alongside Japanese ones."""
        chunker = TextChunker(
            strategy=ChunkStrategy.SENTENCE,
            chunk_size=40,
            min_chunk_size=1,
        )
        text = "Goroutines are cheap. チャネルで通信します。Do not communicate by sharing memory."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        merged = " ".join(chunk.text for chunk in chunks)
        assert "チャネルで通信します。" in merged
        assert "Goroutines are cheap." in merged

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
