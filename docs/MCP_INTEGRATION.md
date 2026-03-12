# MCP Integration Guide

This guide explains how to integrate MCP (Model Context Protocol) tools into the CreditAI LangGraph agent.

## Overview

The MCP integration allows the LangGraph agent to consume external data sources via MCP servers, such as:
- **Supabase**: Fetch merchant profiles, transaction history, etc.
- **CRM systems**: Retrieve customer data
- **External APIs**: Access third-party data sources

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Agent                          │
│                                                             │
│  ┌──────────────┐      ┌─────────────────────────────┐    │
│  │   classify   │─────▶│  fetch_merchant_data_node   │    │
│  └──────────────┘      └─────────────────────────────┘    │
│                                     │                      │
│                                     ▼                      │
│                         ┌─────────────────────┐            │
│                         │  MCP Client         │            │
│                         │  (langchain-mcp)    │            │
│                         └─────────────────────┘            │
│                                     │                      │
└─────────────────────────────────────┼──────────────────────┘
                                      │
                                      ▼
                        ┌──────────────────────────┐
                        │   MCP Server (Supabase)  │
                        │   http://localhost:8000  │
                        └──────────────────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   Supabase    │
                              │   Database    │
                              └───────────────┘
```

## Setup

### 1. Install Dependencies

```bash
pip install langchain-mcp-adapters
```

This is already added to `requirements.txt`.

### 2. Configure Environment Variables

Add the following to your `.env` file:

```env
# MCP (Model Context Protocol) Configuration
MCP_SUPABASE_URL=http://localhost:8000/sse
MCP_SUPABASE_TRANSPORT=sse
```

**Configuration Options:**
- `MCP_SUPABASE_URL`: The SSE endpoint of your Supabase MCP server
- `MCP_SUPABASE_TRANSPORT`: Transport protocol (`sse` or `stdio`)

### 3. Start MCP Server

You need to run a Supabase MCP server that exposes merchant data tools.

Example MCP server (Python):

```python
# supabase_mcp_server.py
from mcp import Server
from mcp.server import stdio_server, sse_server
from supabase import create_client

# Initialize Supabase client
supabase = create_client(
    "https://your-project.supabase.co",
    "your-anon-key"
)

# Define MCP tool
async def fetch_merchant_by_id(merchant_id: str):
    """Fetch merchant profile from Supabase by merchant_id."""
    result = supabase.table("merchants").select("*").eq("id", merchant_id).execute()
    if result.data:
        return result.data[0]
    return {"error": "Merchant not found"}

# Create MCP server
server = Server("supabase-mcp")
server.add_tool("fetch_merchant_by_id", fetch_merchant_by_id)

# Run SSE server
if __name__ == "__main__":
    sse_server(server, port=8000)
```

Run the server:

```bash
python supabase_mcp_server.py
```

## Usage

### 1. Initialize MCP Tools in Agent

```python
from app.ai.langgraph_agent import LangGraphAgent

# Create agent
agent = LangGraphAgent()

# Register standard tools
agent.register_tools([...])

# Register MCP tools
await agent.register_mcp_tools()
```

### 2. Use Agent with Merchant Assessment

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

**Workflow:**

1. **classify** → Identifies this as a full loan assessment
2. **fetch_merchant_data** → Extracts merchant_id="4827", calls MCP tool
3. **document_ingestion** → Processes any uploaded documents
4. **data_completeness** → Checks if required fields are present
5. **credit_scoring** → Calculates credit score using merchant data
6. **explainability** → Generates SHAP explanations
7. **fairness_check** → Validates fairness
8. **analysis** → Synthesizes findings
9. **response** → Generates final report

## Merchant Profile Schema

The `fetch_merchant_data_node` stores merchant data in state:

```python
state["merchant_profile"] = {
    "merchant_id": "4827",
    "name": "Coffee Shop Co.",
    "industry": "Food & Beverage",
    "registration_date": "2020-01-15",
    "annual_revenue": 250000,
    "monthly_transactions": 1200,
    "average_transaction_value": 25.50,
    "credit_history": {...},
    "payment_behavior": {...}
}
```

This profile is then used by downstream nodes:
- **data_completeness**: Checks if critical fields are present
- **credit_scoring**: Uses revenue, transaction data for scoring
- **analysis**: Synthesizes merchant profile into final report

## MCP Client API

### get_mcp_tools()

Retrieve all MCP tools from configured servers:

```python
from app.ai.mcp_client import get_mcp_tools

tools = await get_mcp_tools()
# Returns: List[BaseTool]
```

### get_mcp_client()

Get raw MCP client (async context manager):

```python
from app.ai.mcp_client import get_mcp_client

async with get_mcp_client() as client:
    tools = client.get_tools()
    # Use tools...
```

### get_supabase_tool()

Get specific tool by name:

```python
from app.ai.mcp_client import get_supabase_tool

merchant_tool = await get_supabase_tool("fetch_merchant_by_id")
result = await merchant_tool.ainvoke({"merchant_id": "4827"})
```

## Merchant ID Extraction

The `fetch_merchant_data_node` automatically extracts merchant_id from user input:

**Supported patterns:**
- `"Assess merchant ID 4827"` → `"4827"`
- `"merchant_id: ABC-123"` → `"ABC-123"`
- `"Evaluate merchant 4827"` → `"4827"`
- `"ID: 4827"` → `"4827"`
- `"assess 4827"` → `"4827"`

## Error Handling

The integration handles errors gracefully:

1. **No MCP server configured**: Agent runs without MCP tools
2. **Merchant ID not found**: Continues with partial data
3. **MCP tool unavailable**: Logs warning, continues workflow
4. **Tool invocation fails**: Stores error in merchant_profile, continues

## Extending with Additional MCP Servers

To add more MCP servers (e.g., CRM, external APIs):

### 1. Update config.py

```python
# Add to Settings class
mcp_crm_url: str = ""
mcp_crm_transport: str = "sse"
```

### 2. Update mcp_client.py

```python
def get_mcp_server_config():
    config = {}

    # Supabase
    if settings.mcp_supabase_url:
        config["supabase"] = {...}

    # CRM (NEW)
    if settings.mcp_crm_url:
        config["crm"] = {
            "url": settings.mcp_crm_url,
            "transport": settings.mcp_crm_transport
        }

    return config
```

### 3. Create New Node (Optional)

If you need specialized processing for CRM data, create a new node:

```python
# app/ai/nodes/fetch_crm_data.py
async def fetch_crm_data_node(state, llm, tools):
    # Extract customer_id
    # Call CRM MCP tool
    # Store in state["crm_profile"]
    ...
```

## Testing

### Manual Test

```python
import asyncio
from app.ai.mcp_client import get_mcp_tools

async def test_mcp():
    tools = await get_mcp_tools()
    print(f"Available MCP tools: {[t.name for t in tools]}")

    merchant_tool = tools[0]
    result = await merchant_tool.ainvoke({"merchant_id": "4827"})
    print(f"Merchant data: {result}")

asyncio.run(test_mcp())
```

### Integration Test

```python
import asyncio
from app.ai.langgraph_agent import LangGraphAgent

async def test_agent():
    agent = LangGraphAgent()
    await agent.register_mcp_tools()

    async for chunk in agent.stream_chat_completion(
        model="agent/loan-analyst",
        messages=[{"role": "user", "content": "Assess merchant 4827"}]
    ):
        print(chunk)

asyncio.run(test_agent())
```

## Troubleshooting

### Issue: "No MCP servers configured"

**Solution:** Check that `MCP_SUPABASE_URL` is set in `.env`

### Issue: "MCP client connection failed"

**Solution:** Ensure MCP server is running:
```bash
curl http://localhost:8000/sse
```

### Issue: "MCP tool not found"

**Solution:** Check available tools:
```python
tools = await get_mcp_tools()
print([t.name for t in tools])
```

### Issue: Merchant ID not extracted

**Solution:** Check input pattern. Add custom pattern to `extract_merchant_id()`:
```python
# In fetch_merchant_data.py
pattern5 = r'your_custom_pattern'
```

## Production Considerations

1. **Connection Pooling**: The `get_mcp_client()` context manager handles cleanup automatically

2. **Timeouts**: Add timeout handling for MCP tool calls:
   ```python
   import asyncio

   result = await asyncio.wait_for(
       merchant_tool.ainvoke({...}),
       timeout=5.0
   )
   ```

3. **Caching**: Consider caching merchant profiles to reduce MCP calls

4. **Monitoring**: Log MCP tool performance:
   ```python
   import time
   start = time.time()
   result = await merchant_tool.ainvoke({...})
   logger.info(f"MCP call took {time.time() - start:.2f}s")
   ```

5. **Fallback**: If MCP fails, continue with user-provided data:
   ```python
   try:
       merchant_profile = await fetch_from_mcp(merchant_id)
   except Exception as e:
       logger.warning(f"MCP failed, using user data: {e}")
       merchant_profile = extract_from_user_input(state)
   ```

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [langchain-mcp-adapters Documentation](https://github.com/rectalogic/langchain-mcp-adapters)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
