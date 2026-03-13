import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)


async def simple_response_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node: Simple Response

        Handles non-loan assessment queries with a straightforward response.

        Args:
            state: Current loan assessment state
            llm: ChatAnthropic LLM instance

        Returns:
            Updated state with simple response
        """
        messages = state["messages"]
        selected_profile_id = state.get("selected_profile_id", "")

        profile_context = ""
        if selected_profile_id:
            profile_context = f"\n\nThe loan officer has selected Applicant #{selected_profile_id} from the sidebar panel. If relevant, mention that you can assess this applicant."
        else:
            profile_context = "\n\nNo applicant profile is currently selected. If the user wants a credit assessment, suggest they select an applicant from the right sidebar panel, or provide an applicant ID."

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
- If they want a new assessment, suggest they select an applicant from the sidebar or provide an applicant ID.{profile_context}"""

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