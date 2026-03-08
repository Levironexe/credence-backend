import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import ToolNode
from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

async def execute_tools_node(state: LoanAssessmentState, llm, tool_node) -> Dict[str, Any]:
        """
        Node 3: Tool Execution

        Executes tools selected by the LLM and captures results.

        Args:
            state: Current loan assessment state
            llm: ChatAnthropic LLM instance (not used, but kept for consistency)
            tool_node: ToolNode instance for executing tool calls

        Returns:
            Updated state with tool execution results
        """
        last_message = state["messages"][-1]

        # Check if there are tool calls to execute
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔧 Executing {len(last_message.tool_calls)} tool(s)")

            # Log each tool call with arguments
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                logger.info(f"   📞 Calling tool: {tool_name}")
                logger.info(f"      Arguments: {tool_args}")

            # Use ToolNode to execute all tool calls
            result = await tool_node.ainvoke(state)
            logger.info("✅ Tool execution completed")

            # Track which tools were used
            tools_used = state.get("tools_used", [])
            tool_results = state.get("tool_results", [])

            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tools_used.append(tool_name)
                tool_results.append({
                    "tool": tool_name,
                    "args": tool_call.get("args", {}),
                    "timestamp": "now"  # You could add actual timestamp
                })

            logger.info(f"   Tools executed: {', '.join([tc['name'] for tc in last_message.tool_calls])}")

            return {
                **result,
                "tools_used": tools_used,
                "tool_results": tool_results,
            }

        # No tools to execute
        return state
