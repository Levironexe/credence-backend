import logging
from typing import Dict, Any
from functools import partial

from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.state import LoanAssessmentState, QueryIntent

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """You are an intelligent query classifier for SME loan assessment. Analyze the user's query and classify it into ONE of these intents:

**1. simple_explanation**
- Educational/general questions about lending, credit, finance
- No specific loan data or assessment request
- **ALSO applies to follow-up questions about a previous assessment** — e.g. asking "why is the default probability so high?", "explain the fairness check results", "what does the score mean?", "can we still approve?", "what are external credit scores?"
- If the conversation history already contains a Loan Assessment Report (with credit score, SHAP factors, fairness results, etc.), and the user asks about that report, classify as simple_explanation — do NOT re-run the full assessment
- Examples: "What is a good debt-to-equity ratio?", "How do credit scores work?", "What factors affect loan approval?", "Why is the default probability 44%?", "Explain the fairness failures", "Should we request a co-signer?"

**2. single_tool**
- Query needs EXACTLY one tool to answer
- User provides some data but wants a single specific analysis
- **IMPORTANT: Questions about lending regulations, policies, laws, circulars, SBV rules, credit scoring methodology, CIC scores, compliance requirements, or best practices should use lending_knowledge_retriever** — even if they look like "general questions". The knowledge base has authoritative, institution-specific answers.
- Examples: "Check data completeness for: revenue=120M, loan=300M", "Calculate credit score with these metrics: ...", "What are the lending limits under Law 32?", "What is the CIC credit score range?", "What does Circular 11 say about loan classification?", "What are the provisioning rates?", "How does the Credence Credit Engine score borrowers?", "What are the capital adequacy requirements?"
- Tool options: credit_score_model, data_completeness_checker, financial_statement_analyzer, shap_explainer, counterfactual_generator, lending_knowledge_retriever

**3. re_assessment**
- User wants to RE-RUN a credit assessment on an already-assessed applicant with CHANGED metrics
- Key signal: applicant reference PLUS explicit new metric values OR what-if language
- Trigger phrases: "re-assess", "reassess", "assess again", "what if", "with different",
  "with new metrics", "change X to Y", "if revenue was", "scenario where", "recalculate",
  "assuming revenue", "suppose margin", "update the score"
- Examples:
  - "Re-assess applicant #285000 with revenue=500K and margin=18%"
  - "What if applicant #270000 had annual income of 800K?"
  - "Recalculate the score assuming AMT_CREDIT=200000"
- IMPORTANT: Even if applicant is selected in sidebar AND message contains what-if/metric-change
  language, classify as re_assessment

**4. full_assessment**
- Complex loan assessment with complete/rich financial data
- Requires multiple tools and comprehensive analysis
- ALSO applies when the user references an applicant by ID (e.g. "applicant #270000") — the system will look up the full data automatically, so treat this as a complete data request, NOT as "need_more_data"
- **Does NOT apply to follow-up questions about an existing report** — those are simple_explanation
- Examples: "Assess this $300M VND loan: 120M monthly revenue, 18% margin, 3 years old", "Analyze this loan application [full details]", "Assess applicant #270000", "Score applicant #285000", "Look up applicant 300000"

**5. need_more_data**
- User wants assessment but provides insufficient data
- Missing critical fields like loan amount, revenue, tenure
- IMPORTANT: Do NOT classify as need_more_data if the user provides an applicant ID number — that ID is used to look up all required data automatically
- Examples: "Why was my loan rejected?", "Can I get a loan?", "Assess my business" (no details)

Classify the query and provide:
- intent: The intent type
- tool_needed: (only for single_tool) Which tool is needed
- confidence: 0.0-1.0 confidence score
- reasoning: Brief explanation (1 sentence)"""


async def classify_node(state: LoanAssessmentState, llm) -> Dict[str, Any]:
    """
    Node 0: Classification

    Uses LLM to intelligently determine if the query requires loan assessment
    or is a general/educational question.

    Args:
        state: Current assessment state
        llm:   ChatAnthropic (or any LangChain chat model) injected by the agent

    Returns:
        Updated state with intent_type, single_tool_name, and analysis_steps
    """
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    selected_profile_id = state.get("selected_profile_id", "")

    # Handle multimodal content (list of parts)
    if isinstance(last_message, list):
        last_message = " ".join([part.get("text", "") for part in last_message if isinstance(part, dict) and part.get("type") == "text"])

    # Check if conversation history contains a previous assessment report
    has_prior_assessment = False
    for msg in messages[:-1]:  # All messages except the last (current query)
        content = msg.content if hasattr(msg, 'content') else ""
        if isinstance(content, str) and "Loan Assessment Report" in content:
            has_prior_assessment = True
            break

    # Build classifier input with context
    classifier_input = last_message
    if has_prior_assessment:
        classifier_input = f"[CONTEXT: A Loan Assessment Report was already generated earlier in this conversation. The user may be asking a follow-up question about it.]\n\n{last_message}"
    if selected_profile_id:
        classifier_input = f"[Applicant #{selected_profile_id} is selected in sidebar] {classifier_input}"

    structured_llm = llm.with_structured_output(QueryIntent, method="function_calling")

    result: QueryIntent = await structured_llm.ainvoke([
        SystemMessage(content=CLASSIFICATION_PROMPT),
        HumanMessage(content=classifier_input)
    ])

    logger.info(f"🎯 Query classified as: {result.intent} (confidence: {result.confidence:.2f})")
    logger.info(f"   Reasoning: {result.reasoning}")
    if selected_profile_id:
        logger.info(f"   Selected profile: #{selected_profile_id}")

    if result.intent == "single_tool" and result.tool_needed:
        logger.info(f"   Tool needed: {result.tool_needed}")

    return {
        **state,
        "intent_type": result.intent,
        "single_tool_name": result.tool_needed or "",
        "analysis_steps": [f"Intent: {result.intent} - {result.reasoning}"]
    }