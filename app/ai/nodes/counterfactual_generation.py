import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def counterfactual_generation_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Counterfactual Generation

    Generate improvement paths for REJECTED applicants only.
    Shows what specific changes would push score above approval threshold.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with counterfactual improvement scenarios
    """
    logger.info("💡 Generating improvement paths...")

    # Find counterfactual generator tool
    counterfactual_tool = next((t for t in tools if t.name == "counterfactual_generator"), None)

    if not counterfactual_tool:
        logger.warning("⚠️ counterfactual_generator tool not available — skipping")
        return state

    # Get current credit score
    current_score = state.get("credit_score", 0)

    if current_score >= 670:
        logger.warning("⚠️ Credit score >= 670 — counterfactual generation not needed")
        return state

    logger.info(f"   Current score: {current_score}")
    logger.info("   Finding minimal changes to reach approval threshold (670)...")

    try:
        # Get features from state
        extracted_fields = state.get("extracted_fields", {})

        # Prepare current features
        current_features = {
            **extracted_fields,
            "credit_score": current_score,
            "default_probability": state.get("default_probability", 0.0),
            "risk_level": state.get
            ("risk_level", "high")
        }

        # Call counterfactual generator
        result = await counterfactual_tool.ainvoke({
            "current_features": current_features,
            "current_score": current_score,
            "target_score": 670
        })

        counterfactuals = result.get("counterfactuals", [])

        logger.info(f"   ✅ {len(counterfactuals)} improvement path(s) found")

        # Log each counterfactual
        for i, cf in enumerate(counterfactuals[:3], 1):  # Log top 3
            changes = cf.get("changes", {})
            expected_score = cf.get("expected_score", 0)
            logger.info(f"      Path {i}: {changes} → score: {expected_score}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Counterfactual generation: {len(counterfactuals)} improvement paths identified"
        )

        return {
            **state,
            "counterfactuals": counterfactuals,
            "analysis_steps": analysis_steps,
        }

    except Exception as e:
        logger.error(f"❌ Error generating counterfactuals: {str(e)}")
        return state
