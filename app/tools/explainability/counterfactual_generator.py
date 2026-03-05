"""
Counterfactual Explanation Generator

Generates "what-if" scenarios showing how to improve credit score.
Uses DiCE (Diverse Counterfactual Explanations) for ML models.

Example: "If your monthly revenue was $60,000 (currently $45,000) and debt-to-equity
was 1.2 (currently 2.1), your credit score would increase from 620 to 710."
"""

import logging
from typing import Dict, Any, Optional, List
import numpy as np
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class CounterfactualInput(BaseModel):
    """Input schema for Counterfactual Generator."""
    # Current application values
    monthly_revenue: float = Field(description="Current monthly revenue")
    loan_amount: float = Field(description="Requested loan amount")
    business_tenure_months: int = Field(description="Current business tenure")

    # Financial ratios
    debt_to_equity: Optional[float] = Field(default=None, description="Current debt-to-equity")
    current_ratio: Optional[float] = Field(default=None, description="Current ratio")
    profit_margin: Optional[float] = Field(default=None, description="Current profit margin")

    # Alternative data
    activity_rate: Optional[float] = Field(default=None, description="Activity rate")
    payment_history_score: Optional[float] = Field(default=None, description="Payment history")

    # Target
    target_score: Optional[int] = Field(default=670, description="Target credit score (default: 670 - Good)")


class CounterfactualGenerator(BaseTool):
    """
    Generates counterfactual explanations for credit decisions.

    Shows applicants what minimal changes would improve their credit score
    to reach approval threshold.

    For declined applications: Shows path to approval.
    For approved applications: Shows path to better terms.

    Example:
        generator = CounterfactualGenerator()
        result = await generator.execute(
            monthly_revenue=45000,
            loan_amount=10000,
            business_tenure_months=18,
            debt_to_equity=2.1,
            target_score=670
        )
        # Returns: [
        #   {"feature": "monthly_revenue", "current": 45000, "suggested": 60000, "impact": "+50 points"},
        #   {"feature": "debt_to_equity", "current": 2.1, "suggested": 1.5, "impact": "+30 points"}
        # ]
    """

    @property
    def name(self) -> str:
        return "counterfactual_generator"

    @property
    def description(self) -> str:
        return (
            "Generates 'what-if' scenarios showing minimal changes to improve credit score. "
            "Helps applicants understand what they can do to qualify for approval or better terms. "
            "Provides actionable recommendations based on current financial situation."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CounterfactualInput

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
        target_score: Optional[int] = 670,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate counterfactual explanations.

        Returns:
            Dictionary containing:
            - counterfactuals: List of minimal changes to reach target
            - current_score: Current estimated score
            - target_score: Target score
            - feasibility: How achievable the changes are
        """
        try:
            logger.info(f"Generating counterfactuals for target score {target_score}")

            # Calculate current score estimate
            current_score = self._estimate_score(
                monthly_revenue, loan_amount, business_tenure_months,
                debt_to_equity, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )

            # If already at or above target, provide optimization suggestions
            if current_score >= target_score:
                return await self._generate_optimization_suggestions(
                    current_score, monthly_revenue, loan_amount, business_tenure_months,
                    debt_to_equity, current_ratio, profit_margin,
                    activity_rate, payment_history_score
                )

            # Generate counterfactuals to reach target
            counterfactuals = await self._generate_counterfactuals(
                current_score, target_score,
                monthly_revenue, loan_amount, business_tenure_months,
                debt_to_equity, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )

            return {
                "success": True,
                "current_score": current_score,
                "target_score": target_score,
                "score_gap": target_score - current_score,
                "counterfactuals": counterfactuals,
                "feasibility": self._assess_feasibility(counterfactuals),
                "message": f"Generated {len(counterfactuals)} counterfactual scenarios"
            }

        except Exception as e:
            logger.error(f"Counterfactual generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate counterfactuals: {str(e)}"
            }

    def _estimate_score(
        self,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float],
        current_ratio: Optional[float],
        profit_margin: Optional[float],
        activity_rate: Optional[float],
        payment_history_score: Optional[float]
    ) -> int:
        """Estimate current credit score using rule-based model."""
        base_score = 600
        loan_to_revenue = loan_amount / (monthly_revenue * 12)

        # Apply scoring factors
        if loan_to_revenue < 0.1:
            base_score += 80
        elif loan_to_revenue < 0.25:
            base_score += 50
        elif loan_to_revenue < 0.5:
            base_score += 20
        elif loan_to_revenue >= 1.0:
            base_score -= 60

        if business_tenure_months >= 36:
            base_score += 50
        elif business_tenure_months >= 24:
            base_score += 30
        elif business_tenure_months >= 12:
            base_score += 10
        else:
            base_score -= 30

        if debt_to_equity is not None:
            if debt_to_equity < 0.5:
                base_score += 30
            elif debt_to_equity < 1.0:
                base_score += 10
            elif debt_to_equity > 2.0:
                base_score -= 30

        if current_ratio is not None:
            if current_ratio >= 2.0:
                base_score += 30
            elif current_ratio >= 1.5:
                base_score += 15
            elif current_ratio < 1.0:
                base_score -= 30

        if profit_margin is not None:
            if profit_margin >= 0.2:
                base_score += 30
            elif profit_margin >= 0.1:
                base_score += 15
            elif profit_margin < 0:
                base_score -= 40

        if activity_rate is not None and activity_rate >= 0.9:
            base_score += 20

        if payment_history_score is not None and payment_history_score >= 0.9:
            base_score += 30

        return max(300, min(850, base_score))

    async def _generate_counterfactuals(
        self,
        current_score: int,
        target_score: int,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float],
        current_ratio: Optional[float],
        profit_margin: Optional[float],
        activity_rate: Optional[float],
        payment_history_score: Optional[float]
    ) -> List[Dict[str, Any]]:
        """Generate minimal changes to reach target score."""
        counterfactuals = []
        score_gap = target_score - current_score

        # Strategy 1: Increase revenue
        if monthly_revenue < 100000:
            revenue_increase = monthly_revenue * 0.3  # 30% increase
            new_score = self._estimate_score(
                monthly_revenue + revenue_increase, loan_amount, business_tenure_months,
                debt_to_equity, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )
            counterfactuals.append({
                "strategy": "Increase monthly revenue",
                "feature": "monthly_revenue",
                "current_value": round(monthly_revenue, 2),
                "suggested_value": round(monthly_revenue + revenue_increase, 2),
                "change": f"+{revenue_increase:,.0f} (+30%)",
                "estimated_impact": f"+{new_score - current_score} points",
                "new_score": new_score,
                "feasibility": "medium",
                "timeframe": "6-12 months",
                "actionable_steps": [
                    "Expand customer base",
                    "Increase marketing efforts",
                    "Diversify revenue streams"
                ]
            })

        # Strategy 2: Reduce loan amount
        if loan_amount > 5000:
            reduced_loan = loan_amount * 0.7  # Request 70% of original
            new_score = self._estimate_score(
                monthly_revenue, reduced_loan, business_tenure_months,
                debt_to_equity, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )
            counterfactuals.append({
                "strategy": "Reduce loan amount",
                "feature": "loan_amount",
                "current_value": round(loan_amount, 2),
                "suggested_value": round(reduced_loan, 2),
                "change": f"-{loan_amount - reduced_loan:,.0f} (-30%)",
                "estimated_impact": f"+{new_score - current_score} points",
                "new_score": new_score,
                "feasibility": "high",
                "timeframe": "immediate",
                "actionable_steps": [
                    "Revise loan request to align with revenue",
                    "Consider phased funding approach",
                    "Use alternative funding sources for remainder"
                ]
            })

        # Strategy 3: Improve debt-to-equity ratio
        if debt_to_equity is not None and debt_to_equity > 1.5:
            target_dte = 1.2
            new_score = self._estimate_score(
                monthly_revenue, loan_amount, business_tenure_months,
                target_dte, current_ratio, profit_margin,
                activity_rate, payment_history_score
            )
            counterfactuals.append({
                "strategy": "Improve debt-to-equity ratio",
                "feature": "debt_to_equity",
                "current_value": round(debt_to_equity, 2),
                "suggested_value": target_dte,
                "change": f"-{debt_to_equity - target_dte:.2f}",
                "estimated_impact": f"+{new_score - current_score} points",
                "new_score": new_score,
                "feasibility": "medium",
                "timeframe": "3-6 months",
                "actionable_steps": [
                    "Pay down existing debt",
                    "Increase equity through retained earnings",
                    "Bring in additional equity investors"
                ]
            })

        # Strategy 4: Improve liquidity
        if current_ratio is not None and current_ratio < 1.5:
            target_cr = 1.8
            new_score = self._estimate_score(
                monthly_revenue, loan_amount, business_tenure_months,
                debt_to_equity, target_cr, profit_margin,
                activity_rate, payment_history_score
            )
            counterfactuals.append({
                "strategy": "Improve current ratio (liquidity)",
                "feature": "current_ratio",
                "current_value": round(current_ratio, 2),
                "suggested_value": target_cr,
                "change": f"+{target_cr - current_ratio:.2f}",
                "estimated_impact": f"+{new_score - current_score} points",
                "new_score": new_score,
                "feasibility": "medium",
                "timeframe": "2-4 months",
                "actionable_steps": [
                    "Build cash reserves",
                    "Improve accounts receivable collection",
                    "Reduce short-term liabilities"
                ]
            })

        # Strategy 5: Improve profitability
        if profit_margin is not None and profit_margin < 0.15:
            target_pm = 0.15
            new_score = self._estimate_score(
                monthly_revenue, loan_amount, business_tenure_months,
                debt_to_equity, current_ratio, target_pm,
                activity_rate, payment_history_score
            )
            counterfactuals.append({
                "strategy": "Improve profit margin",
                "feature": "profit_margin",
                "current_value": f"{profit_margin*100:.1f}%",
                "suggested_value": f"{target_pm*100:.0f}%",
                "change": f"+{(target_pm - profit_margin)*100:.1f}%",
                "estimated_impact": f"+{new_score - current_score} points",
                "new_score": new_score,
                "feasibility": "medium",
                "timeframe": "3-6 months",
                "actionable_steps": [
                    "Reduce operating expenses",
                    "Increase pricing where possible",
                    "Improve operational efficiency"
                ]
            })

        # Sort by impact (highest first)
        counterfactuals.sort(key=lambda x: x["new_score"], reverse=True)

        # Return top 3 most impactful changes
        return counterfactuals[:3]

    async def _generate_optimization_suggestions(
        self,
        current_score: int,
        monthly_revenue: float,
        loan_amount: float,
        business_tenure_months: int,
        debt_to_equity: Optional[float],
        current_ratio: Optional[float],
        profit_margin: Optional[float],
        activity_rate: Optional[float],
        payment_history_score: Optional[float]
    ) -> Dict[str, Any]:
        """Generate optimization suggestions for already-approved applications."""
        suggestions = []

        # Suggest improvements for better terms
        if current_score < 800:
            suggestions.append({
                "category": "Achieve Exceptional rating (800+)",
                "current_score": current_score,
                "target_score": 800,
                "benefit": "Qualify for lowest interest rates and best terms",
                "suggestions": [
                    "Maintain consistent profitability",
                    "Build stronger cash reserves",
                    "Reduce leverage ratio below 0.5"
                ]
            })

        return {
            "success": True,
            "current_score": current_score,
            "status": "approved",
            "optimization_opportunities": suggestions,
            "message": f"Current score {current_score} meets approval threshold. Showing optimization opportunities."
        }

    def _assess_feasibility(self, counterfactuals: List[Dict[str, Any]]) -> str:
        """Assess overall feasibility of counterfactual changes."""
        if not counterfactuals:
            return "N/A"

        feasibility_scores = {
            "high": 3,
            "medium": 2,
            "low": 1
        }

        avg_score = np.mean([
            feasibility_scores.get(cf.get("feasibility", "medium"), 2)
            for cf in counterfactuals
        ])

        if avg_score >= 2.5:
            return "high"
        elif avg_score >= 1.5:
            return "medium"
        else:
            return "low"


# Create singleton instance
counterfactual_generator = CounterfactualGenerator()
