import logging
from typing import AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# Map friendly model names to OpenRouter model IDs
MODEL_MAPPING = {
    "claude-haiku-4.5": "anthropic/claude-haiku-4.5",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "claude-haiku": "anthropic/claude-haiku-4.5",
    "claude-sonnet-4.5": "anthropic/claude-sonnet-4",
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4",
    "claude-sonnet": "anthropic/claude-sonnet-4",
}


class ClaudeClient:
    """Client for Claude via OpenRouter with streaming support."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openrouter_api_key or settings.ai_gateway_api_key
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
        ) if self.api_key else None

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not configured - Claude client will fail if used")

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        # Strip provider prefix if present (e.g., "claude/anthropic/claude-haiku-4.5" -> "anthropic/claude-haiku-4.5")
        if "/" in model:
            # Could be "claude/model" or "claude/anthropic/model"
            parts = model.split("/", 1)
            if parts[0] in ("claude", "anthropic"):
                model = parts[1] if "/" in parts[1] else model
            else:
                model = parts[1]

        # Map friendly names to OpenRouter IDs
        openrouter_model = MODEL_MAPPING.get(model, model)
        # Ensure it has provider prefix for OpenRouter
        if "/" not in openrouter_model:
            openrouter_model = f"anthropic/{openrouter_model}"

        logger.info(f"Streaming from OpenRouter: model={openrouter_model}, messages={len(messages)}")

        try:
            stream = await self.client.chat.completions.create(
                model=openrouter_model,
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield {
                            "choices": [{
                                "delta": {
                                    "content": delta.content
                                }
                            }]
                        }

            logger.info("OpenRouter streaming complete")

        except Exception as e:
            logger.error(f"OpenRouter streaming error: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        **kwargs,
    ) -> Dict[str, Any]:
        if "/" in model:
            parts = model.split("/", 1)
            if parts[0] in ("claude", "anthropic"):
                model = parts[1] if "/" in parts[1] else model
            else:
                model = parts[1]

        openrouter_model = MODEL_MAPPING.get(model, model)
        if "/" not in openrouter_model:
            openrouter_model = f"anthropic/{openrouter_model}"

        logger.info(f"Calling OpenRouter: model={openrouter_model}, messages={len(messages)}")

        try:
            response = await self.client.chat.completions.create(
                model=openrouter_model,
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
                stream=False,
            )

            return {
                "choices": [{
                    "message": {
                        "role": response.choices[0].message.role,
                        "content": response.choices[0].message.content
                    }
                }],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else {}
            }

        except Exception as e:
            logger.error(f"OpenRouter error: {type(e).__name__}: {str(e)}", exc_info=True)
            raise
