import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

async def response_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 5: Response Generation

        Generates a final formatted loan assessment report for the user.
        Structures findings in a clear, professional format suitable for loan officers.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with final formatted response
        """
        messages = state["messages"]
        risk_level = state.get("risk_level", "medium")
        tools_used = state.get("tools_used", [])

        # Use different prompt based on whether tools were used
        if tools_used:
            # Formal credit report when tools were used
            response_prompt = f"""Generate a final loan assessment report based on the analysis.

**Assessment Summary:**
- Risk Level: {risk_level.upper()}
- Credit Score: {state.get('credit_score', 'Not calculated')}
- Default Probability: {state.get('default_probability', 'Not calculated')}
- Tools Used: {', '.join(tools_used)}

**Format Requirements:**
- Clear, professional tone suitable for a loan officer
- Structured sections (Executive Summary, Financial Analysis, Credit Decision, Recommendations)
- Actionable loan recommendation (approve/decline, amount, rate, terms)
- Reference specific financial metrics and risk factors

Start your response with "# Loan Assessment Report\n\n" followed by the report."""
        else:
            # More conversational response when no tools were used
            response_prompt = """Based on the loan assessment planning above, provide helpful guidance to the user.

**Your Response Should:**
- Be conversational and natural (not a formal report)
- Acknowledge what information is needed to investigate further
- Provide actionable next steps for the user
- Explain what you would do if specific indicators were provided
- Be concise and helpful

Do NOT use rigid templates or empty sections. Just have a natural conversation about their query."""

        final_response = await llm.ainvoke([
            SystemMessage(content=response_prompt),
            *messages
        ])

        logger.info("Loan assessment complete - final report generated")

        return {
            **state,
            "messages": state["messages"] + [final_response],
            "final_response": final_response.content,
        }
