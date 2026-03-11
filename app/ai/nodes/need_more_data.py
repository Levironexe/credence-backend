import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

async def need_more_data_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node: Need More Data Response

        Handles queries where the user wants an assessment but hasn't provided
        sufficient financial data. Prompts them for the required information.

        Args:
            state: Current assessment state
            llm: ChatAnthropic LLM instance

        Returns:
            Updated state with data request response
        """
        messages = state["messages"]

        # Include analysis steps context (e.g. failed applicant lookup) so LLM can give a relevant response
        analysis_steps = state.get("analysis_steps", [])
        context = ""
        if analysis_steps:
            context = f"\n\nContext from prior analysis steps:\n" + "\n".join(f"- {s}" for s in analysis_steps)

        prompt = f"""The user wants a loan assessment but hasn't provided enough data.{context}

If an applicant lookup failed (invalid ID), tell the user the valid ID range and suggest they try again.

Otherwise, politely request the missing critical information needed for assessment:
- Loan amount requested
- Monthly/annual revenue
- Business age/tenure
- Profit margin or net income
- Industry/business type

Keep it friendly and concise (2-3 sentences). Explain that you need these details to provide an accurate credit assessment."""

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            *messages
        ])

        logger.info("Requested additional data from user")

        return {
            **state,
            "messages": state["messages"] + [response],
            "final_response": response.content,
        }
