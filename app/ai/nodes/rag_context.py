"""
RAG Context Node

Retrieves relevant lending regulations from the knowledge base
based on the applicant's credit score and risk profile.
Runs as a visible pipeline step — invokes lending_knowledge_retriever
tool so it appears in the frontend pipeline UI.
"""

import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage
from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def rag_context_node(state: LoanAssessmentState, llm, tools) -> Dict[str, Any]:
    """
    Node: RAG Context Retrieval

    Queries the lending knowledge base for regulations relevant to the
    applicant's score band and decision. Invokes the lending_knowledge_retriever
    tool so the frontend sees it as a visible tool call in the pipeline.
    """
    credit_score = state.get("credit_score", 0)
    default_probability = state.get("default_probability", 0.0)
    tools_used = state.get("tools_used", [])

    if not tools_used or not credit_score:
        logger.info("RAG context skipped - no credit score available")
        return state

    score_band = (
        "Exceptional" if credit_score >= 800
        else "Very Good" if credit_score >= 740
        else "Good" if credit_score >= 670
        else "Fair" if credit_score >= 580
        else "Poor"
    )
    decision = (
        "AUTO-APPROVE" if credit_score >= 800
        else "APPROVE (with conditions)" if credit_score >= 670
        else "MANUAL REVIEW" if credit_score >= 580
        else "DECLINE"
    )

    # Find the lending_knowledge_retriever tool
    retriever_tool = None
    for tool in tools:
        if tool.name == "lending_knowledge_retriever":
            retriever_tool = tool
            break

    if not retriever_tool:
        logger.warning("lending_knowledge_retriever tool not found - skipping RAG")
        return state

    try:
        # Build a targeted query based on the applicant's situation
        rag_query = (
            f"lending decision {decision} credit score {score_band} "
            f"default probability {default_probability:.0%} "
            f"loan classification provisioning capital adequacy"
        )

        # Invoke the tool directly — this generates on_tool_start/on_tool_end
        # events that the SSE transform picks up as visible tool calls
        result = await retriever_tool.ainvoke({"query": rag_query, "k": 3})

        # Extract context from tool result
        rag_context = ""
        if isinstance(result, dict):
            rag_context = result.get("context", "")
        elif isinstance(result, str):
            import json
            try:
                parsed = json.loads(result)
                rag_context = parsed.get("context", "")
            except (json.JSONDecodeError, AttributeError):
                rag_context = result

        if rag_context:
            logger.info(f"RAG retrieved regulatory context ({len(rag_context)} chars)")

            # Inject as an AIMessage so the response node can see it
            rag_message = AIMessage(
                content=f"[Regulatory Context for {score_band} ({decision})]\n\n{rag_context}"
            )

            return {
                **state,
                "rag_context": rag_context,
                "messages": list(state.get("messages", [])) + [rag_message],
            }
        else:
            logger.info("RAG retrieval returned no results")

    except Exception as e:
        logger.warning(f"RAG context retrieval failed: {e}")

    return state
