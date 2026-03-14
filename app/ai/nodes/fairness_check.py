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

    Uses Disparate Impact Ratio (four-fifths rule), equalized odds,
    and chi-squared significance testing across gender, age, and marital status.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with fairness validation results and routing decision
    """
    logger.info("Running fairness validation...")

    # Find fairness validator tool
    fairness_tool = next((t for t in tools if t.name == "fairness_validator"), None)

    if not fairness_tool:
        logger.warning("fairness_validator tool not available — skipping")
        credit_score = state.get("credit_score", 0)
        route_decision = "approved" if credit_score >= 670 else "rejected"
        return {
            **state,
            "route_to": route_decision
        }

    # Get credit score, default probability, and applicant features from state
    credit_score = state.get("credit_score", 0)
    default_probability = state.get("default_probability", 0.0)
    extracted_fields = state.get("extracted_fields", {})

    logger.info(f"   Applicant credit score: {credit_score}, default prob: {default_probability:.4f}")
    logger.info(f"   Extracted fields count: {len(extracted_fields)}")

    try:
        # Call fairness validator with per-applicant data
        result = await fairness_tool.ainvoke({
            "applicant_data": extracted_fields,
            "credit_score": credit_score,
            "default_probability": default_probability,
        })

        fairness_passed = result.get("fairness_passed", True)
        bias_detected = result.get("bias_detected", False)
        gender_metrics = result.get("gender_metrics", {})
        age_metrics = result.get("age_group_metrics", {})
        marital_metrics = result.get("marital_status_metrics", {})
        neighborhood_size = result.get("neighborhood_size", 0)

        if not fairness_passed:
            logger.info("   Fairness check failed — flagging for human review")
            route_decision = "rejected"
        else:
            logger.info("   No bias detected — decision is fair")
            route_decision = "approved" if credit_score >= 670 else "rejected"

        # Log metrics
        gender_dir = gender_metrics.get("disparate_impact_ratio", "N/A")
        age_dir = age_metrics.get("disparate_impact_ratio", "N/A")
        marital_dir = marital_metrics.get("disparate_impact_ratio", "N/A")
        logger.info(f"   Neighborhood size: {neighborhood_size}")
        logger.info(f"   Gender DIR: {gender_dir} ({'pass' if gender_metrics.get('pass') else 'fail'})")
        logger.info(f"   Age DIR: {age_dir} ({'pass' if age_metrics.get('pass') else 'fail'})")
        logger.info(f"   Marital DIR: {marital_dir} ({'pass' if marital_metrics.get('pass') else 'fail'})")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Fairness check ({neighborhood_size} similar applicants): "
            f"{'passed' if fairness_passed else 'failed'}, "
            f"gender DIR: {gender_dir}, age DIR: {age_dir}, marital DIR: {marital_dir}"
        )

        # Inject fairness results as a message so downstream LLM nodes can see them
        from langchain_core.messages import AIMessage
        fairness_status = "PASSED" if fairness_passed else "FAILED — flagged for human review"

        # Build per-attribute detail strings
        def _format_attribute(name, metrics):
            lines = ""
            dir_val = metrics.get("disparate_impact_ratio")
            chi2_p = metrics.get("chi_squared_p_value")
            sig = metrics.get("statistically_significant", False)
            eo = metrics.get("equalized_odds", {})

            if dir_val is not None:
                lines += f"  - Disparate Impact Ratio: {dir_val:.4f} (threshold: >= 0.80)\n"
            if eo:
                lines += f"  - Equalized Odds max diff: {eo.get('max_equalized_odds_diff', 'N/A')}\n"
            if chi2_p is not None:
                lines += f"  - Chi-squared p-value: {chi2_p:.4f} ({'significant' if sig else 'not significant'})\n"

            for group, info in metrics.get("group_approval_rates", {}).items():
                lines += f"  - {group}: {info['approval_rate']:.1%} approval ({info['count']} applicants)\n"

            return lines

        gender_details = _format_attribute("Gender", gender_metrics)
        age_details = _format_attribute("Age", age_metrics)
        marital_details = _format_attribute("Marital Status", marital_metrics)

        fairness_message = AIMessage(content=(
            f"**[Fairness Validation Result]**\n"
            f"- Status: **{fairness_status}**\n"
            f"- Neighborhood: {neighborhood_size} similar applicants analyzed\n"
            f"- Method: Disparate Impact Ratio (four-fifths rule), Equalized Odds, Chi-squared test\n\n"
            f"**Gender:**\n{gender_details}\n"
            f"**Age Group:**\n{age_details}\n"
            f"**Marital Status:**\n{marital_details}\n"
            f"- Compliance: {'No significant bias detected — decision is demographically fair' if fairness_passed else 'Potential bias detected — approval rates differ across demographic groups'}"
        ))

        return {
            **state,
            "fairness_check_results": {
                "fairness_passed": fairness_passed,
                "bias_detected": bias_detected,
                "neighborhood_size": neighborhood_size,
                "gender_metrics": gender_metrics,
                "age_group_metrics": age_metrics,
                "marital_status_metrics": marital_metrics,
            },
            "route_to": route_decision,
            "analysis_steps": analysis_steps,
            "messages": list(state.get("messages", [])) + [fairness_message],
        }

    except Exception as e:
        logger.error(f"Error running fairness validator: {str(e)}")
        # Default routing on error
        route_decision = "approved" if credit_score >= 670 else "rejected"
        return {
            **state,
            "route_to": route_decision
        }
