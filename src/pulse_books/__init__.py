"""書籍 PDF RAG 取り込み(pulse Phase 2、設計書 §6).

旧 catchup_ai.core.rag.chunker を移植した唯一の流用資産を含む。
PDF 抽出・embedding(Ollama)・pgvector 書き込みは書籍 RAG 実装タスクで追加する。
"""

from .chunker import ChunkStrategy, TextChunk, TextChunker

__all__ = [
    "ChunkStrategy",
    "TextChunk",
    "TextChunker",
]
