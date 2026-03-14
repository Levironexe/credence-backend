import logging
from typing import Dict, Any

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


class ExtractedMetrics(BaseModel):
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metric values explicitly stated by the user, keyed by Home Credit column name or descriptive snake_case"
    )
    has_overrides: bool = Field(
        default=False,
        description="True if any metric values were explicitly stated by the user"
    )


METRIC_EXTRACTION_PROMPT = """Extract ONLY explicitly stated metric values from the user's message.

Map to Home Credit column names where possible:
- AMT_INCOME_TOTAL → annual income / revenue / yearly income
- AMT_CREDIT → loan amount / credit amount
- AMT_ANNUITY → monthly payment / annuity
- DAYS_BIRTH → age in years (convert: years * -365.25, round to int)
- DAYS_EMPLOYED → years employed (convert: years * -365.25, round to int)

For values not in the model (e.g. profit_margin, debt_to_equity): use descriptive snake_case keys.

Currency: strip symbols and convert shorthand (500K → 500000, 1.2M → 1200000, 300M → 300000000).
Percentages: store as decimal (18% → 0.18).

If nothing explicit is stated, return empty dict and has_overrides=False.

IMPORTANT: Only extract values the user EXPLICITLY states. Do not infer or guess."""


async def metric_extraction_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
    """
    Node: Metric Extraction

    Uses LLM structured output to parse user-stated metric overrides from the message.
    Extracted values are stored in user_metric_overrides and merged over dataset values
    by data_completeness_node.

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic (or any LangChain chat model) injected by the agent

    Returns:
        Updated state with user_metric_overrides dict
    """
    logger.info("📐 Extracting user metric overrides from message...")

    messages = state.get("messages", [])
    if not messages:
        logger.info("   No messages in state — skipping metric extraction")
        return {**state, "user_metric_overrides": {}}

    last_message = messages[-1].content

    # Handle multimodal content (list of parts)
    if isinstance(last_message, list):
        last_message = " ".join([
            part.get("text", "")
            for part in last_message
            if isinstance(part, dict) and part.get("type") == "text"
        ])

    try:
        structured_llm = llm.with_structured_output(ExtractedMetrics)
        result: ExtractedMetrics = await structured_llm.ainvoke([
            SystemMessage(content=METRIC_EXTRACTION_PROMPT),
            HumanMessage(content=last_message)
        ])

        if result.has_overrides and result.metrics:
            logger.info(f"   Extracted {len(result.metrics)} metric override(s): {list(result.metrics.keys())}")
            return {**state, "user_metric_overrides": result.metrics}
        else:
            logger.info("   No explicit metric overrides found in message")
            return {**state, "user_metric_overrides": {}}

    except Exception as e:
        logger.warning(f"   Metric extraction failed (fail-open): {type(e).__name__}: {e}")
        return {**state, "user_metric_overrides": {}}
