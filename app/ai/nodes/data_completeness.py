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

    # Check for applicant ID — either from sidebar selection or from message text
    import re
    selected_profile_id = state.get("selected_profile_id", "")
    applicant_match = re.search(r'applicant\s*#?\s*(\d+)', last_message, re.IGNORECASE)

    applicant_id = None
    if selected_profile_id and selected_profile_id.isdigit():
        applicant_id = int(selected_profile_id)
        logger.info(f"   Using selected profile from sidebar: #{applicant_id}")
    elif applicant_match:
        applicant_id = int(applicant_match.group(1))

    if applicant_id is not None:
        logger.info(f"   Detected applicant lookup: #{applicant_id}")

        # Load from database only
        try:
            from app.database import AsyncSessionLocal
            from app.models.applicant import Applicant
            from app.routers.applicants import map_db_to_features
            from sqlalchemy import select as sa_select

            async with AsyncSessionLocal() as db_session:
                result = await db_session.execute(
                    sa_select(Applicant).where(Applicant.id == applicant_id)
                )
                db_app = result.scalar_one_or_none()

            if db_app:
                extracted_features = map_db_to_features(db_app)
                logger.info(f"   Loaded {len(extracted_features)} features from DB for applicant #{applicant_id}")

                analysis_steps = state.get("analysis_steps", [])
                analysis_steps.append(
                    f"Data completeness check: loaded "
                    f"({len(extracted_features)} features) — applicant #{applicant_id} from database"
                )

                return {
                    **state,
                    "applicant_id": applicant_id,
                    "data_completeness_score": 1.0,
                    "route_to": "complete",
                    "analysis_steps": analysis_steps,
                    "extracted_fields": extracted_features,
                }
        except Exception as e:
            logger.warning(f"   DB lookup failed for applicant #{applicant_id}: {e}")

        # Not found in DB
        error_msg = f"Applicant #{applicant_id} not found in database."
        logger.warning(f"   {error_msg}")

        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(f"Applicant lookup failed: {error_msg}")

        return {
            **state,
            "data_completeness_score": 0.0,
            "route_to": "incomplete",
            "analysis_steps": analysis_steps,
            "extracted_fields": {},
        }

    # Import the feature extraction from credit_scoring_node
    from app.ai.nodes.credit_scoring import extract_features_from_message

    # Extract features from the message
    extracted_features = extract_features_from_message(last_message)
    logger.info(f"   Extracted features from message: {extracted_features}")

    try:
        # Call the tool with extracted features (wrap in applicant_data per tool schema)
        result = await completeness_tool.ainvoke({"applicant_data": extracted_features})

        completeness_score = result.get("completeness_score", 0.0)
        missing_fields = result.get("missing_fields", {})  # dict: {name: {importance, label}}
        fields_present = result.get("fields_present", 0)
        fields_missing = result.get("fields_missing", 0)
        can_proceed = result.get("can_proceed", True)

        logger.info(f"   Fields present: {fields_present}, missing: {fields_missing}")

        # Group missing fields by SHAP importance (missing_fields is a dict)
        for field_name, info in missing_fields.items():
            imp = info.get("importance", 0)
            label = info.get("label", field_name)
            level = "high" if imp >= 0.20 else ("medium" if imp >= 0.10 else "low")
            logger.info(f"   Missing ({level} impact): {label}  [SHAP: {imp:.4f}]")

        # Determine routing — use can_proceed from tool, or fallback threshold
        if can_proceed:
            logger.info(f"   Completeness score: {completeness_score:.2f} — sufficient, proceeding")
            route_decision = "complete"
        else:
            logger.info(f"   Completeness score: {completeness_score:.2f} — insufficient, requesting missing data")
            route_decision = "incomplete"

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Data completeness check: {completeness_score:.2f} "
            f"({fields_present} present, {fields_missing} missing)"
        )

        return {
            **state,
            "data_completeness_score": completeness_score,
            "route_to": route_decision,
            "analysis_steps": analysis_steps,
            "extracted_fields": extracted_features,
        }

    except Exception as e:
        logger.error(f" Error running data completeness check: {str(e)}")
        # Default to complete on error to not block the flow
        return {
            **state,
            "data_completeness_score": 0.5,
            "route_to": "complete"
        }
