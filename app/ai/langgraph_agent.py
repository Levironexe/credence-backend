"""
LangGraph Agent for SME Loan Assessment

This module implements a multi-step reasoning agent using LangGraph for
SME loan analysis, credit scoring, and risk assessment.

The agent follows a multi-node graph structure:
1. Planning: Assess loan application and determine analysis approach
2. Data Completeness Check: Identify missing critical fields
3. Tool Selection: Choose appropriate financial analysis tools
4. Tool Execution: Run selected tools to gather financial data
5. Credit Scoring: Calculate credit score and default probability
6. Analysis: Synthesize findings and risk assessment
7. Response Generation: Format final credit report

The agent maintains compatibility with the existing gateway interface,
returning OpenAI-compatible SSE chunks for seamless frontend integration.
"""

import logging
import base64
import httpx
import re
from enum import Enum
from typing import AsyncGenerator, List, Dict, Any, Literal, TypedDict, Annotated, Sequence, Optional, ClassVar
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.config import settings
# from app.ai.mcp_client import get_mcp_tools
from app.ai.nodes.classify import classify_node
from app.ai.nodes.planning import planning_node
from app.ai.nodes.tool_selection import tool_selection_node
from app.ai.nodes.single_tool_execution import single_tool_execution_node
from app.ai.nodes.execute_tools import execute_tools_node
from app.ai.nodes.analysis import analysis_node
from app.ai.nodes.response import response_node
from app.ai.nodes.need_more_data import need_more_data_node
from app.ai.nodes.simple_response import simple_response_node
from app.ai.nodes.document_ingestion import document_ingestion_node
from app.ai.nodes.data_completeness import data_completeness_node
from app.ai.nodes.credit_scoring import credit_scoring_node
from app.ai.nodes.explainability import explainability_node
from app.ai.nodes.fairness_check import fairness_check_node
from app.ai.nodes.counterfactual_generation import counterfactual_generation_node
from app.ai.nodes.fetch_merchant_data import fetch_merchant_data_node
from app.ai.state import LoanAssessmentState, QueryIntent
from app.ai.edges.routing import (
    route_by_intent,
    should_use_tools,
    continue_investigation,
    calculate_query_complexity,
    route_after_data_completeness,
    route_after_fairness_check
)

from functools import partial

logger = logging.getLogger(__name__)


# ============ CONFIGURATION CONSTANTS ============

# Tool execution limits
MAX_TOOL_STEPS = 10
BASE_STEPS = 3

# Risk assessment
DEFAULT_RISK_LEVEL = "medium"

# Credit score scale (Credence Score, 300-850)
CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 850

# Loan assessment keywords for complexity calculation
LOAN_KEYWORDS = [
    "revenue", "loan", "profit", "margin", "debt", "equity",
    "assets", "liabilities", "cash flow", "ebitda", "roce",
    "collateral", "guarantee", "tenure", "repayment"
]


# ============ LANGGRAPH AGENT CLASS ============

class LangGraphAgent:
    """
    LangGraph-powered SME loan assessment agent.

    This agent orchestrates multi-step loan assessments using financial analysis tools
    and LLM reasoning. It implements the same interface as ClaudeClient/GeminiClient
    for seamless integration with the existing gateway pattern.

    Usage:
        agent = LangGraphAgent()
        agent.register_tools([financial_statement_analyzer, credit_score_model, ...])

        async for chunk in agent.stream_chat_completion(
            model="agent/loan-analyst",
            messages=[{"role": "user", "content": "Assess loan for Coffee Shop Co..."}],
            temperature=0.7
        ):
            # chunk is in OpenAI-compatible format
            print(chunk)
    """

    # System prompt for tool calling and loan assessment
    SYSTEM_PROMPT: ClassVar[str] = """
You are CredenceAI, an SME loan assessment assistant.

Rules:
- Always follow the user's request exactly.
- If a tool exists for a task, you MUST use it.
- Never fabricate tool outputs.
- Never guess financial calculations.
- Always rely on tool results for credit scoring or analysis.
- If multiple tools are needed, call them in logical order.

IMPORTANT - Do NOT call these tools (they are handled by dedicated nodes):
- NEVER call data_completeness_checker — data completeness was already checked
- NEVER call credit_score_model — credit scoring is handled by a dedicated node
- NEVER call shap_explainer — explainability is handled by a dedicated node
- NEVER call fairness_validator — fairness check is handled by a dedicated node
- NEVER call counterfactual_generator — counterfactual generation is handled by a dedicated node

Priority:
Correct tool usage > reasoning > formatting.
"""

    def __init__(self):
        """Initialize the agent with LLM and build the loan assessment graph."""
        # Get model name from settings and map to Anthropic API format
        model_name = getattr(settings, 'agent_model', 'claude-sonnet-4-6')

        # Map friendly names to actual Anthropic API model names
        model_mapping = {
            # Haiku models (4.5 from Oct 2025)
            "claude-haiku-4.5": "claude-haiku-4-5-20251001",
            "claude-haiku-4-5": "claude-haiku-4-5-20251001",
            "claude-haiku": "claude-haiku-4-5-20251001",
            # Sonnet models (3.5 from Oct 2024)
            "claude-sonnet-4.5": "claude-3-5-sonnet-20241022",
            "claude-sonnet-4-5": "claude-3-5-sonnet-20241022",
            "claude-sonnet-3.5": "claude-3-5-sonnet-20241022",
            "claude-sonnet": "claude-3-5-sonnet-20241022",
            # Fallback to old Claude 3 Haiku if needed
            "claude-3-haiku": "claude-3-haiku-20240307",
            "claude-sonnet-4-6": "claude-sonnet-4-6"
        }
        anthropic_model = model_mapping.get(model_name, model_name)

        # Initialize LLM for reasoning (using Claude for multi-step reasoning)
        self.llm = ChatAnthropic(
            model=anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.7,
            max_tokens=4096,
        )

        # Tools will be registered here
        self.tools = []
        self.tool_node = None

        # Tool streaming state (reset per request in stream_chat_completion)
        self._tool_buffer = {}  # {run_id: {name, input, streamed}}

        # Build the loan assessment graph
        self.app = self._build_graph()

        logger.info(f"LangGraph agent initialized with model: {anthropic_model}")

    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """
        Recursively convert numpy types and NaN/Infinity to JSON-safe Python types.
        """
        import math
        import numpy as np
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            val = float(obj)
            return None if (math.isnan(val) or math.isinf(val)) else val
        elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        elif isinstance(obj, dict):
            return {k: LangGraphAgent._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [LangGraphAgent._sanitize_for_json(v) for v in obj]
        elif isinstance(obj, np.ndarray):
            return [LangGraphAgent._sanitize_for_json(v) for v in obj.tolist()]
        return obj

    def _format_tool_output(self, output: Any) -> str:
        """
        Format tool output for consistent display in SSE stream.

        Handles various output types: ToolMessage, dict, str, or other types.
        Attempts to pretty-print JSON when possible.

        Args:
            output: Raw tool output (ToolMessage, dict, str, or other)

        Returns:
            Formatted output string (pretty-printed JSON or plain text)
        """
        import json

        # Handle LangChain ToolMessage format
        if hasattr(output, 'content'):
            output_content = output.content
            try:
                # Try to parse if it's a JSON string
                parsed_output = json.loads(output_content)
                return json.dumps(self._sanitize_for_json(parsed_output), indent=2)
            except (json.JSONDecodeError, TypeError):
                return output_content
        elif isinstance(output, dict):
            return json.dumps(self._sanitize_for_json(output), indent=2)
        elif isinstance(output, str):
            try:
                parsed = json.loads(output)
                return json.dumps(self._sanitize_for_json(parsed), indent=2)
            except (json.JSONDecodeError, TypeError):
                return output
        else:
            return str(output)

    # async def register_mcp_tools(self):
    #     """
    #     Register MCP tools from configured MCP servers.

    #     This method fetches tools from MCP servers (Supabase, etc.) and
    #     merges them with existing tools.

    #     MCP tools are added to self.tools and the graph is rebuilt.

    #     Usage:
    #         agent = LangGraphAgent()
    #         await agent.register_mcp_tools()
    #     """
    #     try:
    #         logger.info("📦 Fetching MCP tools...")
    #         mcp_tools = await get_mcp_tools()

    #         if mcp_tools:
    #             # Merge with existing tools
    #             self.tools.extend(mcp_tools)
    #             self.tool_node = ToolNode(self.tools)

    #             # Rebuild graph with combined tools
    #             self.app = self._build_graph()

    #             logger.info(f"✅ Registered {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}")
    #         else:
    #             logger.warning("⚠️ No MCP tools available")

    #     except Exception as e:
    #         logger.warning(f"⚠️ Failed to register MCP tools: {str(e)}")
    #         logger.info("Continuing without MCP tools")

    def register_tools(self, tools: list):
        """
        Register tools for the agent to use during investigations.

        Args:
            tools: List of LangChain tools (use BaseTool.to_langchain_tool())
        """
        self.tools = tools
        if tools:
            self.tool_node = ToolNode(tools)
            # Rebuild graph with tools
            self.app = self._build_graph()
            logger.info(f"Registered {len(tools)} tools: {[t.name for t in tools]}")
        else:
            logger.warning("No tools registered - agent will run in reasoning-only mode")

    def _build_graph(self) -> StateGraph:
        """
        Build the SME loan assessment graph with dynamic routing.

        Complete flow:
        classify → fetch_merchant_data → document_ingestion → data_completeness
        → planning → tool_selection → execute_tools → credit_scoring
        → explainability → fairness_check → counterfactual_generation (conditional)
        → analysis → response

        Returns:
            Compiled StateGraph ready for execution
        """
        workflow = StateGraph(LoanAssessmentState)

        # ── Existing nodes ──────────────────────────────────────
        workflow.add_node("classify",
            partial(classify_node, llm=self.llm))
        workflow.add_node("simple_response",
            partial(simple_response_node, llm=self.llm))
        workflow.add_node("single_tool_execution",
            partial(single_tool_execution_node, llm=self.llm, tools=self.tools))
        workflow.add_node("need_more_data",
            partial(need_more_data_node, llm=self.llm))
        workflow.add_node("planning",
            partial(planning_node, llm=self.llm))
        workflow.add_node("tool_selection",
            partial(tool_selection_node, llm=self.llm, tools=self.tools, testing_system_prompt=self.SYSTEM_PROMPT))
        workflow.add_node("execute_tools",
            partial(execute_tools_node, llm=self.llm, tool_node=self.tool_node))
        workflow.add_node("analysis",
            partial(analysis_node, llm=self.llm))
        workflow.add_node("response",
            partial(response_node, llm=self.llm))
        workflow.add_node("document_ingestion",
            partial(document_ingestion_node, llm=self.llm, tools=self.tools))
        workflow.add_node("data_completeness",
            partial(data_completeness_node, llm=self.llm, tools=self.tools))
        workflow.add_node("credit_scoring",
            partial(credit_scoring_node, llm=self.llm, tools=self.tools))
        workflow.add_node("explainability",
            partial(explainability_node, llm=self.llm, tools=self.tools))
        workflow.add_node("fairness_check",
            partial(fairness_check_node, llm=self.llm, tools=self.tools))
        workflow.add_node("counterfactual_generation",
            partial(counterfactual_generation_node, llm=self.llm, tools=self.tools))
        workflow.add_node("fetch_merchant_data",
            partial(fetch_merchant_data_node, llm=self.llm, tools=self.tools))

        # ── Entry point ──────────────────────────────────────────
        workflow.set_entry_point("classify")

        # ── Classify routing ─────────────────────────────────────
        workflow.add_conditional_edges(
            "classify",
            route_by_intent,
            {
                "simple":       "simple_response",
                "single_tool":  "single_tool_execution",
                "full":         "fetch_merchant_data",   # NEW: fetch merchant data first
                "need_data":    "need_more_data"
            }
        )

        # ── Terminal nodes ───────────────────────────────────────
        workflow.add_edge("simple_response",       END)
        workflow.add_edge("single_tool_execution", END)
        workflow.add_edge("need_more_data",        END)

        # ── Full assessment flow ─────────────────────────────────
        workflow.add_edge("fetch_merchant_data", "document_ingestion")
        workflow.add_edge("document_ingestion", "data_completeness")

        workflow.add_conditional_edges(
            "data_completeness",
            route_after_data_completeness,
            {
                "complete":   "planning",
                "incomplete": "need_more_data"
            }
        )

        workflow.add_edge("planning", "tool_selection")

        workflow.add_conditional_edges(
            "tool_selection",
            should_use_tools,
            {
                "execute": "execute_tools",
                "skip":    "credit_scoring"   # changed: was "analysis"
            }
        )

        workflow.add_conditional_edges(
            "execute_tools",
            continue_investigation,
            {
                "continue": "tool_selection",
                "analyze":  "credit_scoring"  # changed: was "analysis"
            }
        )

        # ── New dedicated nodes flow ─────────────────────────────
        workflow.add_edge("credit_scoring",  "explainability")
        workflow.add_edge("explainability",  "fairness_check")

        workflow.add_conditional_edges(
            "fairness_check",
            route_after_fairness_check,
            {
                "approved": "analysis",
                "rejected": "counterfactual_generation"
            }
        )

        workflow.add_edge("counterfactual_generation", "analysis")

        # ── Final nodes ───────────────────────────────────────────
        workflow.add_edge("analysis",  "response")
        workflow.add_edge("response",  END)

        return workflow.compile()

    # ============ STREAMING INTERFACE ============

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        selected_profile_id: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion using LangGraph agent.

        This method implements the same interface as ClaudeClient and GeminiClient,
        allowing seamless integration with the existing gateway pattern.

        Args:
            model: Model identifier (e.g., "agent/cyber-analyst")
            messages: List of message dicts with "role" and "content"
            temperature: Sampling temperature (currently not used by graph)

        Yields:
            Chunks in OpenAI-compatible format:
            {"choices": [{"delta": {"content": "text"}}]}

        Example:
            async for chunk in agent.stream_chat_completion(
                model="agent/cyber-analyst",
                messages=[{"role": "user", "content": "Analyze IP 1.2.3.4"}],
                temperature=0.7
            ):
                print(chunk)
        """
        logger.info(f"Starting LangGraph agent execution with {len(messages)} messages")

        # Reset tool streaming state for this new request
        self._tool_buffer = {}
        self._emitted_nodes = set()  # Track which nodes already emitted node_start
        self._waterfall_plot = None  # SHAP waterfall plot data URI (base64)
        self._waterfall_emitted = False
        self._response_text_buf = ""  # Accumulates response text for SHAP table detection

        # Debug: log the messages structure
        logger.debug(f"Received messages: {messages}")

        # Convert messages to LangChain format
        lc_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            # Handle content as list (multimodal support) - LANGCHAIN FORMAT
            if isinstance(content, list):
                # Convert to LangChain's multimodal format (NOT raw Anthropic API format)
                lc_content = []
                for part in content:
                    if part.get("type") == "text":
                        lc_content.append({
                            "type": "text",
                            "text": part.get("text", "")
                        })
                    elif part.get("type") == "image_url":
                        # Fetch image and convert to base64 string (not data URI)
                        image_url = part.get("image_url", {}).get("url", "")
                        logger.info(f"[LangGraph] Processing image URL: {image_url}")
                        if image_url:
                            try:
                                logger.info(f"[LangGraph] Fetching image: {image_url}")
                                async with httpx.AsyncClient() as http_client:
                                    response = await http_client.get(image_url)
                                    response.raise_for_status()
                                    image_data = response.content

                                    # Detect media type
                                    media_type = response.headers.get("content-type", "image/png")
                                    if not media_type.startswith("image/"):
                                        media_type = "image/png"

                                    # Convert to base64 string
                                    base64_str = base64.b64encode(image_data).decode("utf-8")

                                    # LangChain ChatAnthropic expects image_url dict with data URI
                                    lc_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{media_type};base64,{base64_str}"}
                                    })
                                    logger.info(f"[LangGraph] Successfully converted image to base64, size: {len(image_data)} bytes")
                            except Exception as e:
                                logger.error(f"[LangGraph] Failed to fetch image from {image_url}: {e}")
                                pass
                content = lc_content if lc_content else ""

            # Skip empty messages
            if not content or not role:
                logger.warning(f"Skipping empty message: role={role}, content={content}")
                continue

            # Convert to LangChain message types
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        logger.info(f"Converted to {len(lc_messages)} LangChain messages")

        # Ensure we have at least one message
        if not lc_messages:
            error_msg = "No valid messages received. Please provide a query."
            logger.error(f"{error_msg} Original messages: {messages}")
            yield {
                "choices": [{
                    "delta": {
                        "content": f"**Error**: {error_msg}"
                    }
                }]
            }
            return

        # Scan messages for PDF uploads to populate documents_processed
        documents_processed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    text = part.get("text", "")
                    pdf_matches = re.findall(r'\[PDF uploaded:\s*(.+?),\s*URL:\s*(.+?)\]', text)
                    for name, url in pdf_matches:
                        # Extract filename from URL
                        filename = url.strip().split("/")[-1]
                        documents_processed.append({
                            "type": "pdf",
                            "name": name.strip(),
                            "url": url.strip(),
                            "file_path": filename,
                        })
            elif isinstance(content, str):
                pdf_matches = re.findall(r'\[PDF uploaded:\s*(.+?),\s*URL:\s*(.+?)\]', content)
                for name, url in pdf_matches:
                    filename = url.strip().split("/")[-1]
                    documents_processed.append({
                        "type": "pdf",
                        "name": name.strip(),
                        "url": url.strip(),
                        "file_path": filename,
                    })

        if documents_processed:
            logger.info(f"Found {len(documents_processed)} PDF document(s) in messages")

        # Initialize investigation state
        initial_state: LoanAssessmentState = {
            "messages": lc_messages,
            "tools_used": [],
            "tool_results": [],
            "final_response": "",
            "extracted_fields": {},  # Populated by data_completeness_node
            "documents_processed": documents_processed,
            "selected_profile_id": selected_profile_id,
        }

        try:
            # Stream events from the graph execution
            event_count = 0
            async for event in self.app.astream_events(
                initial_state,
                version="v2"
            ):
                event_count += 1
                event_type = event.get("event")
                logger.debug(f"📡 LangGraph event #{event_count}: {event_type}")

                try:
                    # Transform LangGraph events to structured SSE format
                    async for chunk in self._transform_event_to_sse(event):
                        yield chunk
                except Exception as transform_error:
                    logger.error(f" Error transforming event #{event_count} ({event_type}): {type(transform_error).__name__}: {str(transform_error)}", exc_info=True)
                    # Continue processing other events
                    continue

            logger.info(f"✅ LangGraph execution complete. Processed {event_count} events.")

        except Exception as e:
            logger.error(f" FATAL: LangGraph agent error: {type(e).__name__}: {str(e)}", exc_info=True)
            # Yield error as structured event
            yield {
                "type": "error",
                "error": str(e),
                "traceback": f"{type(e).__name__}"
            }

    async def _transform_event_to_sse(
        self,
        event: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Transform LangGraph stream events into structured SSE chunks.

        Event Types:
        - on_chat_model_stream: LLM generating text (→ "text" or "reasoning" based on node)
        - on_tool_start: Tool execution beginning (→ "tool_call")
        - on_tool_end: Tool execution complete (→ "tool_result")
        - on_chain_start: Node execution beginning (→ "node_start")
        - on_chain_end: Node execution complete (→ "skip" for bypassed nodes)

        SSE Format (all events include "type" field):
        {
            "type": "text" | "reasoning" | "tool_call" | "tool_result" | "node_start" | "skip",
            "choices": [{"delta": {"content": "..."}}],  # backward compatibility
            # type-specific fields...
        }

        Args:
            event: LangGraph stream event

        Yields:
            Structured SSE chunk dicts
        """
        event_type = event.get("event")
        data = event.get("data", {})
        name = event.get("name", "")
        run_id = event.get("run_id", "")
        metadata = event.get("metadata", {})

        # Node headers mapping
        NODE_HEADERS = {
            "classify": "Classifying query",
            "fetch_merchant_data": "Fetching merchant profile",
            "document_ingestion": "Processing documents",
            "data_completeness": "Checking data completeness",
            "planning": "Planning analysis",
            "credit_scoring": "Computing credit score",
            "explainability": "Running SHAP explainability",
            "fairness_check": "Running fairness validation",
            "counterfactual_generation": "Generating improvement paths",
            "analysis": "Synthesizing findings",
            "response": "Generating report",
        }

        # User-facing nodes (emit "text" instead of "reasoning")
        USER_FACING_NODES = {
            "analysis", "response", "simple_response",
            "need_more_data", "single_tool_execution"
        }

        # Stream LLM text generation
        if event_type == "on_chat_model_stream":
            chunk = data.get("chunk")
            if chunk and hasattr(chunk, 'content') and chunk.content:
                content = chunk.content

                # Filter out tool_use blocks (internal LLM tool calling metadata)
                if isinstance(content, (list, dict)):
                    return
                if isinstance(content, str) and (
                    "'type': 'tool_use'" in content or
                    '"type": "tool_use"' in content or
                    content.strip().startswith("[{")
                ):
                    return

                # Determine if this is user-facing text or internal reasoning
                node_name = metadata.get("langgraph_node", "")

                if node_name in USER_FACING_NODES:
                    # Inject SHAP waterfall plot before the SHAP table.
                    # Buffer tokens until we see "| # |" (table header),
                    # then flush: text before table → image → table line onward.
                    # Safety: if buffer exceeds 4KB without match, flush it
                    # (the heading simply wasn't there this time).
                    if not self._waterfall_emitted and self._waterfall_plot:
                        self._response_text_buf += content
                        table_marker = "| # |"
                        if table_marker in self._response_text_buf:
                            self._waterfall_emitted = True
                            idx = self._response_text_buf.index(table_marker)
                            # Walk back to the start of the line containing "| # |"
                            line_start = self._response_text_buf.rfind("\n", 0, idx)
                            split_at = line_start + 1 if line_start >= 0 else 0
                            before = self._response_text_buf[:split_at]
                            after = self._response_text_buf[split_at:]
                            if before:
                                yield {"type": "text", "content": before}
                            img_md = f"![SHAP Waterfall Plot]({self._waterfall_plot})\n\n"
                            yield {"type": "text", "content": img_md}
                            if after:
                                yield {"type": "text", "content": after}
                            self._response_text_buf = ""
                            content = None
                        elif len(self._response_text_buf) > 4096:
                            # Safety flush — marker not found, emit buffer as-is
                            self._waterfall_emitted = True
                            yield {"type": "text", "content": self._response_text_buf}
                            self._response_text_buf = ""
                            content = None
                        else:
                            # Keep buffering
                            content = None

                    if content is not None:
                        logger.debug(f"📤 Emitting TEXT from node: {node_name}")
                        yield {
                            "type": "text",
                            "content": content
                        }
                else:
                    logger.debug(f"📤 Emitting REASONING from node: {node_name}")
                    yield {
                        "type": "reasoning",
                        "node": node_name,
                        "content": content
                    }

        # Tool execution start
        elif event_type == "on_tool_start":
            tool_input = self._sanitize_for_json(data.get("input", {}))
            tool_name = name

            # Store tool info in buffer (keyed by run_id)
            self._tool_buffer[run_id] = {
                "name": tool_name,
                "input": tool_input,
                "streamed": False
            }

            # Emit tool_call event
            logger.debug(f"📤 Emitting TOOL_CALL: {tool_name}")
            yield {
                "type": "tool_call",
                "tool": tool_name,
                "input": tool_input
            }

        # Tool execution end
        elif event_type == "on_tool_end":
            tool_info = self._tool_buffer.get(run_id)
            if not tool_info or tool_info.get("streamed"):
                return

            tool_name = tool_info["name"]
            tool_input = tool_info["input"]
            output = data.get("output", {})

            # Capture SHAP waterfall plot data URI before formatting
            if tool_name == "shap_explainer":
                raw = output
                if hasattr(raw, 'content'):
                    try:
                        import json as _json
                        raw = _json.loads(raw.content)
                    except (ValueError, TypeError):
                        raw = {}
                if isinstance(raw, dict):
                    wp = raw.get("waterfall_plot", "")
                    if wp and isinstance(wp, str) and wp.startswith("data:image"):
                        self._waterfall_plot = wp
                        logger.debug("📊 Captured SHAP waterfall plot (base64)")

            # Strip large base64 data from tool output before sending to frontend
            output_for_sse = output
            if isinstance(output, dict) and "waterfall_plot" in output:
                output_for_sse = {k: v for k, v in output.items() if k != "waterfall_plot"}
            elif hasattr(output, 'content') and isinstance(output.content, str):
                try:
                    import json as _json
                    parsed = _json.loads(output.content)
                    if isinstance(parsed, dict) and "waterfall_plot" in parsed:
                        parsed.pop("waterfall_plot")
                        output_for_sse = type(output)(content=_json.dumps(parsed))
                except (ValueError, TypeError):
                    pass

            formatted_output = self._format_tool_output(output_for_sse)

            # Emit tool_result event
            logger.debug(f"📤 Emitting TOOL_RESULT: {tool_name}")
            yield {
                "type": "tool_result",
                "tool": tool_name,
                "input": tool_input,
                "output": formatted_output
            }

            # Mark as streamed
            tool_info["streamed"] = True

        # Node execution start
        elif event_type == "on_chain_start":
            node_name = metadata.get("langgraph_node", "")

            # Emit node_start for nodes with headers (deduplicate — only first event per node)
            if node_name in NODE_HEADERS and node_name not in self._emitted_nodes:
                self._emitted_nodes.add(node_name)
                logger.debug(f"📤 Emitting NODE_START: {node_name} - {NODE_HEADERS[node_name]}")
                yield {
                    "type": "node_start",
                    "node": node_name,
                    "message": NODE_HEADERS[node_name]
                }

        # Node execution end (check for skipped nodes)
        elif event_type == "on_chain_end":
            node_name = metadata.get("langgraph_node", "")
            output = data.get("output", {})

            # Check if counterfactual_generation should be skipped
            if node_name == "fairness_check":
                # Ensure output is a dict before calling .get()
                if isinstance(output, dict):
                    credit_score = output.get("credit_score", 0)
                    if credit_score >= 670:
                        logger.debug(f"📤 Emitting SKIP: counterfactual_generation (score {credit_score} >= 670)")
                        yield {
                            "type": "skip",
                            "node": "counterfactual_generation",
                            "message": f"[counterfactual skipped — score {credit_score} above threshold 670]"
                        }
