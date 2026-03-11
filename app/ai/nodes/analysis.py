import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)

async def analysis_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 4: Analysis

        Previously synthesized findings via LLM. Now skipped entirely —
        the response node handles all report generation directly from
        ML model outputs (credit score, SHAP, fairness, counterfactuals)
        that are already injected as AIMessages in the conversation.

        This node is kept as a pass-through to avoid breaking the graph edges.
        """
        tools_used = state.get("tools_used", [])

        if not tools_used:
            logger.info("Skipping analysis node - no tools were used")
            return state

        # Pass through — do NOT generate any LLM response here.
        # The response node will generate the full report directly.
        logger.info("Analysis node: pass-through (report generated in response node)")
        return state
