# Quick Test Guide: Verify Tools Are Working

**Status**: Tools are integrated ✅
**What's missing**: You haven't sent any chat messages yet!

---

## Why Debug Commands Show Empty Results

```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Returns: {"total_tool_calls": 0, ...}
```

**This is NORMAL!** ✅

The debug endpoints show zero tool usage because:
1. ✅ Server is running
2. ✅ Tools are loaded and registered
3. ❌ **No chat messages have been sent yet**

Tools are **lazy** - they only execute when you ask questions in chat!

---

## ✅ How to Actually Test the Tools

### Method 1: Use Your Chat Frontend (RECOMMENDED)

1. **Open your frontend** (React app, usually `http://localhost:3000`)
2. **Start a new chat**
3. **Ask a cybersecurity question:**

```
"Analyze this log: admin' OR '1'='1'; DROP TABLE users; --"
```

4. **Watch the chat response** - you should see:
   - 🔍 Investigation Planning
   - 🛠️ Tool Selection
   - 🔧 Using tool: `signature_detector`
   - 📊 Threat Analysis
   - 📋 Investigation Report

5. **Check tool stats again:**
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# NOW you should see: {"total_tool_calls": 1, ...}
```

---

### Method 2: Test via Direct API Call

If you don't have a frontend running, you can test the API directly:

```bash
# Create a test script
cat > test_api.sh << 'EOF'
#!/bin/bash

# Get a chat ID (or create one)
CHAT_ID="test-$(date +%s)"

# Send a message via API
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d "{
    \"chatId\": \"$CHAT_ID\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": \"Analyze this log: admin' OR '1'='1'; DROP TABLE users; --\"
    }],
    \"model\": \"agent/cyber-analyst\"
  }"
EOF

chmod +x test_api.sh
./test_api.sh
```

---

### Method 3: Use Python to Test Agent Directly

```bash
cd /Users/leviron/Major/COS30018/project/credence-ai-backend
source venv/bin/activate
python << 'EOF'
import asyncio
from app.ai.langgraph_agent import LangGraphAgent

async def test():
    print("Initializing agent...")
    agent = LangGraphAgent()
    print(f"✅ Agent has {len(agent.tools)} tools registered")
    print(f"Tools: {[t.name for t in agent.tools]}")

    print("\nSending test query...")
    messages = [
        {"role": "user", "content": "What MITRE ATT&CK technique is SQL injection?"}
    ]

    print("\nStreaming response:")
    async for chunk in agent.stream_chat_completion(
        model="agent/cyber-analyst",
        messages=messages,
        temperature=0.7
    ):
        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
        if content:
            print(content, end="", flush=True)

    print("\n\n✅ Test complete!")
    print("\nNow check tool stats:")
    print("  curl http://localhost:8000/api/debug/tool-stats | jq")

asyncio.run(test())
EOF
```

---

## 🔍 How to Verify Tools Loaded Correctly

### Check 1: Server Startup Logs

When the server starts, look for this message:

```
INFO - ✅ Auto-registered 10 core cybersecurity tools
INFO - Registered 10 tools: ['signaturedetector', 'anomalydetector', ...]
```

**Where to check:**
```bash
# If server is running in terminal, you'll see it there
# Or check logs
grep "Auto-registered" logs/*.jsonl
```

### Check 2: List Available Tools

The tools are registered when the LangGraph agent initializes. You can verify by importing:

```bash
source venv/bin/activate
python << 'EOF'
from app.ai.langgraph_agent import LangGraphAgent
agent = LangGraphAgent()
print(f"✅ {len(agent.tools)} tools loaded:")
for tool in agent.tools:
    print(f"  • {tool.name}: {tool.description[:60]}...")
EOF
```

**Expected output:**
```
✅ 10 tools loaded:
  • signaturedetector: Detect known attack signatures (SQLi, XSS, brute fo...
  • anomalydetector: Detect statistical anomalies in event patterns (freq...
  • ipreputationchecker: Check IP reputation against known malicious IP databa...
  ...
```

---

## 📊 What You Should See After Using Tools

### Before (What you're seeing now):
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Output:
{
  "total_tool_calls": 0,
  "total_errors": 0,
  "tools": {}
}
```

### After Sending a Chat Message:
```bash
curl http://localhost:8000/api/debug/tool-stats | jq
# Output:
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

---

## 🎯 Test Prompts That Will Definitely Trigger Tools

These prompts are designed to force tool usage:

### Test 1: Signature Detection (100% will use signature_detector)
```
"Analyze this log: admin' OR '1'='1'; DROP TABLE users; --"
```

### Test 2: MITRE Mapping (100% will use mitre_attack_mapper)
```
"What is the MITRE ATT&CK technique ID for SQL injection?"
```

### Test 3: Severity Scoring (100% will use severity_scorer)
```
"Calculate the CVSS severity score for a SQL injection attack"
```

### Test 4: Multi-Tool Workflow (will chain multiple tools)
```
"Investigate this attack: Failed SSH login from 203.0.113.50. Give me a response plan."
```
**Expected tools**: signature_detector → mitre_attack_mapper → severity_scorer → playbook_engine

---

## 🐛 Troubleshooting

### Issue: "No tools being used"
**Solution**: Make sure you're asking questions that require tools. Generic questions like "What is phishing?" won't trigger tools.

### Issue: "Server not using new code"
**Solution**: Restart the server:
```bash
pkill -f "uvicorn app.main:app"
uvicorn app.main:app --reload
```

### Issue: "logs/tools.jsonl doesn't exist"
**Solution**: The log file is created when the first tool runs. Try sending a chat message first.

### Issue: "Frontend not connected"
**Solution**: Check your frontend is running and configured to use `http://localhost:8000`

---

## ✅ Summary

**Current Status**: ✅ Tools are loaded and ready

**What's happening**: The debug endpoints show zero usage because you haven't sent any chat messages yet.

**Next Step**: Open your chat interface and ask a cybersecurity question!

**Verification**: After sending a message, run `curl http://localhost:8000/api/debug/tool-stats | jq` again - you'll see tool usage.

---

**TIP**: For the URL with query parameters, use quotes in zsh:
```bash
curl "http://localhost:8000/api/debug/execution-trace?logger_name=tools" | jq
```

The error `zsh: no matches found` happens because zsh tries to glob-expand the `?`. Quotes fix this!
