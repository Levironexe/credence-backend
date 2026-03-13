import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

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
## 6. How to Improve

Write one sentence: "The following changes would bring the applicant above the 670 approval threshold, ranked from easiest to most difficult:"

Then COPY the Path tables EXACTLY as they appear in the [Counterfactual Analysis] message — including the ### Path headings with effort level and "+X pts", the Effort column (Now/Weeks/Months), the arrow deltas like (↓-318,480) or (↑+63,000) in the Target column, and the "Resulting improvement" rows for derived ratios. Do NOT remove, rephrase, round, or summarize ANY part of the tables. Reproduce them character-for-character. Include up to 3 paths."""
            else:
                counterfactual_section = ""

            response_prompt = f"""Generate a loan assessment report for a loan officer. Use the EXACT structure below. Fill in data from the analysis results in the conversation history.

**CRITICAL RULES:**
- Credence Credit Score is **{credit_score}/850** ({score_band}). This is the ONLY credit score. Do NOT use EXT_SOURCE values as scores.
- Default Probability is **{default_probability:.1%}**
- Risk Level is **{risk_level.upper()}**
- Decision is **{decision}**
- Use ONLY data from the analysis result messages. Do NOT invent numbers.
- This report is for LOAN OFFICERS — use credit/lending industry language, NOT technical ML terminology.
- NEVER mention: XGBoost, SHAP, machine learning, model, features, training, dataset, Home Credit, ML, AI model, neural network, algorithm, or any technical term.
- Instead of "SHAP Impact +0.5962", write the influence as "Strong influence" / "Moderate influence" / "Minor influence".
- Instead of "Features Analyzed: 17/128", write "Data Points Reviewed: 17".
- Instead of "XGBoost model", say "Credence Credit Engine" or just omit it.
- Refer to factors as "credit factors" not "features" or "SHAP factors".

---

**YOU MUST follow this EXACT structure:**

# Loan Assessment Report

## 1. Executive Summary

Render as a table:

| Field | Value |
|-------|-------|
| Credit Score | **{credit_score} / 850** ({score_band}) |
| Default Probability | **{default_probability:.1%}** |
| Risk Level | **{risk_level.upper()}** |
| Decision | **{decision}** |
| Data Points Reviewed | (number from the analysis result, just the number — e.g. "17") |

---

## 2. Credit Score Breakdown

Write one sentence: "**Credence Score: {credit_score} / 850 ({score_band})** — assessed using the applicant's financial profile, credit bureau data, and lending history."

### Key Factors Driving Score

Do NOT include any image link here — the waterfall chart is injected automatically.

Render as a table:

| # | Factor | Influence | Value | Impact |
|---|--------|-----------|-------|--------|
| 1 | (use the "label" field from the analysis) | Strong / Moderate / Minor | value | Increases risk / Reduces risk |
| ... | ... | ... | ... | ... |

Rules for the Influence column:
- abs(shap_value) >= 0.15: "Strong"
- abs(shap_value) >= 0.05: "Moderate"
- abs(shap_value) < 0.05: "Minor"

Include up to 7-10 factors. Use the "label" field for Factor name, "value" for Value, and "direction" for Impact. Do NOT show raw numeric SHAP values.

---

## 3. Risk Assessment

### Overall Risk: {risk_level.upper()}

### Risk Factors
List the top 2-4 negative factors as risk concerns. Explain each in one sentence using plain language a loan officer would understand (e.g., "Short employment history (1 year) suggests limited job stability"). Do NOT mention SHAP values or model internals.

IMPORTANT: NEVER list gender, age, ethnicity, religion, or marital status as a risk factor — these are protected attributes. The Fairness Check section handles demographic analysis separately.

### Mitigating Strengths
List the top 2-3 positive factors as strengths. Explain each in one sentence (e.g., "Strong credit bureau score (0.71) indicates reliable repayment history").

---

## 4. Fairness Check

Render the fairness results as a table:

| Check | Gender | Age Group | Marital Status |
|-------|--------|-----------|----------------|
| Equal Approval Rate | X.XX | X.XX | X.XX |
| Prediction Consistency | X.XX | X.XX | X.XX |
| Statistical Significance | X.XX | X.XX | X.XX |
| Result | PASSED/FAILED | PASSED/FAILED | PASSED/FAILED |

Brief explanation: "Equal Approval Rate checks whether approval rates are consistent across demographic groups (threshold: 0.80). Prediction Consistency checks whether accuracy is equal across groups."

Then one sentence: "No bias detected — decision is fair across all demographic groups." or "Potential bias detected — flagged for human review."

---

## 5. Lending Decision

Render as a table:

| Parameter | Recommendation |
|-----------|---------------|
| Decision | **{decision}** |
| Key Reasons | (2-3 key credit factors driving this decision, in plain language) |
| Conditions | (if approved: what to verify; if declined: why) |
| Monitoring | (if approved: review frequency recommendation) |
{counterfactual_section}

---

**STYLE RULES:**
- Write for a loan officer with 5+ years of experience — professional, concise, actionable
- Use tables extensively — loan officers scan tables, not paragraphs
- Keep text between tables to 1-2 sentences max
- No filler text, no preamble, no "In conclusion..."
- Do NOT add sections not listed above
- Do NOT add a Regulatory Notes or Methodology section
- Your FIRST output character MUST be "#" (the heading). No text before it.
- Start directly with "# Loan Assessment Report"
- Use USD ($) for all monetary values
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

        # Filter messages: only pass user query + data messages to avoid the LLM
        # echoing counterfactual/analysis AIMessages as if they were its own prior response.
        # Keep: HumanMessage (user query), SystemMessage, and AIMessages that contain
        # structured data markers like [XGBoost], [SHAP], [Fairness], [Counterfactual]
        from langchain_core.messages import BaseMessage
        filtered_messages = []
        for msg in messages:
            if isinstance(msg, (SystemMessage, HumanMessage)):
                filtered_messages.append(msg)
            elif isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else ""
                # Only keep data-bearing AIMessages (injected by pipeline nodes)
                if any(marker in content for marker in [
                    "[XGBoost", "[SHAP", "[Fairness", "[Counterfactual",
                    "ML Model Result", "Feature Importance", "Validation Result",
                ]):
                    # Wrap as HumanMessage so the LLM doesn't treat it as its own prior output
                    filtered_messages.append(HumanMessage(content=content))

        # Stream the response so tokens appear incrementally in the frontend
        collected_content = ""
        try:
            async for chunk in llm.astream([
                SystemMessage(content=response_prompt),
                *filtered_messages
            ]):
                if hasattr(chunk, 'content') and chunk.content:
                    collected_content += chunk.content
        except Exception as e:
            logger.error(f"Error streaming response: {type(e).__name__}: {e}")
            if not collected_content:
                collected_content = "Error generating report. The analysis pipeline completed successfully — please try again."

        # Inject SHAP waterfall plot image into the response (if available)
        # The LLM can't include the base64 image (too large for context),
        # so we insert it post-generation before the factors table.
        import re
        shap_data = state.get("shap_explanations") or {}
        waterfall_plot = shap_data.get("waterfall_plot")
        if waterfall_plot and collected_content:
            # Remove any hallucinated image links the LLM may have generated
            collected_content = re.sub(
                r'!\[.*?(?:SHAP|Waterfall|waterfall|Chart|chart).*?\]\([^)]*\)\s*\n?',
                '',
                collected_content
            )
            # Insert the real waterfall plot before the factors table
            table_pattern = re.search(
                r'(\|\s*#\s*\|\s*Factor\s*\|\s*(?:SHAP Impact|Influence)\s*\|)',
                collected_content
            )
            if table_pattern:
                insert_pos = table_pattern.start()
                collected_content = (
                    collected_content[:insert_pos]
                    + f"![SHAP Waterfall Plot]({waterfall_plot})\n\n"
                    + collected_content[insert_pos:]
                )

        final_response = AIMessage(content=collected_content)
        logger.info(f"Loan assessment complete - final report generated ({len(collected_content)} chars)")

        # Save results to DB only when a full assessment was performed on a DB applicant
        applicant_id = state.get("applicant_id", 0)
        if applicant_id and credit_score:
            try:
                from app.database import AsyncSessionLocal
                from app.models.applicant import ApplicantResult

                async with AsyncSessionLocal() as db_session:
                    result_row = ApplicantResult(
                        applicant_id=applicant_id,
                        credit_score=int(credit_score) if credit_score else None,
                        score_band=score_band,
                        default_probability=float(default_probability) if default_probability else None,
                        risk_level=risk_level,
                        decision=decision,
                        shap_explanations=state.get("shap_explanations"),
                        fairness_results=state.get("fairness_check_results"),
                        counterfactuals=state.get("counterfactuals"),
                        full_report=collected_content,
                    )
                    db_session.add(result_row)
                    await db_session.commit()
                logger.info(f"Saved assessment result to DB for applicant #{applicant_id}")
            except Exception as e:
                logger.error(f"Failed to save result to DB: {e}")

        return {
            **state,
            "messages": state["messages"] + [final_response],
            "final_response": collected_content,
        }
