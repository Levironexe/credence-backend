"""
RAG Service for Lending Knowledge Base

Provides retrieval-augmented generation for lending regulations, policies, and best practices.
Uses pgvector + OpenAI embeddings for semantic search.
"""

import logging
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain.docstore.document import Document
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RAGService:
    """
    RAG service for lending knowledge retrieval.

    Knowledge base includes:
    - Basel III capital requirements
    - Dodd-Frank Act provisions
    - Fair Credit Reporting Act (FCRA)
    - Equal Credit Opportunity Act (ECOA)
    - SME lending best practices
    - Industry-specific risk factors
    """

    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self._initialized = False

    async def initialize(self):
        """Initialize embeddings and vector store."""
        if self._initialized:
            return

        try:
            # Initialize OpenAI embeddings
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions
            )

            # Initialize pgvector store
            connection_string = (
                f"postgresql://{settings.database_user}:{settings.database_password}"
                f"@{settings.database_host}:{settings.database_port}/{settings.database_name}"
            )

            self.vectorstore = PGVector(
                connection=connection_string,
                embeddings=self.embeddings,
                collection_name="lending_knowledge",
                use_jsonb=True
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
            # Perform similarity search
            if filter_metadata:
                docs = await self.vectorstore.asimilarity_search(
                    query,
                    k=k,
                    filter=filter_metadata
                )
            else:
                docs = await self.vectorstore.asimilarity_search(query, k=k)

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
            results = await self.vectorstore.asimilarity_search_with_score(query, k=k)

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
            ids = await self.vectorstore.aadd_documents(documents)
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
