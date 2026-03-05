"""
Integration tests for loan assessment workflow
"""

import pytest
from app.tools.credit_scoring.credit_score_model import credit_score_model
from app.tools.validation.data_completeness_checker import data_completeness_checker
from app.tools.explainability.shap_explainer import shap_explainer
from app.tools.explainability.counterfactual_generator import counterfactual_generator


@pytest.mark.asyncio
class TestLoanAssessmentWorkflow:
    """Test complete loan assessment workflow"""

    async def test_approved_application(self):
        """Test successful loan approval workflow"""
        # Strong application
        result = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=36,
            debt_to_equity=0.8,
            current_ratio=1.8,
            profit_margin=0.15,
            activity_rate=0.95,
            payment_history_score=0.9
        )

        assert result["success"] is True
        assert result["credit_score"] >= 670
        assert result["score_band"] in ["Good", "Very Good", "Exceptional"]
        assert result["default_probability"] < 0.5

    async def test_declined_application(self):
        """Test declined application workflow"""
        # Weak application
        result = await credit_score_model.execute(
            monthly_revenue=10000,
            loan_amount=15000,
            business_tenure_months=6,
            debt_to_equity=3.0,
            current_ratio=0.8,
            profit_margin=-0.05
        )

        assert result["success"] is True
        assert result["credit_score"] < 670
        assert result["default_probability"] > 0.3

    async def test_data_completeness_check(self):
        """Test data completeness validation"""
        result = await data_completeness_checker.execute(
            monthly_revenue=50000,
            loan_amount=10000,
            business_tenure_months=24,
            debt_to_equity=None,  # Missing
            current_ratio=None,  # Missing
            profit_margin=0.1
        )

        assert result["success"] is True
        assert result["completeness_score"] < 1.0
        assert len(result["missing_fields"]) > 0

    async def test_shap_explanations(self):
        """Test SHAP feature importance explanations"""
        result = await shap_explainer.execute(
            monthly_revenue=50000,
            loan_amount=10000,
            business_tenure_months=24,
            debt_to_equity=1.5,
            current_ratio=1.5,
            profit_margin=0.12
        )

        assert result["success"] is True
        assert "top_features" in result
        assert len(result["top_features"]) > 0
        assert "explanations" in result

    async def test_counterfactual_generation(self):
        """Test counterfactual recommendations"""
        # Borderline application
        result = await counterfactual_generator.execute(
            monthly_revenue=30000,
            loan_amount=10000,
            business_tenure_months=18,
            debt_to_equity=2.0,
            current_ratio=1.2,
            profit_margin=0.08,
            target_score=670
        )

        assert result["success"] is True
        assert "counterfactuals" in result
        assert len(result["counterfactuals"]) > 0
        assert "feasibility" in result

    async def test_complete_workflow(self):
        """Test complete end-to-end loan assessment"""
        # Step 1: Check data completeness
        completeness = await data_completeness_checker.execute(
            monthly_revenue=45000,
            loan_amount=8000,
            business_tenure_months=20,
            debt_to_equity=1.6,
            current_ratio=1.4,
            profit_margin=0.11,
            activity_rate=0.85
        )
        assert completeness["success"] is True

        # Step 2: Calculate credit score
        score = await credit_score_model.execute(
            monthly_revenue=45000,
            loan_amount=8000,
            business_tenure_months=20,
            debt_to_equity=1.6,
            current_ratio=1.4,
            profit_margin=0.11,
            activity_rate=0.85
        )
        assert score["success"] is True

        # Step 3: Explain decision
        explanation = await shap_explainer.execute(
            monthly_revenue=45000,
            loan_amount=8000,
            business_tenure_months=20,
            debt_to_equity=1.6,
            current_ratio=1.4,
            profit_margin=0.11,
            activity_rate=0.85
        )
        assert explanation["success"] is True

        # Step 4: Generate counterfactuals if needed
        if score["credit_score"] < 740:
            counterfactual = await counterfactual_generator.execute(
                monthly_revenue=45000,
                loan_amount=8000,
                business_tenure_months=20,
                debt_to_equity=1.6,
                current_ratio=1.4,
                profit_margin=0.11,
                activity_rate=0.85,
                target_score=740
            )
            assert counterfactual["success"] is True


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling"""

    async def test_zero_revenue(self):
        """Test handling of zero revenue"""
        result = await credit_score_model.execute(
            monthly_revenue=0,
            loan_amount=5000,
            business_tenure_months=12
        )
        assert result["success"] is True
        assert result["credit_score"] == 300  # Minimum score

    async def test_negative_profit_margin(self):
        """Test unprofitable business"""
        result = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=24,
            profit_margin=-0.15
        )
        assert result["success"] is True
        assert result["credit_score"] < 600

    async def test_very_high_loan_to_revenue(self):
        """Test excessive loan amount"""
        result = await credit_score_model.execute(
            monthly_revenue=10000,
            loan_amount=200000,  # 20x annual revenue
            business_tenure_months=12
        )
        assert result["success"] is True
        assert result["default_probability"] > 0.5

    async def test_startup_business(self):
        """Test very new business"""
        result = await credit_score_model.execute(
            monthly_revenue=30000,
            loan_amount=5000,
            business_tenure_months=3  # 3 months old
        )
        assert result["success"] is True
        assert result["credit_score"] < 650


@pytest.mark.asyncio
class TestModelConsistency:
    """Test model consistency and behavior"""

    async def test_score_increases_with_revenue(self):
        """Higher revenue should increase score"""
        low_revenue = await credit_score_model.execute(
            monthly_revenue=20000,
            loan_amount=5000,
            business_tenure_months=24
        )

        high_revenue = await credit_score_model.execute(
            monthly_revenue=80000,
            loan_amount=5000,
            business_tenure_months=24
        )

        assert high_revenue["credit_score"] > low_revenue["credit_score"]

    async def test_score_decreases_with_loan_amount(self):
        """Higher loan amount should decrease score"""
        small_loan = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=2000,
            business_tenure_months=24
        )

        large_loan = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=20000,
            business_tenure_months=24
        )

        assert small_loan["credit_score"] > large_loan["credit_score"]

    async def test_score_increases_with_tenure(self):
        """Longer tenure should increase score"""
        new_business = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=6
        )

        established = await credit_score_model.execute(
            monthly_revenue=50000,
            loan_amount=5000,
            business_tenure_months=48
        )

        assert established["credit_score"] > new_business["credit_score"]
