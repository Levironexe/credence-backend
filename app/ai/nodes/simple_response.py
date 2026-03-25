import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

# Keywords that indicate the question may benefit from RAG knowledge base lookup
RAG_TRIGGER_KEYWORDS = [
    "regulation", "law", "circular", "decree", "sbv", "state bank",
    "lending limit", "provisioning", "classification", "capital adequacy",
    "basel", "cic", "credit score", "aml", "anti-money", "kyc",
    "consumer protection", "fintech", "sandbox", "collateral",
    "loan classification", "npl", "non-performing", "risk weight",
    "policy", "compliance", "requirement", "rule", "guideline",
    "best practice", "credence score", "default risk", "early warning",
    "debt ratio", "sme", "small and medium",
]


def _should_query_rag(messages) -> bool:
    """Check if the user's question likely relates to lending knowledge."""
    last_message = messages[-1].content if messages else ""
    if isinstance(last_message, list):
        last_message = " ".join(
            part.get("text", "") for part in last_message
            if isinstance(part, dict) and part.get("type") == "text"
        )
    query_lower = last_message.lower()
    return any(kw in query_lower for kw in RAG_TRIGGER_KEYWORDS)


async def simple_response_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node: Simple Response

        Handles non-loan assessment queries with a straightforward response.
        Automatically queries the RAG knowledge base when the question relates
        to lending regulations, policies, or best practices.

        Args:
            state: Current loan assessment state
            llm: ChatAnthropic LLM instance

        Returns:
            Updated state with simple response
        """
        messages = state["messages"]
        selected_profile_id = state.get("selected_profile_id", "")

        # --- RAG context injection ---
        rag_context = ""
        if _should_query_rag(messages):
            try:
                from app.services.rag_service import rag_service

                last_msg = messages[-1].content if messages else ""
                if isinstance(last_msg, list):
                    last_msg = " ".join(
                        part.get("text", "") for part in last_msg
                        if isinstance(part, dict) and part.get("type") == "text"
                    )

                docs = await rag_service.retrieve(query=last_msg, k=3)
                if docs:
                    rag_context = "\n\n**Relevant Knowledge Base Context:**\n" + rag_service.format_context(docs)
                    logger.info(f"RAG injected {len(docs)} documents into simple_response")
            except Exception as e:
                logger.warning(f"RAG retrieval failed in simple_response, continuing without: {e}")

        profile_context = ""
        if selected_profile_id:
            profile_context = f"\n\nThe loan officer has selected Applicant #{selected_profile_id} from the sidebar panel. If relevant, mention that you can assess this applicant."
        else:
            profile_context = "\n\nNo applicant profile is currently selected. If the user wants a credit assessment, suggest they select an applicant from the right sidebar panel, or provide an applicant ID."

        rag_instruction = ""
        if rag_context:
            rag_instruction = """
- **IMPORTANT**: Relevant documents from the lending knowledge base are provided below. Use them as your PRIMARY source for answering regulatory, policy, or best-practice questions. Cite specific laws, circulars, or guidelines when possible. Do NOT rely on general knowledge when the knowledge base provides an answer."""

        SIMPLE_RESPONSE_PROMPT = f"""You are Credence AI, an SME loan assessment assistant for Vietnamese financial institutions.

You are responding to a loan officer's question. This may be:
- A follow-up question about a previous assessment report in this conversation
- A general question about credit, lending, or finance

**Instructions:**
- If the conversation history contains a Loan Assessment Report, USE that data to answer follow-up questions. Reference specific numbers, factors, and findings from the report.
- Be specific and data-driven — don't give generic answers when you have the actual assessment data in context.
- Write for a loan officer with 5+ years of experience — professional, concise, actionable.
- NEVER mention technical ML terms (XGBoost, SHAP, model, features, training data). Use credit/lending industry language.
- Instead of "SHAP values" say "credit factors" or "score drivers". Instead of "model" say "Credence Credit Engine" or just omit.
- If they want a new assessment, suggest they select an applicant from the sidebar or provide an applicant ID.{rag_instruction}{profile_context}{rag_context}"""

        collected_content = ""
        async for chunk in llm.astream([
            SystemMessage(content=SIMPLE_RESPONSE_PROMPT),
            *messages
        ]):
            if hasattr(chunk, 'content') and chunk.content:
                collected_content += chunk.content

        response = AIMessage(content=collected_content)
        logger.info("Generated simple response for non-assessment query")

        return {
            **state,
            "messages": state["messages"] + [response],
            "final_response": collected_content,
        }