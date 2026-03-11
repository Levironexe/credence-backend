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

    Run TreeSHAP on the credit score to produce per-feature importance scores.
    Depends on credit_scoring_node having run first.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with SHAP explanations
    """
    logger.info("🔍 Running SHAP explainability (TreeSHAP)...")

    # Find SHAP explainer tool
    shap_tool = next((t for t in tools if t.name == "shap_explainer"), None)

    if not shap_tool:
        logger.warning("⚠️ shap_explainer tool not available — skipping")
        return state

    # Check if credit score exists
    credit_score = state.get("credit_score")
    if not credit_score:
        logger.warning("⚠️ No credit score available — cannot run SHAP explainer")
        return state

    logger.info("   Analyzing feature contributions...")

    try:
        # Get features from state (set by data_completeness_node)
        extracted_fields = state.get("extracted_fields", {})

        if not extracted_fields:
            logger.warning("⚠️ No extracted features available — cannot run SHAP explainer")
            return state

        # Call SHAP explainer (wrap in applicant_data per tool schema)
        result = await shap_tool.ainvoke({"applicant_data": extracted_fields})

        explanations = result.get("explanations", [])

        # Log top 3 features
        logger.info("   ✅ Top factors identified:")
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

        # Inject SHAP results as a message so downstream LLM nodes can see them
        from langchain_core.messages import AIMessage
        shap_lines = ["**[SHAP Feature Importance — Top Factors Driving Credit Score]**"]
        for i, feat in enumerate(explanations[:7], 1):
            label = feat.get("label", feat.get("feature", "unknown"))
            shap_val = feat.get("shap_value", 0.0)
            direction = feat.get("direction", "")
            value = feat.get("value", "")
            shap_lines.append(f"{i}. **{label}**: SHAP={shap_val:+.4f} ({direction}) [value={value}]")
        shap_message = AIMessage(content="\n".join(shap_lines))

        return {
            **state,
            "shap_explanations": {
                "explanations": explanations,
                "base_value": result.get("base_value"),
            },
            "analysis_steps": analysis_steps,
            "messages": list(state.get("messages", [])) + [shap_message],
        }

    except Exception as e:
        logger.error(f" Error running SHAP explainer: {str(e)}")
        return state
