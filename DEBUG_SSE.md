# SSE Stream Debugging Guide

## Problem: Stream stops after classify node_start (appearing twice)

The frontend only receives:
```
data: {"type": "node_start", "node": "classify", "message": "📋 Classifying query..."}
data: {"type": "node_start", "node": "classify", "message": "📋 Classifying query..."}
```

Then nothing else comes through.

## Debugging Steps

### Step 1: Test Backend Directly (Bypass Frontend)

Run the test script to see raw SSE output:

```bash
cd credence-backend

# Make script executable
chmod +x test_sse_stream.py

# Run test
python test_sse_stream.py
```

**Expected Output**:
```
🚀 Starting SSE stream test...
================================================================================
STREAMING EVENTS:
================================================================================
✅ Connected - Status: 200

[1] 🎯 NODE_START: classify - 📋 Classifying query...
[2] 🧠 REASONING (classify): I need to analyze this loan application...
[3] 🎯 NODE_START: document_ingestion - 📄 Processing documents...
[4] 🎯 NODE_START: data_completeness - 🔍 Checking data completeness...
[5] 🔧 TOOL_CALL: data_completeness_checker
[6] ✅ TOOL_RESULT: data_completeness_checker
[7] 🎯 NODE_START: planning - 📋 Planning analysis...
...
```

**If you only see classify node_start**:
- The LangGraph execution is failing after classify
- Check backend logs for exceptions

### Step 2: Check Backend Logs

Run backend with DEBUG logging:

```bash
cd credence-backend
uvicorn app.main:app --reload --log-level debug
```

**Look for these log patterns**:

✅ **Healthy Stream**:
```
DEBUG:app.ai.langgraph_agent:📡 LangGraph event #1: on_chain_start
DEBUG:app.ai.langgraph_agent:📤 Emitting NODE_START: classify - 📋 Classifying query...
INFO:app.routers.chat:✅ Passing through structured event: node_start - classify

DEBUG:app.ai.langgraph_agent:📡 LangGraph event #2: on_chat_model_stream
DEBUG:app.ai.langgraph_agent:📤 Emitting REASONING from node: classify

DEBUG:app.ai.langgraph_agent:📡 LangGraph event #3: on_chain_start
DEBUG:app.ai.langgraph_agent:📤 Emitting NODE_START: document_ingestion
...
INFO:app.ai.langgraph_agent:✅ LangGraph execution complete. Processed 156 events.
```

❌ **Broken Stream**:
```
DEBUG:app.ai.langgraph_agent:📡 LangGraph event #1: on_chain_start
DEBUG:app.ai.langgraph_agent:📤 Emitting NODE_START: classify
INFO:app.routers.chat:✅ Passing through structured event: node_start - classify

# Stream stops here - no more events

ERROR:app.ai.langgraph_agent:❌ FATAL: LangGraph agent error: AttributeError: ...
```

### Step 3: Common Issues and Fixes

#### Issue 1: Duplicate classify node_start

**Symptom**: Same node_start event appears twice

**Causes**:
- LangGraph retry mechanism
- Agent being invoked twice
- `on_chain_start` firing multiple times

**Debug**:
```bash
# Check if classify node is in the graph twice
grep -n "add_node.*classify" app/ai/langgraph_agent.py

# Check if there are multiple entry points
grep -n "set_entry_point.*classify" app/ai/langgraph_agent.py
```

**Fix**: Ensure classify node is only added once and only one entry point exists

---

#### Issue 2: Stream stops after classify

**Symptom**: Only classify node_start, then silence

**Causes**:
1. Exception in classify node execution
2. Routing function failing
3. LangGraph state corruption
4. LLM API error (e.g., httpx.ResponseNotRead)

**Debug**:
Check logs for:
```bash
# Look for exceptions
grep -A 10 "ERROR.*langgraph" logs.txt
grep -A 10 "FATAL" logs.txt

# Look for routing decisions
grep "Routing to" logs.txt
```

**Common Exceptions**:

**A) httpx.ResponseNotRead**
```
ERROR: httpx.ResponseNotRead: Attempted to read response content, but response has already been read.
```

**Fix**: Ensure LLM client doesn't reuse consumed response bodies

**B) KeyError in routing**
```
ERROR: KeyError: 'intent_type'
```

**Fix**: Check state initialization includes all required fields

**C) AttributeError in nodes**
```
ERROR: AttributeError: 'str' object has no attribute 'get'
```

**Fix**: Add type checks before accessing dict methods

---

#### Issue 3: No errors but stream still stops

**Symptom**: Backend logs show "complete" but frontend gets nothing

**Causes**:
- Events being filtered out by router
- Type field missing from events
- SSE format malformed

**Debug**:
```bash
# Check if events have correct type field
grep "Passing through structured event" logs.txt

# Count how many events are emitted vs passed through
grep "Emitting" logs.txt | wc -l
grep "Passing through" logs.txt | wc -l
```

**Fix**: Ensure all emitted events have `type` field and are in the pass-through list

---

### Step 4: Enable Maximum Logging

Edit `app/ai/langgraph_agent.py`:

```python
# At top of file
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# In _transform_event_to_sse, log EVERY event
async def _transform_event_to_sse(self, event: Dict[str, Any]):
    event_type = event.get("event")
    logger.debug(f"📥 RAW EVENT: {event_type} - {json.dumps(event, indent=2)[:500]}")
    # ... rest of method
```

This will show:
- Every raw LangGraph event
- What's being filtered out
- What's being transformed

---

### Step 5: Test Individual Nodes

Test nodes in isolation:

```python
# test_nodes.py
import asyncio
from app.ai.nodes.classify import classify_node
from app.ai.state import LoanAssessmentState
from langchain_anthropic import ChatAnthropic

async def test_classify():
    llm = ChatAnthropic(model="claude-sonnet-4")

    state: LoanAssessmentState = {
        "messages": [HumanMessage(content="Test loan application")],
        "tools_used": [],
        "tool_results": [],
        "final_response": "",
    }

    result = await classify_node(state, llm=llm, tools=[])
    print(f"Result: {result}")
    print(f"Intent type: {result.get('intent_type')}")

asyncio.run(test_classify())
```

---

## Expected Full Event Sequence

For a loan assessment query, you should see:

```
1. node_start: classify
2. reasoning: classify (LLM deciding intent)
3. node_start: document_ingestion
4. node_start: data_completeness
5. tool_call: data_completeness_checker
6. tool_result: data_completeness_checker
7. node_start: planning
8. reasoning: planning (LLM making plan)
9. node_start: tool_selection
10. reasoning: tool_selection (LLM choosing tools)
11. node_start: execute_tools
12. tool_call: credit_score_model
13. tool_result: credit_score_model
14. node_start: credit_scoring
15. node_start: explainability
16. tool_call: shap_explainer
17. tool_result: shap_explainer
18. node_start: fairness_check
19. tool_call: fairness_validator
20. tool_result: fairness_validator
21. skip: counterfactual_generation (if score >= 670)
    OR node_start: counterfactual_generation (if score < 670)
22. node_start: analysis
23. reasoning: analysis (LLM synthesizing)
24. node_start: response
25. text: Final loan assessment report
26. finish
```

If you don't see this full sequence, the break point tells you which node is failing.

---

## Quick Fixes Checklist

- [ ] Run `test_sse_stream.py` - see raw events
- [ ] Check backend logs for `❌ ERROR` or `❌ FATAL`
- [ ] Verify all nodes have correct routing
- [ ] Ensure `USER_FACING_NODES` is correct
- [ ] Check `route_by_intent` returns valid values
- [ ] Verify LLM API key is valid
- [ ] Test with `--log-level debug`
- [ ] Check if state has all required fields

---

## Need More Help?

1. **Capture full logs**:
   ```bash
   uvicorn app.main:app --reload --log-level debug 2>&1 | tee debug.log
   ```

2. **Run test script**:
   ```bash
   python test_sse_stream.py > test_output.txt 2>&1
   ```

3. **Share both files** with error details
