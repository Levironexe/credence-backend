# Test Prompts to Verify Tools Are Working

**Status**: Server restarted with integrated tools ✅
**Next Step**: Try these prompts in your chat frontend

---

## 🎯 Test These Prompts (Copy & Paste)

### Test 1: SQL Injection Detection ⭐ HIGHLY RECOMMENDED
```
Analyze this log entry for threats: admin' OR '1'='1'; DROP TABLE users; --
```

**What should happen:**
- Agent uses `signature_detector` tool
- Detects SQL injection patterns
- Returns CRITICAL severity

**Verification:**
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Should show: "signature_detector": {"calls": 1, ...}
```

---

### Test 2: MITRE ATT&CK Technique Query
```
What is the MITRE ATT&CK technique ID for SQL injection attacks?
```

**What should happen:**
- Agent uses `mitre_attack_mapper` tool
- Returns: T1190 (Exploit Public-Facing Application)
- Provides tactic: Initial Access

**Verification:**
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Should show: "mitre_attack_mapper": {"calls": 1, ...}
```

---

### Test 3: Severity Calculation
```
Calculate the severity score for a SQL injection attack with 3 indicators detected
```

**What should happen:**
- Agent uses `severity_scorer` tool
- Returns CRITICAL rating (10.0/10)
- Explains CVSS-like calculation

**Verification:**
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Should show: "severity_scorer": {"calls": 1, ...}
```

---

### Test 4: Multi-Tool Investigation ⭐ FULL WORKFLOW
```
I detected this in my web server logs: "GET /login?user=admin' OR 1=1--". Please investigate this threat and give me a response plan.
```

**What should happen:**
- Agent chains multiple tools:
  1. `signature_detector` → Detects SQLi
  2. `mitre_attack_mapper` → Maps to T1190
  3. `severity_scorer` → Rates as CRITICAL
  4. `playbook_engine` → Generates 5-step response plan

**Verification:**
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Should show 4 different tools with calls
```

---

## 🔍 How to Know Tools Are Working

### In Chat Response - Look For:

✅ **Tool Selection Header:**
```
🛠️ Tool Selection
🔧 Using tool: signature_detector
```

✅ **Multiple Sections:**
```
# 🔍 Investigation Planning
[Agent's plan]

# 🛠️ Tool Selection
🔧 Using tool: signature_detector ✓

# 📊 Threat Analysis
[Analysis based on tool results]

# 📋 Investigation Report
[Final report]
```

❌ **If NO tools used, you'll only see:**
```
# 🔍 Investigation Planning
[Response without tools]
```

---

## 🐛 Troubleshooting

### If tools still aren't being used:

#### Check 1: Server loaded tools
```bash
cd /Users/leviron/Major/COS30018/project/aegis-ai-backend
source venv/bin/activate
python << 'EOF'
from app.ai.langgraph_agent import LangGraphAgent
agent = LangGraphAgent()
print(f"✅ {len(agent.tools)} tools loaded")
EOF
```

Expected: `✅ 10 tools loaded`

#### Check 2: Server logs show tool registration
```bash
tail -50 server.log | grep "Auto-registered"
```

Expected: `INFO - ✅ Auto-registered 10 core cybersecurity tools`

#### Check 3: Try the most explicit prompt
```
Use the signature_detector tool to analyze this SQL injection: admin' OR 1=1--
```

This explicitly tells the agent to use a specific tool.

---

## 📊 After Testing - Verify Tool Usage

### Check tool statistics:
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
```

### Expected output after Test 1:
```json
{
  "total_tool_calls": 1,
  "total_errors": 0,
  "tools": {
    "signature_detector": {
      "calls": 1,
      "errors": 0,
      "total_duration": 0.045,
      "avg_duration": 0.045
    }
  }
}
```

### Check execution trace:
```bash
curl "http://localhost:8000/api/debug/execution-trace?logger_name=tools&limit=10" | jq
```

### View tool logs:
```bash
tail -20 logs/tools.jsonl | jq
```

---

## ⚡ Quick Test Script

If you want to test without the frontend:

```bash
cd /Users/leviron/Major/COS30018/project/aegis-ai-backend
source venv/bin/activate

# Test with Python
python << 'EOF'
import asyncio
from app.ai.langgraph_agent import LangGraphAgent

async def quick_test():
    agent = LangGraphAgent()
    print(f"Agent has {len(agent.tools)} tools\n")

    messages = [{
        "role": "user",
        "content": "What is the MITRE ATT&CK technique for SQL injection?"
    }]

    print("Sending query...\n")
    async for chunk in agent.stream_chat_completion(
        model="agent/cyber-analyst",
        messages=messages,
        temperature=0.7
    ):
        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
        if content:
            print(content, end="", flush=True)

    print("\n\n✅ Done! Check tool stats:")
    print("curl http://localhost:8000/api/debug/tool-stats | jq")

asyncio.run(quick_test())
EOF
```

---

## ✅ Success Indicators

You'll know tools are working when you see:

1. ✅ Chat response has "🛠️ Tool Selection" section
2. ✅ Chat response shows "🔧 Using tool: [toolname]"
3. ✅ `tool-stats` shows `total_tool_calls > 0`
4. ✅ `logs/tools.jsonl` file exists and has entries
5. ✅ Agent response references specific data from tool execution

---

**Current Server Status**: ✅ Running on http://localhost:8000
**Tools Status**: ✅ 10 tools integrated
**Ready to Test**: ✅ YES - Try Test 1 or Test 4 above

---

**Pro Tip**: Copy Test 1 or Test 4 prompt exactly as written - they're designed to maximize the chance of tool usage!
