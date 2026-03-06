# Implementation Roadmap: Credence AI → Production-Grade

**Version**: 1.0
**Date**: 2026-02-26
**Goal**: Close the 1.64-point gap to reach 8.86/10 (97% of Cyber LLM SOC quality)
**Timeline**: 10 weeks (phased approach)

---

## Overview

This roadmap transforms Credence AI from a **7.22/10 academic project** into an **8.86/10 production-grade cybersecurity platform** by implementing:
- ✅ 12 missing cybersecurity tools (100% completion)
- ✅ Multi-agent architecture (G2 requirement)
- ✅ Critical security hardening
- ✅ Production observability
- ✅ Comprehensive documentation

---

## Phase 1: Critical Security (Weeks 1-2)

**Goal**: Fix CRITICAL security vulnerabilities
**Impact**: +0.15 points (Engineering Maturity: 6.33 → 7.5)

### Task 1.1: Enable CSRF Protection

**Current State**: CSRF protection is **disabled** (noted in code comments)
**Target State**: Full CSRF validation like Cyber LLM SOC

**Implementation**:
```python
# app/routers/auth.py
from itsdangerous import URLSafeTimedSerializer

def generate_csrf_state(session_id: str) -> str:
    """Generate cryptographically secure CSRF state token"""
    serializer = URLSafeTimedSerializer(settings.secret_key)
    return serializer.dumps({
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat()
    })

def validate_csrf_state(state: str, session_id: str, max_age: int = 600) -> bool:
    """Validate CSRF state token (10 min expiry)"""
    try:
        serializer = URLSafeTimedSerializer(settings.secret_key)
        data = serializer.loads(state, max_age=max_age)
        return data["session_id"] == session_id
    except Exception:
        return False

# Update OAuth flow to use state parameter
```

**Files to Modify**:
- `app/routers/auth.py` (add CSRF state generation/validation)
- `app/config.py` (add CSRF settings)

**Success Criteria**:
- All OAuth requests include `state` parameter
- State validation fails for mismatched/expired tokens
- No session hijacking possible

---

### Task 1.2: Implement Rate Limiting

**Current State**: Configured but **not enforced**
**Target State**: Token bucket algorithm like Cyber LLM SOC

**Implementation**:
```python
# app/middleware/rate_limiter.py
from collections import defaultdict
from datetime import datetime, timedelta

class TokenBucketRateLimiter:
    """Token bucket rate limiter (10 requests/min per IP)"""

    def __init__(self, capacity: int = 10, refill_rate: float = 10/60):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.buckets = defaultdict(lambda: {
            "tokens": capacity,
            "last_refill": datetime.utcnow()
        })

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is allowed"""
        now = datetime.utcnow()
        bucket = self.buckets[client_ip]

        # Refill tokens
        elapsed = (now - bucket["last_refill"]).total_seconds()
        bucket["tokens"] = min(
            self.capacity,
            bucket["tokens"] + elapsed * self.refill_rate
        )
        bucket["last_refill"] = now

        # Consume token
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        return False

# Middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": 60}
        )
    return await call_next(request)
```

**Files to Modify**:
- Create `app/middleware/rate_limiter.py`
- `app/main.py` (add middleware)
- `app/config.py` (add rate limit settings)

**Success Criteria**:
- 11th request in 60 seconds returns 429
- Rate limits reset after 60 seconds
- Per-IP tracking works correctly

---

### Task 1.3: Add Prompt Injection Detection

**Current State**: No protection against prompt injection attacks
**Target State**: Pre-execution blocking like Cyber LLM SOC

**Implementation**:
```python
# app/utils/input_validator.py
_PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all prior",
    "system prompt",
    "developer message",
    "reveal hidden instructions",
    "bypass policy",
    "disable guardrails",
    "you are now",
    "new instructions",
    "disregard above",
    "forget everything",
    "act as if"
)

def detect_prompt_injection(user_input: str) -> tuple[bool, str | None]:
    """
    Detect prompt injection attempts.

    Returns:
        (is_safe, detected_marker)
    """
    lower_input = user_input.lower()
    for marker in _PROMPT_INJECTION_MARKERS:
        if marker in lower_input:
            return (False, marker)
    return (True, None)

# app/routers/chat.py
async def stream_chat_response(...):
    # Validate input before processing
    is_safe, marker = detect_prompt_injection(user_message_text)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail=f"Potentially unsafe input detected: {marker}"
        )
```

**Files to Modify**:
- Create `app/utils/input_validator.py`
- `app/routers/chat.py` (add validation before LLM call)

**Success Criteria**:
- Requests with "ignore previous instructions" are blocked
- Safe requests pass through
- Clear error messages for users

---

### Task 1.4: Add Input Sanitization

**Implementation**:
```python
# app/utils/input_validator.py
import re

def sanitize_input(text: str, max_length: int = 50000) -> str:
    """
    Sanitize user input:
    - Strip control characters
    - Normalize whitespace
    - Enforce size limits
    """
    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    # Normalize whitespace
    text = ' '.join(text.split())

    # Enforce size limit
    if len(text) > max_length:
        raise ValueError(f"Input too long ({len(text)} > {max_length} chars)")

    return text
```

**Files to Modify**:
- `app/utils/input_validator.py` (add sanitization)
- All input handlers (chat, document, file upload)

---

### Task 1.5: Implement Output Content Policy

**Implementation**:
```python
# app/utils/output_guard.py
_OUTPUT_POLICY_DENYLIST = (
    "BEGIN PRIVATE KEY",
    "OPENAI_API_KEY=",
    "ANTHROPIC_API_KEY=",
    "authorization: bearer ",
    "password:",
    "how to weaponize",
    "drop table users",
    "rm -rf /",
    "eval(request.body)"
)

def validate_output_safety(response: str) -> tuple[bool, str | None]:
    """
    Check if LLM response violates content policy.

    Returns:
        (is_safe, violation_reason)
    """
    lower_response = response.lower()
    for banned_pattern in _OUTPUT_POLICY_DENYLIST:
        if banned_pattern.lower() in lower_response:
            return (False, f"Content policy violation: {banned_pattern}")
    return (True, None)
```

**Files to Modify**:
- Create `app/utils/output_guard.py`
- `app/ai/langgraph_agent.py` (validate before returning response)

---

**Phase 1 Deliverables**:
- ✅ CSRF protection enabled
- ✅ Rate limiting enforced (10 req/min per IP)
- ✅ Prompt injection detection (12+ markers)
- ✅ Input sanitization (control chars, size limits)
- ✅ Output content policy (secrets, weaponization)

**Phase 1 Estimated Effort**: 16-20 hours

---

## Phase 2: Complete Missing Tools (Weeks 3-4)

**Goal**: Implement 12 remaining cybersecurity tools
**Impact**: +1.10 points (Features: 6.75 → 9.5)

### Task 2.1: Replace Demo Data with Real APIs

#### IP Reputation Checker (Replace Hardcoded Data)

**Current State**: Only recognizes 5 hardcoded IPs
**Target State**: Real API integration (AbuseIPDB or VirusTotal)

**Option A: AbuseIPDB (Recommended)**
```python
# app/tools/detection/ip_reputation_checker.py
import requests
from typing import Dict, Any

class IPReputationChecker(BaseTool):
    name = "ip_reputation_checker"

    def __init__(self):
        self.api_key = settings.abuseipdb_api_key
        self.base_url = "https://api.abuseipdb.com/api/v2"

    @log_tool_execution("ip_reputation_checker")
    async def execute(self, **kwargs) -> Dict[str, Any]:
        input_data = IPReputationInput(**kwargs)

        headers = {
            "Key": self.api_key,
            "Accept": "application/json"
        }
        params = {
            "ipAddress": input_data.ip_address,
            "maxAgeInDays": 90
        }

        try:
            response = requests.get(
                f"{self.base_url}/check",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()["data"]

            return {
                "ip": input_data.ip_address,
                "is_malicious": data["abuseConfidenceScore"] > 50,
                "abuse_score": data["abuseConfidenceScore"],
                "total_reports": data["totalReports"],
                "last_reported": data["lastReportedAt"],
                "usage_type": data.get("usageType", "Unknown"),
                "country": data.get("countryCode", "Unknown")
            }
        except Exception as e:
            # Fallback to basic validation
            return self._fallback_validation(input_data.ip_address)
```

**Files to Modify**:
- `app/tools/detection/ip_reputation_checker.py` (replace hardcoded logic)
- `app/config.py` (add `ABUSEIPDB_API_KEY`)
- `.env.example` (document API key)

**Free Tier**: 1,000 requests/day

---

#### CVE Lookup (Replace Hardcoded Data)

**Current State**: Only knows 3 CVEs
**Target State**: NVD API integration

**Implementation**:
```python
# app/tools/cti_enrichment/cve_lookup.py
import requests
from typing import Dict, Any

class CVELookup(BaseTool):
    name = "cve_lookup"

    def __init__(self):
        self.base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    @log_tool_execution("cve_lookup")
    async def execute(self, **kwargs) -> Dict[str, Any]:
        input_data = CVELookupInput(**kwargs)

        params = {"cveId": input_data.cve_id}

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()

            if data["totalResults"] == 0:
                return {"error": f"CVE {input_data.cve_id} not found"}

            vuln = data["vulnerabilities"][0]["cve"]

            # Extract CVSS score
            metrics = vuln.get("metrics", {})
            cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})

            return {
                "cve_id": input_data.cve_id,
                "description": vuln["descriptions"][0]["value"],
                "severity": cvss_v3.get("baseSeverity", "Unknown"),
                "cvss_score": cvss_v3.get("baseScore", 0.0),
                "vector_string": cvss_v3.get("vectorString", ""),
                "published_date": vuln["published"],
                "last_modified": vuln["lastModified"],
                "references": [ref["url"] for ref in vuln.get("references", [])][:3]
            }
        except Exception as e:
            return {"error": f"CVE lookup failed: {str(e)}"}
```

**Free Tier**: No API key required (rate limited to 5 requests/30 seconds)

---

### Task 2.2: Add CTI Integration (AlienVault OTX)

**New Tool**: Cyber Threat Intelligence Fetcher

**Implementation**:
```python
# app/tools/cti_enrichment/cti_fetcher.py
from OTXv2 import OTXv2
from typing import Dict, Any, List

class CTIFetcherInput(BaseModel):
    query_type: str  # "threat_type" or "ioc"
    query_value: str  # e.g., "ransomware" or "192.168.1.1"

class CTIFetcher(BaseTool):
    """Fetch threat intelligence from AlienVault OTX"""

    name = "cti_fetcher"
    needs_approval = False

    def __init__(self):
        self.otx = OTXv2(settings.otx_api_key)

    def description(self) -> str:
        return """Fetches cyber threat intelligence from AlienVault OTX.
        Supports threat types (ransomware, phishing, ddos) and IOC queries (ip, domain, hash)."""

    def input_schema(self) -> type[BaseModel]:
        return CTIFetcherInput

    @log_tool_execution("cti_fetcher")
    async def execute(self, **kwargs) -> Dict[str, Any]:
        input_data = CTIFetcherInput(**kwargs)

        try:
            if input_data.query_type == "ip":
                result = self.otx.get_indicator_details_full(
                    OTXv2.IndicatorTypes.IPv4,
                    input_data.query_value
                )
                return self._format_ip_result(result)

            elif input_data.query_type == "domain":
                result = self.otx.get_indicator_details_full(
                    OTXv2.IndicatorTypes.DOMAIN,
                    input_data.query_value
                )
                return self._format_domain_result(result)

            elif input_data.query_type == "threat_type":
                pulses = self.otx.search_pulses(input_data.query_value)
                return self._format_threat_pulses(pulses)

            else:
                return {"error": f"Unknown query type: {input_data.query_type}"}

        except Exception as e:
            # Fallback mode
            return self._fallback_cti_report(input_data.query_value)

    def _fallback_cti_report(self, query: str) -> Dict[str, Any]:
        """Deterministic fallback when OTX unavailable"""
        return {
            "source": "fallback",
            "query": query,
            "observations": [
                f"CTI service unavailable for {query}",
                "Using baseline threat assessment"
            ],
            "recommended_actions": [
                "Monitor for similar activity",
                "Check internal logs for related events"
            ],
            "confidence": "low"
        }
```

**Dependencies**: `pip install OTXv2`

**Files to Create**:
- `app/tools/cti_enrichment/cti_fetcher.py`

**Files to Modify**:
- `app/config.py` (add `OTX_API_KEY`)
- `app/ai/langgraph_agent.py` (register tool)
- `.env.example` (document API key)

**Free Tier**: Unlimited (requires free account)

---

### Task 2.3: Add RAG Retrieval Tool

**New Tool**: Knowledge Base Retriever

**Implementation**:
```python
# app/tools/knowledge/rag_retriever.py
from pathlib import Path
from typing import List, Dict, Any
import re

class RAGRetrieverInput(BaseModel):
    query: str
    top_k: int = 3

class RAGRetriever(BaseTool):
    """Retrieve relevant knowledge from local knowledge base"""

    name = "rag_retriever"
    needs_approval = False

    def __init__(self):
        self.knowledge_dir = Path("data/knowledge")
        self.index = self._build_index()

    def _build_index(self) -> Dict[str, List[Dict[str, str]]]:
        """Build simple lexical index of knowledge chunks"""
        index = {}

        for file_path in self.knowledge_dir.glob("**/*.md"):
            with open(file_path, "r") as f:
                content = f.read()

            # Split into chunks (by heading)
            chunks = re.split(r'\n## ', content)
            for i, chunk in enumerate(chunks):
                chunk_id = f"{file_path.stem}_chunk_{i}"
                index[chunk_id] = {
                    "text": chunk,
                    "source": str(file_path.relative_to(self.knowledge_dir)),
                    "chunk_id": chunk_id
                }

        return index

    @log_tool_execution("rag_retriever")
    async def execute(self, **kwargs) -> Dict[str, Any]:
        input_data = RAGRetrieverInput(**kwargs)

        # Simple lexical matching (can upgrade to embeddings later)
        query_terms = set(input_data.query.lower().split())

        scored_chunks = []
        for chunk_id, chunk_data in self.index.items():
            chunk_terms = set(chunk_data["text"].lower().split())
            score = len(query_terms & chunk_terms)  # Overlap count
            if score > 0:
                scored_chunks.append((score, chunk_data))

        # Sort by score and take top_k
        top_chunks = sorted(scored_chunks, reverse=True)[:input_data.top_k]

        return {
            "query": input_data.query,
            "results": [
                {
                    "text": chunk["text"][:500],  # Truncate for context
                    "source": chunk["source"],
                    "chunk_id": chunk["chunk_id"],
                    "relevance_score": score
                }
                for score, chunk in top_chunks
            ],
            "total_results": len(top_chunks)
        }
```

**Setup**:
```bash
mkdir -p data/knowledge
# Add markdown files with security best practices, MITRE ATT&CK docs, etc.
```

**Files to Create**:
- `app/tools/knowledge/rag_retriever.py`
- `data/knowledge/mitre_attack.md` (download MITRE framework docs)
- `data/knowledge/owasp_top10.md`
- `data/knowledge/incident_response_playbooks.md`

---

### Task 2.4: Implement Remaining 9 Tools

#### Detection Tools

**1. ML Classifier**
```python
# app/tools/detection/ml_classifier.py
from sklearn.ensemble import IsolationForest
import numpy as np

class MLClassifier(BaseTool):
    """Anomaly detection using Isolation Forest"""

    def execute(self, **kwargs):
        # Train on normal behavior patterns
        # Detect outliers in new events
        pass
```

**2. Time Series Analyzer**
```python
# app/tools/detection/time_series_analyzer.py
import pandas as pd

class TimeSeriesAnalyzer(BaseTool):
    """Detect trends and anomalies in time-series logs"""

    def execute(self, **kwargs):
        # Rolling averages, spike detection
        pass
```

#### CTI Enrichment Tools

**3. MISP Connector**
```python
# app/tools/cti_enrichment/misp_connector.py
from pymisp import PyMISP

class MISPConnector(BaseTool):
    """Connect to MISP threat intelligence platform"""
    pass
```

**4. STIX/TAXII Parser**
```python
# app/tools/cti_enrichment/stix_parser.py
from stix2 import parse

class STIXParser(BaseTool):
    """Parse STIX threat intelligence feeds"""
    pass
```

#### Correlation Tools

**5. Network Graph Correlator**
```python
# app/tools/correlation/network_graph_correlator.py
import networkx as nx

class NetworkGraphCorrelator(BaseTool):
    """Build attack graphs from correlated events"""

    def execute(self, **kwargs):
        # Create graph of IPs, processes, files
        # Identify attack paths
        pass
```

#### Incident Response Tools

**6. Firewall Rule Generator**
```python
# app/tools/incident_response/firewall_rule_gen.py
class FirewallRuleGenerator(BaseTool):
    """Generate firewall rules to block threats"""

    def execute(self, **kwargs):
        # Generate iptables, AWS Security Group rules
        pass
```

**7. Notification Sender**
```python
# app/tools/incident_response/notification_sender.py
import smtplib
from slack_sdk import WebClient

class NotificationSender(BaseTool):
    """Send alerts via email, Slack, PagerDuty"""
    pass
```

**8. Report Generator**
```python
# app/tools/incident_response/report_generator.py
from jinja2 import Template

class ReportGenerator(BaseTool):
    """Generate executive summary reports"""

    def execute(self, **kwargs):
        # Use Jinja2 templates for PDF/HTML reports
        pass
```

#### Log Ingestion Tools

**9. Integrate log_normalizer.py**
- Install `watchdog` library
- Register in `langgraph_agent.py`

**10. Integrate streaming_ingestor.py**
- Import in `langgraph_agent.py`
- Add to `_register_default_tools()`

---

**Phase 2 Deliverables**:
- ✅ IP reputation with real AbuseIPDB/VirusTotal API
- ✅ CVE lookup with NVD API
- ✅ CTI integration with AlienVault OTX
- ✅ RAG retrieval from local knowledge base
- ✅ 9 additional tools implemented
- ✅ 100% tool completion (22/22 tools)

**Phase 2 Estimated Effort**: 30-40 hours

---

## Phase 3: Multi-Agent Architecture (Weeks 5-7)

**Goal**: Implement G2 requirement (multi-agent workflow)
**Impact**: +0.19 points (Architecture: 7.25 → 8.5)

### Task 3.1: Design 6 Specialized Agents

**Agent Roles** (inspired by Cyber LLM SOC):

1. **LogAnalyzer Agent**
   - Parse logs and identify threats
   - Classify severity (CRITICAL/HIGH/MEDIUM/LOW)
   - Extract IOCs (IPs, domains, hashes)

2. **ThreatPredictor Agent**
   - Forecast attack progression
   - Use CTI to predict next steps
   - Assess likelihood of compromise

3. **IncidentResponder Agent**
   - Create containment plans
   - Generate remediation steps
   - Suggest automated responses

4. **WorkerPlanner Agent**
   - Dynamically spawn specialized tasks
   - Coordinate parallel investigations
   - Manage evidence collection

5. **Verifier Agent**
   - Quality-check responses
   - Validate evidence requirements
   - Ensure completeness

6. **Orchestrator Agent**
   - Consolidate multi-agent outputs
   - Generate executive summary
   - Format final report

---

### Task 3.2: Implement LangGraph Multi-Agent Workflow

**Architecture**:
```python
# app/ai/multiagent_workflow.py
from langgraph.graph import StateGraph
from typing_extensions import TypedDict

class MultiAgentState(TypedDict):
    messages: List[BaseMessage]
    raw_logs: str
    parsed_events: List[Dict[str, Any]]
    threat_assessment: Dict[str, Any]
    incident_plan: Dict[str, Any]
    evidence_collected: List[Dict[str, Any]]
    quality_checks: Dict[str, bool]
    final_report: str

def create_multiagent_workflow() -> StateGraph:
    """Create sequential multi-agent pipeline"""

    workflow = StateGraph(MultiAgentState)

    # Add nodes
    workflow.add_node("log_analyzer", log_analyzer_node)
    workflow.add_node("threat_predictor", threat_predictor_node)
    workflow.add_node("incident_responder", incident_responder_node)
    workflow.add_node("worker_planner", worker_planner_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("orchestrator", orchestrator_node)

    # Sequential edges
    workflow.set_entry_point("log_analyzer")
    workflow.add_edge("log_analyzer", "threat_predictor")
    workflow.add_edge("threat_predictor", "incident_responder")
    workflow.add_edge("incident_responder", "worker_planner")
    workflow.add_edge("worker_planner", "verifier")
    workflow.add_edge("verifier", "orchestrator")
    workflow.add_edge("orchestrator", END)

    return workflow.compile()
```

**Files to Create**:
- `app/ai/multiagent_workflow.py`
- `app/ai/agents/log_analyzer.py`
- `app/ai/agents/threat_predictor.py`
- `app/ai/agents/incident_responder.py`
- `app/ai/agents/worker_planner.py`
- `app/ai/agents/verifier.py`
- `app/ai/agents/orchestrator.py`

---

### Task 3.3: Add Evidence-Based Reasoning

**Implementation**:
```python
# app/ai/agents/verifier.py
EVIDENCE_REQUIREMENTS = {
    "CRITICAL": 3,  # Require 3+ pieces of evidence
    "HIGH": 2,
    "MEDIUM": 1,
    "LOW": 0
}

def verifier_node(state: MultiAgentState) -> MultiAgentState:
    """Verify response quality and evidence"""

    severity = state["threat_assessment"]["severity"]
    required_evidence = EVIDENCE_REQUIREMENTS[severity]
    actual_evidence = len(state["evidence_collected"])

    if actual_evidence < required_evidence:
        # Trigger WorkerPlanner to collect more evidence
        return {
            **state,
            "quality_checks": {
                "evidence_sufficient": False,
                "required": required_evidence,
                "actual": actual_evidence
            }
        }

    return {
        **state,
        "quality_checks": {
            "evidence_sufficient": True,
            "verified": True
        }
    }
```

---

### Task 3.4: Implement Adaptive Model Routing

**Implementation**:
```python
# app/ai/adaptive_router.py
from typing import Literal

def select_model(task_complexity: Literal["simple", "complex"]) -> str:
    """
    Route to fast model (Haiku) or strong model (Sonnet).

    Simple tasks:
    - Log parsing
    - Pattern matching
    - Basic classification

    Complex tasks:
    - Multi-step reasoning
    - Evidence synthesis
    - Executive summaries
    """
    if task_complexity == "simple":
        return "claude-haiku-4-5"  # Fast, cheap
    else:
        return "claude-sonnet-4-5"  # Slower, smarter

# Usage in agents
def log_analyzer_node(state: MultiAgentState):
    llm = ChatAnthropic(model=select_model("simple"))
    # ... parsing logic
```

---

**Phase 3 Deliverables**:
- ✅ 6 specialized agents implemented
- ✅ LangGraph multi-agent workflow (sequential pipeline)
- ✅ Evidence-based reasoning with verification gates
- ✅ Adaptive model routing (Haiku ↔ Sonnet)
- ✅ Quality checks and evidence validation

**Phase 3 Estimated Effort**: 40-50 hours

---

## Phase 4: Production Readiness (Weeks 8-9)

**Goal**: Add observability, monitoring, and deployment features
**Impact**: +0.13 points (Engineering Maturity: 7.5 → 9.0)

### Task 4.1: Add OpenAPI Documentation

**Implementation**:
```python
# app/main.py
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Credence AI - Cybersecurity Agent API",
    description="LLM-powered autonomous cybersecurity investigation platform",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc UI
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Credence AI API",
        version="1.0.0",
        description="""
        # Credence AI - Cybersecurity Agent API

        ## Features
        - Multi-agent threat analysis
        - 22 cybersecurity tools
        - Real-time CTI integration
        - Evidence-based reasoning

        ## Authentication
        - OAuth 2.0 (Google)
        - Session-based auth

        ## Rate Limits
        - 10 requests/minute per IP
        """,
        routes=app.routes,
    )

    openapi_schema["info"]["x-logo"] = {
        "url": "https://yourlogo.png"
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

**Enhance Schemas**:
```python
# app/schemas/chat.py
class ChatRequest(BaseModel):
    """
    Chat request with message and optional context.

    Example:
        ```json
        {
          "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "Analyze this log..."}]
          },
          "selectedChatModel": "agent/cyber-analyst"
        }
        ```
    """
    message: Optional[MessageInput] = Field(
        None,
        description="Single message to send",
        example={"role": "user", "parts": [{"type": "text", "text": "Hello"}]}
    )
    # ... other fields with descriptions and examples
```

**Files to Modify**:
- `app/main.py` (enable OpenAPI)
- All `app/schemas/*.py` (add field descriptions and examples)
- All routers (add endpoint descriptions)

---

### Task 4.2: Add Health/Readiness Endpoints

**Implementation**:
```python
# app/routers/health.py
from fastapi import APIRouter, status
from typing import Dict, Any

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for load balancer.

    Returns 200 if service is running (doesn't check dependencies).
    """
    return {"status": "healthy"}

@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness check for Kubernetes.

    Checks:
    - Database connection
    - LLM API reachability
    - Required environment variables

    Returns 200 only if all checks pass.
    """
    checks = {
        "database": False,
        "llm_api": False,
        "config": False
    }

    # Check database
    try:
        await db.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        pass

    # Check LLM API (lightweight ping)
    try:
        # Quick API key validation
        checks["llm_api"] = bool(settings.anthropic_api_key)
    except Exception:
        pass

    # Check config
    checks["config"] = all([
        settings.secret_key,
        settings.database_url
    ])

    all_ready = all(checks.values())

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks
    }
```

**Files to Create**:
- `app/routers/health.py`

**Files to Modify**:
- `app/main.py` (include router)

---

### Task 4.3: Add Metrics Dashboard

**Implementation**:
```python
# app/utils/metrics.py
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any

class MetricsCollector:
    """In-memory metrics collector (use Redis/Prometheus for production)"""

    def __init__(self):
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.latencies = []
        self.tool_calls = defaultdict(int)
        self.recent_runs = []

    def record_request(self, endpoint: str, latency: float, status: str):
        self.request_counts[endpoint] += 1
        if status == "error":
            self.error_counts[endpoint] += 1
        self.latencies.append(latency)

    def record_tool_call(self, tool_name: str, success: bool):
        self.tool_calls[f"{tool_name}_{'success' if success else 'failure'}"] += 1

    def get_dashboard(self) -> Dict[str, Any]:
        return {
            "total_requests": sum(self.request_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "avg_latency_ms": sum(self.latencies) / len(self.latencies) if self.latencies else 0,
            "tool_calls": dict(self.tool_calls),
            "recent_runs": self.recent_runs[-200:]  # Last 200
        }

metrics = MetricsCollector()

# app/routers/metrics.py
@router.get("/api/v1/metrics/dashboard")
async def metrics_dashboard():
    """Real-time metrics dashboard"""
    return metrics.get_dashboard()
```

---

### Task 4.4: Add Budget Guards

**Implementation**:
```python
# app/config.py
class Settings(BaseSettings):
    # ... existing settings

    # Budget limits
    MAX_AGENT_STEPS: int = 12
    MAX_TOOL_CALLS: int = 8
    MAX_RUNTIME_SECONDS: int = 60
    MAX_WORKER_TASKS: int = 4

# app/ai/langgraph_agent.py
from app.config import settings
import time

class AgentBudgetExceeded(Exception):
    pass

def tool_execution_node(state: CyberSecurityState) -> CyberSecurityState:
    start_time = time.time()
    step_count = len(state.get("investigation_steps", []))
    tool_calls = len(state.get("tools_used", []))

    # Check budget
    if step_count >= settings.MAX_AGENT_STEPS:
        raise AgentBudgetExceeded(f"Max steps exceeded: {step_count}")

    if tool_calls >= settings.MAX_TOOL_CALLS:
        raise AgentBudgetExceeded(f"Max tool calls exceeded: {tool_calls}")

    if (time.time() - start_time) > settings.MAX_RUNTIME_SECONDS:
        raise AgentBudgetExceeded("Max runtime exceeded")

    # ... execute tool
```

---

### Task 4.5: Add Correlation IDs for Logging

**Implementation**:
```python
# app/middleware/correlation_id.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        correlation_id_var.set(correlation_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

# app/utils/structured_logger.py
def log_with_correlation(message: str, **kwargs):
    correlation_id = correlation_id_var.get()
    logger.info(message, extra={"correlation_id": correlation_id, **kwargs})
```

---

**Phase 4 Deliverables**:
- ✅ OpenAPI/Swagger documentation at `/docs`
- ✅ Health endpoint (`/health`)
- ✅ Readiness endpoint (`/ready`)
- ✅ Metrics dashboard (`/api/v1/metrics/dashboard`)
- ✅ Budget guards (max steps, max tools, max runtime)
- ✅ Correlation IDs in all logs

**Phase 4 Estimated Effort**: 20-30 hours

---

## Phase 5: Documentation & Polish (Week 10)

**Goal**: Production-grade documentation
**Impact**: +0.28 points (Documentation: 6.25 → 9.0)

### Task 5.1: Create .env.example

**Implementation**:
```bash
# .env.example
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/credence_ai

# LLM Providers
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
GOOGLE_API_KEY=xxx

# Threat Intelligence
OTX_API_KEY=xxx  # AlienVault OTX (free)
ABUSEIPDB_API_KEY=xxx  # AbuseIPDB (free tier: 1000/day)

# OAuth
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx

# Security
SECRET_KEY=your-secret-key-here-change-in-production
CSRF_SECRET=your-csrf-secret-here

# Server
ENVIRONMENT=development  # development | staging | production
PORT=8000

# Rate Limiting
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60

# Agent Settings
MAX_AGENT_STEPS=12
MAX_TOOL_CALLS=8
MAX_RUNTIME_SECONDS=60
```

---

### Task 5.2: Write Deployment Guide

**File**: `docs/DEPLOYMENT_GUIDE.md`

**Contents**:
- Prerequisites (Python 3.10+, PostgreSQL, Redis)
- Local development setup
- Docker deployment
- Render.com deployment
- Vercel deployment (frontend)
- Environment variable configuration
- Database migration steps
- Health check verification
- Troubleshooting common issues

---

### Task 5.3: Add Architecture Diagrams

**File**: `docs/ARCHITECTURE.md`

**Diagrams to Create** (using Mermaid):
1. System architecture (frontend ↔ backend ↔ database ↔ LLM APIs)
2. Multi-agent workflow (sequential pipeline)
3. Request flow (user → API → agent → tools → response)
4. Database schema (users, chats, messages, documents)

Example:
```mermaid
graph TD
    A[User] -->|HTTPS| B[Next.js Frontend]
    B -->|SSE Stream| C[FastAPI Backend]
    C -->|Query| D[PostgreSQL]
    C -->|Invoke| E[LangGraph Agent]
    E -->|Select| F[LogAnalyzer]
    F -->|Next| G[ThreatPredictor]
    G -->|Next| H[IncidentResponder]
    H -->|Next| I[Verifier]
    I -->|Next| J[Orchestrator]
    E -->|Call| K[Tools]
    K -->|CTI| L[AlienVault OTX]
    K -->|IP Rep| M[AbuseIPDB]
    K -->|CVE| N[NVD API]
```

---

### Task 5.4: Create Production Runbook

**File**: `docs/PRODUCTION_RUNBOOK.md`

**Sections**:
- Monitoring setup (Datadog, Prometheus)
- Alerting rules (error rate >5%, latency >2s)
- Incident response procedures
- Scaling guidelines (horizontal/vertical)
- Database backup/restore
- Log aggregation (CloudWatch, Loki)
- Performance tuning
- Security audit checklist

---

**Phase 5 Deliverables**:
- ✅ `.env.example` with all configuration options
- ✅ `DEPLOYMENT_GUIDE.md` with step-by-step instructions
- ✅ `ARCHITECTURE.md` with Mermaid diagrams
- ✅ `PRODUCTION_RUNBOOK.md` for operations

**Phase 5 Estimated Effort**: 15-20 hours

---

## Success Metrics

### Quantitative Targets

| Metric | Current | Target | Gap Closed |
|--------|---------|--------|------------|
| **Overall Score** | 7.22/10 | 8.86/10 | 1.64 points |
| Features Score | 6.75/10 | 9.5/10 | +2.75 |
| Architecture Score | 7.25/10 | 8.5/10 | +1.25 |
| Code Quality Score | 6.6/10 | 8.5/10 | +1.9 |
| Documentation Score | 6.25/10 | 9.0/10 | +2.75 |
| Engineering Maturity Score | 6.33/10 | 9.0/10 | +2.67 |
| **Tool Completion** | 10/22 (45%) | 22/22 (100%) | +55% |
| **Security Gaps** | 7 critical | 0 critical | 100% |

### Qualitative Goals

- ✅ Pass security audit (CSRF, rate limiting, input validation)
- ✅ Achieve G2 requirement (multi-agent system functional)
- ✅ Production-ready deployment (Docker, health checks, monitoring)
- ✅ Complete API documentation (OpenAPI at `/docs`)
- ✅ 100% tool functionality (no demo data)

---

## Timeline Overview

| Phase | Duration | Effort | Deliverables |
|-------|----------|--------|--------------|
| Phase 1: Security | Weeks 1-2 | 16-20h | CSRF, rate limiting, input validation, output guards |
| Phase 2: Tools | Weeks 3-4 | 30-40h | 12 missing tools, real APIs (CTI, IP, CVE, RAG) |
| Phase 3: Multi-Agent | Weeks 5-7 | 40-50h | 6 agents, LangGraph workflow, evidence-based reasoning |
| Phase 4: Production | Weeks 8-9 | 20-30h | OpenAPI, health checks, metrics, budget guards |
| Phase 5: Documentation | Week 10 | 15-20h | .env.example, deployment guide, architecture diagrams |
| **TOTAL** | **10 weeks** | **121-160h** | **Complete production-grade system** |

---

## Risk Mitigation

### High-Risk Items

1. **Multi-Agent Complexity** (Phase 3)
   - **Risk**: LangGraph multi-agent workflow is complex
   - **Mitigation**: Start with 2-agent prototype, incrementally add agents
   - **Fallback**: Keep single-agent mode as backup

2. **External API Dependencies** (Phase 2)
   - **Risk**: OTX, AbuseIPDB, NVD APIs may have rate limits or downtime
   - **Mitigation**: Implement fallback modes (like Cyber LLM SOC)
   - **Fallback**: Use cached/demo data when APIs unavailable

3. **Rate Limiting Implementation** (Phase 1)
   - **Risk**: In-memory rate limiting won't scale horizontally
   - **Mitigation**: Document Redis-based rate limiting for future
   - **Fallback**: Accept single-instance limitation for now

---

## Post-Roadmap: Future Enhancements

**Not included in 10-week plan** (can be added later):

1. **Testing Suite** (if needed)
   - Pytest unit tests for all tools
   - Integration tests for multi-agent workflows
   - Coverage target: 60-80%

2. **Database Migration**
   - Replace JSONL persistence with PostgreSQL for sessions
   - Add read replicas for scalability

3. **Horizontal Scaling**
   - Redis-based rate limiting
   - Distributed agent cache
   - Load balancer configuration

4. **Advanced Monitoring**
   - Prometheus metrics export
   - Grafana dashboards
   - Sentry error tracking

5. **UI Enhancements**
   - Real-time trace visualization (like Cyber LLM SOC's live monitor)
   - Workflow progress indicators
   - Interactive evidence browser

---

## Conclusion

This roadmap closes the 1.64-point gap between Credence AI (7.22/10) and Cyber LLM SOC (9.0/10) by systematically addressing:

1. **Critical Security Vulnerabilities** (CSRF, rate limiting, injection defense)
2. **Feature Completeness** (22/22 tools with real API integrations)
3. **Multi-Agent Architecture** (G1 + G2 both fully functional)
4. **Production Readiness** (OpenAPI, health checks, metrics, budget guards)
5. **Professional Documentation** (deployment guides, architecture diagrams, runbooks)

**Estimated Total Effort**: 121-160 hours over 10 weeks

**Final Projected Score**: 8.86/10 (97% of Cyber LLM SOC quality)

**Key Success Factor**: Focus on security (Phase 1) and tools (Phase 2) first, as these provide the highest ROI. Multi-agent architecture (Phase 3) is impressive but can be deferred if timeline is tight.
