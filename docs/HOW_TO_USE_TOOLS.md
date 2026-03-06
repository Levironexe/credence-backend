# How to Use the Integrated Cybersecurity Tools

**Status**: ✅ 10 tools integrated and ready to use
**Date**: February 25, 2026

---

## 🚀 Quick Start

### 1. Start the Server
```bash
cd /Users/leviron/Major/COS30018/project/credence-ai-backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### 2. Open the Chat Interface
Navigate to your frontend (usually `http://localhost:3000` or similar)

### 3. Start Asking Cybersecurity Questions!

The agent will **automatically** select and use the appropriate tools based on your query.

---

## 💬 Example Prompts to Try

### 🔍 **Detection & Analysis**

#### Test 1: SQL Injection Detection
```
User: "Analyze this log: admin' OR '1'='1'; DROP TABLE users; --"
```
**Expected Tools Used**: `signature_detector`
**What Happens**: Detects SQL injection patterns, reports severity as CRITICAL

#### Test 2: Multiple Threat Detection
```
User: "Check this log for threats: <script>alert('XSS')</script> and SELECT * FROM users--"
```
**Expected Tools Used**: `signature_detector`
**What Happens**: Detects both XSS and SQLi, lists all findings

#### Test 3: Brute Force Detection
```
User: "Analyze: Failed login attempt 15/20 for user admin from 192.168.1.100"
```
**Expected Tools Used**: `signature_detector`, possibly `ip_reputation_checker`
**What Happens**: Identifies brute force attack pattern

---

### 🗺️ **Threat Intelligence**

#### Test 4: MITRE ATT&CK Mapping
```
User: "What MITRE ATT&CK technique is SQL injection?"
```
**Expected Tools Used**: `mitre_attack_mapper`
**What Happens**: Returns T1190 (Exploit Public-Facing Application), tactic: Initial Access

#### Test 5: Map Multiple Attack Types
```
User: "Map these to MITRE ATT&CK: brute force, port scan, command injection"
```
**Expected Tools Used**: `mitre_attack_mapper` (multiple calls)
**What Happens**: Returns T1110, T1046, T1059 with tactics

#### Test 6: CVE Lookup
```
User: "Look up CVE-2021-44228"
```
**Expected Tools Used**: `cve_lookup`
**What Happens**: Returns Log4Shell vulnerability information

---

### 📊 **Severity Assessment**

#### Test 7: Severity Scoring
```
User: "Rate the severity of a SQL injection attack with 3 indicators"
```
**Expected Tools Used**: `severity_scorer`
**What Happens**: Returns CRITICAL severity (9.5+/10)

#### Test 8: Compare Severities
```
User: "Which is more severe: port scan or brute force attack?"
```
**Expected Tools Used**: `severity_scorer` (twice)
**What Happens**: Compares scores (brute force: 6.5, port scan: 4.0)

---

### 🔗 **Event Correlation**

#### Test 9: Correlate Events
```
User: "Correlate these events: [Failed SSH login from 10.0.0.5], [Port scan from 10.0.0.5], [Malware execution from 10.0.0.5]"
```
**Expected Tools Used**: `event_correlator`
**What Happens**: Groups events by source IP, identifies attack chain

---

### 🚨 **Incident Response**

#### Test 10: Generate Playbook
```
User: "Generate an incident response playbook for SQL injection"
```
**Expected Tools Used**: `playbook_engine`
**What Happens**: Returns 5-step remediation plan

#### Test 11: Full Investigation Workflow
```
User: "I detected a SQL injection attempt. What should I do?"
```
**Expected Tools Used**: `mitre_attack_mapper`, `severity_scorer`, `playbook_engine`
**What Happens**:
1. Maps to MITRE (T1190)
2. Calculates severity (CRITICAL)
3. Generates response playbook

---

### 📂 **Log Analysis**

#### Test 12: Parse Log File
```
User: "Read the log file at /var/log/syslog and show the last 100 entries"
```
**Expected Tools Used**: `log_file_reader`
**What Happens**: Parses syslog format, extracts entries

#### Test 13: Extract Structured Data
```
User: "Extract IPs and timestamps from this log: '2024-02-25 10:30:00 Failed login from 192.168.1.100'"
```
**Expected Tools Used**: `structured_log_parser`
**What Happens**: Extracts structured fields (IPs, timestamps, severity, actions)

---

## 🎯 Multi-Tool Workflows

### Workflow 1: Complete Attack Investigation
```
User: "I found this in my logs: 'admin' OR 1=1; DROP TABLE users--'. Investigate this threat."
```

**Agent Workflow**:
1. 🔧 `signature_detector` → Detects SQL injection
2. 🔧 `mitre_attack_mapper` → Maps to T1190
3. 🔧 `severity_scorer` → Rates as CRITICAL (10.0/10)
4. 🔧 `playbook_engine` → Generates 5-step response plan

**Final Report**:
```
📋 Investigation Report

Executive Summary:
CRITICAL SQL injection attempt detected using UNION-based attack vectors.

Findings:
- Attack Type: SQL Injection
- MITRE Technique: T1190 (Exploit Public-Facing Application)
- Severity: CRITICAL (10.0/10)
- Indicators: 2 SQL injection patterns detected

Recommendations:
1. Isolate affected database server
2. Review application logs for injection attempts
3. Patch vulnerable SQL queries with parameterized statements
4. Run database integrity check
5. Monitor for continued attack attempts
```

### Workflow 2: Brute Force Investigation
```
User: "Multiple failed SSH login attempts from 203.0.113.50. What's happening?"
```

**Agent Workflow**:
1. 🔧 `signature_detector` → Detects brute force pattern
2. 🔧 `ip_reputation_checker` → Checks IP reputation
3. 🔧 `mitre_attack_mapper` → Maps to T1110 (Credential Access)
4. 🔧 `severity_scorer` → Rates as HIGH (6.5/10)
5. 🔧 `playbook_engine` → Generates containment plan

---

## 🐛 Debugging Tool Usage

### Method 1: Watch Tool Execution in Real-Time
```bash
# In terminal, tail the tools log
tail -f logs/tools.jsonl | jq -r '"\(.timestamp) [\(.event_type)] \(.tool_name // "N/A")"'
```

### Method 2: Check Tool Statistics
```bash
# After a chat session, check which tools were used
curl http://localhost:8000/api/debug/tool-stats | jq
```

**Example Output**:
```json
{
  "total_tool_calls": 4,
  "total_errors": 0,
  "tools": {
    "signature_detector": {
      "calls": 1,
      "errors": 0,
      "total_duration": 0.045,
      "avg_duration": 0.045
    },
    "mitre_attack_mapper": {
      "calls": 1,
      "errors": 0,
      "total_duration": 0.012,
      "avg_duration": 0.012
    },
    "severity_scorer": {
      "calls": 1,
      "errors": 0,
      "total_duration": 0.008,
      "avg_duration": 0.008
    },
    "playbook_engine": {
      "calls": 1,
      "errors": 0,
      "total_duration": 0.015,
      "avg_duration": 0.015
    }
  }
}
```

### Method 3: View Execution Trace
```bash
curl "http://localhost:8000/api/debug/execution-trace?logger_name=tools&limit=20" | jq
```

### Method 4: Check LangGraph Agent Logs
Look for these messages in server logs:
- `✅ Auto-registered 10 core cybersecurity tools` → Tools loaded successfully
- `🔧 Tool selection node: 10 tools available` → Agent is considering tools
- `✅ Tools selected: [...]` → LLM chose specific tools
- `Executing X tool(s)` → Tools are running

---

## 🔧 Tool Descriptions

| Tool Name | Purpose | Example Use Case |
|-----------|---------|------------------|
| **signature_detector** | Pattern matching for known attacks | Detect SQLi, XSS, brute force, command injection |
| **anomaly_detector** | Statistical anomaly detection | Find unusual event patterns, spike detection |
| **ip_reputation_checker** | IP reputation lookup | Check if IP is on blocklists |
| **mitre_attack_mapper** | Map attacks to MITRE ATT&CK | Understand attack tactics and techniques |
| **cve_lookup** | CVE vulnerability information | Get details about known vulnerabilities |
| **event_correlator** | Correlate related events | Link events from same attacker |
| **severity_scorer** | CVSS-like severity calculation | Prioritize incident response |
| **playbook_engine** | Generate response playbooks | Automated incident response guidance |
| **log_file_reader** | Parse various log formats | Read syslog, JSON, CSV, EVTX logs |
| **structured_log_parser** | Extract structured fields | Pull out IPs, timestamps, URLs, hashes |

---

## ❓ FAQ

### Q: How do I know if tools are being used?
A: Look for the "🛠️ Tool Selection" and "🔧 Using tool: ..." messages in the chat response.

### Q: What if the agent doesn't use tools?
A: The agent intelligently decides when tools are needed. For general questions like "What is phishing?", it won't use tools. For specific indicators like "Analyze IP 1.2.3.4", it will.

### Q: Can I force the agent to use a specific tool?
A: Yes! Mention the tool by name: "Use the signature_detector tool to analyze this log: ..."

### Q: How many tools can the agent use at once?
A: The agent can chain multiple tools in sequence, up to 5 tool steps by default (configurable).

### Q: Are tool results logged?
A: Yes! All tool executions are logged to `logs/tools.jsonl` with inputs, outputs, duration, and errors.

---

## 🎓 Pro Tips

1. **Be Specific**: Instead of "Check this log", say "Analyze this log for SQL injection: [log text]"

2. **Provide Context**: "I'm investigating a breach. Analyze this IP: 203.0.113.50"

3. **Request Multi-Step Analysis**: "Investigate this threat and give me a response plan"

4. **Use Real Data**: Copy-paste actual log entries, IPs, or attack patterns

5. **Chain Questions**: "What MITRE technique is this? → What's the severity? → Generate a playbook"

---

## 📚 Additional Resources

- **Tool Implementation**: See `app/tools/*/` directories
- **LangGraph Agent**: [app/ai/langgraph_agent.py](app/ai/langgraph_agent.py)
- **Tool Testing**: Run `python test_tool_integration.py`
- **Debug Endpoints**: [app/routers/debug.py](app/routers/debug.py)

---

**Status**: ✅ Ready to use
**Last Updated**: 2026-02-25
**Tools Integrated**: 10/12 (83%)
