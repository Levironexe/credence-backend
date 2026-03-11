"""
Credit Score Model Tool

Uses the trained stable XGBoost model (Home Credit, 128 features) to predict
default probability and convert to a 300-850 credit score.
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)


class CreditScoreInput(BaseModel):
    """Input: raw applicant data as a flat dictionary."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features. Can include any subset of the 128 Home Credit features."
    )


class CreditScoreModel(BaseTool):
    """
    Credit scoring using trained XGBoost model on Home Credit dataset.

    Accepts raw applicant data, encodes categoricals using saved label encoders,
    imputes missing values with training medians, and predicts default probability.

    Credit Score Bands (Credence scale, 300-850):
    - 800-850: Exceptional -> AUTO-APPROVE
    - 740-799: Very Good -> APPROVE (standard terms)
    - 670-739: Good -> APPROVE (with conditions)
    - 580-669: Fair -> MANUAL REVIEW
    - 300-579: Poor -> DECLINE (with counterfactual guidance)
    """

    @staticmethod
    def prob_to_score(p: float) -> int:
        return int(850 - p * 550)

    @staticmethod
    def score_band(score: int) -> str:
        if score >= 800: return "Exceptional"
        if score >= 740: return "Very Good"
        if score >= 670: return "Good"
        if score >= 580: return "Fair"
        return "Poor"

    @staticmethod
    def decision_from_score(score: int) -> str:
        if score >= 800: return "AUTO-APPROVE"
        if score >= 670: return "APPROVE (with conditions)"
        if score >= 580: return "MANUAL REVIEW"
        return "DECLINE"

    @property
    def name(self) -> str:
        return "credit_score_model"

    @property
    def description(self) -> str:
        return (
            "Calculates credit scores (300-850 scale) for loan applications. "
            "Uses XGBoost model trained on Home Credit dataset (307K samples, 128 features). "
            "Returns default probability, credit score, score band, and lending decision."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CreditScoreInput

    async def execute(self, applicant_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.model is None:
                return await self._compute_rule_based_score(applicant_data)

            return await self._compute_ml_score(applicant_data)

        except Exception as e:
            logger.error(f"Credit score calculation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to calculate credit score: {str(e)}"
            }

    async def _compute_ml_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Score using the trained XGBoost model."""
        feature_names = artifacts.feature_names
        row = pd.Series(index=feature_names, dtype=object)

        # Fill provided values
        for feat in feature_names:
            if feat in data:
                row[feat] = data[feat]

        # Encode categoricals using saved label encoders
        if artifacts.label_encoders:
            for col, le in artifacts.label_encoders.items():
                if col in row.index and isinstance(row.get(col), str):
                    try:
                        row[col] = le.transform([row[col]])[0]
                    except ValueError:
                        row[col] = np.nan

        # Impute missing with training medians
        if artifacts.X_train is not None:
            for feat in feature_names:
                if pd.isna(row.get(feat)):
                    if feat in artifacts.X_train.columns:
                        row[feat] = float(artifacts.X_train[feat].median())
                    else:
                        row[feat] = 0.0

        # Predict
        X = row[feature_names].values.astype(float).reshape(1, -1)
        prob = float(artifacts.model.predict_proba(X)[0, 1])
        credit_score = self.prob_to_score(prob)

        return {
            "success": True,
            "default_probability": round(prob, 4),
            "credit_score": credit_score,
            "score_band": self.score_band(credit_score),
            "decision": self.decision_from_score(credit_score),
            "approved": credit_score >= 670,
            "model_type": "XGBoost (Home Credit, stable)",
            "features_provided": sum(1 for f in feature_names if f in data),
            "features_total": len(feature_names),
            "message": f"Credit score: {credit_score} ({self.score_band(credit_score)})"
        }

    async def _compute_rule_based_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback rule-based scoring."""
        income = data.get("AMT_INCOME_TOTAL", data.get("person_income", 50000))
        credit = data.get("AMT_CREDIT", data.get("loan_amnt", 100000))
        emp_days = abs(data.get("DAYS_EMPLOYED", 0))

        ratio = credit / (income + 1)
        emp_years = emp_days / 365.25

        base_score = 600
        if ratio < 2: base_score += 80
        elif ratio < 4: base_score += 30
        elif ratio > 6: base_score -= 80
        if emp_years >= 5: base_score += 40
        elif emp_years >= 2: base_score += 20
        elif emp_years < 1: base_score -= 30

        credit_score = max(300, min(850, base_score))
        prob = (850 - credit_score) / 550.0

        return {
            "success": True,
            "default_probability": round(prob, 4),
            "credit_score": credit_score,
            "score_band": self.score_band(credit_score),
            "decision": self.decision_from_score(credit_score),
            "approved": credit_score >= 670,
            "model_type": "rule-based (fallback)",
            "message": f"Credit score: {credit_score} ({self.score_band(credit_score)}) - RULE-BASED"
        }


# Singleton
credit_score_model = CreditScoreModel()
