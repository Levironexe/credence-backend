# CreditAI Architecture Diagrams

## 1. System Architecture

```mermaid
graph TB
    subgraph Client["Frontend - Next.js 16 + React 19"]
        UI[Chat Interface]
        DB_FE[Dashboard]
        SSE_Handler[SSE Stream Handler]
    end

    subgraph Auth["Authentication"]
        Google[Google OAuth 2.0]
        NextAuth[NextAuth.js]
    end

    subgraph Backend["Backend - FastAPI"]
        API[REST API + SSE Streaming]

        subgraph Agent["LangGraph Agent - 18 Nodes"]
            Classify[Intent Classifier]
            Pipeline[ML Tool Pipeline]
            ResponseGen[Response Generator]
        end

        subgraph Tools["5 ML Tools"]
            T1["Credit Scoring Model - XGBoost 128 features"]
            T2["SHAP Explainer - TreeSHAP + Waterfall plots"]
            T3["Counterfactual Generator - DiCE-ML + Greedy"]
            T4["Fairness Validator - FairLearn bias detection"]
            T5["Data Completeness Checker - SHAP-weighted ranking"]
        end
    end

    subgraph LLM["LLM Provider"]
        Claude["Claude API - Haiku 4.5 / Sonnet"]
    end

    subgraph Data["Data Layer"]
        Supabase[("Supabase PostgreSQL + pgvector")]
        Models[("ML Model Artifacts - XGBoost, DiCE, SHAP")]
    end

    UI -->|Natural language query| API
    DB_FE -->|Applicant lookup| API
    API -->|SSE events| SSE_Handler
    SSE_Handler --> UI

    Google --> NextAuth
    NextAuth --> API

    API --> Agent
    Agent -->|Tool-use function calling| Claude
    Claude -->|Tool selection| Agent
    Agent --> Tools

    Tools --> Models
    API --> Supabase

    style Client fill:#1a1a2e,stroke:#e94560,color:#fff
    style Backend fill:#16213e,stroke:#0f3460,color:#fff
    style Agent fill:#0f3460,stroke:#533483,color:#fff
    style Tools fill:#533483,stroke:#e94560,color:#fff
    style LLM fill:#2d1b69,stroke:#533483,color:#fff
    style Data fill:#1a1a2e,stroke:#0f3460,color:#fff
```

---

## 2. LangGraph Agent - Node Workflow

```mermaid
graph TD
    START((Start)) --> classify

    classify{{"Classify - LLM intent detection"}}

    classify -->|simple_explanation| simple_response["Simple Response"]
    classify -->|single_tool| single_tool["Single Tool Execution"]
    classify -->|need_more_data| need_data["Need More Data"]
    classify -->|re_assessment| metric_extraction["Metric Extraction - parse user overrides"]
    classify -->|full_assessment| fetch_merchant["Fetch Merchant Data"]

    simple_response --> END1((End))
    single_tool --> END2((End))
    need_data --> END3((End))

    fetch_merchant --> doc_ingestion["Document Ingestion - PDF/Excel parsing"]
    metric_extraction --> data_completeness

    doc_ingestion --> data_completeness{{"Data Completeness - SHAP-weighted gap check"}}

    data_completeness -->|"60%+ complete, has profile"| credit_scoring
    data_completeness -->|"60%+ complete, no profile"| planning
    data_completeness -->|"below 60%"| need_data2["Need More Data"]
    need_data2 --> END4((End))

    planning["Planning - LLM assesses approach"] --> tool_selection

    tool_selection{{"Tool Selection - LLM picks tools"}}
    tool_selection -->|tools selected| execute_tools["Execute Tools"]
    tool_selection -->|no tools needed| credit_scoring

    execute_tools --> shouldContinue{{"Continue?"}}
    shouldContinue -->|more tools needed| tool_selection
    shouldContinue -->|done| credit_scoring

    credit_scoring["Credit Scoring - XGBoost predict, 300-850"]
    credit_scoring --> explainability

    explainability["Explainability - TreeSHAP feature importance"]
    explainability --> fairness_check

    fairness_check{{"Fairness Check - FairLearn bias detection"}}
    fairness_check -->|"score >= 670 approved"| analysis
    fairness_check -->|"score < 670 rejected"| counterfactual

    counterfactual["Counterfactual Generation - DiCE improvement paths"]
    counterfactual --> analysis

    analysis["Analysis - Synthesize all findings"]
    analysis --> responseNode["Response - Format credit report"]
    responseNode --> END5((End))

    style classify fill:#e6a817,stroke:#333,color:#000
    style data_completeness fill:#e6a817,stroke:#333,color:#000
    style tool_selection fill:#e6a817,stroke:#333,color:#000
    style shouldContinue fill:#e6a817,stroke:#333,color:#000
    style fairness_check fill:#e6a817,stroke:#333,color:#000
    style credit_scoring fill:#2d8659,stroke:#333,color:#fff
    style explainability fill:#2d8659,stroke:#333,color:#fff
    style counterfactual fill:#2d8659,stroke:#333,color:#fff
    style planning fill:#4a69bd,stroke:#333,color:#fff
    style analysis fill:#4a69bd,stroke:#333,color:#fff
    style responseNode fill:#4a69bd,stroke:#333,color:#fff
    style fetch_merchant fill:#6c5ce7,stroke:#333,color:#fff
    style doc_ingestion fill:#6c5ce7,stroke:#333,color:#fff
    style metric_extraction fill:#6c5ce7,stroke:#333,color:#fff
    style simple_response fill:#636e72,stroke:#333,color:#fff
    style single_tool fill:#636e72,stroke:#333,color:#fff
    style need_data fill:#636e72,stroke:#333,color:#fff
    style need_data2 fill:#636e72,stroke:#333,color:#fff
```

---

## 3. Credit Assessment Pipeline - What Happens Per Query

```mermaid
sequenceDiagram
    actor LO as Loan Officer
    participant UI as Next.js Frontend
    participant API as FastAPI Backend
    participant Agent as LangGraph Agent
    participant LLM as Claude Haiku 4.5
    participant ML as ML Tools

    LO->>UI: Assess applicant 270000
    UI->>API: POST /api/chat SSE stream
    API->>Agent: Initialize state + messages

    rect rgb(40, 40, 70)
        Note over Agent,LLM: Phase 1 - Classification
        Agent->>LLM: Classify intent via structured output
        LLM-->>Agent: intent full_assessment
        Agent-->>UI: SSE node_start classify
    end

    rect rgb(40, 50, 60)
        Note over Agent,ML: Phase 2 - Data Collection
        Agent->>ML: Fetch applicant profile from DB
        ML-->>Agent: 128-feature profile loaded
        Agent->>ML: Check data completeness
        ML-->>Agent: 87% complete SHAP-weighted
        Agent-->>UI: SSE tool_result data_completeness
    end

    rect rgb(30, 60, 50)
        Note over Agent,ML: Phase 3 - ML Scoring Pipeline
        Agent->>ML: credit_scoring_model features
        ML-->>Agent: P default 0.24 Score 718 Band Good
        Agent-->>UI: SSE tool_result credit_score

        Agent->>ML: shap_explainer features
        ML-->>Agent: Top factors + waterfall plot
        Agent-->>UI: SSE tool_result shap

        Agent->>ML: fairness_validator features score
        ML-->>Agent: No demographic bias detected
        Agent-->>UI: SSE tool_result fairness
    end

    rect rgb(50, 40, 60)
        Note over Agent,LLM: Phase 4 - Report Generation
        Agent->>LLM: Synthesize findings into report
        LLM-->>Agent: Structured credit report
        Agent-->>UI: SSE text streaming response
    end

    UI-->>LO: Credit Analysis Report with score factors recommendation
```

---

## 4. Explainability Stack - From Score to Actionable Guidance

```mermaid
graph LR
    subgraph Input["Applicant Data"]
        Raw["128 Features - Home Credit Dataset"]
    end

    subgraph Scoring["Credit Scoring"]
        XGB["XGBoost - Predict P default"]
        Map["Score Mapping - 850 minus P x 550"]
    end

    subgraph Explain["Explainability"]
        SHAP["TreeSHAP - Per-feature contributions"]
        WF["Waterfall Plot - base64 PNG"]
    end

    subgraph Fairness["Fairness Validation"]
        FL["FairLearn - Disparate impact, Equalized odds, Chi-squared"]
    end

    subgraph Counter["Counterfactual Generation"]
        DICE["DiCE-ML - Genetic algorithm"]
        GreedyOpt["Greedy Optimizer - Effort-ranked fallback"]
        Paths["3 Improvement Paths - Easiest first"]
    end

    subgraph Decision["Lending Decision"]
        D1["800-850: Auto-approve"]
        D2["740-799: Approve"]
        D3["670-739: Approve with conditions"]
        D4["580-669: Manual review"]
        D5["300-579: Decline + guidance"]
    end

    Raw --> XGB
    XGB --> Map
    Map --> Decision

    Raw --> SHAP
    SHAP --> WF

    Raw --> FL
    Map --> FL

    Raw --> DICE
    DICE -->|no solution| GreedyOpt
    DICE -->|found| Paths
    GreedyOpt --> Paths

    style Input fill:#2c3e50,stroke:#ecf0f1,color:#fff
    style Scoring fill:#27ae60,stroke:#ecf0f1,color:#fff
    style Explain fill:#2980b9,stroke:#ecf0f1,color:#fff
    style Fairness fill:#8e44ad,stroke:#ecf0f1,color:#fff
    style Counter fill:#d35400,stroke:#ecf0f1,color:#fff
    style Decision fill:#c0392b,stroke:#ecf0f1,color:#fff
```

---

## 5. Real-Time Streaming Architecture - SSE Event Flow

```mermaid
graph LR
    subgraph BE["FastAPI Backend"]
        LG[LangGraph Agent]
        E1["node_start event"]
        E2["reasoning event"]
        E3["tool_call event"]
        E4["tool_result event"]
        E5["text event"]
        LG --> E1
        LG --> E2
        LG --> E3
        LG --> E4
        LG --> E5
    end

    subgraph Transport["SSE Transport"]
        SSE["Server-Sent Events - data JSON newline newline"]
    end

    subgraph FE["Next.js Frontend"]
        Handler[SSE Event Handler]
        Parts["Unified Parts Array"]
        R1["Node indicator badge"]
        R2["Reasoning block collapsible"]
        R3["Tool call collapsed"]
        R4["Tool result expandable"]
        R5["Text response streamed"]

        Handler --> Parts
        Parts --> R1
        Parts --> R2
        Parts --> R3
        Parts --> R4
        Parts --> R5
    end

    E1 --> SSE
    E2 --> SSE
    E3 --> SSE
    E4 --> SSE
    E5 --> SSE
    SSE --> Handler

    style BE fill:#1e3a5f,stroke:#5dade2,color:#fff
    style Transport fill:#2c3e50,stroke:#f39c12,color:#fff
    style FE fill:#1a1a2e,stroke:#e94560,color:#fff
```

---

## 6. Data Flow - From Loan Officer to Decision

```mermaid
graph TD
    subgraph User["Loan Officer"]
        Q["Can this applicant get a 5000 dollar loan?"]
    end

    subgraph Ingestion["Data Ingestion"]
        NL["Natural Language Parsing"]
        Profile["Applicant Profile Lookup - 46K profiles"]
        Doc["Document Upload - PDF/Excel"]
    end

    subgraph QualityCheck["Data Quality"]
        DC["Data Completeness Checker"]
        Missing["Missing: loan_amount, dependents"]
        Fill["Median-impute optional fields"]
        DC --> Missing
        DC --> Fill
    end

    subgraph MLPipeline["ML Pipeline"]
        FE["128 Features - Home Credit Schema"]
        XGB["XGBoost - Trained on 307K samples"]
        ScoreOut["Credence Score 300-850"]
    end

    subgraph XAI["Explainability Layer"]
        S["SHAP - Top risk factors with contribution points"]
        F["Fairness - Gender age bias detection"]
        CF["Counterfactuals - Reduce loan to 4K or wait 4 months"]
    end

    subgraph Output["Decision Output"]
        Report["Credit Report - Score + Factors + Recommendation + Improvement paths"]
    end

    Q --> NL
    NL --> Profile
    NL --> Doc
    Profile --> DC
    Doc --> DC
    Fill --> FE
    FE --> XGB
    XGB --> ScoreOut
    ScoreOut --> S
    ScoreOut --> F
    ScoreOut -->|score below 670| CF
    S --> Report
    F --> Report
    CF --> Report

    style User fill:#2c3e50,stroke:#ecf0f1,color:#fff
    style Ingestion fill:#1e3a5f,stroke:#ecf0f1,color:#fff
    style QualityCheck fill:#1a472a,stroke:#ecf0f1,color:#fff
    style MLPipeline fill:#27ae60,stroke:#ecf0f1,color:#fff
    style XAI fill:#6c3483,stroke:#ecf0f1,color:#fff
    style Output fill:#c0392b,stroke:#ecf0f1,color:#fff
```
