import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)
async def planning_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 1: Planning

        Assesses the user's query and determines the loan assessment approach.
        Performs initial risk classification and outlines assessment steps.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with assessment plan and initial risk classification
        """
        messages = state["messages"]
        last_message = messages[-1].content if messages else ""
        selected_profile_id = state.get("selected_profile_id", "")
        extracted_fields = state.get("extracted_fields", {})
        applicant_id = state.get("applicant_id", None)

        # Build context about the applicant data already loaded
        data_context = ""
        if applicant_id:
            data_context = f"\nApplicant #{applicant_id} data loaded from database with {len(extracted_fields)} features."
            # Summarize key fields for the planner
            key_fields = {}
            field_labels = {
                "AMT_INCOME_TOTAL": "Annual Income",
                "AMT_CREDIT": "Loan Amount",
                "AMT_ANNUITY": "Monthly Payment",
                "AMT_GOODS_PRICE": "Goods Price",
                "DAYS_BIRTH": "Age (days)",
                "DAYS_EMPLOYED": "Employment (days)",
                "EXT_SOURCE_1": "External Score 1",
                "EXT_SOURCE_2": "External Score 2",
                "EXT_SOURCE_3": "External Score 3",
            }
            for feat, label in field_labels.items():
                if feat in extracted_fields and extracted_fields[feat] is not None:
                    key_fields[label] = extracted_fields[feat]
            if key_fields:
                data_context += "\nKey data points: " + ", ".join(f"{k}={v}" for k, v in key_fields.items())
        elif selected_profile_id:
            data_context = f"\nApplicant #{selected_profile_id} selected from sidebar. Data loaded from database."

        planning_prompt = f"""You are Credence AI's planning module. You are part of an automated loan assessment pipeline.

IMPORTANT: The applicant data has ALREADY been loaded from the database. Do NOT ask for data — it is available.
{data_context}

The pipeline will automatically run these steps after your plan:
- Credit scoring (XGBoost → Credence Score 300-850 + default probability)
- Score factor analysis (SHAP → key drivers)
- Fairness validation (demographic bias check)
- Improvement paths (counterfactual scenarios)

Your job: briefly note the assessment approach. Think through:
1. What do we know about this applicant from the data?
2. Initial risk impression (low/medium/high/critical)
3. Any flags or special considerations

Be concise — 3-5 bullet points. Internal notes only, not user-facing."""

        # Use astream so tokens appear in real-time as "Thinking" in the pipeline
        collected_content = ""
        async for chunk in llm.astream([
            SystemMessage(content=planning_prompt),
            HumanMessage(content=f"Plan the assessment for this applicant request: {last_message}")
        ]):
            if hasattr(chunk, 'content') and chunk.content:
                collected_content += chunk.content

        # Build AIMessage from the collected content
        response = AIMessage(content=collected_content)

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
