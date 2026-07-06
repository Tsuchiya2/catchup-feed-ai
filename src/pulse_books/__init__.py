"""書籍 PDF RAG 取り込み(pulse Phase 2、設計書 §6).

pulse-books CLI(cli.py)がエントリポイント:
PDF 抽出(pdf.py)→ チャンク化(chunker.py、旧実装からの唯一の流用資産)
→ embedding(embedding.py、Ollama bge-m3・ローカル限定 C-12)
→ Pi の pgvector books / book_chunks(db.py。テーブル作成は backend の責務)。
"""

from .chunker import ChunkStrategy, TextChunk, TextChunker

__all__ = [
    "ChunkStrategy",
    "TextChunk",
    "TextChunker",
]
