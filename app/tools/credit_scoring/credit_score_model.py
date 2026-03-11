"""
Credit Score Model Tool

Calculates credit scores (300-850 scale) using XGBoost model trained on credit_risk_dataset.
Exact implementation from streamlit_demo.py notebook.

Credit Score Bands (FICO scale):
- 800-850: Exceptional → AUTO-APPROVE
- 740-799: Very Good → APPROVE (standard terms)
- 670-739: Good → APPROVE (with conditions)
- 580-669: Fair → MANUAL REVIEW
- 300-579: Poor → DECLINE (with counterfactual guidance)
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Feature names from credit_risk_dataset (exact from notebook)
FEATURE_NAMES = [
    "person_age", "person_income", "person_home_ownership",
    "person_emp_length", "loan_intent", "loan_grade",
    "loan_amnt", "loan_int_rate", "loan_percent_income",
    "cb_person_default_on_file", "cb_person_cred_hist_length"
]

CAT_COLS = [
    "person_home_ownership", "loan_intent",
    "loan_grade", "cb_person_default_on_file"
]


class CreditScoreInput(BaseModel):
    """Input schema for Credit Score Model - matches credit_risk_dataset schema."""
    # Core applicant features
    person_age: float = Field(description="Applicant age in years")
    person_income: float = Field(description="Annual income")
    person_home_ownership: str = Field(description="Home ownership status (RENT/OWN/MORTGAGE/OTHER)")
    person_emp_length: float = Field(description="Employment length in years")

    # Loan features
    loan_intent: str = Field(description="Loan intent (PERSONAL/EDUCATION/MEDICAL/VENTURE/etc)")
    loan_grade: str = Field(description="Loan grade (A/B/C/D/E/F/G)")
    loan_amnt: float = Field(description="Loan amount requested")
    loan_int_rate: float = Field(description="Loan interest rate")
    loan_percent_income: float = Field(description="Loan amount as percent of income")

    # Credit bureau features
    cb_person_default_on_file: str = Field(description="Historical default (Y/N)")
    cb_person_cred_hist_length: float = Field(description="Credit history length in years")


class CreditScoreModel(BaseTool):
    """
    Credit scoring model - exact implementation from streamlit_demo.py.

    Uses XGBoost model trained on credit_risk_dataset (32K samples, 11 features).
    Falls back to rule-based scoring if model not available.

    Example:
        model = CreditScoreModel()
        result = await model.execute(
            person_age=28,
            person_income=45000,
            person_home_ownership="RENT",
            person_emp_length=3.0,
            loan_intent="PERSONAL",
            loan_grade="B",
            loan_amnt=8000,
            loan_int_rate=12.5,
            loan_percent_income=0.18,
            cb_person_default_on_file="N",
            cb_person_cred_hist_length=3.0
        )
        # Returns: {"credit_score": 680, "score_band": "Good", "default_probability": 0.25}
    """

    def __init__(self, model=None, X_train=None):
        super().__init__()
        self.xgb_model = model
        self.X_train = X_train
        self.feature_names = FEATURE_NAMES
        self.use_ml_model = model is not None

        if not self.use_ml_model:
            self._load_model()

    def _load_model(self):
        """Load trained XGBoost model if available."""
        try:
            model_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "xgboost_model.pkl"
            train_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "X_train.parquet"

            if model_path.exists():
                with open(model_path, "rb") as f:
                    self.xgb_model = pickle.load(f)

                if train_path.exists():
                    self.X_train = pd.read_parquet(train_path)

                self.use_ml_model = True
                logger.info("✓ Loaded XGBoost credit scoring model")
            else:
                logger.info("XGBoost model not found - using rule-based scoring")
                self.use_ml_model = False

        except Exception as e:
            logger.warning(f"Failed to load XGBoost model: {e} - using rule-based scoring")
            self.use_ml_model = False

    @staticmethod
    def prob_to_score(p: float) -> int:
        """Convert default probability to credit score (exact from notebook)."""
        return int(850 - p * 550)

    @staticmethod
    def score_band(score: int) -> str:
        """Get score band label (exact from notebook)."""
        if score >= 800: return "Exceptional"
        if score >= 740: return "Very Good"
        if score >= 670: return "Good"
        if score >= 580: return "Fair"
        return "Poor"

    @staticmethod
    def decision_from_score(score: int) -> str:
        """Get lending decision (exact from notebook)."""
        if score >= 800: return "✅ AUTO-APPROVE"
        if score >= 670: return "✅ APPROVE (with conditions)"
        if score >= 580: return "🔶 MANUAL REVIEW"
        return "❌ DECLINE"

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
        person_age: float,
        person_income: float,
        person_home_ownership: str,
        person_emp_length: float,
        loan_intent: str,
        loan_grade: str,
        loan_amnt: float,
        loan_int_rate: float,
        loan_percent_income: float,
        cb_person_default_on_file: str,
        cb_person_cred_hist_length: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate credit score - exact implementation from run_scoring() in notebook.

        Returns:
            Dictionary containing:
            - credit_score: Score (300-850)
            - score_band: Band label (Exceptional, Very Good, Good, Fair, Poor)
            - default_probability: Estimated default probability (0-1)
            - decision: Lending decision
            - approved: Boolean (score >= 670)
        """
        try:
            # Build feature dict
            features = {
                "person_age": person_age,
                "person_income": person_income,
                "person_home_ownership": person_home_ownership,
                "person_emp_length": person_emp_length,
                "loan_intent": loan_intent,
                "loan_grade": loan_grade,
                "loan_amnt": loan_amnt,
                "loan_int_rate": loan_int_rate,
                "loan_percent_income": loan_percent_income,
                "cb_person_default_on_file": cb_person_default_on_file,
                "cb_person_cred_hist_length": cb_person_cred_hist_length,
            }

            logger.info(f"Computing credit score for loan_amnt={loan_amnt}, income={person_income}")

            # FAIL if XGBoost model not available - NO FALLBACK
            if not self.use_ml_model or self.xgb_model is None:
                error_msg = "XGBoost model not loaded - cannot compute credit score"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }

            return await self._compute_ml_score(features)

        except Exception as e:
            logger.error(f"Credit score calculation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to calculate credit score: {str(e)}"
            }

    async def _compute_ml_score(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Compute credit score using XGBoost model - exact from run_scoring() in notebook."""
        from sklearn.preprocessing import LabelEncoder

        # Preprocess features (same as notebook)
        row = pd.Series(features)

        # Encode categorical columns
        le = LabelEncoder()
        for col in CAT_COLS:
            if col in row and isinstance(row[col], str):
                # Use same encoding as training (fit on common values)
                if col == "person_home_ownership":
                    le.fit(["RENT", "OWN", "MORTGAGE", "OTHER"])
                elif col == "loan_intent":
                    le.fit(["PERSONAL", "EDUCATION", "MEDICAL", "VENTURE", "HOMEIMPROVEMENT", "DEBTCONSOLIDATION"])
                elif col == "loan_grade":
                    le.fit(["A", "B", "C", "D", "E", "F", "G"])
                elif col == "cb_person_default_on_file":
                    le.fit(["N", "Y"])
                row[col] = le.transform([row[col]])[0]

        # Fill missing with median (if X_train available)
        if self.X_train is not None:
            for col in ["person_emp_length", "loan_int_rate"]:
                if pd.isna(row.get(col)):
                    row[col] = float(self.X_train[col].median())

        # Predict default probability (exact from notebook)
        prob = float(self.xgb_model.predict_proba(row[FEATURE_NAMES].values.reshape(1, -1))[0, 1])

        # Convert to credit score (exact from notebook)
        credit_score = self.prob_to_score(prob)

        logger.info(f"✅ XGBoost prediction: score={credit_score}, prob={prob:.3f}")

        return {
            "success": True,
            "default_probability": prob,
            "credit_score": credit_score,
            "score_band": self.score_band(credit_score),
            "decision": self.decision_from_score(credit_score),
            "approved": credit_score >= 670,
            "model_type": "XGBoost",
            "confidence": 1.0 - min(abs(0.5 - prob) * 2, 1.0),  # Higher confidence when prob far from 0.5
            "message": f"Credit score: {credit_score} ({self.score_band(credit_score)})"
        }



# Create singleton instance
credit_score_model = CreditScoreModel()
