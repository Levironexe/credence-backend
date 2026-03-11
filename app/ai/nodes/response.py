import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

async def response_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
        """
        Node 5: Response Generation

        Generates a final formatted loan assessment report for the user.
        Structures findings in a clear, professional format suitable for loan officers.

        Args:
            state: Current loan assessment state

        Returns:
            Updated state with final formatted response
        """
        messages = state["messages"]
        risk_level = state.get("risk_level", "medium")
        tools_used = state.get("tools_used", [])

        credit_score = state.get('credit_score', 0)
        default_probability = state.get('default_probability', 0.0)
        score_band = "Exceptional" if credit_score >= 800 else "Very Good" if credit_score >= 740 else "Good" if credit_score >= 670 else "Fair" if credit_score >= 580 else "Poor"
        decision = "AUTO-APPROVE" if credit_score >= 800 else "APPROVE (with conditions)" if credit_score >= 670 else "MANUAL REVIEW" if credit_score >= 580 else "DECLINE"

        # Check if counterfactuals are available (only for declined applicants)
        has_counterfactuals = credit_score < 670 and bool(state.get("counterfactuals"))

        # Use different prompt based on whether tools were used
        if tools_used:
            # Build the counterfactual section instruction
            if has_counterfactuals:
                counterfactual_section = """
## 6. How to Improve (Counterfactual Analysis)

Write one sentence: "The following changes would bring the applicant above the 670 approval threshold:"

Then COPY the Path tables EXACTLY as they appear in the [Counterfactual Analysis] message — including the ### Path headings with "+X pts", and the arrow deltas like (↓-318,480) or (↑+63,000) in the Target Value column. Do NOT remove, rephrase, round, or summarize ANY part of the tables. Reproduce them character-for-character. Include up to 3 paths."""
            else:
                counterfactual_section = ""

            response_prompt = f"""Generate a loan assessment report using the EXACT structure below. Fill in data from the ML model results in the conversation history.

**CRITICAL RULES:**
- Credence Credit Score is **{credit_score}/850** ({score_band}). This is the ONLY credit score. Do NOT use EXT_SOURCE values as scores.
- Default Probability is **{default_probability:.1%}**
- Risk Level is **{risk_level.upper()}**
- Decision is **{decision}**
- Use ONLY data from the [XGBoost ML Model Result], [SHAP Feature Importance], [Fairness Validation Result], and [Counterfactual Analysis] messages. Do NOT invent numbers.

---

**YOU MUST follow this EXACT structure:**

# Loan Assessment Report

## 1. Executive Summary

Render as a table:

| Field | Value |
|-------|-------|
| Credence Credit Score | **{credit_score} / 850** ({score_band}) |
| Default Probability | **{default_probability:.1%}** |
| Risk Level | **{risk_level.upper()}** |
| Decision | **{decision}** |
| Features Analyzed | (from the ML model result message) |
| Model | XGBoost (Home Credit, 128 features) |

---

## 2. Credit Score Breakdown

Write one sentence: "**Credence Score: {credit_score}** — computed by XGBoost ML model trained on Home Credit dataset (128 features)."

Then render the SHAP analysis from the [SHAP Feature Importance] message as a table:

### Top Factors Driving Score (SHAP Analysis)

| # | Factor | SHAP Impact | Value | Direction |
|---|--------|-------------|-------|-----------|
| 1 | (from SHAP message) | +/-0.XXXX | value | Positive/Negative |
| ... | ... | ... | ... | ... |

Include up to 5-7 factors from the SHAP message. Use the "label" field for Factor name, "shap_value" for Impact, "value" for Value, and "direction" for Direction.

---

## 3. Risk Assessment

**Overall Risk: {risk_level.upper()}**

### Risk Factors
List the top 2-4 negative SHAP factors as risk concerns. Explain each in one sentence using plain language a loan officer would understand (e.g., "Short employment history (1 year) suggests limited job stability").

IMPORTANT: NEVER list gender, age, ethnicity, religion, or marital status as a risk factor — these are protected attributes. If gender or age appears as a SHAP factor, skip it in this section. The Fairness Validation section handles demographic analysis separately.

### Mitigating Strengths
List the top 2-3 positive SHAP factors as strengths. Explain each in one sentence (e.g., "Strong external credit bureau score (0.71) indicates reliable repayment history").

---

## 4. Fairness Validation

Render the fairness check from the [Fairness Validation Result] message as a table:

| Metric | Gender | Age Group |
|--------|--------|-----------|
| Demographic Parity Diff | X.XXXX | X.XXXX |
| Equalized Odds Diff | X.XXXX | X.XXXX |
| Status | PASSED/FAILED | PASSED/FAILED |

Then one sentence: "No bias detected — decision is demographically fair." or "Potential bias detected — flagged for human review."

---

## 5. Lending Decision

Render as a table:

| Parameter | Recommendation |
|-----------|---------------|
| Decision | **{decision}** |
| Primary Reasons | (2-3 key factors from SHAP driving this decision) |
| Conditions | (if approved: what to verify; if declined: why) |
| Monitoring | (if approved: review frequency recommendation) |
{counterfactual_section}

---

**STYLE RULES:**
- Use tables extensively — loan officers scan tables, not paragraphs
- Keep text between tables to 1-2 sentences max
- No filler text, no preamble, no "In conclusion..."
- Do NOT add sections not listed above
- Do NOT add a Regulatory Notes section
- Start directly with "# Loan Assessment Report"
"""

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

        final_response = await llm.ainvoke([
            SystemMessage(content=response_prompt),
            *messages
        ])

        logger.info("Loan assessment complete - final report generated")

        return {
            **state,
            "messages": state["messages"] + [final_response],
            "final_response": final_response.content,
        }
