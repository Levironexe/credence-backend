import logging
from enum import Enum
from typing import Literal, TypedDict, Annotated, Sequence, Optional
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)
# ============ QUERY INTENT TYPE ============

class QueryIntentType(str, Enum):
    """
    Enum for query intent classification types.

    Provides type-safe routing for dynamic workflow selection.
    """
    SIMPLE_EXPLANATION = "simple_explanation"
    SINGLE_TOOL = "single_tool"
    FULL_ASSESSMENT = "full_assessment"
    NEED_MORE_DATA = "need_more_data"


# ============ QUERY INTENT MODEL ============

class QueryIntent(BaseModel):
    """
    Structured classification of user query intent for dynamic workflow routing.

    Intent Types:
    - simple_explanation: General questions requiring only knowledge/explanation
    - single_tool: Queries needing exactly one tool execution
    - full_assessment: Complex loan assessments requiring multiple tools
    - need_more_data: Assessment requests lacking required financial data
    """
    intent: Literal["simple_explanation", "single_tool", "full_assessment", "need_more_data"] = Field(
        description="The type of query intent"
    )
    tool_needed: Optional[str] = Field(
        default=None,
        description="For single_tool intent: name of the specific tool required"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score for the classification (0.0-1.0)"
    )
    reasoning: str = Field(
        description="Brief explanation of why this intent was chosen"
    )


# ============ STATE DEFINITION ============

class LoanAssessmentState(TypedDict):
    """
    State for the SME loan assessment agent.

    This state is passed through all nodes in the graph and maintains
    context throughout the loan assessment workflow.
    """
    # Core conversation
    messages: Annotated[Sequence[BaseMessage], add_messages]  # Message history with add_messages reducer

    # Query routing (dynamic workflow selection)
    intent_type: str  # Query intent: "simple_explanation" | "single_tool" | "full_assessment" | "need_more_data"
    single_tool_name: str  # For single_tool intent: specific tool name to execute
    route_to: str  # Internal routing signal between nodes (e.g., "complete"/"incomplete", "approved"/"rejected")

    # Assessment workflow tracking
    analysis_steps: list[str]  # Chronological sequence of analysis actions taken
    documents_processed: list[dict]  # Uploaded financial documents (PDFs, bank statements, etc.)
    extracted_fields: dict  # Financial fields extracted by data_completeness_checker (with VND conversion)

    # Financial metrics
    financial_ratios: dict  # Key ratios: debt-to-equity, current ratio, ROE, profit margin, etc.
    revenue_trends: dict  # Time series analysis of revenue growth/decline
    cash_flow_analysis: dict  # Operating, investing, financing cash flow ratios

    # Credit assessment results
    credit_score: float  # 300-850 Credence Credit Score
    default_probability: float  # 0.0-1.0 probability of loan default
    risk_level: str  # Risk classification: "low" | "medium" | "high" | "critical"
    risk_factors: list[str]  # Identified risk factors (e.g., "high leverage", "declining revenue")

    # Business intelligence
    industry_benchmarks: dict  # Peer comparison metrics for borrower's industry
    alternative_data: dict  # Non-traditional data: mobile money, POS revenue, utility payments
    merchant_profile: dict  # Merchant data fetched from MCP Supabase (ID, name, transactions, etc.)

    # Tool execution tracking
    tools_used: list[str]  # Names of tools invoked during assessment
    tool_results: list[dict]  # Raw results from each tool execution
    data_completeness_score: float  # 0.0-1.0: completeness of provided financial data

    # Loan decision and explainability
    loan_recommendation: dict  # Decision: {action: "approve"|"reject", amount: float, rate: float, terms: str}
    shap_explanations: dict  # SHAP feature importance explaining credit score factors
    counterfactuals: list[dict]  # Improvement scenarios for rejected/marginal applicants
    fairness_check_results: dict  # Causal fairness validation results (bias detection)

    # Applicant context from sidebar
    selected_profile_id: str  # Applicant ID selected in frontend sidebar (empty = none)

    # Final output
    final_response: str  # Generated credit assessment report (markdown format)
