import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def fairness_check_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Fairness Check

    Validate that the credit decision is demographically fair.
    Always runs on every assessment — never skipped.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with fairness validation results and routing decision
    """
    logger.info("⚖️ Running fairness validation...")

    # Find fairness validator tool
    fairness_tool = next((t for t in tools if t.name == "fairness_validator"), None)

    if not fairness_tool:
        logger.warning("⚠️ fairness_validator tool not available — skipping")
        # Default to approved if score >= 670
        credit_score = state.get("credit_score", 0)
        route_decision = "approved" if credit_score >= 670 else "rejected"
        return {
            **state,
            "route_to": route_decision
        }

    # Get credit score and features
    credit_score = state.get("credit_score", 0)
    extracted_fields = state.get("extracted_fields", {})

    # Combine extracted fields with credit scoring results
    features = {
        **extracted_fields,
        "credit_score": credit_score,
        "default_probability": state.get("default_probability", 0.0),
        "risk_level": state.get("risk_level", "medium")
    }

    # Protected attributes to check
    protected_attributes = ["gender", "region", "ethnicity"]

    logger.info("   Checking demographic parity...")
    logger.info(f"   Flipping protected attributes ({', '.join(protected_attributes)})...")

    try:
        # Call fairness validator
        result = await fairness_tool.ainvoke({
            "features": features,
            "protected_attributes": protected_attributes
        })

        fairness_passed = result.get("fairness_passed", True)
        demographic_parity_difference = result.get("demographic_parity_difference", 0.0)
        bias_detected = result.get("bias_detected", False)

        if bias_detected:
            logger.info("   ⚠️ Bias detected — flagging for human review")
            route_decision = "rejected"  # Always reject if bias detected
        elif not fairness_passed:
            logger.info("   ⚠️ Fairness check failed — flagging for human review")
            route_decision = "rejected"
        else:
            logger.info("   ✅ No bias detected — decision is fair")
            # Route based on credit score
            route_decision = "approved" if credit_score >= 670 else "rejected"

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Fairness check: {'passed' if fairness_passed else 'failed'}, "
            f"bias: {'detected' if bias_detected else 'none'}, "
            f"parity diff: {demographic_parity_difference:.3f}"
        )

        return {
            **state,
            "fairness_check_results": {
                "fairness_passed": fairness_passed,
                "demographic_parity_difference": demographic_parity_difference,
                "bias_detected": bias_detected
            },
            "route_to": route_decision,
            "analysis_steps": analysis_steps,
        }

    except Exception as e:
        logger.error(f" Error running fairness validator: {str(e)}")
        # Default routing on error
        route_decision = "approved" if credit_score >= 670 else "rejected"
        return {
            **state,
            "route_to": route_decision
        }
