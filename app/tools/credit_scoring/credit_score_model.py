"""
Credit Score Model Tool

Calculates credit scores (300-850 scale) using machine learning models.
Supports both rule-based (prototype) and XGBoost (production) modes.

Credit Score Bands (FICO scale):
- 800-850: Exceptional
- 740-799: Very Good
- 670-739: Good
- 580-669: Fair
- 300-579: Poor
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class CreditScoreInput(BaseModel):
    """Input schema for Credit Score Model."""
    # Financial metrics
    monthly_revenue: float = Field(description="Monthly revenue (trailing 12 months average)")
    loan_amount: float = Field(description="Requested loan amount")
    business_tenure_months: int = Field(description="Business tenure in months")

    # Financial ratios (from statement analyzer)
    debt_to_equity: Optional[float] = Field(default=None, description="Debt-to-equity ratio")
    current_ratio: Optional[float] = Field(default=None, description="Current ratio")
    profit_margin: Optional[float] = Field(default=None, description="Net profit margin")

    # Business context
    industry: Optional[str] = Field(default="general", description="Industry/sector")

    # Alternative data (optional)
    activity_rate: Optional[float] = Field(default=None, description="Business activity rate (0-1)")
    payment_history_score: Optional[float] = Field(default=None, description="Payment punctuality score (0-1)")


class CreditScoreModel(BaseTool):
    """
    Credit scoring model for SME loan assessment.

    Uses financial ratios, business metrics, and alternative data to calculate
    a credit score on the 300-850 scale (FICO-compatible).

    Supports two modes:
    - Rule-based (prototype): Simple scoring algorithm
    - XGBoost (production): Trained ML model with AUC > 0.85

    Example:
        model = CreditScoreModel()
        result = await model.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=18,
            debt_to_equity=0.8,
            current_ratio=1.5
        )
        # Returns: {"credit_score": 680, "score_band": "Good", "default_probability": 0.25}
    """

    def __init__(self):
        super().__init__()
        self.xgb_model = None
        self.feature_names = None
        self.use_ml_model = False
        self._load_model()

    def _load_model(self):
        """Load trained XGBoost model if available."""
        try:
            model_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "xgboost_model.pkl"
            features_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "feature_names.pkl"

            if model_path.exists() and features_path.exists():
                with open(model_path, "rb") as f:
                    self.xgb_model = pickle.load(f)
                with open(features_path, "rb") as f:
                    self.feature_names = pickle.load(f)

                self.use_ml_model = True
                logger.info("✓ Loaded XGBoost credit scoring model")
            else:
                logger.info("XGBoost model not found - using rule-based scoring")
                self.use_ml_model = False

        except Exception as e:
            logger.warning(f"Failed to load XGBoost model: {e} - using rule-based scoring")
            self.use_ml_model = False

    @property
    def name(self) -> str:
        return "credit_score_model"

    @property
    def description(self) -> str:
        return (
            "Calculates credit scores (300-850 scale) for SME loan applications. "
            "Uses financial ratios, business metrics, and alternative data to predict "
            "default probability and assign a FICO-compatible credit score."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CreditScoreInput

    async def execute(
        self,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float] = None,
        current_ratio: Optional[float] = None,
        profit_margin: Optional[float] = None,
        industry: Optional[str] = "general",
        activity_rate: Optional[float] = None,
        payment_history_score: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate credit score.

        Returns:
            Dictionary containing:
            - credit_score: Score (300-850)
            - score_band: Band label (Exceptional, Very Good, Good, Fair, Poor)
            - default_probability: Estimated default probability (0-1)
            - confidence: Model confidence (0-1)
            - recommendation: Loan decision recommendation
        """
        try:
            logger.info(f"Computing credit score for loan_amount={loan_amount}, revenue={monthly_revenue}")

            # Use XGBoost model if available, otherwise fallback to rule-based
            if self.use_ml_model and self.xgb_model is not None:
                return await self._compute_ml_score(
                    monthly_revenue, loan_amount, business_tenure_months,
                    debt_to_equity, current_ratio, profit_margin,
                    activity_rate, payment_history_score
                )
            else:
                return await self._compute_rule_based_score(
                    monthly_revenue, loan_amount, business_tenure_months,
                    debt_to_equity, current_ratio, profit_margin,
                    activity_rate, payment_history_score
                )

        except Exception as e:
            logger.error(f"Credit score calculation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to calculate credit score: {str(e)}"
            }

    async def _compute_ml_score(
        self,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float],
        current_ratio: Optional[float],
        profit_margin: Optional[float],
        activity_rate: Optional[float],
        payment_history_score: Optional[float]
    ) -> Dict[str, Any]:
        """Compute credit score using XGBoost model."""
        try:
            # Calculate derived features
            total_assets = monthly_revenue * 12 * 5  # Estimate
            total_liabilities = total_assets * (debt_to_equity if debt_to_equity else 0.8)
            net_income = monthly_revenue * 12 * (profit_margin if profit_margin else 0.1)
            current_assets = total_assets * 0.4
            current_liabilities = current_assets / (current_ratio if current_ratio else 1.2)
            loan_to_revenue_ratio = loan_amount / (monthly_revenue * 12)

            # Build feature vector
            features = {
                "loan_amount": loan_amount,
                "monthly_revenue": monthly_revenue,
                "business_tenure_months": business_tenure_months,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "net_income": net_income,
                "activity_rate": activity_rate if activity_rate else 0.75,
                "payment_history_score": payment_history_score if payment_history_score else 0.7,
                "num_dependents": 2,  # Default
                "owner_age": 40,  # Default
                "num_credit_inquiries": 3,  # Default
                "loan_to_revenue_ratio": loan_to_revenue_ratio,
                "debt_to_equity": debt_to_equity if debt_to_equity else 1.0,
                "current_ratio": current_ratio if current_ratio else 1.2,
                "profit_margin": profit_margin if profit_margin else 0.1
            }

            # Create feature array in correct order
            X = np.array([[features[fname] for fname in self.feature_names]])

            # Predict default probability
            default_probability = float(self.xgb_model.predict_proba(X)[0, 1])

            # Convert to credit score (inverse relationship)
            # Default prob 0.0 → score 850, default prob 1.0 → score 300
            credit_score = int(850 - (default_probability * 550))
            credit_score = max(300, min(850, credit_score))

            # Determine score band and recommendation
            if credit_score >= 800:
                score_band = "Exceptional"
                recommendation = "Auto-approve with best terms"
            elif credit_score >= 740:
                score_band = "Very Good"
                recommendation = "Approve with standard terms"
            elif credit_score >= 670:
                score_band = "Good"
                recommendation = "Approve with conditions"
            elif credit_score >= 580:
                score_band = "Fair"
                recommendation = "Manual review required"
            else:
                score_band = "Poor"
                recommendation = "Decline with counterfactual guidance"

            # Confidence based on data completeness
            data_completeness = sum([
                monthly_revenue > 0,
                business_tenure_months > 0,
                debt_to_equity is not None,
                current_ratio is not None,
                profit_margin is not None,
                activity_rate is not None,
                payment_history_score is not None
            ]) / 7.0
            confidence = 0.8 + (0.2 * data_completeness)  # ML model has higher base confidence

            return {
                "success": True,
                "credit_score": credit_score,
                "score_band": score_band,
                "default_probability": round(default_probability, 3),
                "confidence": round(confidence, 2),
                "recommendation": recommendation,
                "loan_to_revenue_ratio": round(loan_to_revenue_ratio, 3),
                "data_completeness": round(data_completeness, 2),
                "model_type": "XGBoost",
                "message": f"Credit score: {credit_score} ({score_band}) - ML MODEL"
            }

        except Exception as e:
            logger.error(f"ML scoring failed: {e} - falling back to rule-based")
            return await self._compute_rule_based_score(
                monthly_revenue, loan_amount, business_tenure_months,
                debt_to_equity, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )

    async def _compute_rule_based_score(
        self,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float],
        current_ratio: Optional[float],
        profit_margin: Optional[float],
        activity_rate: Optional[float],
        payment_history_score: Optional[float]
    ) -> Dict[str, Any]:
        """Compute credit score using rule-based algorithm (prototype)."""

        # Initialize base score
        base_score = 600  # Neutral starting point

        # Factor 1: Loan-to-Revenue Ratio (higher is riskier)
        loan_to_revenue = loan_amount / (monthly_revenue * 12) if monthly_revenue > 0 else 1.0
        if loan_to_revenue < 0.1:
            base_score += 80  # Very low loan relative to revenue
        elif loan_to_revenue < 0.25:
            base_score += 50
        elif loan_to_revenue < 0.5:
            base_score += 20
        elif loan_to_revenue < 1.0:
            base_score -= 20
        else:
            base_score -= 60  # Loan exceeds annual revenue

        # Factor 2: Business Tenure (longer is better)
        if business_tenure_months >= 36:
            base_score += 50  # 3+ years
        elif business_tenure_months >= 24:
            base_score += 30  # 2+ years
        elif business_tenure_months >= 12:
            base_score += 10  # 1+ year
        else:
            base_score -= 30  # Less than 1 year

        # Factor 3: Financial Ratios
        if debt_to_equity is not None:
            if debt_to_equity < 0.5:
                base_score += 30  # Low leverage
            elif debt_to_equity < 1.0:
                base_score += 10
            elif debt_to_equity > 2.0:
                base_score -= 30  # High leverage

        if current_ratio is not None:
            if current_ratio >= 2.0:
                base_score += 30  # Strong liquidity
            elif current_ratio >= 1.5:
                base_score += 15
            elif current_ratio < 1.0:
                base_score -= 30  # Poor liquidity

        if profit_margin is not None:
            if profit_margin >= 0.2:
                base_score += 30  # Strong profitability
            elif profit_margin >= 0.1:
                base_score += 15
            elif profit_margin < 0:
                base_score -= 40  # Unprofitable

        # Factor 4: Alternative Data
        if activity_rate is not None and activity_rate >= 0.9:
            base_score += 20  # Consistent business activity

        if payment_history_score is not None and payment_history_score >= 0.9:
            base_score += 30  # Strong payment history

        # Ensure score is within 300-850 range
        credit_score = max(300, min(850, base_score))

        # Determine score band
        if credit_score >= 800:
            score_band = "Exceptional"
            recommendation = "Auto-approve with best terms"
        elif credit_score >= 740:
            score_band = "Very Good"
            recommendation = "Approve with standard terms"
        elif credit_score >= 670:
            score_band = "Good"
            recommendation = "Approve with conditions"
        elif credit_score >= 580:
            score_band = "Fair"
            recommendation = "Manual review required"
        else:
            score_band = "Poor"
            recommendation = "Decline with counterfactual guidance"

        # Estimate default probability (simplified formula)
        default_probability = (850 - credit_score) / 550.0  # Maps 300→1.0, 850→0.0
        default_probability = max(0.0, min(1.0, default_probability))

        # Confidence score (based on data completeness)
        data_completeness = sum([
            monthly_revenue > 0,
            business_tenure_months > 0,
            debt_to_equity is not None,
            current_ratio is not None,
            profit_margin is not None,
            activity_rate is not None,
            payment_history_score is not None
        ]) / 7.0
        confidence = 0.7 + (0.3 * data_completeness)  # Base 70% + up to 30% from complete data

        return {
            "success": True,
            "credit_score": int(credit_score),
            "score_band": score_band,
            "default_probability": round(default_probability, 3),
            "confidence": round(confidence, 2),
            "recommendation": recommendation,
            "loan_to_revenue_ratio": round(loan_to_revenue, 3),
            "data_completeness": round(data_completeness, 2),
            "model_type": "rule-based",
            "message": f"Credit score: {int(credit_score)} ({score_band}) - RULE-BASED MODE"
        }


# Create singleton instance
credit_score_model = CreditScoreModel()
