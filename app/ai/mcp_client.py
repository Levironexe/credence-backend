"""
MCP (Model Context Protocol) Client Integration

This module provides MCP server connectivity for LangGraph agents,
enabling access to external data sources (Supabase, APIs, etc.) via MCP tools.

Usage:
    async with get_mcp_client() as client:
        tools = client.get_tools()
        # Use tools in LangGraph ToolNode
"""

import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient
from app.config import settings

logger = logging.getLogger(__name__)


# ============ MCP SERVER CONFIGURATION ============

def get_mcp_server_config() -> Dict[str, Dict[str, Any]]:
    """
    Get MCP server configuration from environment variables.

    Configuration is loaded from app.config.settings, which reads from .env:
    - MCP_SUPABASE_URL: Supabase MCP server SSE endpoint
    - MCP_SUPABASE_TRANSPORT: Transport type (default: "sse")

    Returns:
        Dictionary of MCP server configurations

    Example:
        {
            "supabase": {
                "url": "http://localhost:8000/sse",
                "transport": "sse"
            }
        }
    """
    config = {}

    # Supabase MCP Server
    supabase_url = getattr(settings, 'mcp_supabase_url', None)
    if supabase_url:
        config["supabase"] = {
            "url": supabase_url,
            "transport": getattr(settings, 'mcp_supabase_transport', "sse")
        }
        logger.info(f"✅ Configured Supabase MCP server: {supabase_url}")
    else:
        logger.warning("⚠️ MCP_SUPABASE_URL not configured - Supabase tools unavailable")

    # Add additional MCP servers here as needed
    # Example:
    # crm_url = getattr(settings, 'mcp_crm_url', None)
    # if crm_url:
    #     config["crm"] = {
    #         "url": crm_url,
    #         "transport": "sse"
    #     }

    return config


# ============ MCP CLIENT MANAGER ============

@asynccontextmanager
async def get_mcp_client() -> MultiServerMCPClient:
    """
    Create and manage MCP client connection lifecycle.

    This is an async context manager that handles:
    - Connection initialization
    - Automatic cleanup on exit
    - Error handling

    Yields:
        MultiServerMCPClient: Connected MCP client instance

    Usage:
        async with get_mcp_client() as client:
            tools = client.get_tools()
            # tools is a list of LangChain-compatible tools

    Raises:
        Exception: If no MCP servers are configured or connection fails
    """
    server_config = get_mcp_server_config()

    if not server_config:
        logger.error("❌ No MCP servers configured - check your .env file")
        raise ValueError(
            "No MCP servers configured. Please set MCP_SUPABASE_URL in .env"
        )

    logger.info(f"🔌 Initializing MCP client with {len(server_config)} server(s)...")

    try:
        async with MultiServerMCPClient(server_config) as client:
            logger.info("✅ MCP client connected successfully")
            yield client
    except Exception as e:
        logger.error(f"❌ MCP client connection failed: {str(e)}")
        raise


# ============ TOOL RETRIEVAL HELPERS ============

async def get_mcp_tools() -> list:
    """
    Retrieve all available MCP tools from configured servers.

    This is a convenience function that creates a client, fetches tools,
    and handles cleanup automatically.

    Returns:
        List of LangChain-compatible tools from all MCP servers

    Example:
        tools = await get_mcp_tools()
        # tools can be registered with LangGraph ToolNode

    Raises:
        Exception: If MCP client connection fails
    """
    async with get_mcp_client() as client:
        tools = client.get_tools()
        logger.info(f"📦 Retrieved {len(tools)} MCP tools: {[t.name for t in tools]}")
        return tools


async def get_supabase_tool(tool_name: str) -> Optional[Any]:
    """
    Get a specific tool from Supabase MCP server by name.

    Args:
        tool_name: Name of the tool to retrieve (e.g., "fetch_merchant_by_id")

    Returns:
        LangChain tool instance or None if not found

    Example:
        merchant_tool = await get_supabase_tool("fetch_merchant_by_id")
        if merchant_tool:
            result = await merchant_tool.ainvoke({"merchant_id": "4827"})
    """
    async with get_mcp_client() as client:
        tools = client.get_tools()
        tool = next((t for t in tools if t.name == tool_name), None)

        if tool:
            logger.info(f"✅ Found MCP tool: {tool_name}")
        else:
            logger.warning(f"⚠️ MCP tool not found: {tool_name}")
            logger.info(f"Available tools: {[t.name for t in tools]}")

        return tool
