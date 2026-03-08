import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

async def analysis_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 4: Analysis

        Synthesizes financial data, identifies risk factors, and provides credit assessment.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with credit analysis and risk assessment
        """
        messages = state["messages"]
        credit_score = state.get("credit_score", 0)
        risk_level = state.get("risk_level", "medium")
        tools_used = state.get("tools_used", [])
        
        # Skip analysis if no tools were used (nothing to analyze)
        if not tools_used:
            logger.info("⏭️ Skipping analysis node - no tools were used")
            return state

        analysis_prompt = f"""Provide a CONCISE credit analysis based on tool results. Start with "## Credit Analysis\n\n"

**Context:** Risk Level: {risk_level} | Credit Score: {credit_score} | Tools: {', '.join(tools_used) if tools_used else 'None'}

**Required (be brief):**
1. **Credit Score & Key Metrics** - List actual numbers from tool results (1-2 sentences)
2. **Risk Factors** - Top 2-3 concerns from tool outputs (bullet points)
3. **Loan Decision** - Approve/decline, amount, rate, key conditions (3-4 bullet points max)

**Style:** Direct, factual, concise. Use ONLY tool data. No speculation. Aim for 150-200 words total."""

        response = await llm.ainvoke([
            SystemMessage(content=analysis_prompt),
            *messages
        ])

        logger.info("Completed credit analysis based on tool results")

        return {
            **state,
            "messages": state["messages"] + [response],
        }
