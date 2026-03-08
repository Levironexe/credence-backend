import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)
async def planning_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 1: Planning

        Assesses the user's query and determines the loan assessment approach.
        Performs initial risk classification and outlines assessment steps.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with assessment plan and initial risk classification
        """
        messages = state["messages"]
        last_message = messages[-1].content if messages else ""

        planning_prompt = """You are a senior loan officer analyzing SME loan applications. Provide a CONCISE assessment plan (3-5 bullet points max):

1. Analysis type needed (credit scoring, financial analysis, risk assessment)
2. Available data vs. missing information
3. Initial risk level (low/medium/high/critical)
4. Recommended approach (1-2 sentences)

Be brief and actionable."""

        response = await llm.ainvoke([
            SystemMessage(content=planning_prompt),
            HumanMessage(content=last_message)
        ])

        # Extract risk level from response (heuristic-based classification)
        risk_level = "medium"  # default
        content_lower = response.content.lower()

        if any(keyword in content_lower for keyword in ["critical", "urgent", "high default risk", "fraudulent", "insolvent"]):
            risk_level = "critical"
        elif any(keyword in content_lower for keyword in ["high risk", "poor financials", "negative cash flow", "high leverage"]):
            risk_level = "high"
        elif any(keyword in content_lower for keyword in ["moderate risk", "fair", "needs review", "incomplete data"]):
            risk_level = "medium"
        elif any(keyword in content_lower for keyword in ["low risk", "strong financials", "good credit history"]):
            risk_level = "low"

        logger.info(f"Planning complete. Risk level: {risk_level}")

        return {
            **state,
            "analysis_steps": [f"Planning: {response.content}"],
            "risk_level": risk_level,
            "messages": state["messages"] + [response],
        }
