import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def explainability_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Explainability

    Run TreeSHAP on the credit score to produce per-feature importance scores
    and a waterfall plot image.
    """
    logger.info("Running SHAP explainability (TreeSHAP)...")

    # Find SHAP explainer tool
    shap_tool = next((t for t in tools if t.name == "shap_explainer"), None)

    if not shap_tool:
        logger.warning("shap_explainer tool not available — skipping")
        return state

    # Check if credit score exists
    credit_score = state.get("credit_score")
    if not credit_score:
        logger.warning("No credit score available — cannot run SHAP explainer")
        return state

    logger.info("   Analyzing feature contributions...")

    try:
        # Get features from state (set by data_completeness_node)
        extracted_fields = state.get("extracted_fields", {})

        if not extracted_fields:
            logger.warning("No extracted features available — cannot run SHAP explainer")
            return state

        # Call SHAP explainer (wrap in applicant_data per tool schema)
        result = await shap_tool.ainvoke({"applicant_data": extracted_fields})

        explanations = result.get("explanations", [])
        waterfall_plot = result.get("waterfall_plot", None)

        # Log top 3 features
        logger.info("   Top factors identified:")
        for i, feat in enumerate(explanations[:3], 1):
            label = feat.get("label", feat.get("feature", "unknown"))
            shap_val = feat.get("shap_value", 0.0)
            direction = feat.get("direction", "")
            logger.info(f"      {i}. {label}: {shap_val:+.4f} ({direction})")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        top_3_names = [f.get("label", f.get("feature", "?")) for f in explanations[:3]]
        analysis_steps.append(
            f"SHAP analysis: top factors — {', '.join(top_3_names)}"
        )

        # Build the SHAP message with BOTH image and structured data
        # The structured data ensures the LLM can answer follow-up questions
        from langchain_core.messages import AIMessage

        shap_lines = ["**[SHAP Feature Importance — Top Factors Driving Credit Score]**\n"]

        # Note: waterfall plot is stored in state as base64 data URI,
        # passed to the response node via shap_explanations, NOT embedded
        # in the LLM conversation (too large for token context).
        if waterfall_plot:
            shap_lines.append("*(Waterfall plot generated — available for display)*\n")

        # Include structured data so LLM can reference exact values in follow-ups
        shap_lines.append("**Detailed SHAP Values:**\n")
        for i, feat in enumerate(explanations[:10], 1):
            label = feat.get("label", feat.get("feature", "unknown"))
            shap_val = feat.get("shap_value", 0.0)
            direction = feat.get("direction", "")
            value = feat.get("value", "")
            shap_lines.append(f"{i}. **{label}**: SHAP={shap_val:+.4f} ({direction}) [value={value}]")

        base_value = result.get("base_value")
        if base_value is not None:
            shap_lines.append(f"\nBase value (average prediction): {base_value:.4f}")

        shap_message = AIMessage(content="\n".join(shap_lines))

        return {
            **state,
            "shap_explanations": {
                "explanations": explanations,
                "base_value": base_value,
                "waterfall_plot": waterfall_plot,
            },
            "analysis_steps": analysis_steps,
            "messages": list(state.get("messages", [])) + [shap_message],
        }

    except Exception as e:
        logger.error(f" Error running SHAP explainer: {str(e)}")
        return state
