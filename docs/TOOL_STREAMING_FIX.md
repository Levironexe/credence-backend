# Tool Streaming Synchronization Fix

## Problem Statement

When the LangGraph agent called multiple tools in parallel, the streaming output was becoming desynchronized, causing tool inputs and outputs to be mismatched in the UI.

### Symptom

The markdown output looked like this:

```markdown
**Tool called:** `credit_score_model`
**Input:**
```json
{"monthly_revenue": 120000000, ...}
```
**Output:** **Tool called:** `data_completeness_checker`  ← WRONG! This should be credit_score_model's output
**Input:**
```json
{"monthly_revenue": 120000000, ...}
```
**Output:** **Tool called:** `shap_explainer`  ← WRONG! This should be data_completeness_checker's output
...
```

### Root Cause

The `ToolNode` from LangGraph executes tools **in parallel** for performance. The streaming events (`on_tool_start` and `on_tool_end`) were arriving **out of order** because tools complete at different times:

1. **on_tool_start** for `credit_score_model` → Stream `**Tool called:** credit_score_model` + `**Output:**`
2. **on_tool_start** for `data_completeness_checker` → Stream `**Tool called:** data_completeness_checker`
3. **on_tool_end** for `data_completeness_checker` → Stream output (but this goes to credit_score_model's Output section!)
4. **on_tool_end** for `credit_score_model` → Stream output (but this goes to data_completeness_checker's Output section!)

The problem: We were streaming the tool header immediately on `on_tool_start` with a placeholder `**Output:**`, then streaming the first output that arrived, regardless of which tool it belonged to.

## Solution: Tool Output Buffering

### Implementation

**File:** `app/ai/langgraph_agent.py`

**Key Changes:**

1. **Added tool buffer** to track pending tool calls by their `run_id`:

```python
# In _transform_event_to_sse method
run_id = event.get("run_id", "")

# Initialize tool buffer if not exists
if not hasattr(self, '_tool_buffer'):
    self._tool_buffer = {}  # {run_id: {name, input, streamed}}
```

2. **on_tool_start**: Store tool info in buffer, **don't stream yet**:

```python
elif event_type == "on_tool_start":
    # Add header before first tool
    if not hasattr(self, '_tool_header_shown'):
        self._tool_header_shown = True
        yield {"choices": [{"delta": {"content": "\n\n##  Tool Execution\n\n"}}]}

    tool_input = data.get("input", {})
    tool_name = name

    # Store in buffer (keyed by run_id to match with on_tool_end)
    self._tool_buffer[run_id] = {
        "name": tool_name,
        "input": tool_input,
        "streamed": False
    }

    # DON'T stream immediately - wait for on_tool_end
```

3. **on_tool_end**: Retrieve tool info from buffer and stream the **complete tool block**:

```python
elif event_type == "on_tool_end":
    # Get tool info from buffer
    tool_info = self._tool_buffer.get(run_id)
    if not tool_info or tool_info.get("streamed"):
        return

    tool_name = tool_info["name"]
    tool_input = tool_info["input"]
    output = data.get("output", {})

    # Format input and output
    formatted_input = json.dumps(tool_input, indent=2)
    # ... output formatting logic ...

    # Stream COMPLETE tool block (input + output together)
    yield {
        "choices": [{
            "delta": {
                "content": f"**Tool called:** `{tool_name}`\n\n**Input:**\n```json\n{formatted_input}\n```\n\n**Output:**\n```json\n{formatted_output}\n```\n\n---\n\n"
            }
        }]
    }

    # Mark as streamed
    tool_info["streamed"] = True
```

### How It Works

1. When a tool **starts**, we save its name and input to a buffer keyed by `run_id`
2. We **don't stream anything yet** (no premature `**Output:**` placeholder)
3. When a tool **completes**, we:
   - Look up its info in the buffer using `run_id`
   - Stream the **complete atomic block**: Tool name → Input → Output
   - Mark it as streamed to prevent duplicates
4. Tools stream in the **order they complete**, but each tool's input/output stay together

### Result

Now the markdown output is correct:

```markdown
**Tool called:** `credit_score_model`
**Input:**
```json
{"monthly_revenue": 120000000, "loan_amount": 300000000, ...}
```
**Output:**
```json
{"success": true, "credit_score": 715, "score_band": "Good", ...}
```

---

**Tool called:** `data_completeness_checker`
**Input:**
```json
{"monthly_revenue": 120000000, "loan_amount": 300000000, ...}
```
**Output:**
```json
{"success": true, "completeness_score": 0.71, ...}
```

---

**Tool called:** `shap_explainer`
**Input:**
```json
{"monthly_revenue": 120000000, "loan_amount": 300000000, ...}
```
**Output:**
```json
{"success": true, "method": "rule-based", ...}
```

---
```

## Frontend Integration

The frontend parser (`lib/parse-agent-stream.ts`) correctly extracts tool blocks using this regex:

```typescript
const toolBlockRegex =
  /\*\*Tool called:\*\* `([^`]+)`\s*\*\*Input:\*\*\s*```json\s*([\s\S]*?)```\s*(?:\*\*Output:\*\*\s*```json\s*([\s\S]*?)```)?(?:\s*---\s*)?/g;
```

This matches:
- `**Tool called:** \`tool_name\``
- `**Input:**` followed by JSON code block
- `**Output:**` followed by JSON code block (optional for running tools)
- Optional `---` separator

The parser creates **ordered sections** (thought → text → tools → text) which are rendered by `StreamingAgentDisplay`:
- Thought section → Collapsible box
- Text section → Normal markdown (no box)
- Tools section → Collapsible box with individual tool cards
- Text section → Normal markdown (no box)

## Benefits

✅ **Correct tool output matching**: Each tool's input and output are always paired correctly

✅ **Parallel execution preserved**: Tools still run in parallel for performance, only streaming is delayed

✅ **Atomic tool blocks**: Each tool is streamed as a complete unit, making parsing reliable

✅ **Clean UI**: Frontend can confidently parse and display tools in collapsible boxes

✅ **No race conditions**: Using `run_id` ensures we always match the correct tool start/end events

## Testing

To verify the fix works:

1. Submit a loan assessment query that triggers multiple tools:
   ```
   Assess a $300M VND loan for a grocery store with 120M VND monthly revenue,
   18% profit margin, 3 years in business
   ```

2. Check the console logs for parsing success:
   ```
   📊 Total sections: 4 ['thought', 'text', 'tools', 'text']
   📊 Total tools parsed: 3
   ✅ Parsed tool 1: credit_score_model, has output: true
   ✅ Parsed tool 2: data_completeness_checker, has output: true
   ✅ Parsed tool 3: shap_explainer, has output: true
   ```

3. Verify the UI shows:
   - Thought box (collapsed) with planning content
   - Initial analysis text
   - Tools box (expanded) with 3 tool cards
   - Final analysis text

## Related Files

- `credence-backend/app/ai/langgraph_agent.py` - Backend streaming logic with tool buffering
- `credence-chat/lib/parse-agent-stream.ts` - Frontend parser for tool blocks and sections
- `credence-chat/components/streaming-agent-display.tsx` - UI component rendering ordered sections
- `credence-chat/components/message.tsx` - Message component integrating the agent display

## Additional Improvements

Along with this fix, we also made the system prompts more concise:

### Planning Prompt
Changed from verbose instructions to:
```
Provide a CONCISE assessment plan (3-5 bullet points max):
1. Analysis type needed
2. Available data vs. missing information
3. Initial risk level
4. Recommended approach (1-2 sentences)

Be brief and actionable. Avoid lengthy explanations.
```

### Analysis Prompt
Changed to:
```
Provide a CONCISE credit analysis. Start with "## Credit Analysis\n\n"

**Required (be brief):**
1. Credit Score & Key Metrics - List actual numbers (1-2 sentences)
2. Risk Factors - Top 2-3 concerns (bullet points)
3. Loan Decision - Approve/decline, amount, rate, conditions (3-4 bullets max)

Style: Direct, factual, concise. Aim for 150-200 words total.
```

This reduces response verbosity from ~800 words to ~200 words while maintaining all critical information.
