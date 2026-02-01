"""RAG (Retrieval-Augmented Generation) pipeline for article Q&A.

This module provides:
- Retriever: Vector search for relevant articles
- Generator: LLM-based answer generation
- Chunker: Text splitting strategies
- Pipeline: Complete RAG workflow
"""

from .chunker import TextChunker
from .generator import LLMGenerator
from .pipeline import RAGPipeline
from .prompt_templates import PromptTemplates
from .retriever import ArticleRetriever

__all__ = [
    "RAGPipeline",
    "ArticleRetriever",
    "LLMGenerator",
    "TextChunker",
    "PromptTemplates",
]
