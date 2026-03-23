# CreditAI — Presentation Slide Content

---

## Slide: The Problem

- 95% of Vietnamese businesses are micro-SMEs
- 70-80% lack formal credit access (IFC, 2018)
- The global MSME finance gap: **$5.7 trillion** (World Bank, 2017)
- These businesses aren't risky — traditional scoring simply **can't see them**
- IFC estimates 30-40% of MSME rejections come from **data gaps, not actual risk**

**What happens today:**
- Loan officer fills a rigid form
- Black-box score comes back
- Generic rejection letter: "Your application has been declined"
- Applicant has no idea what to improve
- Gives up on formal credit

---

## Slide: Our Solution — CreditAI

An **autonomous AI agent** that talks to loan officers in plain language, picks the right ML tools for each query, and explains every decision it makes.

**What changes:**
- Natural language input replaces rigid forms
- Every score is explained with per-feature SHAP contributions
- Rejected applicants get **concrete improvement paths**: "Reduce loan to $20K or wait 4 months"
- Fairness is validated on every decision — no demographic bias reaches borrowers

---

## Slide: Impact Numbers (from 46,127 real test profiles)

### CreditAI approves 2.3x more applicants at the same risk level

| Metric | Traditional Bank | CreditAI |
|---|---|---|
| Approved applicants | 8,595 (18.6%) | 19,592 (42.5%) |
| Default rate among approved | 2.22% | 2.13% |
| Additional approvals | — | **+10,997 (+128%)** |

- Proposal target was 30% approval lift — **we deliver 128%**
- Default rate is actually **lower** than traditional (2.13% vs 2.22%)

### The hidden creditworthy

**1,906 applicants** that traditional scoring rejects are actually creditworthy.

- CreditAI finds them
- Their default rate: **2.94%** — within the 1.2x parity target
- These are real businesses being denied capital because traditional models can't see them

> "Traditional credit scoring rejects 1,906 creditworthy micro-SMEs in our test set alone. CreditAI finds them — at a lower default rate than the traditional approved pool."

---

## Slide: The 5 ML Tools

The agent autonomously selects and chains these tools per query:

| Tool | What It Does | Tech |
|---|---|---|
| **Credit Scoring Model** | Predicts default probability, maps to 300-850 score | XGBoost, 128 features, trained on 307K samples |
| **SHAP Explainer** | Explains why — per-feature contribution breakdown | TreeSHAP with waterfall plot visualization |
| **Counterfactual Generator** | Shows how to improve — minimal changes for approval | DiCE-ML + greedy optimizer, effort-ranked |
| **Fairness Validator** | Checks for bias — gender, age, marital status | FairLearn: disparate impact, equalized odds |
| **Data Completeness Checker** | Identifies what's missing — ranked by importance | SHAP-weighted field impact ranking |

---

## Slide: How It Works (Architecture)

```
Loan Officer
    |
    | "Can this applicant get a $5,000 loan?"
    v
Next.js Frontend ──SSE streaming──> Real-time tool visibility
    |
    v
FastAPI Backend
    |
    v
LangGraph Agent (18 nodes)
    |
    |── Classify intent
    |── Check data completeness (SHAP-weighted)
    |── Run XGBoost credit scoring
    |── Generate SHAP explanation + waterfall plot
    |── Validate fairness (FairLearn)
    |── Generate counterfactual paths (if declined)
    |── Synthesize report
    |
    v
Claude (Haiku 4.5) ←→ Tool-use function calling
```

---

## Slide: Agentic AI — Not Just an API Call

**Traditional ML credit scoring:**
- Fixed input form → model.predict() → score → done
- One-shot, no context, no explanation

**CreditAI (Agentic approach):**
- Agent **reads** the loan officer's question
- **Decides** which tools to call and in what order
- **Remembers** context across conversation turns
- **Explains** every decision with SHAP
- **Guides** rejected applicants with actionable improvement paths
- **Checks** for demographic bias before any decision reaches a borrower

This follows the **ReAct paradigm** (Yao et al., 2023): an LLM interleaves reasoning with tool actions, extended here with domain-specific financial tools.

---

## Slide: Explainability — Every Score Is Transparent

### Per-decision SHAP breakdown

For every applicant, CreditAI shows:
- Which features pushed the score **up** (green) and **down** (red)
- Exact point contribution of each feature
- Visual waterfall plot

### Example output:
| Factor | Value | Impact |
|---|---|---|
| Monthly order consistency | 94% | +55 pts (reduces risk) |
| Business tenure | 18 months | -42 pts (increases risk) |
| Revenue-to-loan ratio | 1.34 | +30 pts (reduces risk) |
| Employment duration | 2.5 years | -18 pts (increases risk) |

This isn't post-hoc — it's computed **per decision, in real time**.

---

## Slide: Counterfactual Guidance — Turning Rejections Into Roadmaps

**Traditional rejection:** "Your application has been declined."

**CreditAI rejection:**

> Score: 640 (Fair — Manual Review Required)
>
> **To reach approval (670+):**
>
> | Path | Change | Difficulty | Projected Score |
> |---|---|---|---|
> | 1 | Reduce loan from $35K to $20K | Easy — immediate | 695 |
> | 2 | Pay down $7K of outstanding debt | Moderate — 3-6 months | 688 |
> | 3 | Build 2 more years employment history | Long-term | 710 |
>
> **Easiest path: Reduce loan amount → immediate approval**

- Uses **DiCE-ML** (genetic algorithm) with **greedy optimizer** fallback
- **Directional constraints**: income can't go down, age can't decrease
- **Plausibility caps**: no "increase income 10x" suggestions
- **Effort-ranked**: easiest changes shown first

---

## Slide: Fairness — No Bias Reaches Borrowers

Every assessment runs through **FairLearn** fairness validation:

| Check | Method |
|---|---|
| Disparate Impact Ratio | Must exceed 0.80 (four-fifths rule) |
| Equalized Odds | Approval rates compared across groups |
| Chi-squared Test | Statistical significance of any disparity |

Protected attributes checked: **gender, age group, marital status**

From our test set:
- Gender disparate impact: **0.91** (passed)
- Age group disparate impact: **0.89** (passed)
- No systematic bias detected across 46,127 assessments

---

## Slide: Credit Score Distribution (46,127 test profiles)

| Score Band | Count | % | Default Rate | Decision |
|---|---|---|---|---|
| Exceptional (800-850) | 1,173 | 2.5% | 0.68% | Auto-approve |
| Very Good (740-799) | 7,518 | 16.3% | 1.53% | Approve |
| Good (670-739) | 10,901 | 23.6% | 2.70% | Approve with conditions |
| Fair (580-669) | 11,493 | 24.9% | 6.05% | Manual review |
| Poor (300-579) | 15,042 | 32.6% | 16.88% | Decline + guidance |

Default rates increase monotonically: **0.68% → 16.88%** (25x gradient)

This confirms the model meaningfully separates risk across all score bands.

---

## Slide: Model Performance

| Metric | Value |
|---|---|
| AUC-ROC | 0.7705 |
| KS Statistic | 0.4032 |
| Gini Coefficient | 0.5411 |
| Training data | 307K samples, 128 features (Home Credit) |
| Test profiles | 46,127 held-out applicants |

Score band default rates show strong **rank-ordering ability** — the model correctly identifies risk tiers from Exceptional (0.68% default) to Poor (16.88% default).

---

## Slide: Real-Time Agent Visibility

The loan officer sees every step the agent takes in real time:

1. **Classifying query** — intent detection
2. **Loading applicant data** — profile lookup
3. **Checking data completeness** — SHAP-weighted gap analysis
4. **Computing credit score** — XGBoost prediction
5. **Analyzing score factors** — TreeSHAP explanation
6. **Checking lending fairness** — FairLearn validation
7. **Generating improvement paths** — DiCE counterfactuals (if declined)
8. **Generating report** — structured credit assessment

Each step streams as a collapsible card with parameters and results. Full transparency into the AI's reasoning — not a black box.

---

## Slide: Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Backend | FastAPI (async Python) |
| Agent Orchestration | LangGraph (18-node state graph) |
| LLM | Claude Haiku 4.5 (via Anthropic API) |
| ML Model | XGBoost (128 features, 307K training samples) |
| Explainability | SHAP (TreeExplainer), DiCE-ML, FairLearn |
| Database | PostgreSQL (Supabase) + pgvector |
| Auth | Google OAuth 2.0 + NextAuth.js |
| Streaming | Server-Sent Events (structured event types) |

---

## Slide: What Makes CreditAI Different

| Capability | Traditional | ML-based | CreditAI |
|---|---|---|---|
| Input method | Rigid forms | Structured API | **Natural language** |
| Explainability | None | Post-hoc | **SHAP per decision** |
| Rejection guidance | Generic letter | None | **Counterfactual paths** |
| Thin-file handling | Decline | Limited | **128-feature model** |
| Interaction | One-shot | One-shot | **Multi-turn dialogue** |
| Fairness | Not checked | Rarely | **Every decision validated** |
| Agent autonomy | None | None | **Autonomous tool selection** |

---

## Slide: Business Case

- Target market: Vietnamese commercial banks, MFIs, fintech lenders
- 95%+ of Vietnamese businesses are micro-SMEs (VEPR, 2017)
- A mid-sized Vietnamese MFI processes 40K-60K loan applications/year
- Unit cost: ~$0.06 per assessment
- Selling price: $0.15-0.25 per assessment
- **Gross margin: 62-77%**
- Compliance: Vietnamese Cybersecurity Law (24/2018) + Decree 13/2023

---

## Slide: Team

Four Computer Science students:

| Role | Focus |
|---|---|
| Software Developer | Web interface, API integration, agent orchestration |
| Data Engineer | Data pipeline, ETL, dataset ingestion |
| DevOps | Infrastructure, CI/CD, monitoring |
| AI Engineer | XGBoost training, SHAP/DiCE integration, model evaluation |
