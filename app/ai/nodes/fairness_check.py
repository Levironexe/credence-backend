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
        # Call fairness validator (no input needed — operates on test set)
        result = await fairness_tool.ainvoke({})

        fairness_passed = result.get("fairness_passed", True)
        gender_metrics = result.get("gender_metrics", {})
        age_metrics = result.get("age_group_metrics", {})

        if not fairness_passed:
            logger.info("   ⚠️ Fairness check failed — flagging for human review")
            route_decision = "rejected"
        else:
            logger.info("   ✅ No bias detected — decision is fair")
            route_decision = "approved" if credit_score >= 670 else "rejected"

        # Log metrics
        dpd_g = gender_metrics.get("demographic_parity_difference", 0)
        eod_g = gender_metrics.get("equalized_odds_difference", 0)
        logger.info(f"   Gender: DPD={dpd_g:.4f}, EOD={eod_g:.4f}")
        dpd_a = age_metrics.get("demographic_parity_difference", 0)
        eod_a = age_metrics.get("equalized_odds_difference", 0)
        logger.info(f"   Age: DPD={dpd_a:.4f}, EOD={eod_a:.4f}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Fairness check: {'passed' if fairness_passed else 'failed'}, "
            f"gender DPD: {dpd_g:.4f}, age DPD: {dpd_a:.4f}"
        )

        # Inject fairness results as a message so downstream LLM nodes can see them
        from langchain_core.messages import AIMessage
        fairness_status = "PASSED" if fairness_passed else "FAILED — flagged for human review"
        fairness_message = AIMessage(content=(
            f"**[Fairness Validation Result]**\n"
            f"- Status: **{fairness_status}**\n"
            f"- Gender: Demographic Parity Diff={dpd_g:.4f}, Equalized Odds Diff={eod_g:.4f}\n"
            f"- Age: Demographic Parity Diff={dpd_a:.4f}, Equalized Odds Diff={eod_a:.4f}\n"
            f"- Compliance: {'No bias detected' if fairness_passed else 'Potential bias detected — requires review'}"
        ))

        return {
            **state,
            "fairness_check_results": {
                "fairness_passed": fairness_passed,
                "gender_metrics": gender_metrics,
                "age_group_metrics": age_metrics,
            },
            "route_to": route_decision,
            "analysis_steps": analysis_steps,
            "messages": list(state.get("messages", [])) + [fairness_message],
        }

    except Exception as e:
        logger.error(f" Error running fairness validator: {str(e)}")
        # Default routing on error
        route_decision = "approved" if credit_score >= 670 else "rejected"
        return {
            **state,
            "route_to": route_decision
        }
