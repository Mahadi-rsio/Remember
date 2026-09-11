"""Retrieval package — FTS backend (+ future embedding stub)."""
from app.retrieval.interface import Retriever, RetrievalResult
from app.retrieval.fts import FTSRetriever
from app.retrieval.embeddings import EmbeddingRetriever

__all__ = ["Retriever", "RetrievalResult", "FTSRetriever", "EmbeddingRetriever"]
