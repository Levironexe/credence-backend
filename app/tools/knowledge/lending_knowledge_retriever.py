"""
Lending Knowledge Retriever Tool

Retrieves relevant lending regulations, policies, and best practices from the RAG knowledge base.
"""

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)


class KnowledgeRetrieverInput(BaseModel):
    """Input schema for Knowledge Retriever."""
    query: str = Field(description="Search query for lending knowledge (regulations, policies, best practices)")
    category: Optional[str] = Field(
        default=None,
        description="Filter by category: regulation, best_practice, risk_assessment, assessment_methodology"
    )
    k: Optional[int] = Field(default=3, description="Number of documents to retrieve (default: 3)")


class LendingKnowledgeRetriever(BaseTool):
    """
    Retrieves relevant lending knowledge from RAG database.

    Use this tool to:
    - Look up regulatory requirements (Basel III, FCRA, ECOA, Dodd-Frank)
    - Find best practices for financial analysis
    - Understand risk assessment methodologies
    - Get guidance on credit score interpretation
    - Learn about alternative data usage

    Example queries:
    - "What are the FCRA requirements for adverse action notices?"
    - "What financial ratios indicate high default risk?"
    - "How should I interpret a credit score of 680?"
    - "What alternative data can I use for thin-file applicants?"
    """

    @property
    def name(self) -> str:
        return "lending_knowledge_retriever"

    @property
    def description(self) -> str:
        return (
            "Retrieves relevant lending regulations, policies, and best practices from the knowledge base. "
            "Use this to look up regulatory requirements (FCRA, ECOA, Basel III, Dodd-Frank), "
            "financial analysis best practices, risk assessment methodologies, and credit scoring guidelines."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return KnowledgeRetrieverInput

    async def execute(
        self,
        query: str,
        category: Optional[str] = None,
        k: Optional[int] = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Retrieve relevant knowledge from RAG database.

        Args:
            query: Search query
            category: Optional category filter
            k: Number of documents to retrieve

        Returns:
            Dictionary containing retrieved documents and formatted context
        """
        try:
            logger.info(f"Retrieving knowledge for query: {query}")

            # Initialize RAG service if needed
            await rag_service.initialize()

            # Build metadata filter if category specified
            filter_metadata = None
            if category:
                filter_metadata = {"category": category}

            # Retrieve documents
            docs = await rag_service.retrieve(
                query=query,
                k=k,
                filter_metadata=filter_metadata
            )

            if not docs:
                return {
                    "success": True,
                    "documents": [],
                    "context": "No relevant regulations or policies found for this query.",
                    "message": "No results found"
                }

            # Format documents for response
            formatted_docs = []
            for doc in docs:
                formatted_docs.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "Unknown"),
                    "title": doc.metadata.get("title", ""),
                    "category": doc.metadata.get("category", ""),
                    "jurisdiction": doc.metadata.get("jurisdiction", "")
                })

            # Create formatted context for LLM
            context = rag_service.format_context(docs)

            return {
                "success": True,
                "documents": formatted_docs,
                "context": context,
                "count": len(docs),
                "message": f"Retrieved {len(docs)} relevant documents"
            }

        except Exception as e:
            logger.error(f"Knowledge retrieval failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "documents": [],
                "context": "",
                "message": f"Failed to retrieve knowledge: {str(e)}"
            }


# Create singleton instance
lending_knowledge_retriever = LendingKnowledgeRetriever()
