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
    all_extracted_features = {}

    for doc in documents:
        doc_type = doc.get("type", "unknown")
        doc_name = doc.get("name", "unnamed")
        file_path = doc.get("file_path", "")

        logger.info(f"   Processing document: {doc_name} (type: {doc_type})")

        if doc_type == "pdf" and pdf_extractor:
            try:
                # Step 1: Extract text from PDF
                pdf_result = await pdf_extractor.ainvoke({"file_path": file_path})

                if pdf_result and isinstance(pdf_result, str):
                    import json
                    try:
                        pdf_result = json.loads(pdf_result)
                    except (json.JSONDecodeError, TypeError):
                        pdf_result = {"success": False, "error": "Unexpected response format"}

                if pdf_result.get("success") and pdf_result.get("text"):
                    extracted_text = pdf_result["text"]
                    logger.info(f"   ✅ Extracted text from {doc_name} ({pdf_result.get('pages', 0)} pages)")

                    # Step 2: Parse bank statement features from extracted text
                    if bank_statement_parser:
                        try:
                            parse_result = await bank_statement_parser.ainvoke({
                                "statement_text": extracted_text
                            })

                            if parse_result and isinstance(parse_result, str):
                                try:
                                    parse_result = json.loads(parse_result)
                                except (json.JSONDecodeError, TypeError):
                                    parse_result = {"success": False}

                            if parse_result.get("success"):
                                features = parse_result.get("extracted_features", {})
                                all_extracted_features.update(features)
                                logger.info(f"   ✅ Parsed {len(features)} features from {doc_name}")

                                processed_documents.append({
                                    "name": doc_name,
                                    "type": doc_type,
                                    "extracted_data": parse_result,
                                })
                            else:
                                logger.warning(f"   ⚠️ Bank statement parsing returned no features for {doc_name}")
                                processed_documents.append({
                                    "name": doc_name,
                                    "type": doc_type,
                                    "extracted_data": pdf_result,
                                })
                        except Exception as e:
                            logger.error(f"    Bank statement parsing failed for {doc_name}: {str(e)}")
                            processed_documents.append({
                                "name": doc_name,
                                "type": doc_type,
                                "extracted_data": pdf_result,
                            })
                    else:
                        processed_documents.append({
                            "name": doc_name,
                            "type": doc_type,
                            "extracted_data": pdf_result,
                        })
                else:
                    error = pdf_result.get("error", "Unknown error")
                    logger.error(f"    PDF extraction failed for {doc_name}: {error}")
                    processed_documents.append({
                        "name": doc_name,
                        "type": doc_type,
                        "error": error,
                    })

            except Exception as e:
                logger.error(f"    Failed to process {doc_name}: {str(e)}")
                processed_documents.append({
                    "name": doc_name,
                    "type": doc_type,
                    "error": str(e),
                })
        else:
            logger.warning(f"   ⚠️ No suitable tool found for {doc_type}")
            processed_documents.append(doc)

    logger.info(f"📄 Document ingestion complete — processed {len(processed_documents)} document(s)")

    # Merge extracted features into state
    existing_fields = state.get("extracted_fields", {})
    existing_fields.update(all_extracted_features)

    return {
        **state,
        "documents_processed": processed_documents,
        "extracted_fields": existing_fields,
    }
