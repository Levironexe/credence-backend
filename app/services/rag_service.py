"""
RAG Service for Lending Knowledge Base

Provides retrieval-augmented generation for lending regulations, policies, and best practices.
Uses pgvector + OpenRouter embeddings (Perplexity pplx-embed-v1-0.6b) for semantic search.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain.docstore.document import Document
from app.config import settings
from app.services.cache_service import cached, cache_service

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG service for lending knowledge retrieval.

    Knowledge base includes:
    - Vietnam Law on Credit Institutions 2024 (Law 32/2024/QH15)
    - SBV lending regulations (Circular 39/2016, amendments)
    - Asset classification & provisioning (Circular 11/2021)
    - Capital adequacy / Basel III (Circular 14/2025)
    - CIC credit scoring framework (150-750 scale)
    - AML requirements (Law 14/2022/QH15)
    - Consumer protection (Law 19/2023/QH15)
    - SME lending best practices
    """

    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self._initialized = False

    def _get_connection_string(self) -> str:
        """Build pgvector connection string from DATABASE_URL."""
        db_url = settings.database_url
        if not db_url:
            return (
                f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
                f"@{settings.database_host}:{settings.database_port}/{settings.database_name}"
            )

        # Switch from asyncpg to psycopg driver
        conn = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        if not conn.startswith("postgresql+psycopg://"):
            conn = db_url.replace("postgresql://", "postgresql+psycopg://")

        return conn

    async def initialize(self):
        """Initialize embeddings and vector store."""
        if self._initialized:
            return

        try:
            # Initialize embeddings via OpenRouter (OpenAI-compatible API)
            # Perplexity pplx-embed-v1-0.6b: 1024 dims, $0.004/M tokens
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openrouter_api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                check_embedding_ctx_length=False,
                tiktoken_enabled=False,
            )

            connection_string = self._get_connection_string()
            host_info = connection_string.split('@')[1] if '@' in connection_string else 'local'
            logger.info(f"Connecting pgvector to: {host_info}")

            # Use sync mode — PGVector sync works reliably with psycopg
            # Async methods are wrapped with asyncio.to_thread
            self.vectorstore = PGVector(
                connection=connection_string,
                embeddings=self.embeddings,
                collection_name="lending_knowledge",
                use_jsonb=True,
                create_extension=False,
                engine_args={"connect_args": {"prepare_threshold": 0}},
            )

            self._initialized = True
            logger.info("RAG service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
            raise

    @cached("rag_retrieve", ttl=1800)  # Cache for 30 minutes
    async def retrieve(
        self,
        query: str,
        k: int = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Retrieve relevant documents from knowledge base.

        Args:
            query: Search query
            k: Number of documents to retrieve (default: rag_retrieval_k from config)
            filter_metadata: Optional metadata filter (e.g., {"source": "basel_iii"})

        Returns:
            List of Document objects with content and metadata
        """
        if not self._initialized:
            await self.initialize()

        k = k or settings.rag_retrieval_k

        try:
            if filter_metadata:
                docs = await asyncio.to_thread(
                    self.vectorstore.similarity_search,
                    query,
                    k=k,
                    filter=filter_metadata,
                )
            else:
                docs = await asyncio.to_thread(
                    self.vectorstore.similarity_search,
                    query,
                    k=k,
                )

            logger.info(f"Retrieved {len(docs)} documents for query: {query[:100]}")
            return docs

        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return []

    async def retrieve_with_scores(
        self,
        query: str,
        k: int = None,
        score_threshold: float = 0.7
    ) -> List[tuple[Document, float]]:
        """
        Retrieve documents with similarity scores.

        Args:
            query: Search query
            k: Number of documents
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of (Document, score) tuples
        """
        if not self._initialized:
            await self.initialize()

        k = k or settings.rag_retrieval_k

        try:
            results = await asyncio.to_thread(
                self.vectorstore.similarity_search_with_score,
                query,
                k=k,
            )

            # Filter by score threshold
            filtered = [
                (doc, score) for doc, score in results
                if score >= score_threshold
            ]

            logger.info(
                f"Retrieved {len(filtered)}/{len(results)} documents "
                f"above threshold {score_threshold}"
            )
            return filtered

        except Exception as e:
            logger.error(f"RAG retrieval with scores failed: {e}")
            return []

    async def add_documents(
        self,
        documents: List[Document]
    ) -> List[str]:
        """
        Add documents to knowledge base.

        Args:
            documents: List of Document objects with page_content and metadata

        Returns:
            List of document IDs
        """
        if not self._initialized:
            await self.initialize()

        try:
            ids = await asyncio.to_thread(
                self.vectorstore.add_documents,
                documents,
            )
            logger.info(f"Added {len(ids)} documents to knowledge base")
            return ids

        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise

    def format_context(self, documents: List[Document]) -> str:
        """
        Format retrieved documents as context string for LLM.

        Args:
            documents: Retrieved documents

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant regulations or policies found."

        context_parts = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get("source", "Unknown")
            title = doc.metadata.get("title", "")

            context_parts.append(
                f"[{i}] {source}" + (f" - {title}" if title else "") +
                f"\n{doc.page_content}\n"
            )

        return "\n".join(context_parts)


# Singleton instance
rag_service = RAGService()
