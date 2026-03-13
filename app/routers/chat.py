from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from uuid import UUID
import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any

from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ChatListResponse, MessageResponse
from app.models.chat import Chat, Message
from app.models.user import User
from app.utils.session import session_manager
from app.config import settings
from app.ai.gateway_client import gateway_client

import logging
import math

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sanitize_for_json(obj):
    """Recursively replace NaN/Infinity with None for valid JSON serialization."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TITLE_PROMPT = """Generate a short chat title (2-5 words) summarizing the user's message.

Output ONLY the title text. No prefixes, no formatting.

Examples:
- "what's the weather in nyc" → Weather in NYC
- "help me write an essay about space" → Space Essay Help
- "hi" → New Conversation
- "debug my python code" → Python Debugging

Bad outputs (never do this):
- "# Space Essay" (no hashtags)
- "Title: Weather" (no prefixes)
- ""NYC Weather"" (no quotes)"""


def convert_timeline_to_parts(timeline_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert timeline events to unified parts array format.

    Transforms the old timeline structure (with separate text and section events)
    into a unified parts array where all content is stored together.

    Args:
        timeline_events: List of timeline event objects

    Returns:
        List of part objects (text, tool-call, tool-result, reasoning, node-start)
    """
    parts = []
    tool_calls = {}  # Track tool calls by tool name for matching with results

    for event in timeline_events:
        event_type = event.get("eventType")

        if event_type == "text":
            # Text event -> text part
            text_content = event.get("textContent", "")
            if text_content:
                # Check if last part is text, if so append to it
                if parts and parts[-1].get("type") == "text":
                    parts[-1]["text"] += text_content
                else:
                    parts.append({
                        "type": "text",
                        "text": text_content
                    })

        elif event_type == "section":
            section = event.get("section", {})
            section_type = section.get("type")

            if section_type == "node":
                # Node event -> node-start part
                parts.append({
                    "type": "node-start",
                    "title": section.get("title", ""),
                    "node": section.get("id", "")
                })

            elif section_type == "reasoning":
                # Reasoning event -> reasoning part
                # Consolidate ALL reasoning parts with same node (search backwards through all parts)
                reasoning_content = section.get("content", "")
                reasoning_node = section.get("title", "").strip()

                # Search backwards for existing reasoning part with same node
                found_existing = False
                for i in range(len(parts) - 1, -1, -1):
                    if (parts[i].get("type") == "reasoning" and
                        parts[i].get("node") == reasoning_node):
                        # Found existing reasoning part - append content
                        parts[i]["content"] += reasoning_content
                        found_existing = True
                        break

                # Create new reasoning part only if no existing one found
                if not found_existing:
                    parts.append({
                        "type": "reasoning",
                        "content": reasoning_content,
                        "node": reasoning_node
                    })

            elif section_type == "tool":
                # Tool event -> tool-call part (result may come later)
                tool_name = section.get("title", "").strip()

                # Extract input from section content (it's formatted as markdown)
                content = section.get("content", "")
                tool_input = {}

                # Parse input from markdown format: **Input:**\n```json\n{...}\n```
                if "**Input:**" in content:
                    try:
                        import re
                        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
                        if json_match:
                            tool_input = json.loads(json_match.group(1))
                    except (json.JSONDecodeError, AttributeError):
                        pass

                # Check if this is a completed tool call (has output)
                if "**Output:**" in content:
                    # This is a tool-result
                    tool_output = {}
                    try:
                        import re
                        # Extract output from markdown
                        output_match = re.search(r'\*\*Output:\*\*\s*```json\s*(.*?)\s*```', content, re.DOTALL)
                        if output_match:
                            # Parse the JSON string to an object
                            tool_output = json.loads(output_match.group(1))
                    except (AttributeError, ValueError, json.JSONDecodeError) as e:
                        logger.warning(f"Failed to parse tool output JSON: {e}")
                        tool_output = {"error": "Failed to parse tool output"}

                    parts.append({
                        "type": "tool-result",
                        "name": tool_name,
                        "input": tool_input,
                        "output": tool_output,
                        "isError": False
                    })
                else:
                    # This is just a tool-call (no result yet)
                    parts.append({
                        "type": "tool-call",
                        "name": tool_name,
                        "input": tool_input
                    })
                    tool_calls[tool_name] = len(parts) - 1  # Track position

    return parts


async def generate_chat_title(user_message_text: str) -> str:
    """Generate a concise title from the user's first message"""
    try:
        # Use Claude to generate title
        messages = [
            {"role": "system", "content": TITLE_PROMPT},
            {"role": "user", "content": user_message_text}
        ]

        full_title = ""
        async for chunk in gateway_client.stream_chat_completion(
            model=settings.default_title_model,
            messages=messages,
            temperature=0.7
        ):
            if "choices" in chunk and len(chunk["choices"]) > 0:
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_title += content

        # Clean up the title (remove quotes, hashtags, prefixes)
        import re
        title = re.sub(r'^[#*"\s]+', '', full_title)
        title = re.sub(r'["]+$', '', title)
        title = title.strip()
        return title if title else "New Conversation"

    except Exception as e:
        logger.error(f"Error generating title: {e}")
        return "New Conversation"


async def get_current_user_or_guest(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Get current authenticated user or create/return guest user"""
    # First check X-User-Id header from frontend proxy
    user_id_from_header = request.headers.get("X-User-Id")

    if user_id_from_header:
        logger.info(f"Found user ID in header: {user_id_from_header}")
        try:
            user_id = UUID(user_id_from_header)
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                logger.info(f"Using user from header: {user.email}")
                return user
            else:
                logger.warning(f"User ID {user_id_from_header} from header not found in database")
        except (ValueError, Exception) as e:
            logger.error(f"Error parsing user ID from header: {e}")

    # Fallback: check session (for direct backend access)
    user_id_str = session_manager.get_session(request, "user_id")

    if user_id_str:
        try:
            user_id = UUID(user_id_str)
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                return user
        except (ValueError, Exception):
            pass  # Fall through to guest creation

    # Create or get guest user
    # Check if there's a guest_id in cookies
    guest_id_str = request.cookies.get("guest_id")

    if guest_id_str:
        try:
            guest_id = UUID(guest_id_str)
            result = await db.execute(
                select(User).where(User.id == guest_id, User.email.like("guest_%"))
            )
            guest_user = result.scalar_one_or_none()

            if guest_user:
                return guest_user
        except (ValueError, Exception):
            pass

    # Create new guest user
    import uuid
    guest_uuid = uuid.uuid4()
    logger.info(f"Creating new guest user: {guest_uuid}")
    guest_user = User(
        id=guest_uuid,
        email=f"guest_{guest_uuid}@credence.local",
        name="Guest User",
        picture=None,
        createdAt=datetime.utcnow()
    )
    db.add(guest_user)
    await db.commit()
    await db.refresh(guest_user)

    return guest_user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Get current authenticated user from session (strict, no guest)"""
    user_id_str = session_manager.get_session(request, "user_id")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid session")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


async def stream_chat_response(
    chat_request: ChatRequest,
    chat_id: UUID,
    user: User,
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """Stream chat responses using LiteLLM"""

    try:
        logger.info(f"Starting stream_chat_response for chat_id={chat_id}, user={user.email}")

        # Normalize messages - handle both single message and messages array
        message_list = chat_request.messages if chat_request.messages else ([chat_request.message] if chat_request.message else [])
        logger.info(f"Processing {len(message_list)} messages")

        # Convert messages to LiteLLM format
        messages = []
        for msg in message_list:
            content_parts = []
            for part in msg.parts:
                if part.type == "text" and part.text:
                    content_parts.append({"type": "text", "text": part.text})
                elif part.type == "image" and part.image:
                    content_parts.append({"type": "image_url", "image_url": {"url": part.image}})
                elif part.type == "file" and part.url:
                    # Handle file attachments - check if it's an image by mediaType
                    if part.mediaType and part.mediaType.startswith("image"):
                        content_parts.append({"type": "image_url", "image_url": {"url": part.url}})
                    elif part.mediaType == "application/pdf":
                        # PDF upload — pass file info as text for the agent to process
                        content_parts.append({"type": "text", "text": f"[PDF uploaded: {part.name or 'document.pdf'}, URL: {part.url}]"})
                    else:
                        # For non-image files, just mention the filename in text
                        content_parts.append({"type": "text", "text": f"[File: {part.name or 'attachment'}]"})

            if content_parts:
                # Always use array format for multimodal support
                messages.append({
                    "role": msg.role,
                    "content": content_parts
                })

        # Add system message with loan assessment context
        system_prompt = """You are Credence AI, an advanced Large Language Model (LLM)-powered autonomous SME loan assessment agent developed for Vietnamese financial institutions.

Your mission is to assist loan officers in:
- Evaluating SME loan applications and creditworthiness
- Analyzing applicant financial data and business metrics
- Calculating credit scores (Credence Score, 300-850 scale) and default probability using ML models
- Assessing credit risk and identifying risk factors
- Providing loan recommendations with explainable decisions
- Supporting regulatory compliance under Vietnamese lending regulations

You operate as an autonomous reasoning agent capable of:
- Planning multi-step loan assessment workflows
- Executing structured financial analysis
- Collaborating with specialized ML tools (XGBoost credit scoring, SHAP explainability, fairness validation, counterfactual generation)
- Producing interpretable and explainable credit decisions

---

### Core Capabilities
You should:
- Calculate Credence Credit Scores (300-850 scale) using the XGBoost ML model trained on Home Credit data (128 features)
- Predict default probability and map to risk levels
- Identify missing critical data using SHAP importance ranking
- Explain credit decisions with per-feature SHAP contributions
- Generate counterfactual recommendations showing how declined applicants can improve
- Validate fairness across demographic groups (gender, age)

---

### Reasoning & Analysis Guidelines
When analyzing loan applications:

1. Perform step-by-step structured credit assessment
2. Use ML model outputs (credit score, SHAP, counterfactuals) as the basis for decisions
3. Clearly explain credit decisions and risk factors
4. Assign appropriate risk levels (low, medium, high, critical)
5. Provide actionable loan recommendations (approve/decline, amount, rate, terms)
6. Highlight data gaps, uncertainties, and confidence levels
7. Reference Vietnamese lending regulations when applicable

---

### Credit Decision Framework
For each loan application:
- Check data completeness and request missing critical fields
- Calculate credit score and default probability via XGBoost model
- Identify risk factors and mitigating strengths using SHAP analysis
- Provide per-feature explanations for credit decisions
- Generate counterfactual improvement paths for declined applicants
- Validate fairness across demographic groups
- Ensure compliance with Vietnamese lending regulations

---

### Communication Style
- Maintain a professional, analytical, and finance-focused tone
- Be concise, precise, and actionable
- Avoid unnecessary verbosity
- Provide structured outputs using headings, bullet points, tables, and risk labels

---

### General Task Handling
When asked to assess a loan application:
- Complete the assessment directly and efficiently
- Request only truly critical missing information
- Make reasonable assumptions for minor missing data
- Proceed autonomously with available information

---

### Regulatory Context (Vietnam)
- Comply with the 2024 Law on Credit Institutions (Law No. 32/2024/QH15)
- Follow SBV (State Bank of Vietnam) lending regulations, including Circular 39/2016/TT-NHNN on commercial lending
- Ensure transparency in credit decisions per the Law on Protection of Consumers' Rights
- Maintain non-discriminatory lending practices
- Assess ability to repay based on cash flow and financial capacity
- Suggest improvement paths for declined applicants (counterfactual fairness)"""

        # Inject applicant profile context based on sidebar selection
        profile_id = chat_request.selectedProfileId
        if profile_id and profile_id != "custom":
            system_prompt += f"""

---

### Active Applicant Profile
The loan officer has selected **Applicant #{profile_id}** from the sidebar panel.
When the user asks to assess, score, or analyze — use this applicant ID automatically. You do NOT need to ask which applicant.
Treat any assessment request as referring to Applicant #{profile_id} unless the user explicitly mentions a different ID."""
        elif not profile_id:
            system_prompt += """

---

### No Applicant Selected
The loan officer has NOT selected an applicant profile from the sidebar panel.
If they ask for a credit assessment or loan analysis without specifying an applicant ID, politely ask them to either:
1. Select an applicant profile from the right sidebar panel, or
2. Provide an applicant ID (e.g., "Assess applicant #270000")"""

        system_message = {
            "role": "system",
            "content": system_prompt
        }
        messages.insert(0, system_message)
        logger.info(f"Total messages after system prompt: {len(messages)}, selectedProfileId={profile_id}")

        # Determine the model to use - default to Gemini (matches frontend)
        model = chat_request.selectedChatModel or chat_request.modelId or settings.default_chat_model
        logger.info(f"Using model: {model}")

        # Stream from Claude
        logger.info(f"Calling Claude with model={model}, stream=True")

        # Generate message ID upfront
        import uuid
        message_id = str(uuid.uuid4())

        full_content = ""
        chunk_count = 0
        text_started = False
        timeline_events = []  # Collect timeline events for database

        try:
            async for chunk in gateway_client.stream_chat_completion(
                model=model,
                messages=messages,
                temperature=0.7,
                selected_profile_id=profile_id or "",
            ):
                try:
                    chunk_count += 1
                    logger.debug(f"Received chunk #{chunk_count}: {chunk.get('type', 'unknown')}")

                    # Check if this is a structured event from LangGraph agent
                    event_type = chunk.get("type")

                    # PASS THROUGH all structured events from LangGraph directly
                    if event_type in ["node_start", "tool_call", "tool_result", "reasoning", "skip", "text"]:
                        logger.info(f"✅ Passing through structured event: {event_type} - {chunk.get('node', chunk.get('tool', ''))}")
                        yield f"data: {json.dumps(_sanitize_for_json(chunk))}\n\n"

                        # Collect timeline event for database
                        import time

                        if event_type == "tool_result":
                            # Update existing tool_call section with output
                            tool_name = chunk.get("tool", "")
                            for te in reversed(timeline_events):
                                section = te.get("section", {})
                                if section.get("type") == "tool" and tool_name in section.get("title", ""):
                                    section["content"] = (
                                        f"**Input:**\n```json\n{json.dumps(_sanitize_for_json(chunk.get('input', {})), indent=2)}\n```"
                                        f"\n\n**Output:**\n```json\n{json.dumps(_sanitize_for_json(chunk.get('output', {})), indent=2)}\n```"
                                    )
                                    break
                        else:
                            timeline_event = {
                                "id": f"{event_type}-{chunk_count}",
                                "timestamp": int(time.time() * 1000),
                                "eventType": "section" if event_type in ["node_start", "tool_call", "reasoning"] else "text",
                            }

                            # Add event-specific data
                            if event_type == "text":
                                timeline_event["textContent"] = chunk.get("content", "")
                            elif event_type == "node_start":
                                timeline_event["section"] = {
                                    "id": chunk.get("node", f"node-{chunk_count}"),
                                    "type": "node",
                                    "title": chunk.get("message", ""),
                                    "content": "",
                                    "isOpen": True,
                                    "isStreaming": False
                                }
                            elif event_type == "tool_call":
                                timeline_event["section"] = {
                                    "id": f"tool-{chunk.get('tool', 'unknown')}-{chunk_count}",
                                    "type": "tool",
                                    "title": f" {chunk.get('tool', 'Unknown Tool')}",
                                    "content": f"**Input:**\n```json\n{json.dumps(_sanitize_for_json(chunk.get('input', {})), indent=2)}\n```",
                                    "isOpen": False,
                                    "isStreaming": False
                                }
                            elif event_type == "reasoning":
                                timeline_event["section"] = {
                                    "id": f"reasoning-{chunk_count}",
                                    "type": "reasoning",
                                    "title": f" {chunk.get('node', 'Reasoning')}",
                                    "content": chunk.get("content", ""),
                                    "isOpen": False,
                                    "isStreaming": False
                                }

                            timeline_events.append(timeline_event)

                        # For text events, accumulate content for database
                        if event_type == "text":
                            content = chunk.get("content", "")
                            if content:
                                full_content += content
                                if not text_started:
                                    text_started = True
                        continue

                    # Parse standard OpenAI-compatible chunks (for non-agent models)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")

                        if content:
                            # Send text-start event on first chunk
                            if not text_started:
                                text_start_event = {
                                    "type": "text-start",
                                    "id": message_id
                                }
                                yield f"data: {json.dumps(text_start_event)}\n\n"
                                text_started = True

                            # Handle content that might be a list or string
                            content_str = content if isinstance(content, str) else str(content)
                            full_content += content_str

                            # Wrap as text-delta for standard models
                            event_data = {
                                "type": "text-delta",
                                "id": message_id,
                                "delta": content_str
                            }
                            yield f"data: {json.dumps(event_data)}\n\n"

                except Exception as chunk_error:
                    logger.error(f" Error processing chunk #{chunk_count}: {type(chunk_error).__name__}: {str(chunk_error)}", exc_info=True)
                    # Continue processing next chunks
                    continue

        except Exception as stream_error:
            logger.error(f" FATAL: Stream error after {chunk_count} chunks: {type(stream_error).__name__}: {str(stream_error)}", exc_info=True)
            # Send error event to frontend
            error_event = {
                "type": "error",
                "error": str(stream_error),
                "traceback": f"{type(stream_error).__name__}"
            }
            yield f"data: {json.dumps(error_event)}\n\n"

        # Send text-end event
        if text_started:
            text_end_event = {
                "type": "text-end",
                "id": message_id
            }
            yield f"data: {json.dumps(text_end_event)}\n\n"

        logger.info(f"Streaming complete. Processed {chunk_count} chunks, total content length: {len(full_content)}")

        # Extract provider from model string (e.g., "anthropic/claude-sonnet-4.5" -> "anthropic")
        provider = model.split("/")[0] if "/" in model else None

        # Build unified parts array from timeline events
        parts = convert_timeline_to_parts(timeline_events)

        # If no parts were generated from timeline, fall back to simple text part
        if not parts and full_content:
            parts = [{"type": "text", "text": full_content}]

        logger.info(f"Converted {len(timeline_events)} timeline events to {len(parts)} parts")

        # Save assistant message to database with unified parts array
        assistant_message = Message(
            chatId=chat_id,
            role="assistant",
            parts=parts,  # Unified parts array with all content
            attachments=[],
            timelineEvents=timeline_events,  # Keep for backwards compatibility
            provider=provider,
            createdAt=datetime.utcnow()
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        logger.info(f"Saved assistant message with id={assistant_message.id}, parts={len(parts)}, timeline_events={len(timeline_events)}")

        # Save analysis results to ApplicantResults if a profile was selected
        if profile_id and profile_id != "custom" and full_content:
            try:
                from app.models.applicant import ApplicantResult
                # Extract tool results from timeline events
                score_data = {}
                shap_data = None
                fairness_data = None
                counterfactual_data = None
                for te in timeline_events:
                    section = te.get("section", {})
                    if section.get("type") == "tool":
                        content_str = section.get("content", "")
                        title = section.get("title", "")
                        # Parse tool output JSON from the section content
                        if "credit_score_model" in title and "Output" in content_str:
                            try:
                                output_match = content_str.split("**Output:**\n```json\n", 1)
                                if len(output_match) > 1:
                                    json_str = output_match[1].split("\n```")[0]
                                    score_data = json.loads(json_str)
                            except Exception:
                                pass
                        elif "shap_explainer" in title and "Output" in content_str:
                            try:
                                output_match = content_str.split("**Output:**\n```json\n", 1)
                                if len(output_match) > 1:
                                    json_str = output_match[1].split("\n```")[0]
                                    shap_data = json.loads(json_str)
                            except Exception:
                                pass
                        elif "fairness_validator" in title and "Output" in content_str:
                            try:
                                output_match = content_str.split("**Output:**\n```json\n", 1)
                                if len(output_match) > 1:
                                    json_str = output_match[1].split("\n```")[0]
                                    fairness_data = json.loads(json_str)
                            except Exception:
                                pass
                        elif "counterfactual" in title and "Output" in content_str:
                            try:
                                output_match = content_str.split("**Output:**\n```json\n", 1)
                                if len(output_match) > 1:
                                    json_str = output_match[1].split("\n```")[0]
                                    counterfactual_data = json.loads(json_str)
                            except Exception:
                                pass

                # Also try extracting from the parts array (tool-result parts have structured data)
                for p in parts:
                    if p.get("type") == "tool-result" and p.get("data"):
                        pdata = p["data"]
                        name = pdata.get("name", "")
                        output = pdata.get("output")
                        if isinstance(output, str):
                            try:
                                output = json.loads(output)
                            except Exception:
                                pass
                        if isinstance(output, dict):
                            if name == "credit_score_model" and not score_data:
                                score_data = output
                            elif name == "shap_explainer" and not shap_data:
                                shap_data = output
                            elif name == "fairness_validator" and not fairness_data:
                                fairness_data = output
                            elif name == "counterfactual_generator" and not counterfactual_data:
                                counterfactual_data = output

                if score_data.get("credit_score"):
                    credit_score = score_data["credit_score"]
                    result_entry = ApplicantResult(
                        applicant_id=int(profile_id),
                        credit_score=credit_score,
                        score_band=score_data.get("score_band"),
                        default_probability=score_data.get("default_probability"),
                        risk_level="low" if credit_score >= 670 else "medium" if credit_score >= 580 else "high",
                        decision=score_data.get("decision"),
                        shap_explanations=shap_data,
                        fairness_results=fairness_data,
                        counterfactuals=counterfactual_data,
                        full_report=full_content,
                        chat_id=chat_id,
                    )
                    db.add(result_entry)
                    await db.commit()
                    logger.info(f"Saved analysis result for applicant #{profile_id}: score={credit_score}")
                else:
                    logger.info(f"No credit score found in tool results for applicant #{profile_id}, skipping result save")
            except Exception as save_err:
                logger.warning(f"Failed to save analysis result for applicant #{profile_id}: {save_err}")

        # Generate title if this is the first message
        result = await db.execute(select(Chat).where(Chat.id == chat_id))
        current_chat = result.scalar_one_or_none()

        if current_chat and current_chat.title == "New Chat":
            # Get the user's first message text
            user_message_text = ""
            for msg in message_list:
                if msg.role == "user":
                    for part in msg.parts:
                        if part.type == "text" and part.text:
                            user_message_text = part.text
                            break
                    break

            if user_message_text:
                logger.info("Generating title for new chat")
                title = await generate_chat_title(user_message_text)
                current_chat.title = title
                await db.commit()
                logger.info(f"Updated chat title to: {title}")

        # Send finish event and DONE marker
        finish_event = {
            "type": "finish",
            "id": message_id,
            "finishReason": "stop",
            "usage": {
                "promptTokens": 0,
                "completionTokens": len(full_content.split())
            }
        }
        # yield f"data: {json.dumps(finish_event)}\n\n"
        # yield f"data: [DONE]\n\n"
        yield json.dumps(finish_event) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return


    except Exception as e:
        logger.error(f"Error in stream_chat_response: {type(e).__name__}: {str(e)}", exc_info=True)
        error_event = {
            "type": "error",
            "error": str(e)
        }
        # yield f"data: {json.dumps(error_event)}\n\n"
        # yield f"data: [DONE]\n\n"
        yield json.dumps(error_event) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return

        


@router.post("")
async def chat(
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Stream chat responses"""

    # Get or create chat
    chat_id = None
    if chat_request.id:
        try:
            chat_id = UUID(chat_request.id)
        except (ValueError, AttributeError):
            # Invalid UUID, treat as new chat
            chat_id = None

    if chat_id:
        result = await db.execute(select(Chat).where(Chat.id == chat_id))
        chat = result.scalar_one_or_none()

        if not chat:
            # Chat ID provided but doesn't exist - create new chat with this ID
            visibility = chat_request.selectedVisibilityType or "private"
            chat = Chat(
                id=chat_id,
                title="New Chat",
                userId=user.id,
                visibility=visibility,
                createdAt=datetime.utcnow()
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)
        elif chat.userId != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    else:
        # Create new chat
        visibility = chat_request.selectedVisibilityType or "private"
        chat = Chat(
            title="New Chat",
            userId=user.id,
            visibility=visibility,
            createdAt=datetime.utcnow()
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        chat_id = chat.id

    # Save user message - handle both message formats
    user_message = None
    if chat_request.messages and chat_request.messages[-1].role == "user":
        user_message = chat_request.messages[-1]
    elif chat_request.message and chat_request.message.role == "user":
        user_message = chat_request.message

    if user_message:
        message = Message(
            chatId=chat_id,
            role=user_message.role,
            parts=[part.dict() for part in user_message.parts],
            attachments=[att.dict() for att in user_message.attachments],
            createdAt=datetime.utcnow()
        )
        db.add(message)
        await db.commit()

    # Return streaming response in SSE format with AI SDK headers
    response = StreamingResponse(
        stream_chat_response(chat_request, chat_id, user, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Vercel-AI-UI-Message-Stream": "v1"
        }
    )

    # Set guest cookie if this is a guest user
    if user.email.startswith("guest_"):
        response.set_cookie(
            key="guest_id",
            value=str(user.id),
            httponly=True,
            samesite="lax",
            max_age=86400 * 30  # 30 days
        )

    return response


@router.post("/{chat_id}/stream")
async def stream_chat(
    chat_id: str,
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Resume streaming for an existing chat"""

    # Get existing chat
    result = await db.execute(select(Chat).where(Chat.id == UUID(chat_id)))
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.userId != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")

    # Save user message if provided
    user_message = None
    if chat_request.messages and chat_request.messages[-1].role == "user":
        user_message = chat_request.messages[-1]
    elif chat_request.message and chat_request.message.role == "user":
        user_message = chat_request.message

    if user_message:
        message = Message(
            chatId=UUID(chat_id),
            role=user_message.role,
            parts=[part.dict() for part in user_message.parts],
            attachments=[att.dict() for att in user_message.attachments],
            createdAt=datetime.utcnow()
        )
        db.add(message)
        await db.commit()

    # Return streaming response with guest cookie if user is a guest
    # AI SDK expects text/plain not text/event-stream
    response = StreamingResponse(
        stream_chat_response(chat_request, UUID(chat_id), user, db),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Vercel-AI-Data-Stream": "v1"
        }
    )

    # Set guest cookie if this is a guest user
    if user.email.startswith("guest_"):
        response.set_cookie(
            key="guest_id",
            value=str(user.id),
            httponly=True,
            samesite="lax",
            max_age=86400 * 30  # 30 days
        )

    return response


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Get a specific chat by ID"""

    result = await db.execute(
        select(Chat).where(Chat.id == UUID(chat_id))
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.userId != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")

    return ChatResponse.from_orm(chat)


@router.get("/history", response_model=ChatListResponse)
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Get user's chat history"""

    result = await db.execute(
        select(Chat)
        .where(Chat.userId == user.id)
        .order_by(desc(Chat.createdAt))
    )
    chats = result.scalars().all()

    return ChatListResponse(chats=[ChatResponse.from_orm(chat) for chat in chats])


@router.delete("/history")
async def delete_all_chats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Delete all chats for the current user"""

    result = await db.execute(
        select(Chat).where(Chat.userId == user.id)
    )
    chats = result.scalars().all()

    for chat in chats:
        await db.delete(chat)

    await db.commit()

    return {"success": True, "deleted_count": len(chats)}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Delete a chat"""

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.userId != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this chat")

    await db.delete(chat)
    await db.commit()

    return {"success": True}


@router.get("/{chat_id}/messages")
async def get_chat_messages(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_or_guest)
):
    """Get messages for a specific chat"""

    # Verify chat ownership
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.userId != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")

    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.chatId == chat_id)
        .order_by(Message.createdAt)
    )
    messages = result.scalars().all()

    return {"messages": [MessageResponse.from_orm(msg) for msg in messages]}
