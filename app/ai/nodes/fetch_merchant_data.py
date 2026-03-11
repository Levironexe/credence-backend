"""
Fetch Merchant Data Node

This node fetches merchant profile data from Supabase via MCP tools.
It extracts the merchant_id from user input, calls the appropriate MCP tool,
and stores the retrieved merchant profile in LangGraph state.

Integration:
    - Fits between classify → fetch_merchant_data → data_completeness
    - Uses MCP Supabase tools for data retrieval
    - Handles missing merchant_id gracefully
"""

import logging
import re
from typing import Dict, Any, Optional

from app.ai.state import LoanAssessmentState

logger = logging.getLogger(__name__)


def extract_merchant_id(text: str) -> Optional[str]:
    """
    Extract merchant_id from user input using pattern matching.

    Supports various formats:
    - "merchant ID 4827"
    - "merchant_id: 4827"
    - "merchant 4827"
    - "ID: 4827"
    - "assess 4827"

    Args:
        text: User input text

    Returns:
        Extracted merchant_id as string or None if not found

    Example:
        >>> extract_merchant_id("Assess merchant ID 4827")
        "4827"
        >>> extract_merchant_id("Evaluate loan for merchant_id: ABC-123")
        "ABC-123"
    """
    # Pattern 1: "merchant ID 4827" or "merchant_id 4827"
    pattern1 = r'merchant[_\s]*id[:\s]+([a-zA-Z0-9\-_]+)'
    match = re.search(pattern1, text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: "merchant 4827" (without "ID")
    pattern2 = r'merchant[:\s]+([a-zA-Z0-9\-_]+)'
    match = re.search(pattern2, text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: "ID: 4827" or "id 4827"
    pattern3 = r'\bid[:\s]+([a-zA-Z0-9\-_]+)'
    match = re.search(pattern3, text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 4: "assess 4827" (command followed by ID)
    pattern4 = r'\b(?:assess|evaluate|analyze|check)[:\s]+([a-zA-Z0-9\-_]+)'
    match = re.search(pattern4, text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


async def fetch_merchant_data_node(
    state: LoanAssessmentState,
    llm,
    tools: list
) -> Dict[str, Any]:
    """
    Node: Fetch Merchant Data

    Extract merchant_id from user input, fetch merchant profile from Supabase
    via MCP tools, and store in state.

    Workflow:
        1. Extract merchant_id from last user message
        2. Find appropriate MCP tool (fetch_merchant_by_id, query_merchant, etc.)
        3. Invoke tool with merchant_id
        4. Parse and store merchant profile in state
        5. Log results and handle errors

    Args:
        state: Current loan assessment state
        llm: ChatAnthropic LLM instance (not used, kept for consistency)
        tools: List of available tools (including MCP tools)

    Returns:
        Updated state with merchant_profile populated

    State Updates:
        - merchant_profile: Dict containing merchant data from Supabase
        - analysis_steps: Append merchant data fetch status

    Example merchant_profile structure:
        {
            "merchant_id": "4827",
            "name": "Coffee Shop Co.",
            "industry": "Food & Beverage",
            "registration_date": "2020-01-15",
            "annual_revenue": 250000,
            "monthly_transactions": 1200,
            "average_transaction_value": 25.50,
            ...
        }
    """
    logger.info("🔍 Fetching merchant data from MCP Supabase...")

    # Extract last user message
    messages = state.get("messages", [])
    if not messages:
        logger.warning("⚠️ No messages in state - skipping merchant data fetch")
        return {**state, "merchant_profile": {}}

    # Handle multimodal content
    last_message = messages[-1].content
    if isinstance(last_message, list):
        # Extract text from multimodal content
        text_content = " ".join([
            part.get("text", "") for part in last_message
            if part.get("type") == "text"
        ])
    else:
        text_content = last_message

    # Extract merchant_id
    merchant_id = extract_merchant_id(text_content)

    if not merchant_id:
        logger.warning("⚠️ No merchant_id found in user input")
        logger.info(f"   Searched in: {text_content[:100]}...")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append("Merchant data fetch: No merchant_id provided")

        return {
            **state,
            "merchant_profile": {},
            "analysis_steps": analysis_steps
        }

    logger.info(f"   Extracted merchant_id: {merchant_id}")

    # Find MCP Supabase tool for fetching merchant data
    # Common tool names: fetch_merchant_by_id, query_merchant, get_merchant
    merchant_tool = None
    for tool in tools:
        tool_name_lower = tool.name.lower()
        if any(keyword in tool_name_lower for keyword in [
            "merchant", "fetch_merchant", "query_merchant", "get_merchant"
        ]):
            merchant_tool = tool
            logger.info(f"   Using MCP tool: {tool.name}")
            break

    if not merchant_tool:
        logger.warning("⚠️ No merchant-related MCP tool found")
        logger.info(f"   Available tools: {[t.name for t in tools]}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Merchant data fetch: Tool not available (merchant_id: {merchant_id})"
        )

        return {
            **state,
            "merchant_profile": {"merchant_id": merchant_id},
            "analysis_steps": analysis_steps
        }

    # Invoke MCP tool to fetch merchant data
    try:
        logger.info(f"   Calling {merchant_tool.name} with merchant_id: {merchant_id}")

        # Different tools may expect different input formats
        # Try common parameter names
        tool_input = None
        tool_description = getattr(merchant_tool, 'description', '').lower()

        # Determine input format based on tool description or schema
        if 'merchant_id' in tool_description:
            tool_input = {"merchant_id": merchant_id}
        elif 'id' in tool_description:
            tool_input = {"id": merchant_id}
        else:
            # Fallback: try both formats
            tool_input = {"merchant_id": merchant_id}

        logger.debug(f"   Tool input: {tool_input}")

        # Invoke tool
        result = await merchant_tool.ainvoke(tool_input)

        # Parse result
        merchant_profile = {}
        if isinstance(result, dict):
            merchant_profile = result
        elif isinstance(result, str):
            # Try to parse JSON string
            import json
            try:
                merchant_profile = json.loads(result)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Could not parse tool result as JSON: {result[:100]}...")
                merchant_profile = {"raw_response": result}
        elif hasattr(result, 'content'):
            # Handle ToolMessage format
            import json
            try:
                merchant_profile = json.loads(result.content)
            except json.JSONDecodeError:
                merchant_profile = {"raw_response": str(result.content)}
        else:
            merchant_profile = {"raw_response": str(result)}

        # Ensure merchant_id is in the profile
        if "merchant_id" not in merchant_profile:
            merchant_profile["merchant_id"] = merchant_id

        logger.info(f"✅ Merchant data retrieved successfully")
        logger.info(f"   Merchant: {merchant_profile.get('name', 'N/A')}")
        logger.info(f"   Industry: {merchant_profile.get('industry', 'N/A')}")
        logger.info(f"   Fields: {list(merchant_profile.keys())}")

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Merchant data fetch: Success (ID: {merchant_id}, "
            f"{len(merchant_profile)} fields retrieved)"
        )

        return {
            **state,
            "merchant_profile": merchant_profile,
            "analysis_steps": analysis_steps
        }

    except Exception as e:
        logger.error(f"❌ Error fetching merchant data: {str(e)}")
        logger.error(f"   Tool: {merchant_tool.name}")
        logger.error(f"   Input: {tool_input}")

        # Store partial profile with error information
        merchant_profile = {
            "merchant_id": merchant_id,
            "error": str(e),
            "error_type": type(e).__name__
        }

        # Update analysis steps
        analysis_steps = state.get("analysis_steps", [])
        analysis_steps.append(
            f"Merchant data fetch: Failed (ID: {merchant_id}, error: {str(e)[:50]})"
        )

        return {
            **state,
            "merchant_profile": merchant_profile,
            "analysis_steps": analysis_steps
        }
