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

    @staticmethod
    def _compute_derived_features(data: Dict[str, Any], row: pd.Series) -> None:
        """Compute derived features using the exact formulas from training.

        Must match train_and_evaluate.ipynb exactly — same +1 offsets,
        same NaN propagation behaviour. If an input is missing the derived
        feature stays NaN and will be imputed with the training median later.
        """
        def _get(key):
            """Get a numeric value from data, returning None if missing/NaN."""
            v = data.get(key)
            if v is None:
                return None
            try:
                f = float(v)
                return None if np.isnan(f) else f
            except (ValueError, TypeError):
                return None

        income = _get("AMT_INCOME_TOTAL")
        credit = _get("AMT_CREDIT")
        annuity = _get("AMT_ANNUITY")
        goods = _get("AMT_GOODS_PRICE")
        fam = _get("CNT_FAM_MEMBERS")
        days_birth = _get("DAYS_BIRTH")
        days_emp = _get("DAYS_EMPLOYED")
        ext1 = _get("EXT_SOURCE_1")
        ext2 = _get("EXT_SOURCE_2")
        ext3 = _get("EXT_SOURCE_3")
        bureau_active = _get("bureau_active_count")
        bureau_loans = _get("bureau_loan_count")
        bureau_debt = _get("bureau_debt_sum")
        bureau_credit = _get("bureau_credit_sum")
        prev_approved = _get("prev_approved_count")
        prev_apps = _get("prev_app_count")

        # Ratios — training used denominator + 1 to avoid division by zero
        if credit is not None and income is not None:
            row["credit_income_ratio"] = credit / (income + 1)
        if annuity is not None and income is not None:
            row["annuity_income_ratio"] = annuity / (income + 1)
        if credit is not None and goods is not None:
            row["credit_goods_ratio"] = credit / (goods + 1)
        if annuity is not None and credit is not None:
            row["annuity_credit_ratio"] = annuity / (credit + 1)
        if income is not None and fam is not None:
            row["income_per_person"] = income / (fam + 1)

        # Time conversions
        if days_birth is not None:
            row["age_years"] = (-days_birth) / 365.25
        if days_emp is not None:
            row["employment_years"] = (-days_emp) / 365.25
        if days_emp is not None and days_birth is not None:
            row["employed_to_birth_ratio"] = days_emp / (days_birth + 1)

        # Bureau ratios
        if bureau_active is not None and bureau_loans is not None:
            row["bureau_active_ratio"] = bureau_active / (bureau_loans + 1)
        if bureau_debt is not None and bureau_credit is not None:
            row["bureau_debt_credit_ratio"] = bureau_debt / (bureau_credit + 1)

        # Previous application ratio
        if prev_approved is not None and prev_apps is not None:
            row["prev_approval_rate"] = prev_approved / (prev_apps + 1)

        # External source combinations — mean/std use whatever sources are
        # available (matching pandas .mean(axis=1) skipna behaviour in training)
        exts = [v for v in [ext1, ext2, ext3] if v is not None]
        if exts:
            row["ext_source_mean"] = np.mean(exts)
            row["ext_source_std"] = np.std(exts, ddof=1) if len(exts) > 1 else 0.0
        # Product requires all three (NaN * x = NaN in training)
        if ext1 is not None and ext2 is not None and ext3 is not None:
            row["ext_source_product"] = ext1 * ext2 * ext3

    async def _compute_ml_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Score using the trained XGBoost model."""
        feature_names = artifacts.feature_names
        row = pd.Series(index=feature_names, dtype=object)

        # Fill provided values
        for feat in feature_names:
            if feat in data:
                row[feat] = data[feat]

        # Compute derived features from raw inputs (must happen before imputation)
        self._compute_derived_features(data, row)

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


        # Include all provided fields in the response
        applicant_profile = {k: v for k, v in data.items() if v is not None}

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
            "applicant_profile": applicant_profile,
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
