# How to Test if Tools Are Actually Being Used

## 🎯 **Current Status**

**Tools Built**: ✅ 12 tools created and ready
**Tools Integrated**: ❌ Not yet connected to chat interface
**Why**: The existing LangGraph agent uses old `ExampleIOCTool`, new tools need to be registered

---

## 🧪 **Test Method 1: Direct Tool Testing** (Works NOW)

Test tools individually without the agent:

### **Create Test File**:
```bash
cd /Users/leviron/Major/COS30018/project/aegis-ai-backend
cat > test_tools_direct.py << 'EOF'
"""Direct tool testing - works immediately without integration"""
import asyncio
from app.tools.detection.signature_detector import signature_detector
from app.tools.cti_enrichment.mitre_attack_mapper import mitre_attack_mapper
from app.tools.correlation.severity_scorer import severity_scorer
from app.tools.incident_response.playbook_engine import playbook_engine

async def test_detection_flow():
    """Test complete attack detection and response flow"""

    print("=" * 60)
    print("TESTING CYBERSECURITY TOOLS")
    print("=" * 60)

    # Simulated attack log
    attack_log = """
    2025-02-25 10:30:15 Web Server ERROR: SQL query failed
    Request: GET /login?user=admin' OR '1'='1'; DROP TABLE users; --
    Source IP: 192.168.1.100
    Multiple failed authentication attempts detected
    """

    # Step 1: Detect threats
    print("\n[1] DETECTING THREATS...")
    print("-" * 60)
    detections = await signature_detector.execute(
        log_text=attack_log,
        signature_types=["sqli", "xss", "brute_force"]
    )

    print(f"✓ Found {detections['total_detections']} threats:")
    for det in detections['detections']:
        print(f"  • {det['type'].upper()}: '{det['match']}' (Severity: {det['severity']})")

    if detections['total_detections'] == 0:
        print("  No threats detected.")
        return

    # Step 2: Map to MITRE ATT&CK
    print("\n[2] MAPPING TO MITRE ATT&CK...")
    print("-" * 60)
    primary_threat = detections['detections'][0]['type']
    mitre = await mitre_attack_mapper.execute(attack_type=primary_threat)

    if 'error' not in mitre:
        print(f"✓ MITRE ATT&CK Mapping:")
        print(f"  • Technique: {mitre['mitre_technique']}")
        print(f"  • Tactic: {mitre['mitre_tactic']}")
        print(f"  • Name: {mitre['technique_name']}")
        print(f"  • URL: {mitre['mitre_url']}")
    else:
        print(f"  ⚠ {mitre['error']}")

    # Step 3: Calculate severity
    print("\n[3] CALCULATING SEVERITY SCORE...")
    print("-" * 60)
    indicators = [d['match'] for d in detections['detections']]
    severity = await severity_scorer.execute(
        threat_type=primary_threat,
        indicators=indicators
    )

    print(f"✓ Severity Assessment:")
    print(f"  • Threat Type: {severity['threat_type'].upper()}")
    print(f"  • CVSS Score: {severity['final_score']}/10")
    print(f"  • Severity: {severity['severity']}")
    print(f"  • Indicators: {severity['indicator_count']}")

    # Step 4: Generate response playbook
    print("\n[4] GENERATING INCIDENT RESPONSE PLAYBOOK...")
    print("-" * 60)
    playbook = await playbook_engine.execute(
        threat_type=primary_threat,
        severity=severity['severity']
    )

    print(f"✓ Response Plan:")
    print(f"  • Priority: {playbook['priority']}")
    print(f"  • Estimated Time: {playbook.get('estimated_time_minutes', 'N/A')} minutes")
    print(f"  • Steps:")
    for i, step in enumerate(playbook['playbook_steps'], 1):
        print(f"    {i}. {step}")

    # Summary
    print("\n" + "=" * 60)
    print("INVESTIGATION SUMMARY")
    print("=" * 60)
    print(f"Threat: {primary_threat.upper()} ({severity['severity']})")
    print(f"MITRE Technique: {mitre.get('mitre_technique', 'Unknown')}")
    print(f"Action Required: {playbook['priority']} priority response")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_detection_flow())
EOF

# Run the test
python test_tools_direct.py
```

### **Expected Output**:
```
============================================================
TESTING CYBERSECURITY TOOLS
============================================================

[1] DETECTING THREATS...
------------------------------------------------------------
✓ Found 3 threats:
  • SQLI: '' OR '1'='1' (Severity: CRITICAL)
  • SQLI: '; DROP TABLE' (Severity: CRITICAL)
  • BRUTE_FORCE: 'Multiple failed authentication attempts' (Severity: HIGH)

[2] MAPPING TO MITRE ATT&CK...
------------------------------------------------------------
✓ MITRE ATT&CK Mapping:
  • Technique: T1190
  • Tactic: Initial Access
  • Name: Exploit Public-Facing Application
  • URL: https://attack.mitre.org/techniques/T1190/

[3] CALCULATING SEVERITY SCORE...
------------------------------------------------------------
✓ Severity Assessment:
  • Threat Type: SQLI
  • CVSS Score: 10.0/10
  • Severity: CRITICAL
  • Indicators: 3

[4] GENERATING INCIDENT RESPONSE PLAYBOOK...
------------------------------------------------------------
✓ Response Plan:
  • Priority: CRITICAL
  • Estimated Time: 75 minutes
  • Steps:
    1. Isolate affected database server
    2. Review application logs for injection attempts
    3. Patch vulnerable SQL queries with parameterized statements
    4. Run database integrity check
    5. Monitor for continued attack attempts

============================================================
INVESTIGATION SUMMARY
============================================================
Threat: SQLI (CRITICAL)
MITRE Technique: T1190
Action Required: CRITICAL priority response
============================================================
```

---

## 🔧 **Test Method 2: Check Debug Endpoints** (After Starting Server)

```bash
# Terminal 1: Start backend
cd aegis-ai-backend
uvicorn app.main:app --reload

# Terminal 2: Run tool test
python test_tools_direct.py

# Terminal 3: Check if tools were logged
curl http://localhost:8000/api/debug/tool-stats | jq

# Expected output:
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
      ...
    },
    ...
  }
}

# Check execution trace
curl http://localhost:8000/api/debug/execution-trace?logger_name=tools | jq

# Check log files
tail -f logs/tools.jsonl
```

---

## 🤖 **Test Method 3: Via Chat Interface** (Requires Integration)

### **Current Situation**:
The tools are NOT yet integrated into the chat. When you ask questions in chat, the LLM responds but doesn't use your new tools.

### **To Integrate Tools into Chat**:

**Option A: Quick Integration** (Keep existing single agent, add new tools)

```python
# Modify: app/ai/langgraph_agent.py
# Add after line 120 (the register_tools method):

from app.tools.detection.signature_detector import signature_detector
from app.tools.cti_enrichment.mitre_attack_mapper import mitre_attack_mapper
from app.tools.correlation.severity_scorer import severity_scorer

# In __init__ method, register tools:
self.register_tools([
    signature_detector.to_langchain_tool(),
    mitre_attack_mapper.to_langchain_tool(),
    severity_scorer.to_langchain_tool()
])
```

**Option B: Full Multi-Agent System** (Recommended, but more work)
- Create 6 specialized agents
- Build LangGraph workflow
- Replace single agent with multi-agent orchestrator

---

## 📊 **How to Know Tools Are Actually Working in Chat**

Once integrated, test with these prompts:

### **Test 1: Basic Detection**
```
Prompt: "Analyze this log: admin' OR '1'='1'; DROP TABLE users; --"

Expected: Should use signature_detector and report SQLi detection
```

### **Test 2: MITRE Mapping**
```
Prompt: "What MITRE ATT&CK technique is a SQL injection attack?"

Expected: Should use mitre_attack_mapper and return T1190
```

### **Test 3: Severity Scoring**
```
Prompt: "Rate the severity of a SQL injection with multiple indicators"

Expected: Should use severity_scorer and return CRITICAL (9.5+/10)
```

### **Verify Tool Usage**:
```bash
# After each chat, check:
curl http://localhost:8000/api/debug/tool-stats

# Should show increasing "calls" count for each tool used
```

---

## 🎯 **Quick Integration Script**

Want to integrate tools NOW? Run this:

```bash
cd /Users/leviron/Major/COS30018/project/aegis-ai-backend

cat > integrate_tools.py << 'EOF'
"""Quick tool integration into existing agent"""
import sys

# Read current agent file
with open('app/ai/langgraph_agent.py', 'r') as f:
    content = f.read()

# Add imports at top (after existing imports)
import_addition = """
# NEW: Import cybersecurity tools
from app.tools.detection.signature_detector import signature_detector
from app.tools.cti_enrichment.mitre_attack_mapper import mitre_attack_mapper
from app.tools.correlation.severity_scorer import severity_scorer
from app.tools.incident_response.playbook_engine import playbook_engine
"""

# Find where to add imports (after line 27)
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'from app.config import settings' in line:
        lines.insert(i + 1, import_addition)
        break

# Find register_tools method and add default tools
for i, line in enumerate(lines):
    if 'def register_tools(self, tools: list):' in line:
        # Add default tool registration
        lines.insert(i + 1, """
        # Auto-register core cybersecurity tools
        default_tools = [
            signature_detector,
            mitre_attack_mapper,
            severity_scorer,
            playbook_engine
        ]
        tools = default_tools + (tools or [])
""")
        break

# Write back
with open('app/ai/langgraph_agent.py', 'w') as f:
    f.write('\n'.join(lines))

print("✓ Tools integrated into LangGraph agent!")
print("✓ Restart server to apply changes")
EOF

python integrate_tools.py
```

---

## 🚦 **Status Check Commands**

```bash
# 1. Check if tools exist
ls -la app/tools/detection/*.py
ls -la app/tools/cti_enrichment/*.py

# 2. Test tools directly
python test_tools_direct.py

# 3. Check debug endpoints (server must be running)
curl http://localhost:8000/api/debug/tool-stats
curl http://localhost:8000/api/debug/execution-trace?logger_name=tools&limit=10

# 4. Watch logs in real-time
tail -f logs/tools.jsonl | jq

# 5. Grep for tool usage
grep "tool_start" logs/tools.jsonl | jq '.tool_name' | sort | uniq -c
```

---

## ✅ **Summary**

**Right Now**:
- ✅ Tools can be tested directly (Method 1)
- ✅ Debug endpoints work
- ❌ Tools not used in chat (not integrated yet)

**To Enable in Chat**:
1. Run the integration script above, OR
2. Wait for multi-agent system implementation

**Best Test**:
```bash
python test_tools_direct.py
```

This will prove all tools work correctly!

---

**Next Steps**: Would you like me to run the integration script to connect these tools to your chat interface?
