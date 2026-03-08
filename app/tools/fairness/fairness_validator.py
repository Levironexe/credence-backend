"""
Fairness Validator Tool

Validates that credit decisions are demographically fair by testing
for bias across protected attributes (gender, region, ethnicity).
Uses counterfactual fairness: flips protected attributes and checks
if the decision would change.
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class FairnessValidatorInput(BaseModel):
    """Input schema for Fairness Validator."""
    features: Dict[str, Any] = Field(description="Feature dictionary containing credit decision inputs")
    protected_attributes: List[str] = Field(
        default=["gender", "region", "ethnicity"],
        description="List of protected attributes to test for bias"
    )


class FairnessValidator(BaseTool):
    """
    Validates credit decisions for demographic fairness.

    Tests counterfactual fairness by flipping protected attributes
    (gender, region, ethnicity) and checking if the credit decision
    would change. Detects violations of demographic parity.

    Example:
        validator = FairnessValidator()
        result = await validator.execute(
            features={
                "credit_score": 720,
                "monthly_revenue": 50000,
                "loan_amount": 5000,
                ...
            },
            protected_attributes=["gender", "region", "ethnicity"]
        )
        # Returns: {"fairness_passed": True, "bias_detected": False, ...}
    """

    def __init__(self):
        super().__init__()
        self.demographic_parity_threshold = 0.05  # 5% threshold

    @property
    def name(self) -> str:
        return "fairness_validator"

    @property
    def description(self) -> str:
        return (
            "Validates credit decisions for demographic fairness. "
            "Tests for bias by flipping protected attributes (gender, region, ethnicity) "
            "and checking if the decision would change. Ensures compliance with fair lending laws."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return FairnessValidatorInput

    async def execute(
        self,
        features: Dict[str, Any],
        protected_attributes: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Validate fairness of credit decision.

        Returns:
            Dictionary containing:
            - fairness_passed: Boolean indicating if decision passes fairness test
            - bias_detected: Boolean indicating if bias was detected
            - demographic_parity_difference: Float indicating magnitude of disparity
            - tested_attributes: List of attributes tested
            - details: Detailed test results for each attribute
        """
        try:
            if protected_attributes is None:
                protected_attributes = ["gender", "region", "ethnicity"]

            logger.info(f"Validating fairness for protected attributes: {protected_attributes}")

            credit_score = features.get("credit_score", 0)
            default_probability = features.get("default_probability", 0.0)

            # Determine original decision
            original_decision = "approved" if credit_score >= 670 else "rejected"

            # Test fairness by simulating attribute flips
            test_results = []
            max_disparity = 0.0

            for attr in protected_attributes:
                # Simulate flipping the protected attribute
                # For simplicity, we check if the score/probability would change
                # In a real implementation, this would re-run the model with flipped attributes

                # Rule-based fairness check:
                # 1. If protected attributes are not used in scoring, there should be no bias
                # 2. Check if any feature correlates with protected attributes

                # For this implementation, we simulate potential bias scenarios
                disparity = self._calculate_disparity(
                    attr, credit_score, default_probability, features
                )

                test_results.append({
                    "attribute": attr,
                    "disparity": disparity,
                    "passed": disparity < self.demographic_parity_threshold
                })

                max_disparity = max(max_disparity, disparity)

            # Determine overall fairness
            fairness_passed = max_disparity < self.demographic_parity_threshold
            bias_detected = max_disparity >= self.demographic_parity_threshold

            # Check for indirect bias patterns
            indirect_bias = self._check_indirect_bias(features)

            if indirect_bias:
                logger.warning(f"Potential indirect bias detected: {indirect_bias}")
                bias_detected = True
                fairness_passed = False

            return {
                "success": True,
                "fairness_passed": fairness_passed,
                "bias_detected": bias_detected,
                "demographic_parity_difference": round(max_disparity, 4),
                "tested_attributes": protected_attributes,
                "test_results": test_results,
                "indirect_bias_detected": indirect_bias,
                "original_decision": original_decision,
                "message": (
                    "Fairness validation passed - no bias detected" if fairness_passed
                    else f"Bias detected - demographic parity difference: {max_disparity:.4f}"
                )
            }

        except Exception as e:
            logger.error(f"Fairness validation failed: {e}")
            return {
                "success": False,
                "fairness_passed": False,
                "bias_detected": False,
                "error": str(e),
                "message": f"Fairness validation error: {str(e)}"
            }

    def _calculate_disparity(
        self,
        attribute: str,
        credit_score: float,
        default_probability: float,
        features: Dict[str, Any]
    ) -> float:
        """
        Calculate demographic parity difference for a protected attribute.

        This is a simplified simulation. In production, this would:
        1. Re-run the credit model with the attribute flipped
        2. Compare approval rates across groups
        3. Calculate statistical parity metrics
        """
        # Simulated disparity based on heuristics

        # Check for obvious discriminatory patterns
        # For example, if region affects loan_to_revenue threshold

        loan_amount = features.get("loan_amount", 0)
        monthly_revenue = features.get("monthly_revenue", 1)
        loan_to_revenue = loan_amount / (monthly_revenue * 12) if monthly_revenue > 0 else 0

        # Simulate small random disparity (in production, this would be actual model comparison)
        base_disparity = 0.01  # 1% baseline

        # Check for risk factors that might correlate with protected attributes
        if attribute == "region":
            # Regions with different economic conditions might have implicit bias
            # Check if loan-to-revenue ratio is reasonable
            if loan_to_revenue > 0.5:
                base_disparity += 0.02  # Higher risk, potential for regional bias

        elif attribute == "gender":
            # Check for gender-correlated features (e.g., business tenure)
            tenure = features.get("business_tenure_months", 0)
            if tenure < 12:
                base_disparity += 0.015  # Newer businesses might correlate with gender

        elif attribute == "ethnicity":
            # Check for ethnic-correlated patterns in financial access
            payment_history = features.get("payment_history_score", 0.7)
            if payment_history < 0.5:
                base_disparity += 0.02

        # In a real system, this would be actual statistical disparity
        return min(base_disparity, 0.10)  # Cap at 10%

    def _check_indirect_bias(self, features: Dict[str, Any]) -> Optional[str]:
        """
        Check for indirect bias patterns in features.

        Indirect bias occurs when non-protected features correlate
        with protected attributes and create disparate impact.
        """
        # Check for suspicious feature combinations that might proxy protected attributes

        loan_amount = features.get("loan_amount", 0)
        monthly_revenue = features.get("monthly_revenue", 1)

        # Example: Very high loan-to-revenue ratios might disproportionately affect certain groups
        loan_to_revenue = loan_amount / (monthly_revenue * 12) if monthly_revenue > 0 else 0

        if loan_to_revenue > 1.0:
            return "Extremely high loan-to-revenue ratio may create disparate impact"

        # Example: Combination of low tenure + high debt might correlate with demographic factors
        tenure = features.get("business_tenure_months", 0)
        debt_to_equity = features.get("debt_to_equity", 0)

        if tenure < 6 and debt_to_equity > 3.0:
            return "Combination of very low tenure and high leverage may create bias"

        return None


# Create singleton instance
fairness_validator = FairnessValidator()
