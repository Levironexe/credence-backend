import asyncio
import logging
from typing import Dict, Any
from functools import partial
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)


async def single_tool_execution_node(state: LoanAssessmentState, llm, tools) -> Dict[str, Any]:
        """
        Node: Single Tool Execution

        Executes a single specific tool and returns the result directly.
        Bypasses the full planning/tool_selection workflow for efficiency.

        Args:
            state: Current assessment state
            llm: ChatAnthropic LLM instance
            tools: List of available tools

        Returns:
            Updated state with tool result and formatted response
        """
        tool_name = state.get("single_tool_name", "")
        messages = state["messages"]

        if not tool_name:
            logger.error("Single tool execution requested but no tool_name specified")
            return state

        logger.info(f"⚡ Fast path: Executing single tool: {tool_name}")

        # Find the tool by name
        tool_to_execute = None
        for tool in tools:
            if tool.name == tool_name:
                tool_to_execute = tool
                break

        if not tool_to_execute:
            logger.error(f"Tool {tool_name} not found in available tools")
            error_response = AIMessage(content=f"Error: Tool '{tool_name}' is not available.")
            return {
                **state,
                "messages": state["messages"] + [error_response],
                "final_response": error_response.content,
            }

        # Use LLM with this single tool bound to extract parameters
        llm_with_tool = llm.bind_tools([tool_to_execute], tool_choice="any")

        # Only pass the last user message to keep token usage low (50K tokens/min limit)
        recent_messages = messages[-1:]

        # Ask LLM to call the tool with appropriate parameters
        tool_prompt = f"""Extract the parameters for the {tool_name} tool from the user's query and call it."""

        tool_call_message = await llm_with_tool.ainvoke([
            SystemMessage(content=tool_prompt),
            *recent_messages
        ])

        # Execute the tool
        if hasattr(tool_call_message, 'tool_calls') and tool_call_message.tool_calls:
            # Create a minimal ToolNode with just this tool
            tool_node = ToolNode([tool_to_execute])
            temp_state = {"messages": list(recent_messages) + [tool_call_message]}
            result = await tool_node.ainvoke(temp_state)

            # Format the result into a natural response
            tool_result_message = result["messages"][-1]
            if tool_name == "lending_knowledge_retriever":
                summary_prompt = (
                    "The lending knowledge base was queried. Synthesize the retrieved documents into a clear, "
                    "authoritative answer for the loan officer. Cite specific regulations, laws, or circulars "
                    "(e.g., 'Under Law 32/2024, Article X...' or 'Per Circular 11/2021...'). "
                    "Write for a loan officer with 5+ years of experience — professional, concise, actionable. "
                    "NEVER mention 'RAG', 'vector database', 'embeddings', or 'knowledge base' — just present "
                    "the information as authoritative lending guidance."
                )
            else:
                summary_prompt = f"""The {tool_name} tool was executed. Summarize the results in a clear, concise way for the user."""

            # Only pass user question + tool result for summarization (not full history)
            # Truncate tool result to avoid exceeding rate limits (RAG results can be very large)
            last_user_msg = recent_messages[-1]
            result_content = tool_result_message.content if hasattr(tool_result_message, 'content') else str(tool_result_message)
            if len(result_content) > 3000:
                result_content = result_content[:3000] + "\n\n[... truncated for brevity]"
            final_response = await llm.ainvoke([
                SystemMessage(content=summary_prompt),
                last_user_msg,
                HumanMessage(content=f"Tool result:\n{result_content}"),
            ], max_tokens=1024)

            return {
                **state,
                "messages": state["messages"] + [tool_call_message, tool_result_message, final_response],
                "tools_used": [tool_name],
                "final_response": final_response.content,
            }

        # If tool call failed, return error
        error_response = AIMessage(content=f"Could not extract parameters for {tool_name} from your query.")
        return {
            **state,
            "messages": state["messages"] + [error_response],
            "final_response": error_response.content,
        }