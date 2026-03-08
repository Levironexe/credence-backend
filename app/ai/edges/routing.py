"""
Routing Functions for LangGraph Agent

Pure functions that determine conditional edges in the loan assessment workflow.
These functions only read state and return routing decisions - no LLM calls or side effects.
"""

import logging
from typing import Literal
from app.ai.state import LoanAssessmentState, QueryIntentType

logger = logging.getLogger(__name__)


def route_by_intent(state: LoanAssessmentState) -> Literal["simple", "single_tool", "full", "need_data"]:
    """
    Dynamic routing based on classified query intent.

    Routes to different workflow paths:
    - simple: Direct to simple_response for explanations
    - single_tool: Execute one specific tool
    - full: Full assessment workflow (planning -> tool_selection -> etc.)
    - need_data: Prompt user for missing data

    Args:
        state: Current assessment state

    Returns:
        Routing destination based on intent_type
    """
    intent = state.get("intent_type", QueryIntentType.FULL_ASSESSMENT.value)

    routing_map = {
        QueryIntentType.SIMPLE_EXPLANATION.value: "simple",
        QueryIntentType.SINGLE_TOOL.value: "single_tool",
        QueryIntentType.FULL_ASSESSMENT.value: "full",
        QueryIntentType.NEED_MORE_DATA.value: "need_data"
    }

    route = routing_map.get(intent, "full")
    logger.info(f"Routing to: {route} (intent: {intent})")

    return route


def should_use_tools(state: LoanAssessmentState) -> Literal["execute", "skip"]:
    """
    Decide whether tools should be executed or skipped.

    Args:
        state: Current investigation state

    Returns:
        "execute" if tools were called, "skip" otherwise
    """
    last_message = state["messages"][-1]

    logger.info("Checking if tools should be used:")
    logger.info(f"   Last message type: {type(last_message)}")
    logger.info(f"   Has tool_calls attribute: {hasattr(last_message, 'tool_calls')}")

    # Check if LLM requested tool calls
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        tool_names = [tc.get('name') if isinstance(tc, dict) else tc['name'] for tc in last_message.tool_calls]
        logger.info(f"   Tool calls found: {tool_names}")
        return "execute"

    logger.warning("   No tool calls found - skipping to analysis")
    content_preview = last_message.content[:200] if hasattr(last_message, 'content') else 'N/A'
    logger.debug(f"   Message content preview: {content_preview}")
    return "skip"


def calculate_query_complexity(state: LoanAssessmentState) -> int:
    """
    Calculate query complexity score to determine adaptive max_steps.

    Factors:
    - Data richness: More financial metrics = more complex
    - Tool results: More tools used = more complex analysis needed
    - Missing data score: Lower completeness = need more investigation

    Returns:
        Complexity score (0-5) for adaptive max_steps
    """
    last_message = state["messages"][-1] if state.get("messages") else None
    if not last_message:
        return 0

    content = str(last_message.content).lower()

    # Count financial data points mentioned
    data_indicators = [
        "revenue", "loan", "amount", "profit", "margin", "tenure", "years",
        "debt", "equity", "assets", "liabilities", "cash flow", "income"
    ]
    data_richness = sum(1 for indicator in data_indicators if indicator in content)

    # Check data completeness from state
    completeness = state.get("data_completeness_score", 1.0)

    # Calculate complexity
    complexity = min(data_richness // 2, 3)  # 0-3 from data richness
    if completeness < 0.7:
        complexity += 1  # +1 if data incomplete (need more tools)

    return min(complexity, 5)


def continue_investigation(state: LoanAssessmentState) -> Literal["continue", "analyze"]:
    """
    Decide if more investigation steps are needed with adaptive max_steps.

    Uses dynamic max_steps based on query complexity:
    - Simple queries: 3 tools max
    - Complex queries: Up to 10 tools

    Checks:
    1. Have we exceeded adaptive max tool steps?
    2. Did the last message request more tool calls?

    Args:
        state: Current investigation state

    Returns:
        "continue" to loop back for more tools, "analyze" to proceed to analysis
    """
    tools_used = state.get("tools_used", [])

    # Calculate adaptive max steps based on query complexity
    complexity_score = calculate_query_complexity(state)
    base_steps = 3
    max_steps = base_steps + complexity_score  # Range: 3-8 tools
    max_steps = min(max_steps, 10)  # Cap at 10 to prevent runaway

    logger.info(f"Complexity score: {complexity_score}, Max steps: {max_steps}, Current: {len(tools_used)}")

    if len(tools_used) >= max_steps:
        logger.info(f"Max tool steps ({max_steps}) reached - moving to analysis")
        return "analyze"

    # Check if LLM wants to call more tools
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        logger.info("Additional tools requested - continuing investigation")
        return "continue"

    return "analyze"


def route_after_data_completeness(state: LoanAssessmentState) -> Literal["complete", "incomplete"]:
    """
    Route based on data completeness check results.

    Args:
        state: Current loan assessment state

    Returns:
        "complete" if data is sufficient, "incomplete" if missing critical fields
    """
    route_to = state.get("route_to", "complete")
    completeness_score = state.get("data_completeness_score", 1.0)

    if route_to == "incomplete" or completeness_score < 0.4:
        logger.info(f"Routing to need_more_data (completeness: {completeness_score:.2f})")
        return "incomplete"
    else:
        logger.info(f"Routing to planning (completeness: {completeness_score:.2f})")
        return "complete"


def route_after_fairness_check(state: LoanAssessmentState) -> Literal["approved", "rejected"]:
    """
    Route based on credit score and fairness check results.

    Args:
        state: Current loan assessment state

    Returns:
        "approved" if score >= 670 and no bias detected, "rejected" otherwise
    """
    credit_score = state.get("credit_score", 0)
    fairness_results = state.get("fairness_check_results", {})
    bias_detected = fairness_results.get("bias_detected", False)
    route_to = state.get("route_to", "rejected")

    # If bias detected, always reject regardless of score
    if bias_detected:
        logger.info(f"Routing to counterfactual_generation (bias detected, score: {credit_score})")
        return "rejected"

    # Route based on state["route_to"] set by fairness_check_node
    if route_to == "rejected" or credit_score < 670:
        logger.info(f"Routing to counterfactual_generation (score: {credit_score})")
        return "rejected"
    else:
        logger.info(f"Routing to analysis (score: {credit_score}, no bias)")
        return "approved"
