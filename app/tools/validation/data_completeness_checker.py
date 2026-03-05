"""
Data Completeness Checker Tool

Identifies missing fields in loan applications and ranks them by importance using
SHAP-based feature importance scores.

This helps guide the loan officer to request the most valuable missing data first,
improving assessment accuracy efficiently.
"""

import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class DataCompletenessInput(BaseModel):
    """Input schema for Data Completeness Checker."""
    # Required fields
    monthly_revenue: Optional[float] = Field(default=None, description="Monthly revenue")
    loan_amount: Optional[float] = Field(default=None, description="Loan amount requested")
    business_tenure_months: Optional[int] = Field(default=None, description="Business tenure")

    # Financial statement fields (optional)
    total_assets: Optional[float] = Field(default=None, description="Total assets")
    total_liabilities: Optional[float] = Field(default=None, description="Total liabilities")
    net_income: Optional[float] = Field(default=None, description="Net income")

    # Alternative data fields (optional)
    activity_rate: Optional[float] = Field(default=None, description="Business activity rate")
    payment_history_score: Optional[float] = Field(default=None, description="Payment history")
    num_dependents: Optional[int] = Field(default=None, description="Number of dependents")


class DataCompletenessChecker(BaseTool):
    """
    Checks data completeness and ranks missing fields by importance.

    Uses SHAP feature importance (from credit scoring model) to determine
    which missing fields would have the highest impact on the credit score.

    Production version will:
    - Use actual SHAP values from XGBoost model
    - Dynamically compute importance based on model training
    - Provide personalized missing field recommendations

    Example:
        checker = DataCompletenessChecker()
        result = await checker.execute(
            monthly_revenue=50000,
            loan_amount=None,  # Missing
            business_tenure_months=18,
            total_assets=None,  # Missing
            activity_rate=0.95
        )
        # Returns: completeness_score, missing_fields ranked by impact
    """

    # SHAP feature importance (from credit scoring model)
    # Production: Load from trained model
    FEATURE_IMPORTANCE = {
        "loan_amount": 0.25,  # Highest impact
        "monthly_revenue": 0.20,
        "business_tenure_months": 0.15,
        "total_assets": 0.12,
        "total_liabilities": 0.10,
        "net_income": 0.08,
        "activity_rate": 0.05,
        "payment_history_score": 0.03,
        "num_dependents": 0.02
    }

    @property
    def name(self) -> str:
        return "data_completeness_checker"

    @property
    def description(self) -> str:
        return (
            "Checks data completeness for loan applications and ranks missing fields "
            "by importance using SHAP feature importance. Guides loan officers to request "
            "the most valuable missing data first."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return DataCompletenessInput

    async def execute(
        self,
        monthly_revenue: Optional[float] = None,
        loan_amount: Optional[float] = None,
        business_tenure_months: Optional[int] = None,
        total_assets: Optional[float] = None,
        total_liabilities: Optional[float] = None,
        net_income: Optional[float] = None,
        activity_rate: Optional[float] = None,
        payment_history_score: Optional[float] = None,
        num_dependents: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Check data completeness and rank missing fields.

        Returns:
            Dictionary containing:
            - completeness_score: Overall completeness (0-1)
            - missing_fields: List of missing fields ranked by impact
            - recommendation: What to request from user
            - critical_missing: List of critical missing fields
        """
        try:
            logger.info("Checking data completeness")

            # Build field presence map
            fields = {
                "monthly_revenue": monthly_revenue,
                "loan_amount": loan_amount,
                "business_tenure_months": business_tenure_months,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "net_income": net_income,
                "activity_rate": activity_rate,
                "payment_history_score": payment_history_score,
                "num_dependents": num_dependents
            }

            # Calculate completeness
            present_fields = [field for field, value in fields.items() if value is not None]
            missing_fields_list = [field for field, value in fields.items() if value is None]

            # Weight by importance
            total_importance = sum(self.FEATURE_IMPORTANCE.values())
            present_importance = sum(
                self.FEATURE_IMPORTANCE.get(field, 0) for field in present_fields
            )
            completeness_score = present_importance / total_importance if total_importance > 0 else 0.0

            # Rank missing fields by importance
            missing_with_importance = [
                {
                    "field": field,
                    "importance": self.FEATURE_IMPORTANCE.get(field, 0),
                    "impact": "critical" if self.FEATURE_IMPORTANCE.get(field, 0) > 0.15 else
                            "high" if self.FEATURE_IMPORTANCE.get(field, 0) > 0.10 else
                            "medium" if self.FEATURE_IMPORTANCE.get(field, 0) > 0.05 else "low"
                }
                for field in missing_fields_list
            ]

            # Sort by importance (descending)
            missing_with_importance.sort(key=lambda x: x["importance"], reverse=True)

            # Identify critical missing fields (importance > 0.15)
            critical_missing = [
                item for item in missing_with_importance if item["importance"] > 0.15
            ]

            # Generate recommendation
            if completeness_score >= 0.9:
                recommendation = "Data is complete. Proceed with credit assessment."
            elif completeness_score >= 0.7:
                top_missing = missing_with_importance[:2] if missing_with_importance else []
                recommendation = f"Good data completeness. Optionally request: {', '.join([m['field'] for m in top_missing])}"
            elif completeness_score >= 0.5:
                top_missing = missing_with_importance[:3] if missing_with_importance else []
                recommendation = f"Moderate completeness. Please provide: {', '.join([m['field'] for m in top_missing])}"
            else:
                recommendation = "Low data completeness. Critical fields missing. Assessment accuracy will be low."

            return {
                "success": True,
                "completeness_score": round(completeness_score, 2),
                "missing_fields": missing_with_importance,
                "critical_missing": critical_missing,
                "total_fields": len(fields),
                "present_fields": len(present_fields),
                "missing_count": len(missing_fields_list),
                "recommendation": recommendation,
                "message": f"Data completeness: {int(completeness_score * 100)}%"
            }

        except Exception as e:
            logger.error(f"Data completeness check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to check data completeness: {str(e)}"
            }


# Create singleton instance
data_completeness_checker = DataCompletenessChecker()
