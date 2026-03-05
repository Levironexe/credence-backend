# Aegis AI - Course Questions Presentation

---

## 04 - ReAct Pattern

### ReAct: Reasoning and Acting

**What is ReAct?**
- LLM combines **reasoning** (thinking) and **acting** (tool use) in a loop
- Agent alternates between: Thought → Action → Observation → Thought...

**How Our Agent Decides to Act:**

1. **Classification** - Pattern matching or LLM determines query type
2. **Planning** - Agent reasons about what investigation is needed
3. **Tool Selection** - LLM chooses tools based on context
4. **Execution** - Tools run and return observations
5. **Analysis** - Agent reasons about tool results
6. **Response** - Final answer based on reasoning + observations

**Example Flow:**
```
User: "Analyze this log: admin' OR '1'='1'"
↓
Thought: "This looks like SQL injection"
Action: Call signature_detector(log_text="admin' OR '1'='1'")
Observation: {detected: "sqli", severity: "CRITICAL"}
Thought: "Confirmed SQLi, map to MITRE"
Action: Call mitre_attack_mapper(attack_type="sqli")
Observation: {technique: "T1190", tactic: "Initial Access"}
Response: "Critical SQL injection detected..."
```

---

## 05 - LLM Tool Use Mechanism

### How Tool Calling Works

**Process Overview:**

1. **Tool Registration**
   - Tools defined with name, description, and input schema
   - Converted to LangChain `StructuredTool` format

2. **LLM Binding**
   ```python
   llm_with_tools = self.llm.bind_tools(self.tools)
   ```
   - LLM receives tool definitions in its system context

3. **JSON-Style Request Generation**
   - LLM decides which tool to call
   - Generates structured output:
   ```json
   {
     "tool": "signature_detector",
     "args": {
       "log_text": "admin' OR '1'='1'",
       "signature_types": ["sqli"]
     }
   }
   ```

4. **Tool Execution**
   - LangGraph's `ToolNode` catches tool calls
   - Executes the tool with validated inputs
   - Returns results to LLM

5. **Result Integration**
   - Tool output added to message history
   - LLM uses results for final response

**Key Code:**
```python
# Tool definition
class SignatureDetectorInput(BaseModel):
    log_text: str
    signature_types: Optional[List[str]] = None

# LLM generates this automatically
tool_call = {
    "name": "signaturedetector",
    "args": {"log_text": "...", "signature_types": ["sqli"]}
}
```

---

## 06 - Context Window Management

### Short-Term Memory Strategy

**Our Approach: Stateful Message History**

**1. Full Message Passing**
- LangGraph maintains `messages` list in state
- Each node receives complete conversation history
- No truncation - all context preserved within workflow

**2. State Management**
```python
class CyberSecurityState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    investigation_steps: List[str]
    iocs_found: List[str]
    tools_used: List[str]
    # ... other fields
```

**3. Why This Works for Our Use Case**
- Cybersecurity investigations are typically **single queries**
- Not long multi-turn conversations
- Each investigation is self-contained

**4. Memory Between Turns**
- FastAPI stores conversation history per `chat_id`
- Database: `chats` table with `messages` JSON field
- New message → Load history → Run agent → Save updated history

**Example:**
```python
# Load previous messages
previous_messages = db_chat.messages or []

# Add new user message
messages = previous_messages + [{"role": "user", "content": query}]

# Run agent with full history
result = await agent.stream_chat_completion(messages=messages)

# Save complete history
db_chat.messages = messages + [{"role": "assistant", "content": result}]
```

**Trade-offs:**
- ✅ Simple and reliable
- ✅ No information loss
- ⚠️ Limited to ~200k tokens (Claude's window)
- ⚠️ Costs increase with conversation length

**Future Optimization:**
- Could implement sliding window (last N messages)
- Could use summarization for long conversations
- Current approach sufficient for SOC analyst workflows

---

