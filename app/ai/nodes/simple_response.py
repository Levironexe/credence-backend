import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

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

        SIMPLE_RESPONSE_PROMPT = """You are Credence AI, an SME loan assessment assistant.

        The user has asked a general question (not related to loan assessment).
        Respond naturally and helpfully.

        If they want loan assessment help, mention that you can analyze loan applications, calculate credit scores, assess financial statements, and provide lending recommendations."""

        response = await llm.ainvoke([
            SystemMessage(content=SIMPLE_RESPONSE_PROMPT),
            *messages
        ])

        logger.info("Generated simple response for non-assessment query")

        return {
            **state,
            "messages": state["messages"] + [response],
            "final_response": response.content,
        }