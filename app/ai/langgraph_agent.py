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
from typing import AsyncGenerator, List, Dict, Any, Literal, TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from app.config import settings

logger = logging.getLogger(__name__)


# ============ STATE DEFINITION ============

class LoanAssessmentState(TypedDict):
    """
    State for the SME loan assessment agent.

    This state is passed through all nodes in the graph and maintains
    context throughout the loan assessment workflow.
    """
    # Core conversation
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Assessment workflow
    analysis_steps: list[str]  # Sequence of analysis actions taken
    documents_processed: list[dict]  # Uploaded financial documents

    # Financial metrics
    financial_ratios: dict  # debt-to-equity, current ratio, ROE, etc.
    revenue_trends: dict  # Time series analysis results
    cash_flow_analysis: dict  # Cash flow ratios and patterns

    # Credit assessment
    credit_score: float  # 300-850 scale
    default_probability: float  # 0-1
    risk_level: str  # "low", "medium", "high", "critical"
    risk_factors: list[str]  # Identified risk factors

    # Business context
    industry_benchmarks: dict  # Comparison to industry standards
    alternative_data: dict  # Mobile money, POS revenue, utility payments

    # Tool execution tracking
    tools_used: list[str]  # Names of tools invoked
    tool_results: list[dict]  # Results from tool executions
    data_completeness_score: float  # 0-1 (SHAP-based importance)

    # Decision and explainability
    loan_recommendation: dict  # approve/reject, loan amount, interest rate, terms
    shap_explanations: dict  # Feature importance for credit score
    counterfactuals: list[dict]  # Improvement paths for rejected applicants
    fairness_check_results: dict  # Causal fairness validation

    # Response generation
    final_response: str  # Generated credit report


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

    def __init__(self):
        """Initialize the agent with LLM and build the investigation graph."""
        # Get model name from settings and map to Anthropic API format
        model_name = getattr(settings, 'agent_model', 'claude-haiku-4.5')

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

        # Build the investigation graph
        self.app = self._build_graph()

        logger.info(f"LangGraph agent initialized with model: {anthropic_model}")

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
        Build the SME loan assessment graph.

        Graph structure:

            START
              ↓
          Classify (determine if loan assessment query)
              ↓
          Planning (assess application, determine approach)
              ↓
          Tool Selection (LLM decides which tools to use)
              ↓
          ┌─────────────┐
          │ Use Tools?  │
          └─────────────┘
             ↓       ↓
            Yes      No
             ↓       ↓
          Execute   Skip
          Tools      ↓
             ↓       ↓
          ┌─────────────┐
          │ Continue?   │
          └─────────────┘
             ↓       ↓
            Yes      No
             ↓       ↓
          (loop)  Analysis (synthesize financial findings)
                     ↓
                  Response (generate credit report)
                     ↓
                    END

        Returns:
            Compiled StateGraph ready for execution
        """
        workflow = StateGraph(LoanAssessmentState)

        # Add all nodes to the graph
        workflow.add_node("classify", self._classify_node)  # NEW: Determine if security query
        workflow.add_node("simple_response", self._simple_response_node)  # NEW: For non-security queries
        workflow.add_node("planning", self._planning_node)
        workflow.add_node("tool_selection", self._tool_selection_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        workflow.add_node("analysis", self._analysis_node)
        workflow.add_node("response", self._response_node)

        # Define entry point
        workflow.set_entry_point("classify")

        # Classify → Security investigation OR Simple response
        workflow.add_conditional_edges(
            "classify",
            self._is_security_query,
            {
                "security": "planning",
                "general": "simple_response"
            }
        )

        # Simple response → END
        workflow.add_edge("simple_response", END)

        # Define edges between security investigation nodes
        workflow.add_edge("planning", "tool_selection")

        # Conditional: use tools or skip to analysis?
        workflow.add_conditional_edges(
            "tool_selection",
            self._should_use_tools,
            {
                "execute": "execute_tools",
                "skip": "analysis"
            }
        )

        # Conditional: continue investigation or move to analysis?
        workflow.add_conditional_edges(
            "execute_tools",
            self._continue_investigation,
            {
                "continue": "tool_selection",  # Loop for multi-step investigation
                "analyze": "analysis"
            }
        )

        # Final edges
        workflow.add_edge("analysis", "response")
        workflow.add_edge("response", END)

        return workflow.compile()

    # ============ NODE IMPLEMENTATIONS ============

    async def _classify_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 0: Classification

        Uses LLM to intelligently determine if the query requires loan assessment
        or is a general/educational question.

        Args:
            state: Current assessment state

        Returns:
            Updated state with classification
        """
        messages = state["messages"]
        last_message = messages[-1].content if messages else ""

        classification_prompt = """You are a query classifier. Classify the user's query as either "investigation" or "general".

**investigation** = User wants to assess a loan, analyze financial data, calculate credit scores, or evaluate specific loan applications
**general** = User asks educational questions (what/why/how), seeks explanations, or general financial advice

Examples of "investigation":
- "Assess this loan application: $300M VND, 120M monthly revenue..."
- "Calculate credit score for this business"
- "Why was this loan rejected? How to improve?"
- "Analyze financial statements for creditworthiness"

Examples of "general":
- "What is a good debt-to-equity ratio?"
- "How do credit scores work?"
- "What factors affect loan approval?"

Respond with EXACTLY one word: "investigation" or "general"."""

        # Use with_structured_output to force single-word response
        from pydantic import BaseModel, Field

        class Classification(BaseModel):
            type: str = Field(description="Either 'investigation' or 'general'")

        structured_llm = self.llm.with_structured_output(Classification)

        result = await structured_llm.ainvoke([
            SystemMessage(content=classification_prompt),
            HumanMessage(content=last_message)
        ])

        classification = result.type.strip().lower()

        # Validate response
        if "investigation" in classification:
            logger.info("🔍 LLM classified as: LOAN ASSESSMENT")
            return {**state, "analysis_steps": ["Classified as loan assessment query"]}
        else:
            logger.info("💬 LLM classified as: GENERAL QUESTION")
            return {**state, "analysis_steps": ["Classified as general query"]}

    async def _simple_response_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node: Simple Response

        Handles non-security queries with a straightforward response.

        Args:
            state: Current investigation state

        Returns:
            Updated state with simple response
        """
        messages = state["messages"]

        # Build tool information for the prompt
        tool_info = ""
        if self.tools:
            tool_list = "\n".join([f"- **{tool.name}**: {tool.description}" for tool in self.tools])
            tool_info = f"""

**Available Investigation Tools:**
{tool_list}

**How to use them:**
Simply provide indicators in your query (e.g., "Analyze IP 45.142.213.100" or "Check domain evil.com") and I'll automatically use the appropriate tools to investigate."""

        # Use LLM to respond naturally to general questions
        simple_prompt = f"""You are Credence AI, an SME loan assessment assistant.

The user has asked a general question (not related to loan assessment).
Respond naturally and helpfully.{tool_info}

If they want loan assessment help, mention that you can analyze loan applications, calculate credit scores, assess financial statements, and provide lending recommendations."""

        response = await self.llm.ainvoke([
            SystemMessage(content=simple_prompt),
            *messages
        ])

        logger.info("Generated simple response for non-security query")

        return {
            **state,
            "messages": state["messages"] + [response],
            "final_response": response.content,
        }

    async def _planning_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 1: Planning

        Assesses the user's query and determines the investigation approach.
        Performs initial risk classification and outlines investigation steps.

        Args:
            state: Current investigation state

        Returns:
            Updated state with investigation plan and severity assessment
        """
        messages = state["messages"]
        last_message = messages[-1].content if messages else ""

        planning_prompt = """You are a senior loan officer analyzing SME loan applications. Analyze this query and determine:

1. What type of analysis is needed? (financial statement analysis, credit scoring, data verification, risk assessment, etc.)
2. What financial information do we have vs. what we need to gather?
3. Initial risk assessment based on the application (low/medium/high/critical)
4. Recommended assessment approach (2-3 sentences)

Provide a brief, actionable loan assessment plan."""

        response = await self.llm.ainvoke([
            SystemMessage(content=planning_prompt),
            HumanMessage(content=last_message)
        ])

        # Extract risk level from response (heuristic-based classification)
        risk_level = "medium"  # default
        content_lower = response.content.lower()

        if any(keyword in content_lower for keyword in ["critical", "urgent", "high default risk", "fraudulent", "insolvent"]):
            risk_level = "critical"
        elif any(keyword in content_lower for keyword in ["high risk", "poor financials", "negative cash flow", "high leverage"]):
            risk_level = "high"
        elif any(keyword in content_lower for keyword in ["moderate risk", "fair", "needs review", "incomplete data"]):
            risk_level = "medium"
        elif any(keyword in content_lower for keyword in ["low risk", "strong financials", "good credit history"]):
            risk_level = "low"

        logger.info(f"Planning complete. Risk level: {risk_level}")

        return {
            **state,
            "analysis_steps": [f"Planning: {response.content}"],
            "risk_level": risk_level,
            "messages": state["messages"] + [response],
        }

    async def _tool_selection_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 2: Tool Selection

        LLM analyzes the investigation plan and selects appropriate tools.
        If no tools are available, proceeds to analysis with reasoning only.

        Args:
            state: Current investigation state

        Returns:
            Updated state with tool calls (if tools were selected)
        """
        messages = state["messages"]

        # If no tools available, skip this node
        if not self.tools:
            logger.warning("⚠️ No tools available - proceeding to analysis")
            return state

        logger.info(f"🔧 Tool selection node: {len(self.tools)} tools available")
        logger.info(f"   Available tools: {[t.name for t in self.tools]}")
        logger.info(f"   Tool descriptions: {[(t.name, t.description[:80]) for t in self.tools]}")

        # Check if query contains specific financial data that requires tool usage
        last_message = messages[-1].content if messages else ""
        last_message_lower = last_message.lower()

        # Patterns that indicate we should force tool usage for loan assessment
        loan_keywords = [
            "loan", "credit", "assess", "approval", "rejection", "default",
            "financial statement", "balance sheet", "revenue", "profit", "cash flow",
            "debt", "asset", "liability", "ratio", "score", "probability",
            "counterfactual", "improve", "shap", "explain"
        ]

        # Check if ANY loan/financial keyword is present
        has_loan_data = any(keyword in last_message_lower for keyword in loan_keywords)

        # Also check for numeric financial data patterns (amounts, percentages, ratios)
        import re
        has_amounts = bool(re.search(r'\$[\d,]+|\d+k|\d+m|\d+%', last_message_lower))

        requires_tool = has_loan_data or has_amounts

        if requires_tool:
            logger.info(f"   🎯 Detected loan assessment query requiring tool usage (keywords: {has_loan_data}, amounts: {has_amounts})")
            # Force tool usage by setting tool_choice to require it
            llm_with_tools = self.llm.bind_tools(self.tools, tool_choice="any")
        else:
            logger.info("   📝 No specific loan data detected - tools optional")
            # Let LLM decide
            llm_with_tools = self.llm.bind_tools(self.tools)

        logger.info(f"   LLM bound with tools: {llm_with_tools}")

        tool_selection_prompt = """You are selecting tools for SME loan assessment.

**Available Tools:**
- `credit_score_model`: Calculates credit scores (300-850) and default probability
- `financial_statement_analyzer`: Analyzes balance sheets, P&L, cash flow statements
- `data_completeness_checker`: Identifies missing critical fields ranked by importance
- `lending_knowledge_retriever`: Retrieves lending regulations and best practices
- `shap_explainer`: Explains credit decisions with feature importance
- `counterfactual_generator`: Shows how to improve credit score

**Your Task:**
1. Review the assessment plan in the conversation history
2. Select appropriate tools based on the loan application data provided
3. Call tools in logical order (data completeness → credit scoring → explainability)

**CRITICAL RULES:**
- ALWAYS use tools when loan data is provided
- DO NOT just describe what you would do - actually call the tool
- DO NOT make up tool results - wait for actual tool execution

**Examples:**
- Query: "Assess $10K loan, $50K revenue" → Call credit_score_model(loan_amount=10000, monthly_revenue=50000, ...)
- Query: "Loan rejection - how to improve?" → Call counterfactual_generator with applicant's financial data
- Query: "Why was credit score 650?" → Call shap_explainer to show feature importance
- Query: "What is a good debt-to-equity ratio?" → No tools needed (general question)

Make your tool selection now."""

        response = await llm_with_tools.ainvoke([
            SystemMessage(content=tool_selection_prompt),
            *messages
        ])

        # Check if tools were called
        tool_calls = getattr(response, 'tool_calls', [])
        if tool_calls:
            logger.info(f"✅ Tools selected: {[tc['name'] for tc in tool_calls]}")
        else:
            logger.warning("⚠️ No tools selected by LLM - continuing with reasoning only")
            logger.debug(f"   LLM response: {response.content[:200]}")

        return {
            **state,
            "messages": state["messages"] + [response],
        }

    async def _execute_tools_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 3: Tool Execution

        Executes tools selected by the LLM and captures results.

        Args:
            state: Current investigation state

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
            result = await self.tool_node.ainvoke(state)
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

            investigation_steps = state.get("investigation_steps", [])
            investigation_steps.append(f"Executed tools: {', '.join([tc['name'] for tc in last_message.tool_calls])}")

            return {
                **result,
                "tools_used": tools_used,
                "tool_results": tool_results,
                "investigation_steps": investigation_steps,
            }

        # No tools to execute
        return state

    async def _analysis_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 4: Analysis

        Synthesizes financial data, identifies risk factors, and provides credit assessment.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with credit analysis and risk assessment
        """
        messages = state["messages"]
        credit_score = state.get("credit_score", 0)
        risk_level = state.get("risk_level", "medium")
        tools_used = state.get("tools_used", [])

        # Skip analysis if no tools were used (nothing to analyze)
        if not tools_used:
            logger.info("⏭️ Skipping analysis node - no tools were used")
            return state

        analysis_prompt = f"""Analyze the loan assessment results and provide a comprehensive credit evaluation.

**IMPORTANT:** Start your response with the heading "# 📊 Credit Analysis\n\n" followed by your assessment.

**Assessment Context:**
- Risk Level: {risk_level}
- Credit Score: {credit_score}
- Tools Used: {', '.join(tools_used) if tools_used else 'None (reasoning-only)'}

**CRITICAL INSTRUCTION:**
Review the tool results in the conversation history above. The tool outputs contain financial data including:
- Credit scores and score bands
- Financial ratios (debt-to-equity, current ratio, profit margin)
- Default probability estimates
- Data completeness scores
- Recommendations

**Your Analysis MUST:**
1. **Reference specific data from tool results** (credit scores, financial ratios, default probability)
2. **Assess creditworthiness** based on the financial metrics provided
3. **Identify key risk factors** from the tool outputs
4. **Provide loan recommendation** (approve/decline, loan amount, interest rate, terms)

Do NOT speculate or make up information. Use ONLY the data provided by the tools above."""

        response = await self.llm.ainvoke([
            SystemMessage(content=analysis_prompt),
            *messages
        ])

        # Extract MITRE ATT&CK tactics using keyword matching
        mitre_tactics = []
        tactics_keywords = {
            "reconnaissance": "Reconnaissance (TA0043)",
            "initial access": "Initial Access (TA0001)",
            "execution": "Execution (TA0002)",
            "persistence": "Persistence (TA0003)",
            "privilege escalation": "Privilege Escalation (TA0004)",
            "defense evasion": "Defense Evasion (TA0005)",
            "credential access": "Credential Access (TA0006)",
            "discovery": "Discovery (TA0007)",
            "lateral movement": "Lateral Movement (TA0008)",
            "collection": "Collection (TA0009)",
            "exfiltration": "Exfiltration (TA0010)",
            "command and control": "Command and Control (TA0011)",
            "impact": "Impact (TA0040)",
        }

        content_lower = response.content.lower()
        for keyword, tactic in tactics_keywords.items():
            if keyword in content_lower:
                mitre_tactics.append(tactic)

        if mitre_tactics:
            logger.info(f"MITRE tactics identified: {mitre_tactics}")

        investigation_steps = state.get("investigation_steps", [])
        investigation_steps.append(f"Analysis: Identified {len(mitre_tactics)} MITRE tactics")

        return {
            **state,
            "messages": state["messages"] + [response],
            "mitre_tactics": mitre_tactics,
            "investigation_steps": investigation_steps,
        }

    async def _response_node(self, state: LoanAssessmentState) -> Dict[str, Any]:
        """
        Node 5: Response Generation

        Generates a final formatted investigation report for the user.
        Structures findings in a clear, professional format suitable for SOC analysts.

        Args:
            state: Current investigation state

        Returns:
            Updated state with final formatted response
        """
        messages = state["messages"]
        severity = state.get("severity_level", "medium")
        mitre = state.get("mitre_tactics", [])
        iocs = state.get("iocs_found", [])
        tools_used = state.get("tools_used", [])

        # Use different prompt based on whether tools were used
        if tools_used:
            # Formal credit report when tools were used
            response_prompt = f"""Generate a final loan assessment report based on the analysis.

**Assessment Summary:**
- Risk Level: {severity.upper()}
- Credit Score: {state.get('credit_score', 'Not calculated')}
- Default Probability: {state.get('default_probability', 'Not calculated')}
- Tools Used: {', '.join(tools_used)}

**Format Requirements:**
- Clear, professional tone suitable for a loan officer
- Structured sections (Executive Summary, Financial Analysis, Credit Decision, Recommendations)
- Actionable loan recommendation (approve/decline, amount, rate, terms)
- Reference specific financial metrics and risk factors

Start your response with "# 📋 Loan Assessment Report\n\n" followed by the report."""
        else:
            # More conversational response when no tools were used
            response_prompt = """Based on the loan assessment planning above, provide helpful guidance to the user.

**Your Response Should:**
- Be conversational and natural (not a formal report)
- Acknowledge what information is needed to investigate further
- Provide actionable next steps for the user
- Explain what you would do if specific indicators were provided
- Be concise and helpful

Do NOT use rigid templates or empty sections. Just have a natural conversation about their query."""

        final_response = await self.llm.ainvoke([
            SystemMessage(content=response_prompt),
            *messages
        ])

        logger.info("Investigation complete - final report generated")

        return {
            **state,
            "messages": state["messages"] + [final_response],
            "final_response": final_response.content,
        }

    # ============ CONDITIONAL EDGE FUNCTIONS ============

    def _is_security_query(self, state: LoanAssessmentState) -> Literal["security", "general"]:
        """
        Determine if the query is loan assessment-related or general.

        Args:
            state: Current assessment state

        Returns:
            "security" if it's a loan assessment query, "general" otherwise
        """
        analysis_steps = state.get("analysis_steps", [])

        # Check the classification from the classify node
        if analysis_steps and ("loan" in analysis_steps[0].lower() or "credit" in analysis_steps[0].lower()):
            return "security"  # Keep same routing logic
        return "general"

    def _should_use_tools(self, state: LoanAssessmentState) -> Literal["execute", "skip"]:
        """
        Decide whether tools should be executed or skipped.

        Args:
            state: Current investigation state

        Returns:
            "execute" if tools were called, "skip" otherwise
        """
        last_message = state["messages"][-1]

        logger.info("🔍 Checking if tools should be used:")
        logger.info(f"   Last message type: {type(last_message)}")
        logger.info(f"   Has tool_calls attribute: {hasattr(last_message, 'tool_calls')}")

        # Check if LLM requested tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"   ✅ Tool calls found: {[tc.get('name') if isinstance(tc, dict) else tc['name'] for tc in last_message.tool_calls]}")
            return "execute"

        logger.warning("   ❌ No tool calls found - skipping to analysis")
        logger.debug(f"   Message content preview: {last_message.content[:200] if hasattr(last_message, 'content') else 'N/A'}")
        return "skip"

    def _continue_investigation(self, state: LoanAssessmentState) -> Literal["continue", "analyze"]:
        """
        Decide if more investigation steps are needed or if we should analyze.

        Checks:
        1. Have we exceeded max tool steps?
        2. Did the last message request more tool calls?

        Args:
            state: Current investigation state

        Returns:
            "continue" to loop back for more tools, "analyze" to proceed to analysis
        """
        # Check max tool iterations (prevent infinite loops)
        max_steps = getattr(settings, 'max_tool_steps', 5)
        tools_used = state.get("tools_used", [])

        if len(tools_used) >= max_steps:
            logger.info(f"Max tool steps ({max_steps}) reached - moving to analysis")
            return "analyze"

        # Check if LLM wants to call more tools
        last_message = state["messages"][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info("Additional tools requested - continuing investigation")
            return "continue"

        return "analyze"

    # ============ STREAMING INTERFACE ============

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
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

        # Reset tool header flag for this new request
        self._tool_header_shown = False

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

            # Convert to LangChain message types (skip system messages for graph)
            if role == "user":
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
                        "content": f"⚠️ **Error**: {error_msg}"
                    }
                }]
            }
            return

        # Initialize investigation state
        initial_state: LoanAssessmentState = {
            "messages": lc_messages,
            "investigation_steps": [],
            "iocs_found": [],
            "severity_level": "medium",
            "mitre_tactics": [],
            "tools_used": [],
            "tool_results": [],
            "pending_approval": None,
            "final_response": "",
        }

        try:
            # Stream events from the graph execution
            async for event in self.app.astream_events(
                initial_state,
                version="v2"
            ):
                # Transform LangGraph events to OpenAI-compatible SSE format
                async for chunk in self._transform_event_to_sse(event):
                    yield chunk

        except Exception as e:
            logger.error(f"LangGraph agent error: {type(e).__name__}: {str(e)}", exc_info=True)
            # Yield error as SSE event
            yield {
                "choices": [{
                    "delta": {
                        "content": f"\n\n⚠️ **Error during investigation**: {str(e)}"
                    }
                }]
            }

    async def _transform_event_to_sse(
        self,
        event: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Transform LangGraph stream events into OpenAI-compatible SSE chunks.

        This adapter ensures compatibility with the existing frontend that expects
        OpenAI's streaming format.

        LangGraph Event Types:
        - on_chat_model_stream: LLM generating text
        - on_tool_start: Tool execution beginning
        - on_tool_end: Tool execution complete
        - on_chain_start: Node execution beginning
        - on_chain_end: Node execution complete

        OpenAI SSE Format:
        {
            "choices": [{
                "delta": {"content": "text content"}
            }]
        }

        Args:
            event: LangGraph stream event

        Yields:
            OpenAI-compatible chunk dicts
        """
        event_type = event.get("event")
        data = event.get("data", {})
        name = event.get("name", "")

        # Stream LLM text generation
        if event_type == "on_chat_model_stream":
            chunk = data.get("chunk")
            if chunk and hasattr(chunk, 'content') and chunk.content:
                # Skip raw tool_use blocks (these are internal LLM tool calling metadata)
                content = chunk.content

                # Filter out tool_use blocks which appear as lists or dicts
                if isinstance(content, (list, dict)):
                    # Don't stream raw tool metadata to users
                    return

                # Filter out JSON-like tool_use strings
                if isinstance(content, str) and (
                    "'type': 'tool_use'" in content or
                    '"type": "tool_use"' in content or
                    content.strip().startswith("[{")
                ):
                    return

                yield {
                    "choices": [{
                        "delta": {
                            "content": content
                        }
                    }]
                }

        # Stream tool execution updates
        elif event_type == "on_tool_start":
            # Add "Tool Execution" header before first tool (only once)
            if not hasattr(self, '_tool_header_shown'):
                self._tool_header_shown = True
                yield {
                    "choices": [{
                        "delta": {
                            "content": "\n\n## 🔧 Tool Execution\n\n"
                        }
                    }]
                }

            tool_input = data.get("input", {})
            tool_name = name  # Use the name from event directly

            # Format tool input arguments
            import json
            formatted_input = json.dumps(tool_input, indent=2) if tool_input else "{}"

            yield {
                "choices": [{
                    "delta": {
                        "content": f"**Tool called:** `{tool_name}`\n\n**Input:**\n```json\n{formatted_input}\n```\n\n**Output:** "
                    }
                }]
            }

        elif event_type == "on_tool_end":
            # Get the tool result to show output
            output = data.get("output", {})

            # Format the output
            import json
            if isinstance(output, dict):
                # Pretty print the output
                formatted_output = json.dumps(output, indent=2)
            elif isinstance(output, str):
                formatted_output = output
            else:
                formatted_output = str(output)

            yield {
                "choices": [{
                    "delta": {
                        "content": f"\n```json\n{formatted_output}\n```\n\n---\n\n"
                    }
                }]
            }

        # Stream node transitions (loan assessment progress indicators)
        elif event_type == "on_chain_start":
            # Only add header for planning phase - other nodes will add headers only when they have content
            if "planning" in name.lower():
                yield {
                    "choices": [{
                        "delta": {
                            "content": "## 📋 Loan Assessment Planning\n\n"
                        }
                    }]
                }
            # Don't add headers for tool_selection, analysis, or response nodes
            # They will handle their own headers when they have content to show
