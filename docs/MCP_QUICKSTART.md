# MCP Integration - Quick Start

This guide gets you up and running with MCP tools in CreditAI in 5 minutes.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd credence-backend
pip install langchain-mcp-adapters
```

### 2. Configure Environment

Add to `.env`:

```env
# MCP Configuration
MCP_SUPABASE_URL=http://localhost:8000/sse
MCP_SUPABASE_TRANSPORT=sse
```

### 3. Start MCP Server

```bash
# In a separate terminal
python docs/example_supabase_mcp_server.py
```

### 4. Initialize Agent with MCP Tools

```python
from app.ai.langgraph_agent import LangGraphAgent

# Create agent
agent = LangGraphAgent()

# Register standard tools
agent.register_tools([...])  # Your existing tools

# Register MCP tools
await agent.register_mcp_tools()
```

### 5. Test Merchant Assessment

```python
async for chunk in agent.stream_chat_completion(
    model="agent/loan-analyst",
    messages=[{
        "role": "user",
        "content": "Assess merchant ID 4827"
    }]
):
    print(chunk)
```

## 📊 What Happens

```
User Input: "Assess merchant ID 4827"
     ↓
[classify] → Intent: full_assessment
     ↓
[fetch_merchant_data] → Extracts merchant_id="4827"
     ↓                    Calls MCP Supabase tool
     ↓                    Stores merchant_profile in state
     ↓
[document_ingestion] → Processes documents
     ↓
[data_completeness] → Checks completeness using merchant_profile
     ↓
[credit_scoring] → Calculates score using merchant data
     ↓
[explainability] → SHAP analysis
     ↓
[analysis] → Synthesizes findings
     ↓
[response] → Final credit report
```

## 🔧 Files Created

| File | Purpose |
|------|---------|
| `app/ai/mcp_client.py` | MCP client connection manager |
| `app/ai/nodes/fetch_merchant_data.py` | LangGraph node for merchant data fetch |
| `app/ai/state.py` | Updated with `merchant_profile` field |
| `app/config.py` | MCP configuration settings |
| `docs/MCP_INTEGRATION.md` | Comprehensive documentation |
| `docs/example_supabase_mcp_server.py` | Example MCP server |

## 🧪 Test Script

Create `test_mcp.py`:

```python
import asyncio
from app.ai.langgraph_agent import LangGraphAgent

async def test_mcp_integration():
    """Test MCP integration with merchant assessment"""
    print("🧪 Testing MCP Integration\n")

    # Initialize agent
    agent = LangGraphAgent()
    print("✅ Agent initialized")

    # Register MCP tools
    try:
        await agent.register_mcp_tools()
        print("✅ MCP tools registered\n")
    except Exception as e:
        print(f"⚠️  MCP tools unavailable: {e}\n")

    # Test merchant assessment
    print("📋 Testing: 'Assess merchant ID 4827'\n")

    async for chunk in agent.stream_chat_completion(
        model="agent/loan-analyst",
        messages=[{
            "role": "user",
            "content": "Assess merchant ID 4827"
        }]
    ):
        # Print structured events
        if chunk.get("type") == "node_start":
            print(f"▶️  {chunk.get('message')}")
        elif chunk.get("type") == "tool_call":
            print(f"🔧 Tool: {chunk.get('tool')}")
        elif chunk.get("type") == "text":
            print(chunk.get("content"), end="", flush=True)

    print("\n\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(test_mcp_integration())
```

Run test:

```bash
python test_mcp.py
```

## 🎯 Expected Output

```
🧪 Testing MCP Integration

✅ Agent initialized
📦 Fetching MCP tools...
✅ Registered 2 MCP tools: ['fetch_merchant_by_id', 'query_merchants']
✅ MCP tools registered

📋 Testing: 'Assess merchant ID 4827'

▶️  Classifying query
▶️  Fetching merchant profile
🔧 Tool: fetch_merchant_by_id
✅ Merchant data retrieved: Coffee Shop Co.
▶️  Processing documents
▶️  Checking data completeness
▶️  Computing credit score
▶️  Running SHAP explainability
▶️  Running fairness validation
▶️  Synthesizing findings
▶️  Generating report

# Credit Assessment Report: Coffee Shop Co. (ID: 4827)

**Credit Score:** 720 (Good)
**Recommendation:** Approve

## Merchant Profile
- **Industry:** Food & Beverage
- **Annual Revenue:** $250,000
- **Monthly Transactions:** 1,200
...

✅ Test complete!
```

## 🔍 Debugging

### Check MCP Server is Running

```bash
curl http://localhost:8000/sse
```

### Check Available Tools

```python
from app.ai.mcp_client import get_mcp_tools

tools = await get_mcp_tools()
print([t.name for t in tools])
# Output: ['fetch_merchant_by_id', 'query_merchants']
```

### Check Merchant ID Extraction

```python
from app.ai.nodes.fetch_merchant_data import extract_merchant_id

text = "Assess merchant ID 4827"
merchant_id = extract_merchant_id(text)
print(merchant_id)  # Output: "4827"
```

## 📚 Next Steps

- **Production Setup**: See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for production deployment
- **Custom MCP Servers**: Add CRM, external APIs
- **Advanced Features**: Caching, monitoring, fallbacks

## ⚡ Common Issues

| Issue | Solution |
|-------|----------|
| "No MCP servers configured" | Add `MCP_SUPABASE_URL` to `.env` |
| "MCP client connection failed" | Start MCP server: `python docs/example_supabase_mcp_server.py` |
| "Merchant ID not extracted" | Check input pattern or add custom regex in `fetch_merchant_data.py` |
| MCP tools not appearing | Check server is running and URL is correct |

## 🎓 Key Concepts

1. **MCP Client** (`app/ai/mcp_client.py`): Manages connection to MCP servers
2. **MCP Tools**: LangChain-compatible tools from external sources
3. **Fetch Node** (`fetch_merchant_data.py`): LangGraph node that calls MCP tools
4. **State Management**: Merchant profile stored in `state["merchant_profile"]`
5. **Tool Registration**: `await agent.register_mcp_tools()` fetches and registers tools

## 📖 Full Documentation

See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for complete guide including:
- Architecture diagrams
- Production considerations
- Error handling
- Monitoring & performance
- Extending with additional MCP servers
