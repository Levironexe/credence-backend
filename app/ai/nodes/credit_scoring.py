import logging
import re
from typing import Dict, Any

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


def extract_features_from_message(message_content: str) -> Dict[str, Any]:
    """
    Extract credit_risk_dataset features from user message.

    Supports two formats:
    1. CSV format: "22,59000,RENT,123.0,PERSONAL,D,35000,16.02,1,0.59,Y,3"
    2. Natural language (fallback to pattern matching)

    Args:
        message_content: The user's message text

    Returns:
        Dictionary of extracted features matching credit_risk_dataset schema
    """
    features = {}

    # Feature names from credit_risk_dataset
    FEATURE_NAMES = [
        "person_age", "person_income", "person_home_ownership",
        "person_emp_length", "loan_intent", "loan_grade",
        "loan_amnt", "loan_int_rate", "loan_percent_income",
        "cb_person_default_on_file", "cb_person_cred_hist_length"
    ]

    # Try CSV format first (exact match from dataset)
    # Format: person_age,person_income,person_home_ownership,person_emp_length,loan_intent,loan_grade,loan_amnt,loan_int_rate,loan_status,loan_percent_income,cb_person_default_on_file,cb_person_cred_hist_length
    # Example: 22,59000,RENT,123.0,PERSONAL,D,35000,16.02,1,0.59,Y,3

    # More flexible CSV pattern (allows optional spaces)
    csv_pattern = r'(\d+),\s*(\d+),\s*([\w]+),\s*([\d.]+),\s*([\w]+),\s*([A-G]),\s*([\d]+),\s*([\d.]+)(?:,\s*\d+)?,\s*([\d.]+),\s*([YN]),\s*([\d]+)'
    csv_match = re.search(csv_pattern, message_content)

    if csv_match:
        # Parse CSV format
        try:
            features = {
                "person_age": float(csv_match.group(1)),
                "person_income": float(csv_match.group(2)),
                "person_home_ownership": csv_match.group(3),
                "person_emp_length": float(csv_match.group(4)),
                "loan_intent": csv_match.group(5),
                "loan_grade": csv_match.group(6),
                "loan_amnt": float(csv_match.group(7)),
                "loan_int_rate": float(csv_match.group(8)),
                "loan_percent_income": float(csv_match.group(9)),
                "cb_person_default_on_file": csv_match.group(10),
                "cb_person_cred_hist_length": float(csv_match.group(11)),
            }
            logger.info(f"✓ Parsed CSV format successfully: {features}")
            return features
        except (ValueError, IndexError) as e:
            logger.warning(f"✗ Failed to parse CSV format: {e}")

    # Fallback: Try to extract from natural language
    content_lower = message_content.lower()

    # Extract age
    age_patterns = [r'age[:\s]+(\d+)', r'(\d+)\s*years?\s*old']
    for pattern in age_patterns:
        match = re.search(pattern, content_lower)
        if match:
            features['person_age'] = float(match.group(1))
            break

    # Extract income
    income_patterns = [
        r'income[:\s]+\$?(\d+(?:,\d{3})*)',
        r'earn[s]?\s+\$?(\d+(?:,\d{3})*)',
        r'salary[:\s]+\$?(\d+(?:,\d{3})*)'
    ]
    for pattern in income_patterns:
        match = re.search(pattern, content_lower)
        if match:
            features['person_income'] = float(match.group(1).replace(',', ''))
            break

    # Extract loan amount
    loan_patterns = [
        r'loan[:\s]+\$?(\d+(?:,\d{3})*)',
        r'\$(\d+(?:,\d{3})*)\s*loan'
    ]
    for pattern in loan_patterns:
        match = re.search(pattern, content_lower)
        if match:
            features['loan_amnt'] = float(match.group(1).replace(',', ''))
            break

    # Extract home ownership
    if 'rent' in content_lower:
        features['person_home_ownership'] = 'RENT'
    elif 'own' in content_lower or 'owner' in content_lower:
        features['person_home_ownership'] = 'OWN'
    elif 'mortgage' in content_lower:
        features['person_home_ownership'] = 'MORTGAGE'

    # Extract loan intent
    if 'personal' in content_lower:
        features['loan_intent'] = 'PERSONAL'
    elif 'education' in content_lower:
        features['loan_intent'] = 'EDUCATION'
    elif 'medical' in content_lower:
        features['loan_intent'] = 'MEDICAL'
    elif 'venture' in content_lower or 'business' in content_lower:
        features['loan_intent'] = 'VENTURE'

    # Extract employment length
    emp_patterns = [
        r'employed[:\s]+(\d+(?:\.\d+)?)\s*years?',
        r'(\d+(?:\.\d+)?)\s*years?\s*employment'
    ]
    for pattern in emp_patterns:
        match = re.search(pattern, content_lower)
        if match:
            features['person_emp_length'] = float(match.group(1))
            break

    # Extract default history
    if 'default' in content_lower and 'yes' in content_lower:
        features['cb_person_default_on_file'] = 'Y'
    elif 'default' in content_lower and 'no' in content_lower:
        features['cb_person_default_on_file'] = 'N'

    return features


async def credit_scoring_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Credit Scoring

    Dedicated node for running the XGBoost credit score model.
    Credit score must NEVER be generated by the LLM — only by this node.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, but kept for consistency)
        tools: List of available tools

    Returns:
        Updated state with credit score and risk level
    """
    logger.info("⚙️ Running credit score model (XGBoost)...")

    # Find credit score model tool
    credit_model = next((t for t in tools if t.name == "credit_score_model"), None)

    if not credit_model:
        logger.warning("⚠️ credit_score_model tool not available — skipping")
        return state

    # Try to get features from state first (set by data_completeness_node)
    features = state.get("extracted_fields", {})

    # If not in state, extract from message as fallback
    if not features:
        logger.info("   No extracted_fields in state, extracting from message...")
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

        features = extract_features_from_message(last_message)

    if not features:
        logger.warning("⚠️ No financial features found — cannot compute credit score")
        return state

    logger.info(f"   Using features: {features}")
    logger.info("   Computing default probability...")

    try:
        # Call the credit score model
        result = await credit_model.ainvoke(features)

        credit_score = result.get("credit_score", 0)
        default_probability = result.get("default_probability", 0.0)
        score_band = result.get("score_band", "unknown")
        confidence = result.get("confidence", 0.0)
        recommendation = result.get("recommendation", "")

        # Map score to risk level
        if credit_score >= 800:
            risk_level = "low"
        elif credit_score >= 670:
            risk_level = "low"
        elif credit_score >= 580:
            risk_level = "medium"
        else:
            risk_level = "high"

        logger.info(f"   ✅ Score computed: {credit_score} ({score_band})")
        logger.info(f"   Default probability: {default_probability:.2%}")
        logger.info(f"   Risk level: {risk_level}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Credit scoring: {credit_score} ({score_band}), "
            f"default probability: {default_probability:.2%}, "
            f"risk: {risk_level}"
        )

        return {
            **state,
            "credit_score": credit_score,
            "default_probability": default_probability,
            "risk_level": risk_level,
            "analysis_steps": analysis_steps,
        }

    except Exception as e:
        logger.error(f" Error running credit score model: {str(e)}")
        return state
