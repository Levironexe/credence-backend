"""
RAG Service for Lending Knowledge Base

Provides retrieval-augmented generation for lending regulations, policies, and best practices.
Uses pgvector + OpenRouter embeddings (Perplexity pplx-embed-v1-0.6b) for semantic search.

Retrieval uses raw async SQL via the app's existing asyncpg connection pool
(not a separate sync psycopg pool) to avoid connection exhaustion on Supabase.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain.docstore.document import Document
from sqlalchemy import text
from app.config import settings


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
        self.vectorstore = None  # Only used for add_documents (ingestion)
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

            # PGVector is kept for add_documents (ingestion script only).
            # Retrieval uses raw async SQL via the app's asyncpg pool.
            connection_string = self._get_connection_string()
            host_info = connection_string.split('@')[1] if '@' in connection_string else 'local'
            logger.info(f"Connecting pgvector to: {host_info}")

            self.vectorstore = PGVector(
                connection=connection_string,
                embeddings=self.embeddings,
                collection_name="lending_knowledge",
                use_jsonb=True,
                create_extension=False,
                engine_args={
                    "pool_size": 1,
                    "max_overflow": 0,
                    "pool_pre_ping": True,
                    "pool_recycle": 300,
                    "connect_args": {"prepare_threshold": 0},
                },
            )

            self._initialized = True
            logger.info("RAG service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
            raise

    async def retrieve(
        self,
        query: str,
        k: int = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Retrieve relevant documents from knowledge base.

        Uses raw async SQL via the app's existing asyncpg pool to avoid
        connection conflicts with Supabase's PgBouncer pooler.

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
            logger.info(f"Starting similarity search (k={k}) for: {query[:80]}")

            # Embed the query
            query_embedding = await self.embeddings.aembed_query(query)

            # Use the app's existing async engine to run cosine similarity SQL
            from app.database import engine as async_engine

            # langchain_postgres stores embeddings in langchain_pg_embedding table
            # with collection referenced via langchain_pg_collection.
            # Use cast() to avoid asyncpg conflict with ::vector syntax.
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            sql = text(
                "SELECT e.document, e.cmetadata, "
                "1 - (e.embedding <=> cast(:embedding AS vector)) AS score "
                "FROM langchain_pg_embedding e "
                "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                "WHERE c.name = :collection "
                "ORDER BY e.embedding <=> cast(:embedding AS vector) "
                "LIMIT :k"
            )

            async with async_engine.connect() as conn:
                result = await conn.execute(sql, {
                    "embedding": embedding_str,
                    "collection": "lending_knowledge",
                    "k": k,
                })
                rows = result.fetchall()

            docs = []
            for row in rows:
                content = row[0] or ""
                metadata = row[1] if row[1] else {}
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                docs.append(Document(page_content=content, metadata=metadata))

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
            query_embedding = await self.embeddings.aembed_query(query)

            from app.database import engine as async_engine

            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            sql = text(
                "SELECT e.document, e.cmetadata, "
                "1 - (e.embedding <=> cast(:embedding AS vector)) AS score "
                "FROM langchain_pg_embedding e "
                "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                "WHERE c.name = :collection "
                "ORDER BY e.embedding <=> cast(:embedding AS vector) "
                "LIMIT :k"
            )

            async with async_engine.connect() as conn:
                result = await conn.execute(sql, {
                    "embedding": embedding_str,
                    "collection": "lending_knowledge",
                    "k": k,
                })
                rows = result.fetchall()

            results = []
            for row in rows:
                content = row[0] or ""
                metadata = row[1] if row[1] else {}
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                score = float(row[2])
                results.append((Document(page_content=content, metadata=metadata), score))

            filtered = [(doc, score) for doc, score in results if score >= score_threshold]

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
        Uses PGVector's sync add_documents (for ingestion script only).

        Args:
            documents: List of Document objects with page_content and metadata

        Returns:
            List of document IDs
        """
        if not self._initialized:
            await self.initialize()

        import asyncio
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
