import logging
import re
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)

EFFORT_LABELS = {
    "immediate": "Now",
    "short_term": "Weeks",
    "long_term": "Months",
}

PATH_EFFORT_LABELS = {
    "Easiest": "Quick wins — changes you can make today",
    "Moderate": "Short-term actions — achievable in weeks",
    "Requires time": "Long-term plan — requires months of effort",
}


def _parse_numeric(val):
    """Extract numeric value from string like '4.0 years' or '385,308.00'."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r'[^\d.\-]', '', val.replace(',', ''))
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _format_delta(old_val, new_val):
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
    abs_delta = abs(delta)
    if abs_delta >= 1000:
        delta_str = f"{sign}{delta:,.0f}"
    elif abs_delta >= 1:
        delta_str = f"{sign}{delta:,.1f}"
    else:
        delta_str = f"{sign}{delta:,.3f}"
    return f" ({arrow}{delta_str})"


async def counterfactual_generation_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Counterfactual Generation

    Generate effort-ranked improvement paths for REJECTED applicants.
    Paths are ordered: easiest first (loan terms) → moderate (pay debt) → hard (income/employment).
    Derived ratios are recomputed, not independently varied.
    """
    logger.info("Generating improvement paths...")

    counterfactual_tool = next((t for t in tools if t.name == "counterfactual_generator"), None)

    if not counterfactual_tool:
        logger.warning("counterfactual_generator tool not available — skipping")
        return state

    current_score = state.get("credit_score", 0)

    if current_score >= 670:
        logger.warning("Credit score >= 670 — counterfactual generation not needed")
        return state

    logger.info(f"   Current score: {current_score}")
    logger.info("   Finding minimal changes to reach approval threshold (670)...")

    try:
        extracted_fields = state.get("extracted_fields", {})

        if not extracted_fields:
            logger.warning("No extracted features available — cannot generate counterfactuals")
            return state

        result = await counterfactual_tool.ainvoke({"applicant_data": extracted_fields})

        counterfactuals = result.get("counterfactuals", [])
        original_score = result.get("original_score", current_score)

        logger.info(f"   {len(counterfactuals)} improvement path(s) found (original score: {original_score})")

        for i, cf in enumerate(counterfactuals[:3], 1):
            changes = cf.get("changes", [])
            new_score = cf.get("new_score", 0)
            effort = cf.get("effort_level", "?")
            change_summary = ", ".join(c.get("label", c.get("feature", "?")) for c in changes if not c.get("is_derived"))
            logger.info(f"      Path {i} [{effort}]: [{change_summary}] -> score: {new_score}")

        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Counterfactual generation: {len(counterfactuals)} effort-ranked improvement paths identified"
        )

        # Build pre-formatted message for the LLM to copy verbatim
        from langchain_core.messages import AIMessage

        cf_lines = [f"**[Counterfactual Analysis — How to Improve from Score {original_score} to 670+]**"]
        cf_lines.append("")
        cf_lines.append("COPY THE TABLES BELOW EXACTLY INTO THE REPORT — including effort labels, (arrow delta) values, and derived ratio rows. Do NOT remove, paraphrase, or round ANY values.")

        for i, cf in enumerate(counterfactuals[:3], 1):
            changes = cf.get("changes", [])
            new_score = cf.get("new_score", 0)
            score_gain = new_score - original_score
            effort_level = cf.get("effort_level", "")
            effort_desc = PATH_EFFORT_LABELS.get(effort_level, "")

            cf_lines.append(f"\n### Path {i}: {effort_level} (projected score: {new_score}, +{score_gain} pts)")
            if effort_desc:
                cf_lines.append(f"*{effort_desc}*")
            cf_lines.append("")

            # Build brief causal intervention summary in natural advisory tone
            base_changes = [c for c in changes if not c.get("is_derived")]
            interventions = []
            for change in base_changes:
                feat = change.get("feature", "")
                old_val = change.get("current", "?")
                new_val = change.get("suggested", "?")
                old_num = _parse_numeric(old_val)
                new_num = _parse_numeric(new_val)

                if old_num is None or new_num is None:
                    desc = change.get("effort_description", "")
                    if desc:
                        interventions.append(desc)
                    continue

                delta = new_num - old_num

                # Natural advisory language per feature
                if feat == "AMT_CREDIT":
                    interventions.append(
                        f"Consider applying for a smaller loan — bringing it down to "
                        f"${new_num:,.0f} would significantly improve your profile"
                    )
                elif feat == "AMT_GOODS_PRICE":
                    interventions.append(
                        f"Looking at a more affordable option (around ${new_num:,.0f}) "
                        f"would help strengthen this application"
                    )
                elif feat == "AMT_ANNUITY":
                    if delta < 0:
                        interventions.append(
                            f"Extending the repayment term to lower monthly payments "
                            f"to around ${new_num:,.0f} would ease the debt burden"
                        )
                    else:
                        interventions.append(
                            f"Opting for a shorter repayment term (${new_num:,.0f}/month) "
                            f"shows stronger repayment capacity"
                        )
                elif feat == "AMT_INCOME_TOTAL":
                    interventions.append(
                        f"If annual income can reach ${new_num:,.0f} — through a raise, "
                        f"side income, or a co-borrower — the application becomes much stronger"
                    )
                elif feat == "DAYS_EMPLOYED" or "Employment" in change.get("label", ""):
                    interventions.append(
                        f"Staying in the current role longer ({new_val}) would demonstrate "
                        f"job stability — consider reapplying after building more tenure"
                    )
                elif feat == "bureau_debt_sum":
                    interventions.append(
                        f"Paying down existing debt to around ${new_num:,.0f} before applying "
                        f"would free up capacity and improve the credit profile"
                    )
                elif feat == "bureau_active_count":
                    interventions.append(
                        f"Closing {int(old_num - new_num)} unused credit line(s) simplifies "
                        f"the credit profile and reduces perceived risk"
                    )
                else:
                    # Generic fallback
                    if delta > 0:
                        interventions.append(f"Improving {change.get('label', feat).lower()} to {new_val}")
                    else:
                        interventions.append(f"Bringing {change.get('label', feat).lower()} down to {new_val}")

            if interventions:
                cf_lines.append("**What to do:** " + ". ".join(interventions) + ".")
                cf_lines.append("")

            cf_lines.append("| Action | Current | Target | Effort |")
            cf_lines.append("|--------|---------|--------|--------|")

            # Base feature changes first
            for change in base_changes:
                label = change.get("label", change.get("feature", "?"))
                old_val = change.get("current", "?")
                new_val = change.get("suggested", "?")
                effort = change.get("effort", "")
                effort_label = EFFORT_LABELS.get(effort, effort)

                raw_old = old_val
                raw_new = new_val
                if isinstance(old_val, float):
                    old_val = f"{old_val:,.2f}"
                if isinstance(new_val, float):
                    new_val = f"{new_val:,.2f}"
                delta_str = _format_delta(raw_old, raw_new)
                cf_lines.append(f"| {label} | {old_val} | {new_val}{delta_str} | {effort_label} |")

            # Derived ratios as "resulting improvements"
            derived = [c for c in changes if c.get("is_derived")]
            if derived:
                cf_lines.append(f"| **Resulting improvement** | | | |")
                for change in derived:
                    label = change.get("label", change.get("feature", "?"))
                    old_val = change.get("current", "?")
                    new_val = change.get("suggested", "?")
                    raw_old = old_val
                    raw_new = new_val
                    if isinstance(old_val, float):
                        old_val = f"{old_val:.3f}"
                    if isinstance(new_val, float):
                        new_val = f"{new_val:.3f}"
                    delta_str = _format_delta(raw_old, raw_new)
                    cf_lines.append(f"| {label} | {old_val} | {new_val}{delta_str} | auto |")

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
