"""
Activity Event Model for Real-Time LLM Streaming

Provides structured events for real-time visibility into agent workflow,
similar to Perplexity, v0.dev, and Claude Code.

Events include: agent lifecycle, tool execution, workflow transitions, and results.
"""

from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ActivityEventType(Enum):
    """Types of activity events emitted during loan assessment."""

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_THINKING = "agent_thinking"
    AGENT_END = "agent_end"

    # Tool execution
    TOOL_START = "tool_start"
    TOOL_PROGRESS = "tool_progress"  # Progress updates for long-running tools
    TOOL_END = "tool_end"

    # Document processing
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_PROCESSING = "document_processing"
    DOCUMENT_EXTRACTED = "document_extracted"

    # LLM reasoning
    LLM_REASONING = "llm_reasoning"  # Reasoning steps
    LLM_STREAMING = "llm_streaming"  # Text generation

    # Workflow transitions
    WORKFLOW_NODE_START = "workflow_node_start"  # LangGraph node transitions
    WORKFLOW_NODE_END = "workflow_node_end"

    # Results
    RESULT = "result"  # Structured result (credit score, risk level, etc.)
    ERROR = "error"

    # Final response
    RESPONSE_START = "response_start"
    RESPONSE_STREAMING = "response_streaming"
    RESPONSE_END = "response_end"


class ActivityEvent(BaseModel):
    """
    Structured activity event for streaming to frontend.

    Example events:
        - Agent start: {"event_type": "agent_start", "agent_name": "LoanOfficerOrchestrator", "message": "Starting assessment"}
        - Tool start: {"event_type": "tool_start", "tool_name": "CreditScoreModel", "message": "Computing credit score"}
        - Result: {"event_type": "result", "tool_name": "CreditScoreModel", "data": {"credit_score": 680, "score_band": "Good"}}
    """

    event_type: ActivityEventType = Field(description="Type of activity event")
    timestamp: datetime = Field(default_factory=datetime.now, description="Event timestamp")
    agent_name: Optional[str] = Field(default=None, description="Name of agent (if applicable)")
    tool_name: Optional[str] = Field(default=None, description="Name of tool (if applicable)")
    node_name: Optional[str] = Field(default=None, description="LangGraph node name (if applicable)")
    message: str = Field(description="Human-readable description of activity")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured data (progress %, results, etc.)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")

    def to_sse_format(self) -> Dict[str, Any]:
        """
        Convert to Server-Sent Event format for frontend streaming.

        Returns:
            Dictionary compatible with SSE data field
        """
        return {
            "type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "node_name": self.node_name,
            "message": self.message,
            "data": self.data,
            "metadata": self.metadata
        }

    def to_frontend_ui_event(self) -> Dict[str, Any]:
        """
        Convert to frontend UI event format (for activity feed display).

        Returns:
            Dictionary with icon, message, and data for UI rendering
        """
        # Map event types to icons
        icon_map = {
            ActivityEventType.AGENT_START: "🤖",
            ActivityEventType.AGENT_THINKING: "💭",
            ActivityEventType.TOOL_START: "🔧",
            ActivityEventType.TOOL_PROGRESS: "⏳",
            ActivityEventType.TOOL_END: "✅",
            ActivityEventType.DOCUMENT_PROCESSING: "📄",
            ActivityEventType.LLM_REASONING: "💭",
            ActivityEventType.WORKFLOW_NODE_START: "🔄",
            ActivityEventType.RESULT: "✅",
            ActivityEventType.ERROR: "❌",
            ActivityEventType.RESPONSE_START: "📊",
        }

        return {
            "icon": icon_map.get(self.event_type, "📍"),
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value
        }


# Example usage:
#
# # Agent start
# event = ActivityEvent(
#     event_type=ActivityEventType.AGENT_START,
#     agent_name="LoanOfficerOrchestrator",
#     message="Starting loan assessment workflow",
#     data={"applicant_name": "Coffee Shop Co."}
# )
#
# # Tool execution with progress
# event = ActivityEvent(
#     event_type=ActivityEventType.TOOL_START,
#     tool_name="FinancialStatementAnalyzer",
#     message="Extracting data from balance_sheet.pdf",
#     data={"document_type": "balance_sheet"}
# )
#
# # Progress update
# event = ActivityEvent(
#     event_type=ActivityEventType.TOOL_PROGRESS,
#     tool_name="FinancialStatementAnalyzer",
#     message="OCR processing: 50% complete",
#     data={"progress": 0.5}
# )
#
# # Structured result
# event = ActivityEvent(
#     event_type=ActivityEventType.RESULT,
#     tool_name="CreditScoreModel",
#     message="Credit score computed",
#     data={
#         "credit_score": 680,
#         "score_band": "Good",
#         "default_probability": 0.25
#     }
# )
