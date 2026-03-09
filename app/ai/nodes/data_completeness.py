import logging
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


async def data_completeness_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Data Completeness Check

    Check what critical fields are missing, rank them by SHAP importance,
    decide whether to proceed or gate the workflow.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with completeness score and routing decision
    """
    logger.info("🔍 Checking data completeness...")

    # Find data completeness checker tool
    completeness_tool = next((t for t in tools if t.name == "data_completeness_checker"), None)

    if not completeness_tool:
        logger.warning("⚠️ data_completeness_checker tool not available — skipping")
        return {
            **state,
            "data_completeness_score": 1.0,  # Assume complete if tool unavailable
            "route_to": "complete"
        }

    # Extract last user message to check for provided data
    messages = state.get("messages", [])

    # Handle both string and list (multimodal) content
    if messages:
        content = messages[-1].content
        if isinstance(content, list):
            # Extract text from multimodal content
            last_message = " ".join([part.get("text", "") for part in content if part.get("type") == "text"])
        else:
            last_message = content
    else:
        last_message = ""

    # Import the feature extraction from credit_scoring_node
    from app.ai.nodes.credit_scoring import extract_features_from_message

    # Extract features from the message
    extracted_features = extract_features_from_message(last_message)

    try:
        # Call the tool with extracted features (not raw query)
        result = await completeness_tool.ainvoke(extracted_features)

        completeness_score = result.get("completeness_score", 0.0)
        missing_fields = result.get("missing_fields", [])
        present_fields = result.get("present_fields", [])
        extracted_fields = result.get("extracted_fields", {})

        # Log results - present_fields is a list of strings
        logger.info(f"   Available: {', '.join(present_fields) if present_fields else 'None'}")

        # Group missing fields by SHAP importance
        # Fix: use 'field' and 'importance' keys instead of 'name' and 'shap_importance'
        high_impact = [f for f in missing_fields if f.get("importance", 0) >= 0.20]
        medium_impact = [f for f in missing_fields if 0.10 <= f.get("importance", 0) < 0.20]
        low_impact = [f for f in missing_fields if f.get("importance", 0) < 0.10]

        if high_impact:
            for field in high_impact:
                logger.info(f"   Missing (high impact):   {field.get('field', 'unknown')}   [SHAP: {field.get('importance', 0):.2f}]")

        if medium_impact:
            for field in medium_impact:
                logger.info(f"   Missing (medium impact): {field.get('field', 'unknown')}  [SHAP: {field.get('importance', 0):.2f}]")

        if low_impact:
            for field in low_impact:
                logger.info(f"   Missing (low impact):    {field.get('field', 'unknown')}   [SHAP: {field.get('importance', 0):.2f}]")

        # Determine routing
        threshold = 0.4
        if completeness_score < threshold:
            logger.info(f"   Completeness score: {completeness_score:.2f} — below minimum threshold ({threshold}), requesting missing data")
            route_decision = "incomplete"
        else:
            logger.info(f"   Completeness score: {completeness_score:.2f} — above minimum threshold, proceeding")
            route_decision = "complete"

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Data completeness check: {completeness_score:.2f} "
            f"({len(present_fields)} present, {len(missing_fields)} missing)"
        )

        return {
            **state,
            "data_completeness_score": completeness_score,
            "route_to": route_decision,
            "analysis_steps": analysis_steps,
            "extracted_fields": extracted_fields,
        }

    except Exception as e:
        logger.error(f" Error running data completeness check: {str(e)}")
        # Default to complete on error to not block the flow
        return {
            **state,
            "data_completeness_score": 0.5,
            "route_to": "complete"
        }
