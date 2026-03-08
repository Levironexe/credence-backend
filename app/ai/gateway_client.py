# app/ai/gateway_client.py

import logging
from app.ai.llms.claude_client import ClaudeClient
from app.ai.llms.gemini_client import GeminiClient
from app.ai.llms.openai_client import OpenAIClient
from app.ai.langgraph_agent import LangGraphAgent

# Financial Analysis Tools
from app.tools.financial_analysis.statement_analyzer import financial_statement_analyzer
from app.tools.credit_scoring.credit_score_model import credit_score_model
from app.tools.validation.data_completeness_checker import data_completeness_checker
from app.tools.knowledge.lending_knowledge_retriever import lending_knowledge_retriever
from app.tools.explainability.shap_explainer import shap_explainer
from app.tools.explainability.counterfactual_generator import counterfactual_generator
from app.tools.fairness.fairness_validator import fairness_validator

logger = logging.getLogger(__name__)


class GatewayClient:
    def __init__(self):
        # Use lazy initialization - clients created only when needed
        self._claude = None
        self._gemini = None
        self._openai = None
        self._agent = None

        logger.info("Gateway initialized (lazy loading enabled)")

    @property
    def claude(self):
        """Lazy load Claude client"""
        if self._claude is None:
            self._claude = ClaudeClient()
        return self._claude

    @property
    def gemini(self):
        """Lazy load Gemini client"""
        if self._gemini is None:
            self._gemini = GeminiClient()
        return self._gemini

    @property
    def openai(self):
        """Lazy load OpenAI client"""
        if self._openai is None:
            self._openai = OpenAIClient()
        return self._openai

    @property
    def agent(self):
        """Lazy load LangGraph agent"""
        if self._agent is None:
            self._agent = LangGraphAgent()

            # Register financial analysis tools
            tools = [
                financial_statement_analyzer.to_langchain_tool(),
                credit_score_model.to_langchain_tool(),
                data_completeness_checker.to_langchain_tool(),
                lending_knowledge_retriever.to_langchain_tool(),
                shap_explainer.to_langchain_tool(),
                counterfactual_generator.to_langchain_tool(),
                fairness_validator.to_langchain_tool(),
            ]

            self._agent.register_tools(tools)
            logger.info(f"Registered {len(tools)} financial analysis tools")

        return self._agent

    def get_client(self, model: str):
        m = model.lower().strip()

        if "/" in m:
            provider, _ = m.split("/", 1)
        else:
            provider = m

        # Route agent requests to LangGraph agent
        if provider == "agent":
            return self.agent

        if provider in ("anthropic", "claude"):
            return self.claude

        if provider in ("google", "gemini"):
            return self.gemini

        if provider in ("openai", "gpt"):
            return self.openai

        raise ValueError(f"Unsupported model: {model}")


    async def stream_chat_completion(self, model, messages, **kwargs):
        m = model.lower().strip()

        if "/" in m:
            provider, raw_model = m.split("/", 1)
        else:
            provider = m
            raw_model = model

        client = self.get_client(model)

        async for chunk in client.stream_chat_completion(
            model=raw_model,
            messages=messages,
            **kwargs
        ):
            yield chunk


    async def chat_completion(self, model, messages, **kwargs):
        client = self.get_client(model)
        return await client.chat_completion(
            model=model,
            messages=messages,
            **kwargs
        )


# Singleton gateway instance
gateway_client = GatewayClient()
