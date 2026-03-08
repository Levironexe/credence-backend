import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def document_ingestion_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Document Ingestion

    Extract data from uploaded financial documents (PDF, Excel, bank statements).
    Only runs if documents were attached to the request.
    If no documents, pass state through unchanged.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with extracted document data
    """
    documents = state.get("documents_processed", [])

    # If no documents uploaded, skip
    if not documents:
        logger.info("📄 No documents uploaded — skipping document ingestion")
        return {
            **state,
            "messages": state["messages"]
        }

    logger.info(f"📄 Processing {len(documents)} uploaded document(s)...")

    # Find document processing tools
    pdf_extractor = next((t for t in tools if t.name == "pdf_extractor"), None)
    bank_statement_parser = next((t for t in tools if t.name == "bank_statement_parser"), None)

    processed_documents = []

    for doc in documents:
        doc_type = doc.get("type", "unknown")
        doc_name = doc.get("name", "unnamed")

        logger.info(f"   Processing document: {doc_name} (type: {doc_type})")

        # Route to appropriate tool based on document type
        if doc_type == "pdf" and pdf_extractor:
            try:
                result = await pdf_extractor.ainvoke({"document": doc})
                processed_documents.append({
                    "name": doc_name,
                    "type": doc_type,
                    "extracted_data": result
                })
                logger.info(f"   ✅ Extracted data from {doc_name}")
            except Exception as e:
                logger.error(f"   ❌ Failed to process {doc_name}: {str(e)}")
                processed_documents.append({
                    "name": doc_name,
                    "type": doc_type,
                    "error": str(e)
                })

        elif doc_type == "bank_statement" and bank_statement_parser:
            try:
                result = await bank_statement_parser.ainvoke({"document": doc})
                processed_documents.append({
                    "name": doc_name,
                    "type": doc_type,
                    "extracted_data": result
                })
                logger.info(f"   ✅ Extracted data from {doc_name}")
            except Exception as e:
                logger.error(f"   ❌ Failed to process {doc_name}: {str(e)}")
                processed_documents.append({
                    "name": doc_name,
                    "type": doc_type,
                    "error": str(e)
                })
        else:
            logger.warning(f"   ⚠️ No suitable tool found for {doc_type}")
            processed_documents.append(doc)

    logger.info(f"📄 Document ingestion complete — processed {len(processed_documents)} document(s)")

    return {
        **state,
        "documents_processed": processed_documents,
    }
