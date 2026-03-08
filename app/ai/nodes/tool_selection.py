import logging
import re
from typing import Dict, Any
from functools import partial
from langchain_core.messages import SystemMessage, HumanMessage
from app.ai.state import LoanAssessmentState, QueryIntent
logger = logging.getLogger(__name__)


async def tool_selection_node(state: LoanAssessmentState, llm, tools, testing_system_prompt) -> Dict[str, Any]:
        """
        Node 2: Tool Selection

        LLM analyzes the loan assessment plan and selects appropriate tools.
        If no tools are available, proceeds to analysis with reasoning only.

        Args:
            state: Current loan assessment state
            llm: ChatAnthropic LLM instance
            tools: List of available tools
            testing_system_prompt: System prompt for testing mode

        Returns:
            Updated state with tool calls (if tools were selected)
        """
        messages = state["messages"]

        # If no tools available, skip this node
        if not tools:
            logger.warning("⚠️ No tools available - proceeding to analysis")
            return state

        logger.info(f"🔧 Tool selection node: {len(tools)} tools available")
        logger.info(f"   Available tools: {[t.name for t in tools]}")
        logger.info(f"   Tool descriptions: {[(t.name, t.description[:80]) for t in tools]}")

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
        has_amounts = bool(re.search(r'\$[\d,]+|\d+k|\d+m|\d+%', last_message_lower))

        requires_tool = has_loan_data or has_amounts

        if requires_tool:
            logger.info(f"   🎯 Detected loan assessment query requiring tool usage (keywords: {has_loan_data}, amounts: {has_amounts})")
            # Force tool usage by setting tool_choice to require it
            llm_with_tools = llm.bind_tools(tools, tool_choice="any")
        else:
            logger.info("   📝 No specific loan data detected - tools optional")
            # Let LLM decide
            llm_with_tools = llm.bind_tools(tools)

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
            SystemMessage(content=testing_system_prompt),
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
