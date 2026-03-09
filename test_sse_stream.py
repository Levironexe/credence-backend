#!/usr/bin/env python3
"""
Direct SSE stream tester - bypasses frontend to debug backend streaming
"""

import asyncio
import httpx
import json

async def test_sse_stream():
    """Test the SSE stream directly"""

    url = "http://localhost:8000/api/chat"

    payload = {
        "id": "test-123",
        "messages": [
            {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": "A small grocery store in Ho Chi Minh City:\n- Monthly revenue: 120 million VND\n- Operating margin: 18%\n- Business tenure: 3 years\n- Industry: retail grocery\n- Loan requested: 300 million VND\n\nPlease assess this loan application."
                    }
                ]
            }
        ],
        "selectedChatModel": "agent/loan-analyst",
        "selectedVisibilityType": "private"
    }

    print("🚀 Starting SSE stream test...")
    print(f"📡 URL: {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}\n")
    print("=" * 80)
    print("STREAMING EVENTS:")
    print("=" * 80)

    event_count = 0
    event_types = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            print(f"✅ Connected - Status: {response.status_code}\n")

            if response.status_code != 200:
                print(f" Error: {response.status_code}")
                print(await response.aread())
                return

            buffer = ""
            async for chunk in response.aiter_bytes():
                text = chunk.decode('utf-8')
                buffer += text

                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)

                    if line.startswith('data: '):
                        data = line[6:].strip()
                        if not data or data == '[DONE]':
                            continue

                        try:
                            event = json.loads(data)
                            event_count += 1
                            event_type = event.get('type', 'unknown')

                            # Count event types
                            event_types[event_type] = event_types.get(event_type, 0) + 1

                            # Print event
                            if event_type == "node_start":
                                print(f"\n[{event_count}] 🎯 NODE_START: {event.get('node')} - {event.get('message')}")
                            elif event_type == "tool_call":
                                print(f"[{event_count}]  TOOL_CALL: {event.get('tool')}")
                                print(f"    Input: {json.dumps(event.get('input', {}), indent=2)[:200]}...")
                            elif event_type == "tool_result":
                                print(f"[{event_count}] TOOL_RESULT: {event.get('tool')}")
                                output = event.get('output', '')
                                print(f"    Output: {str(output)[:200]}...")
                            elif event_type == "reasoning":
                                content = event.get('content', '')
                                print(f"[{event_count}]  REASONING ({event.get('node')}): {content[:100]}...")
                            elif event_type == "text":
                                content = event.get('content', '')
                                print(f"[{event_count}]  TEXT: {content[:100]}...")
                            elif event_type == "text-delta":
                                delta = event.get('delta', '')
                                print(f"[{event_count}]  TEXT-DELTA: {delta[:100]}...")
                            elif event_type == "skip":
                                print(f"[{event_count}]   SKIP: {event.get('node')} - {event.get('message')}")
                            elif event_type == "error":
                                print(f"\n[{event_count}]  ERROR: {event.get('error')}")
                                print(f"    Traceback: {event.get('traceback')}")
                            else:
                                print(f"[{event_count}]  {event_type.upper()}: {json.dumps(event, indent=2)[:200]}")

                        except json.JSONDecodeError as e:
                            print(f"⚠️  Parse error: {e}")
                            print(f"    Data: {data[:200]}")

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    print(f"Total events: {event_count}")
    print(f"\nEvent breakdown:")
    for event_type, count in sorted(event_types.items()):
        print(f"  {event_type}: {count}")

    if event_count == 0:
        print("\n NO EVENTS RECEIVED - Check backend logs!")
    elif event_count == 1 or (event_count == 2 and event_types.get('node_start') == 2):
        print("\n⚠️  STREAM STOPPED EARLY - Only classify node_start received!")
        print("    Check backend logs for errors in LangGraph execution")
    else:
        print("\n✅ Stream appears healthy")

if __name__ == "__main__":
    asyncio.run(test_sse_stream())
