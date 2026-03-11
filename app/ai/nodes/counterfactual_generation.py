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
        # Get features from state (extracted in data_completeness_node)
        extracted_fields = state.get("extracted_fields", {})

        if not extracted_fields:
            logger.warning("⚠️ No extracted features available — cannot generate counterfactuals")
            return state

        # Call counterfactual generator (wrap in applicant_data per tool schema)
        result = await counterfactual_tool.ainvoke({"applicant_data": extracted_fields})

        counterfactuals = result.get("counterfactuals", [])
        original_score = result.get("original_score", current_score)

        logger.info(f"   ✅ {len(counterfactuals)} improvement path(s) found (original score: {original_score})")

        # Log each counterfactual
        for i, cf in enumerate(counterfactuals[:3], 1):  # Log top 3
            changes = cf.get("changes", [])
            new_score = cf.get("new_score", 0)
            change_summary = ", ".join(c.get("label", c.get("feature", "?")) for c in changes)
            logger.info(f"      Path {i}: [{change_summary}] → score: {new_score}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Counterfactual generation: {len(counterfactuals)} improvement paths identified"
        )

        # Inject counterfactual results as a pre-formatted table the LLM must copy verbatim
        from langchain_core.messages import AIMessage

        # Features where LOWER is better for the applicant
        LOWER_IS_BETTER = {
            "AMT_CREDIT", "AMT_ANNUITY", "AMT_GOODS_PRICE",
            "bureau_debt_sum", "bureau_active_count",
            "credit_income_ratio", "annuity_income_ratio", "bureau_debt_credit_ratio",
        }

        def _parse_numeric(val):
            """Extract numeric value from string like '4.0 years' or '385,308.00'."""
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                import re
                cleaned = re.sub(r'[^\d.\-]', '', val.replace(',', ''))
                try:
                    return float(cleaned)
                except ValueError:
                    return None
            return None

        def _format_delta(old_val, new_val, feature_name):
            """Format delta string with arrow indicator."""
            old_num = _parse_numeric(old_val)
            new_num = _parse_numeric(new_val)
            if old_num is None or new_num is None:
                return ""
            delta = new_num - old_num
            if abs(delta) < 0.001:
                return ""
            arrow = "↑" if delta > 0 else "↓"
            sign = "+" if delta > 0 else ""
            # Format delta value
            abs_delta = abs(delta)
            if abs_delta >= 1000:
                delta_str = f"{sign}{delta:,.0f}"
            elif abs_delta >= 1:
                delta_str = f"{sign}{delta:,.1f}"
            else:
                delta_str = f"{sign}{delta:,.3f}"
            return f" ({arrow}{delta_str})"

        cf_lines = [f"**[Counterfactual Analysis — How to Improve from Score {original_score} to 670+]**"]
        cf_lines.append("")
        cf_lines.append("COPY THE TABLES BELOW EXACTLY INTO THE REPORT — including the (↓/↑ delta) values in the Target column. Do NOT remove, paraphrase, or round ANY values.")
        for i, cf in enumerate(counterfactuals[:3], 1):
            changes = cf.get("changes", [])
            new_score = cf.get("new_score", 0)
            score_gain = new_score - original_score
            cf_lines.append(f"\n### Path {i} (projected score: {new_score}, +{score_gain} pts)")
            cf_lines.append("| Change | Current Value | Target Value |")
            cf_lines.append("|--------|--------------|--------------|")
            for change in changes:
                label = change.get("label", change.get("feature", "?"))
                feature = change.get("feature", "")
                old_val = change.get("current", "?")
                new_val = change.get("suggested", change.get("target", "?"))
                # Format numbers consistently
                raw_old = old_val
                raw_new = new_val
                if isinstance(old_val, float):
                    old_val = f"{old_val:,.2f}"
                if isinstance(new_val, float):
                    new_val = f"{new_val:,.2f}"
                # Compute delta indicator
                delta_str = _format_delta(raw_old, raw_new, feature)
                cf_lines.append(f"| {label} | {old_val} | {new_val}{delta_str} |")
        cf_message = AIMessage(content="\n".join(cf_lines))

        return {
            **state,
            "counterfactuals": counterfactuals,
            "analysis_steps": analysis_steps,
            "messages": list(state.get("messages", [])) + [cf_message],
        }

    except Exception as e:
        logger.error(f" Error generating counterfactuals: {str(e)}")
        return state
