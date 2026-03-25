<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-light.svg" />
    <source media="(prefers-color-scheme: light)" srcset="docs/images/logo-dark.svg" />
    <img src="docs/images/logo-dark.svg" alt="Credence" width="360" />
  </picture>
</p>

<p align="center">
  <strong>Agentic Credit Assessment Engine for Micro-SMEs</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://www.langchain.com/langgraph"><img src="https://img.shields.io/badge/LangGraph-1.0-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph" /></a>
  <a href="https://www.anthropic.com/"><img src="https://img.shields.io/badge/Claude_Haiku_4.5-Anthropic-D4A574?style=for-the-badge&logo=anthropic&logoColor=white" alt="Claude" /></a>
  <br/>
  <a href="https://xgboost.readthedocs.io/"><img src="https://img.shields.io/badge/XGBoost-3.1-F37626?style=for-the-badge&logo=xgboost&logoColor=white" alt="XGBoost" /></a>
  <a href="https://shap.readthedocs.io/"><img src="https://img.shields.io/badge/SHAP-0.51-B721FF?style=for-the-badge" alt="SHAP" /></a>
  <a href="https://fairlearn.org/"><img src="https://img.shields.io/badge/FairLearn-0.13-2D72D2?style=for-the-badge" alt="FairLearn" /></a>
  <a href="https://supabase.com/"><img src="https://img.shields.io/badge/Supabase-pgvector-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" /></a>
</p>

---

This is the backend engine behind **Credence** — an AI agent that handles the full credit assessment lifecycle through natural conversation. A loan officer asks a question, and an 18-node LangGraph agent classifies intent, orchestrates ML tools, scores the applicant, explains every factor, checks for bias, and generates actionable improvement paths for declined applicants.

Built for the **$24B credit gap** in Vietnam, where 98% of businesses are SMEs but only 9.3% can access bank loans.

## How It Works

```
Loan Officer: "Assess applicant #270000"

  1. Classify       → full_assessment (confidence: 0.95)
  2. Fetch Data     → Load 128 features from applicant profile
  3. Completeness   → 87% complete, sufficient to proceed
  4. Credit Scoring → XGBoost → P(default) = 0.24, Score: 718 (Good)
  5. Explainability → TreeSHAP → Top factors: external scores, employment length
  6. Fairness       → FairLearn → No demographic bias detected
  7. Response       → Structured credit report streamed via SSE

→ Decision: APPROVE with conditions
```

For declined applicants, the agent doesn't just say no — it generates concrete improvement paths:

```
Score: 640 (Fair) → To reach 670 (approval threshold):
  1. Reduce loan amount from $35K → $20K     (projected: 695, Easy)
  2. Pay down $7K in outstanding debt          (projected: 688, Moderate)
  3. Build 2 more years of employment history  (projected: 710, Long-term)
```

## Architecture

### 18-Node Agent Pipeline

The LangGraph agent routes queries through a state-driven graph. Simple questions resolve in 2 nodes; full assessments traverse 10+.

```mermaid
graph TD
    START((Start)) --> classify

    classify{{"Classify"}}

    classify -->|simple| simple_response["Simple Response"]
    classify -->|single_tool| single_tool["Single Tool Execution"]
    classify -->|need_data| need_data["Need More Data"]
    classify -->|re_assess| metric_extraction["Metric Extraction"]
    classify -->|full| fetch_merchant["Fetch Merchant Data"]

    simple_response --> END1((End))
    single_tool --> END2((End))
    need_data --> END3((End))

    fetch_merchant --> doc_ingestion["Document Ingestion"]
    metric_extraction --> data_completeness

    doc_ingestion --> data_completeness{{"Data Completeness"}}

    data_completeness -->|complete| credit_scoring
    data_completeness -->|incomplete| need_data2["Need More Data"]
    need_data2 --> END4((End))

    credit_scoring["Credit Scoring"]
    credit_scoring --> explainability

    explainability["SHAP Explainability"]
    explainability --> fairness_check

    fairness_check{{"Fairness Check"}}
    fairness_check -->|approved| analysis
    fairness_check -->|declined| counterfactual

    counterfactual["Counterfactual Generation"]
    counterfactual --> analysis

    analysis["Analysis"] --> responseNode["Response"]
    responseNode --> END5((End))
```

**Node types:**
- **Decision nodes** — classify, data_completeness, tool_selection, fairness_check — conditional routing based on state
- **ML pipeline nodes** — credit_scoring, explainability, counterfactual — call ML tools directly, no LLM
- **LLM reasoning nodes** — planning, analysis, response — call Claude with system prompts

### Agent Tools

| Tool | Purpose | Technology |
|---|---|---|
| `credit_score_model` | Default probability prediction, score 300–850 | XGBoost, 128 features |
| `shap_explainer` | Per-decision feature importance + waterfall plots | TreeSHAP |
| `counterfactual_generator` | Actionable paths for declined applicants | DiCE-ML + greedy optimizer |
| `fairness_validator` | Demographic bias detection on every decision | FairLearn (disparate impact, equalized odds) |
| `data_completeness_checker` | Missing fields ranked by scoring impact | SHAP-weighted field importance |
| `lending_knowledge_retriever` | RAG over lending regulations and policies | pgvector + Perplexity embeddings |
| `financial_statement_analyzer` | Financial ratio analysis from raw data | Rule-based with industry benchmarks |
| `applicant_lookup` | Load full applicant profile by ID | Home Credit test set (46,127 profiles) |

### RAG Knowledge Base

The lending knowledge retriever uses pgvector for semantic search over Vietnamese banking regulations:

- Vietnam Law on Credit Institutions 2024 (Law 32/2024/QH15)
- SBV lending regulations (Circular 39/2016 and amendments)
- Asset classification & provisioning (Circular 11/2021)
- Capital adequacy / Basel III (Circular 14/2025)
- CIC credit scoring framework (150–750 scale)
- AML requirements (Law 14/2022/QH15)
- SME lending best practices

Embeddings: Perplexity `pplx-embed-v1-0.6b` (1024 dims). Retrieval uses raw async SQL over the app's asyncpg connection pool — no separate sync driver needed.

## Model Performance

Trained on the [Home Credit Default Risk](https://www.kaggle.com/c/home-credit-default-risk) dataset — 307K samples, 128 features.

| Metric | Value |
|---|---|
| AUC-ROC | 0.7705 |
| Gini Coefficient | 0.5411 |
| KS Statistic | 0.4032 |
| Recall | 68.6% |
| 5-Fold CV Std Dev | 0.003 |
| Test set | 46,127 applicants |

### Score Band Separation

| Band | Range | Default Rate | Decision |
|---|---|---|---|
| Exceptional | 800–850 | 0.68% | Auto-approve |
| Very Good | 740–799 | 1.53% | Approve |
| Good | 670–739 | 2.70% | Approve with conditions |
| Fair | 580–669 | 6.05% | Manual review |
| Poor | 300–579 | 16.88% | Decline + counterfactual guidance |

25x default rate gradient from Exceptional to Poor. The model uses **ratio features** (loan-to-income, annuity-to-income, employment-to-age) instead of raw dollar amounts — ratios stay meaningful over time as inflation shifts absolute values.

## API Endpoints

### Chat & Agent
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send message to LangGraph agent (SSE stream) |
| `GET` | `/api/history` | Get conversation history |
| `DELETE` | `/api/chat` | Delete conversation |

### Applicant Profiles
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/applicants/search?q={id}` | Search applicant by ID |
| `GET` | `/api/applicants/{id}` | Get full applicant profile (128 features) |
| `GET` | `/api/applicants/{id}/summary` | Get profile summary |

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/google/login` | Initiate Google OAuth |
| `GET` | `/auth/google/callback` | OAuth callback |
| `POST` | `/auth/establish-session` | Establish session with token |
| `GET` | `/auth/me` | Get current user |

### Files & Documents
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/files/upload` | Upload file (images, PDF) |
| `POST` | `/api/document` | Create document |
| `GET` | `/api/document/{id}` | Get document |

### Utilities
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/vote` | Vote on message |
| `GET` | `/api/vote` | Get votes for message |

## Project Structure

```
credence-backend/
├── app/
│   ├── ai/                          # LangGraph agent
│   │   ├── langgraph_agent.py       # Graph definition, 18 nodes, edges
│   │   ├── gateway_client.py        # LLM client + tool binding
│   │   ├── state.py                 # LoanAssessmentState schema
│   │   └── nodes/                   # All 18 agent nodes
│   │       ├── classify.py          # Intent classification (5 intents)
│   │       ├── credit_scoring.py    # XGBoost scoring node
│   │       ├── explainability.py    # TreeSHAP node
│   │       ├── fairness_check.py    # FairLearn validation
│   │       ├── counterfactual_generation.py  # DiCE-ML paths
│   │       ├── data_completeness.py # Field gap analysis
│   │       ├── tool_selection.py    # Dynamic tool dispatch
│   │       ├── response.py          # Final report generation
│   │       └── ...                  # 10 more nodes
│   ├── tools/                       # ML tool implementations
│   │   ├── credit_scoring/          # XGBoost model + applicant lookup
│   │   ├── explainability/          # SHAP explainer + DiCE counterfactuals
│   │   ├── fairness/                # FairLearn bias detection
│   │   ├── knowledge/               # RAG lending knowledge retriever
│   │   ├── financial_analysis/      # Financial statement analyzer
│   │   ├── validation/              # Data completeness checker
│   │   └── document_processing/     # PDF extractor + bank statement parser
│   ├── services/                    # Business logic
│   │   ├── rag_service.py           # pgvector retrieval (async SQL)
│   │   └── cache_service.py         # Response caching
│   ├── routers/                     # API endpoints
│   │   ├── chat.py                  # SSE streaming chat
│   │   ├── applicants.py            # Applicant profile lookup
│   │   ├── auth.py                  # Google OAuth
│   │   └── files.py                 # File upload
│   ├── models/                      # SQLAlchemy ORM models
│   ├── schemas/                     # Pydantic request/response schemas
│   └── config.py                    # Environment configuration
├── ml_models/                       # Trained model artifacts
│   ├── xgboost_model.json           # XGBoost model
│   ├── X_test.csv                   # 46,127 test profiles
│   ├── shap_explainer.pkl           # Pre-computed SHAP explainer
│   └── training_medians.json        # Feature imputation values
├── knowledge_base/                  # RAG source documents
├── notebooks/                       # Jupyter notebooks (training + evaluation)
├── migrations/                      # Alembic database migrations
└── requirements.txt                 # Python dependencies
```

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL with pgvector extension (or Supabase)
- Google OAuth credentials
- Anthropic API key (for Claude Haiku 4.5)

### Installation

```bash
# Clone the repository
git clone https://github.com/ClaudeCodeMax/credence-backend.git
cd credence-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# App
SECRET_KEY=your-secret-key
DEBUG=False

# Database (Supabase PostgreSQL with pgvector)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Frontend
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

# LLM (Anthropic — used by LangGraph agent)
ANTHROPIC_API_KEY=your-anthropic-key

# Embeddings (OpenRouter — for RAG knowledge base)
OPENROUTER_API_KEY=your-openrouter-key
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`. API docs at `/docs`.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115, Uvicorn, async Python |
| Agent | LangGraph 1.0 (18-node state graph), LangChain |
| LLM | Claude Haiku 4.5 via Anthropic API |
| ML Scoring | XGBoost 3.1, scikit-learn |
| Explainability | SHAP 0.51 (TreeSHAP), DiCE-ML |
| Fairness | FairLearn 0.13 |
| Database | PostgreSQL + pgvector (Supabase) |
| ORM | SQLAlchemy 2.0, asyncpg |
| RAG Embeddings | Perplexity pplx-embed-v1-0.6b (1024d) |
| Auth | Google OAuth 2.0 |
| Streaming | Server-Sent Events (sse-starlette) |
| Document Processing | pdfplumber, pytesseract |

## References

- Lundberg & Lee, "A Unified Approach to Interpreting Model Predictions" (NeurIPS 2017)
- Wachter et al., "Counterfactual Explanations Without Opening the Black Box" (2021)
- Kusner et al., "Counterfactual Fairness" (NeurIPS 2017)
- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (ICLR 2023)
- Home Credit Group, "Home Credit Default Risk" (Kaggle 2018)

## License

This project was built for the **Swin Hackathon 2026** by **Team ClaudeCodeMax**.
