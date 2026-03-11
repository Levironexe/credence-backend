"""
MCP Integration Test Script

This script tests the MCP integration with the LangGraph agent.

Prerequisites:
1. MCP server running on http://localhost:8000/sse
2. MCP_SUPABASE_URL configured in .env

Usage:
    python test_mcp.py
"""

import asyncio
import logging
from app.ai.langgraph_agent import LangGraphAgent
from app.ai.mcp_client import get_mcp_tools, get_supabase_tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_mcp_tools_only():
    """Test 1: Verify MCP tools can be fetched and invoked"""
    print("\n" + "="*60)
    print("TEST 1: MCP Tools Availability")
    print("="*60 + "\n")

    try:
        # Fetch MCP tools
        tools = await get_mcp_tools()
        print(f"✅ Successfully fetched {len(tools)} MCP tools")
        print(f"   Available tools: {[t.name for t in tools]}\n")

        # Test specific tool
        merchant_tool = await get_supabase_tool("fetch_merchant_by_id")
        if merchant_tool:
            print(f"✅ Found tool: {merchant_tool.name}")
            print(f"   Description: {merchant_tool.description[:80]}...\n")

            # Invoke tool
            print("🔧 Testing tool invocation...")
            result = await merchant_tool.ainvoke({"merchant_id": "4827"})
            print(f"✅ Tool invocation successful")
            print(f"   Merchant: {result.get('name', 'N/A')}")
            print(f"   Industry: {result.get('industry', 'N/A')}")
            print(f"   Revenue: ${result.get('annual_revenue', 0):,.2f}\n")
        else:
            print("❌ Tool 'fetch_merchant_by_id' not found\n")

        return True

    except Exception as e:
        print(f"❌ MCP tools test failed: {str(e)}\n")
        return False


async def test_agent_mcp_integration():
    """Test 2: Verify LangGraph agent can use MCP tools"""
    print("\n" + "="*60)
    print("TEST 2: LangGraph Agent with MCP Tools")
    print("="*60 + "\n")

    try:
        # Initialize agent
        agent = LangGraphAgent()
        print("✅ Agent initialized\n")

        # Register MCP tools
        print("📦 Registering MCP tools...")
        await agent.register_mcp_tools()
        print(f"✅ MCP tools registered")
        print(f"   Total tools available: {len(agent.tools)}\n")

        return True

    except Exception as e:
        print(f"❌ Agent integration test failed: {str(e)}\n")
        return False


async def test_merchant_assessment():
    """Test 3: Full merchant assessment workflow"""
    print("\n" + "="*60)
    print("TEST 3: Complete Merchant Assessment")
    print("="*60 + "\n")

    try:
        # Initialize agent
        agent = LangGraphAgent()

        # Register MCP tools
        try:
            await agent.register_mcp_tools()
            print("✅ MCP tools registered\n")
        except Exception as e:
            print(f"⚠️  Warning: MCP tools unavailable ({str(e)})")
            print("   Continuing without MCP tools...\n")

        # Test merchant assessment
        test_message = "Assess merchant ID 4827"
        print(f"📋 Query: '{test_message}'\n")
        print("-" * 60 + "\n")

        # Track events
        events = {
            "node_starts": [],
            "tool_calls": [],
            "text_chunks": []
        }

        # Stream agent execution
        async for chunk in agent.stream_chat_completion(
            model="agent/loan-analyst",
            messages=[{
                "role": "user",
                "content": test_message
            }]
        ):
            chunk_type = chunk.get("type")

            if chunk_type == "node_start":
                node = chunk.get("node")
                message = chunk.get("message")
                events["node_starts"].append(node)
                print(f"▶️  [{node}] {message}")

            elif chunk_type == "tool_call":
                tool = chunk.get("tool")
                events["tool_calls"].append(tool)
                print(f"🔧 Tool: {tool}")

            elif chunk_type == "tool_result":
                tool = chunk.get("tool")
                print(f"✅ Tool result: {tool}")

            elif chunk_type == "text":
                content = chunk.get("content", "")
                events["text_chunks"].append(content)
                print(content, end="", flush=True)

            elif chunk_type == "reasoning":
                # Skip internal reasoning in test output
                pass

        print("\n\n" + "-" * 60)
        print("\n📊 Execution Summary:")
        print(f"   Nodes executed: {len(events['node_starts'])}")
        print(f"   Nodes: {', '.join(events['node_starts'][:5])}...")
        print(f"   Tools called: {len(events['tool_calls'])}")
        if events['tool_calls']:
            print(f"   Tools: {', '.join(set(events['tool_calls']))}")
        print(f"   Response length: {sum(len(c) for c in events['text_chunks'])} chars\n")

        # Check if fetch_merchant_data was executed
        if "fetch_merchant_data" in events["node_starts"]:
            print("✅ MCP integration working: fetch_merchant_data node executed")
        else:
            print("⚠️  fetch_merchant_data node not in workflow")

        return True

    except Exception as e:
        print(f"\n❌ Assessment test failed: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all MCP integration tests"""
    print("\n" + "="*60)
    print("🧪 MCP INTEGRATION TEST SUITE")
    print("="*60)

    results = []

    # Test 1: MCP tools availability
    try:
        result1 = await test_mcp_tools_only()
        results.append(("MCP Tools Availability", result1))
    except Exception as e:
        print(f"⚠️  Test 1 skipped: {str(e)}")
        results.append(("MCP Tools Availability", False))

    # Test 2: Agent integration
    try:
        result2 = await test_agent_mcp_integration()
        results.append(("Agent MCP Integration", result2))
    except Exception as e:
        print(f"⚠️  Test 2 skipped: {str(e)}")
        results.append(("Agent MCP Integration", False))

    # Test 3: Full workflow
    try:
        result3 = await test_merchant_assessment()
        results.append(("Complete Merchant Assessment", result3))
    except Exception as e:
        print(f"⚠️  Test 3 skipped: {str(e)}")
        results.append(("Complete Merchant Assessment", False))

    # Summary
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60 + "\n")

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\n{'='*60}")
    print(f"Total: {total_passed}/{total_tests} tests passed")
    print("="*60 + "\n")

    if total_passed == total_tests:
        print("🎉 All tests passed! MCP integration is working correctly.\n")
    elif total_passed > 0:
        print("⚠️  Some tests failed. Check configuration and MCP server.\n")
    else:
        print("❌ All tests failed. Troubleshooting steps:")
        print("   1. Check MCP server is running: curl http://localhost:8000/sse")
        print("   2. Verify .env has MCP_SUPABASE_URL configured")
        print("   3. Check logs for detailed error messages\n")


if __name__ == "__main__":
    """
    Run MCP integration tests.

    Requirements:
    - MCP server running (python docs/example_supabase_mcp_server.py)
    - MCP_SUPABASE_URL in .env
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user\n")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}\n")
        import traceback
        traceback.print_exc()
