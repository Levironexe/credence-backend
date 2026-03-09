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

        # Combine with credit scoring results
        features = {
            **extracted_fields,
            "credit_score": credit_score,
            "default_probability": state.get("default_probability", 0.0),
            "risk_level": state.get("risk_level", "medium")
        }

        # Call SHAP explainer
        result = await shap_tool.ainvoke(features)

        top_features = result.get("top_features", [])
        shap_values = result.get("shap_values", {})

        # Log top 3 features
        logger.info("   ✅ Top factors identified:")
        for i, feature in enumerate(top_features[:3], 1):
            feature_name = feature.get("name", "unknown")
            importance = feature.get("importance", 0.0)
            logger.info(f"      {i}. {feature_name}: {importance:+.3f}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        top_3_names = [f["name"] for f in top_features[:3]]
        analysis_steps.append(
            f"SHAP analysis: top factors — {', '.join(top_3_names)}"
        )

        return {
            **state,
            "shap_explanations": {
                "top_features": top_features,
                "shap_values": shap_values
            },
            "analysis_steps": analysis_steps,
        }

    except Exception as e:
        logger.error(f" Error running SHAP explainer: {str(e)}")
        return state
