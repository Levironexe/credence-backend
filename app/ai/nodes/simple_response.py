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

        SIMPLE_RESPONSE_PROMPT = f"""You are Credence AI, an SME loan assessment assistant.

        The user has asked a general question (not related to loan assessment).
        Respond naturally and helpfully.

        If they want loan assessment help, mention that you can analyze loan applications, calculate credit scores, assess financial statements, and provide lending recommendations.{profile_context}"""

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