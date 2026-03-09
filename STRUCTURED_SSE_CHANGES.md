# Structured SSE Implementation - Complete Changes Summary

## Problem Fixed

**Original Issue**: LangGraph's structured events (node_start, tool_call, etc.) were being converted to generic text-delta events, losing all metadata needed for collapsible UI sections.

**Root Cause**: The router layer was wrapping all events in AI SDK's text-delta format, destroying custom type information.

## Solution Architecture

```
┌─────────────────────┐
│ LangGraph Agent     │ Emits: {"type": "node_start", "node": "classify"}
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Router (chat.py)    │ Pass-through: data: {"type": "node_start", ...}
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Next.js Proxy       │ Pure SSE passthrough
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ useStructuredChat() │ Raw SSE reader, no AI SDK transformation
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ ProcessViewer       │ Renders collapsible sections
└─────────────────────┘
```

## Backend Changes

### 1. **langgraph_agent.py** - Simplified Event Format

**File**: `app/ai/langgraph_agent.py`

**Changed**: Removed `choices[0].delta.content` wrapper from all events

**Before**:
```python
yield {
    "type": "node_start",
    "node": "classify",
    "message": "📋 Classifying query...",
    "choices": [{"delta": {"content": ""}}]  # Unnecessary wrapper
}
```

**After**:
```python
yield {
    "type": "node_start",
    "node": "classify",
    "message": "📋 Classifying query..."  # Clean, simple
}
```

**Events Changed**:
- `node_start`: Removed choices wrapper
- `tool_call`: Removed choices wrapper
- `tool_result`: Removed choices wrapper
- `text`: Changed from `choices[0].delta.content` to `content` field
- `reasoning`: Changed from `choices[0].delta.content` to `content` field
- `skip`: Removed choices wrapper

**Lines Modified**: 560-645

---

### 2. **chat.py** - Pass-Through Router

**File**: `app/routers/chat.py`

**Changed**: Router now detects and passes through structured events unchanged

**Before**:
```python
async for chunk in gateway_client.stream_chat_completion(...):
    # Always wrapped as text-delta
    event_data = {
        "type": "text-delta",
        "id": message_id,
        "delta": content_str
    }
    yield f"data: {json.dumps(event_data)}\n\n"
```

**After**:
```python
async for chunk in gateway_client.stream_chat_completion(...):
    event_type = chunk.get("type")

    # PASS THROUGH structured events directly
    if event_type in ["node_start", "tool_call", "tool_result", "reasoning", "skip", "text"]:
        logger.debug(f"Passing through structured event: {event_type}")
        yield f"data: {json.dumps(chunk)}\n\n"

        # Accumulate text content for database
        if event_type == "text":
            full_content += chunk.get("content", "")
        continue

    # Handle standard OpenAI chunks (for non-agent models)
    # ...
```

**Lines Modified**: 307-365

**Key Changes**:
- Detects custom event types by checking `chunk.get("type")`
- Passes through events with types: `node_start`, `tool_call`, `tool_result`, `reasoning`, `skip`, `text`
- Only transforms standard OpenAI chunks (for backward compatibility with non-agent models)
- Accumulates `text` event content for database storage

---

## Frontend Changes

### 3. **use-structured-chat.ts** - Raw SSE Reader

**File**: `hooks/use-structured-chat.ts`

**Changed**: Complete rewrite - removed AI SDK dependency, reads raw SSE

**Before**: Used `@ai-sdk/react`'s `useChat` hook which transformed events

**After**: Raw SSE stream reader

**Key Implementation**:

```typescript
export function useStructuredChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [collapsibleSections, setCollapsibleSections] = useState<CollapsibleSection[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const sseHandlerRef = useRef<SSEEventHandler | null>(null);

  const sendMessage = async (text: string, options?: any) => {
    const response = await fetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ messages: [...] }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const event = JSON.parse(line.slice(6));
          handleEvent(event);  // Route to correct UI section
        }
      }
    }
  };

  const handleEvent = (event: StructuredEvent) => {
    switch (event.type) {
      case "text":
      case "text-delta":
        // Accumulate in main response area
        setMessages(prev => updateLastMessage(prev, event.content || event.delta));
        break;

      case "node_start":
      case "tool_call":
      case "reasoning":
      case "skip":
      case "tool_result":
        // Pass to SSE handler for collapsible sections
        sseHandlerRef.current?.handleChunk(event);
        break;
    }
  };

  return { messages, collapsibleSections, sendMessage, isStreaming, stop };
}
```

**Lines**: Complete file (170 lines)

**Benefits**:
- Direct control over SSE parsing
- No AI SDK transformation layer
- Proper event routing to UI sections
- Supports abort/stop functionality
- Handles both new (`text`) and legacy (`text-delta`) formats

---

### 4. **sse-handler.ts** - Unchanged

**File**: `lib/sse-handler.ts`

**Status**: Already implemented correctly in previous session

**Purpose**: Manages collapsible section state

---

### 5. **process-viewer.tsx** - Unchanged

**File**: `components/process-viewer.tsx`

**Status**: Already implemented correctly in previous session

**Purpose**: Renders collapsible UI sections

---

### 6. **structured-chat-test.tsx** - New Test Component

**File**: `components/structured-chat-test.tsx`

**Purpose**: Standalone test page for structured SSE

**Features**:
- Uses `useStructuredChat` hook
- Displays messages and collapsible sections
- "Load Example" button for grocery store query
- Debug panel showing state
- Clean separation of main response vs process sections

**Access**: Navigate to `/test-sse`

---

### 7. **app/test-sse/page.tsx** - New Test Page

**File**: `app/test-sse/page.tsx`

**Purpose**: Page route for testing structured SSE

---

### 8. **STRUCTURED_SSE_INTEGRATION.md** - Integration Guide

**File**: Frontend root directory

**Purpose**: Complete guide for integrating into existing chat component

---

## Event Format Specification

### Structured Events (Collapsible UI)

```json
// Node execution start
{
  "type": "node_start",
  "node": "classify",
  "message": "📋 Classifying query..."
}

// Tool execution start
{
  "type": "tool_call",
  "tool": "credit_score_model",
  "input": { "loan_amount": 300000000, "revenue": 120000000 }
}

// Tool execution result
{
  "type": "tool_result",
  "tool": "credit_score_model",
  "input": { ... },
  "output": "{\n  \"credit_score\": 450,\n  \"default_probability\": 0.72\n}"
}

// Internal reasoning
{
  "type": "reasoning",
  "node": "planning",
  "content": "I need to check data completeness first..."
}

// Skipped node
{
  "type": "skip",
  "node": "counterfactual_generation",
  "message": "[counterfactual skipped — score 720 above threshold 670]"
}
```

### Text Events (Main Response)

```json
// User-facing text (from analysis/response nodes)
{
  "type": "text",
  "content": "Based on the financial analysis..."
}

// Legacy AI SDK format (still supported)
{
  "type": "text-delta",
  "id": "msg-abc123",
  "delta": "continuing the response..."
}
```

---

## Testing

### Test Page

Visit: `http://localhost:3000/test-sse`

1. Click "Load Grocery Store Example"
2. Click "Send"
3. Observe:
   - ✅ Collapsible sections appear (📋 Classifying,  Tools, etc.)
   - ✅ Main response streams as normal text
   - ✅ Debug panel shows event counts

### Backend Logs

```bash
# Run backend with debug logging
cd credence-backend
uvicorn app.main:app --reload --log-level debug
```

Expected logs:
```
DEBUG:app.routers.chat:Passing through structured event: node_start
DEBUG:app.routers.chat:Passing through structured event: tool_call
DEBUG:app.routers.chat:Passing through structured event: text
```

### Frontend Console

Expected console output:
```
[SSE Event] node_start {type: 'node_start', node: 'classify', message: '📋 Classifying query...'}
[SSE Event] tool_call {type: 'tool_call', tool: 'credit_score_model', input: {...}}
[SSE Event] text {type: 'text', content: 'Based on the analysis...'}
```

---

## Migration Path

### Phase 1: Testing (Current)
- ✅ Backend changes deployed
- ✅ Test page created at `/test-sse`
- ✅ Integration guide written
- 🔄 Test with real queries

### Phase 2: Main Chat Integration
- Replace `useChat` with `useStructuredChat` in `components/chat.tsx`
- Add `<ProcessViewer sections={collapsibleSections} />` component
- Test with existing chat flows
- Handle edge cases (errors, aborts, reconnects)

### Phase 3: Production
- Remove AI SDK dependency (optional)
- Add analytics for event tracking
- Optimize collapsible section rendering
- Add keyboard shortcuts to expand/collapse

---

## Troubleshooting

### Issue: No collapsible sections appear

**Check**:
1. Browser console for `[SSE Event]` logs
2. Backend logs for "Passing through structured event"
3. Network tab - verify events have `type` field

**Fix**: Ensure `event_type in ["node_start", ...]` check in router

---

### Issue: Stream stops mid-response

**Check**:
1. Backend logs for exceptions
2. `_transform_event_to_sse` error handling
3. Router exception handling

**Fix**: Add try-catch blocks, check for `AttributeError` on dict access

---

### Issue: Text appears in wrong section

**Check**:
1. Verify `USER_FACING_NODES` in `langgraph_agent.py`
2. Check `handleEvent` switch statement in hook
3. Confirm `type: "text"` vs `type: "reasoning"`

**Fix**: Ensure analysis/response nodes emit `type: "text"`

---

## Files Modified Summary

### Backend (3 files)
1. `app/ai/langgraph_agent.py` - Simplified event format
2. `app/routers/chat.py` - Pass-through router
3. `STRUCTURED_SSE_CHANGES.md` (this file)

### Frontend (5 files)
1. `hooks/use-structured-chat.ts` - Raw SSE reader (rewritten)
2. `components/structured-chat-test.tsx` - Test component (new)
3. `app/test-sse/page.tsx` - Test page (new)
4. `STRUCTURED_SSE_INTEGRATION.md` - Integration guide (new)
5. `lib/sse-handler.ts` - Unchanged (from previous session)
6. `components/process-viewer.tsx` - Unchanged (from previous session)

---

## Success Criteria

- [x] Backend emits clean structured events without `choices` wrapper
- [x] Router passes through custom events unchanged
- [x] Frontend uses raw SSE reader (no AI SDK transformation)
- [x] Test page created at `/test-sse`
- [x] Integration guide written
- [ ] Tested with grocery store query (next step)
- [ ] Collapsible sections appear correctly
- [ ] Main text streams separately from process sections

---

## Next Steps

1. **Test the implementation**:
   ```bash
   # Terminal 1 - Backend
   cd credence-backend
   uvicorn app.main:app --reload --log-level debug

   # Terminal 2 - Frontend
   cd credence-chat
   npm run dev
   ```

2. **Navigate to**: `http://localhost:3000/test-sse`

3. **Send grocery store query** and verify:
   - Collapsible sections for tools/nodes
   - Main response in separate area
   - Clean event separation

4. **Check console** for `[SSE Event]` logs

5. **Review backend logs** for structured event pass-through

6. **Report results** with screenshots and console output
