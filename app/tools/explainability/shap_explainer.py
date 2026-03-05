"""
SHAP Explainer Tool

Provides feature importance explanations for credit decisions using SHAP values.
Helps loan officers understand which factors most influenced the credit score.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List
import numpy as np
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SHAPExplainerInput(BaseModel):
    """Input schema for SHAP Explainer."""
    # Same features as credit score model
    monthly_revenue: float = Field(description="Monthly revenue")
    loan_amount: float = Field(description="Requested loan amount")
    business_tenure_months: int = Field(description="Business tenure in months")

    # Financial ratios
    debt_to_equity: Optional[float] = Field(default=None, description="Debt-to-equity ratio")
    current_ratio: Optional[float] = Field(default=None, description="Current ratio")
    profit_margin: Optional[float] = Field(default=None, description="Net profit margin")

    # Alternative data
    activity_rate: Optional[float] = Field(default=None, description="Business activity rate")
    payment_history_score: Optional[float] = Field(default=None, description="Payment history score")


class SHAPExplainer(BaseTool):
    """
    SHAP-based feature importance explainer for credit decisions.

    Uses SHAP (SHapley Additive exPlanations) to explain which features
    contributed most to the credit score decision.

    For XGBoost model: Uses TreeSHAP for fast, accurate explanations.
    For rule-based model: Uses feature importance from data completeness checker.

    Example:
        explainer = SHAPExplainer()
        result = await explainer.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=18,
            debt_to_equity=0.8,
            current_ratio=1.5
        )
        # Returns: {"top_features": [...], "shap_values": {...}, "explanations": [...]}
    """

    def __init__(self):
        super().__init__()
        self.xgb_model = None
        self.feature_names = None
        self.shap_explainer = None
        self.use_ml_model = False
        self._load_model()

    def _load_model(self):
        """Load trained XGBoost model and initialize SHAP explainer."""
        try:
            model_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "xgboost_model.pkl"
            features_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "feature_names.pkl"

            if model_path.exists() and features_path.exists():
                with open(model_path, "rb") as f:
                    self.xgb_model = pickle.load(f)
                with open(features_path, "rb") as f:
                    self.feature_names = pickle.load(f)

                # Initialize SHAP explainer
                try:
                    import shap
                    self.shap_explainer = shap.TreeExplainer(self.xgb_model)
                    self.use_ml_model = True
                    logger.info("✓ Loaded SHAP explainer with XGBoost model")
                except ImportError:
                    logger.warning("SHAP library not available - using rule-based explanations")
                    self.use_ml_model = False

            else:
                logger.info("XGBoost model not found - using rule-based explanations")
                self.use_ml_model = False

        except Exception as e:
            logger.warning(f"Failed to load SHAP explainer: {e} - using rule-based explanations")
            self.use_ml_model = False

    @property
    def name(self) -> str:
        return "shap_explainer"

    @property
    def description(self) -> str:
        return (
            "Explains credit score decisions using SHAP feature importance. "
            "Shows which factors (revenue, tenure, ratios, etc.) most influenced the score. "
            "Helps loan officers understand and justify credit decisions."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return SHAPExplainerInput

    async def execute(
        self,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float] = None,
        current_ratio: Optional[float] = None,
        profit_margin: Optional[float] = None,
        activity_rate: Optional[float] = None,
        payment_history_score: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate SHAP explanations for credit decision.

        Returns:
            Dictionary containing:
            - top_features: List of most important features
            - shap_values: Feature importance values
            - explanations: Human-readable explanations
            - base_value: Model baseline prediction
        """
        try:
            logger.info("Generating SHAP explanations for credit decision")

            if self.use_ml_model and self.shap_explainer is not None:
                return await self._explain_ml_model(
                    monthly_revenue, loan_amount, business_tenure_months,
                    debt_to_equity, current_ratio, profit_margin,
                    activity_rate, payment_history_score
                )
            else:
                return await self._explain_rule_based(
                    monthly_revenue, loan_amount, business_tenure_months,
                    debt_to_equity, current_ratio, profit_margin,
                    activity_rate, payment_history_score
                )

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate explanations: {str(e)}"
            }

    async def _explain_ml_model(
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
        """Generate SHAP explanations using TreeSHAP."""
        import shap

        # Calculate derived features (same as credit_score_model)
        total_assets = monthly_revenue * 12 * 5
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
            "num_dependents": 2,
            "owner_age": 40,
            "num_credit_inquiries": 3,
            "loan_to_revenue_ratio": loan_to_revenue_ratio,
            "debt_to_equity": debt_to_equity if debt_to_equity else 1.0,
            "current_ratio": current_ratio if current_ratio else 1.2,
            "profit_margin": profit_margin if profit_margin else 0.1
        }

        # Create feature array
        X = np.array([[features[fname] for fname in self.feature_names]])

        # Compute SHAP values
        shap_values = self.shap_explainer.shap_values(X)

        # Get base value (model's average prediction)
        base_value = self.shap_explainer.expected_value

        # Create feature importance ranking
        feature_importance = []
        for i, fname in enumerate(self.feature_names):
            importance = abs(float(shap_values[0][i]))
            feature_importance.append({
                "feature": fname,
                "shap_value": float(shap_values[0][i]),
                "importance": importance,
                "feature_value": features[fname]
            })

        # Sort by absolute importance
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

        # Get top 5 features
        top_features = feature_importance[:5]

        # Generate human-readable explanations
        explanations = []
        for item in top_features:
            impact = "increased" if item["shap_value"] > 0 else "decreased"
            explanations.append({
                "feature": item["feature"],
                "value": round(item["feature_value"], 2),
                "impact": impact,
                "contribution": f"{impact.capitalize()} credit score by {abs(item['shap_value']):.1f} points",
                "explanation": self._get_feature_explanation(
                    item["feature"],
                    item["feature_value"],
                    item["shap_value"]
                )
            })

        return {
            "success": True,
            "method": "TreeSHAP",
            "base_value": float(base_value),
            "top_features": top_features,
            "all_features": feature_importance,
            "explanations": explanations,
            "message": f"Generated SHAP explanations with {len(top_features)} top features"
        }

    async def _explain_rule_based(
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
        """Generate explanations using rule-based importance (fallback)."""
        loan_to_revenue = loan_amount / (monthly_revenue * 12)

        # Rule-based feature importance
        features = []

        # Loan-to-revenue ratio (highest impact)
        features.append({
            "feature": "loan_to_revenue_ratio",
            "value": round(loan_to_revenue, 3),
            "importance": 0.25,
            "impact": "negative" if loan_to_revenue > 0.3 else "positive",
            "explanation": f"Loan is {loan_to_revenue*100:.1f}% of annual revenue. " +
                          ("High ratio increases risk." if loan_to_revenue > 0.3 else "Reasonable ratio.")
        })

        # Business tenure
        features.append({
            "feature": "business_tenure_months",
            "value": business_tenure_months,
            "importance": 0.20,
            "impact": "positive" if business_tenure_months >= 24 else "negative",
            "explanation": f"Business has operated for {business_tenure_months} months. " +
                          ("Established track record." if business_tenure_months >= 24 else "Limited history.")
        })

        # Debt-to-equity
        if debt_to_equity is not None:
            features.append({
                "feature": "debt_to_equity",
                "value": round(debt_to_equity, 2),
                "importance": 0.15,
                "impact": "negative" if debt_to_equity > 2.0 else "positive",
                "explanation": f"Debt-to-equity ratio of {debt_to_equity:.2f}. " +
                              ("High leverage." if debt_to_equity > 2.0 else "Moderate leverage.")
            })

        # Current ratio
        if current_ratio is not None:
            features.append({
                "feature": "current_ratio",
                "value": round(current_ratio, 2),
                "importance": 0.12,
                "impact": "positive" if current_ratio >= 1.5 else "negative",
                "explanation": f"Current ratio of {current_ratio:.2f}. " +
                              ("Strong liquidity." if current_ratio >= 1.5 else "Limited liquidity.")
            })

        # Profit margin
        if profit_margin is not None:
            features.append({
                "feature": "profit_margin",
                "value": round(profit_margin, 3),
                "importance": 0.10,
                "impact": "positive" if profit_margin > 0.1 else "negative",
                "explanation": f"Profit margin of {profit_margin*100:.1f}%. " +
                              ("Profitable business." if profit_margin > 0.1 else "Low profitability.")
            })

        # Sort by importance
        features.sort(key=lambda x: x["importance"], reverse=True)

        return {
            "success": True,
            "method": "rule-based",
            "top_features": features[:5],
            "all_features": features,
            "explanations": features[:5],
            "message": "Generated rule-based feature importance explanations"
        }

    def _get_feature_explanation(self, feature: str, value: float, shap_value: float) -> str:
        """Generate human-readable explanation for a feature."""
        impact = "increased" if shap_value > 0 else "decreased"

        explanations = {
            "loan_amount": f"Loan amount of ${value:,.0f} {impact} the score",
            "monthly_revenue": f"Monthly revenue of ${value:,.0f} {impact} the score",
            "business_tenure_months": f"Business tenure of {int(value)} months {impact} the score",
            "loan_to_revenue_ratio": f"Loan-to-revenue ratio of {value:.2%} {impact} the score",
            "debt_to_equity": f"Debt-to-equity ratio of {value:.2f} {impact} the score",
            "current_ratio": f"Current ratio of {value:.2f} {impact} the score",
            "profit_margin": f"Profit margin of {value:.2%} {impact} the score",
            "activity_rate": f"Activity rate of {value:.2%} {impact} the score",
            "payment_history_score": f"Payment history score of {value:.2f} {impact} the score"
        }

        return explanations.get(feature, f"{feature} value of {value:.2f} {impact} the score")


# Create singleton instance
shap_explainer = SHAPExplainer()
