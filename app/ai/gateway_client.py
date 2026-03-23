# app/ai/gateway_client.py

import logging
from app.ai.langgraph_agent import LangGraphAgent

# Financial Analysis Tools
from app.tools.credit_scoring.credit_score_model import credit_score_model
from app.tools.validation.data_completeness_checker import data_completeness_checker
from app.tools.explainability.shap_explainer import shap_explainer
from app.tools.explainability.counterfactual_generator import counterfactual_generator
from app.tools.fairness.fairness_validator import fairness_validator
from app.tools.document_processing.pdf_extractor import pdf_extractor
from app.tools.document_processing.bank_statement_parser import bank_statement_parser

logger = logging.getLogger(__name__)


class GatewayClient:
    def __init__(self):
        self._agent = None
        logger.info("Gateway initialized (all models route through LangGraph agent via OpenRouter)")

    @property
    def agent(self):
        """Lazy load LangGraph agent"""
        if self._agent is None:
            self._agent = LangGraphAgent()

            # Register financial analysis tools
            tools = [
                credit_score_model.to_langchain_tool(),
                data_completeness_checker.to_langchain_tool(),
                shap_explainer.to_langchain_tool(),
                counterfactual_generator.to_langchain_tool(),
                fairness_validator.to_langchain_tool(),
                pdf_extractor.to_langchain_tool(),
                bank_statement_parser.to_langchain_tool(),
            ]

            self._agent.register_tools(tools)
            logger.info(f"Registered {len(tools)} financial analysis tools")

        return self._agent

    async def stream_chat_completion(self, model, messages, **kwargs):
        async for chunk in self.agent.stream_chat_completion(
            model=model,
            messages=messages,
            **kwargs
        ):
            yield chunk

    async def chat_completion(self, model, messages, **kwargs):
        return await self.agent.chat_completion(
            model=model,
            messages=messages,
            **kwargs
        )


# Singleton gateway instance
gateway_client = GatewayClient()
