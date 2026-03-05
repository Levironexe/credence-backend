"""
Credit Score Model Tool

Calculates credit scores (300-850 scale) using machine learning models.
This prototype uses a simple scoring algorithm. The production version will use XGBoost
trained on Home Credit Default Risk dataset (307K rows).

Credit Score Bands (FICO scale):
- 800-850: Exceptional
- 740-799: Very Good
- 670-739: Good
- 580-669: Fair
- 300-579: Poor
"""

import logging
from typing import Dict, Any, Optional
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

    Production version will use XGBoost model trained on:
    - Home Credit Default Risk dataset (307K rows)
    - SoBanHang merchant behavioral data
    - Alternative data sources (mobile money, utility payments)

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

            # IMPLEMENTATION NOTE: This is a prototype using rule-based scoring
            # Production version will use XGBoost model with 200+ engineered features

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
            # Production: Use XGBoost predict_proba
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
                "message": f"Credit score: {int(credit_score)} ({score_band}) - PROTOTYPE MODE"
            }

        except Exception as e:
            logger.error(f"Credit score calculation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to calculate credit score: {str(e)}"
            }


# Create singleton instance
credit_score_model = CreditScoreModel()
