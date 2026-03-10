"""
Counterfactual Explanation Generator

Exact implementation from run_counterfactuals() in streamlit_demo.py.
Simple perturbation approach - tests one feature at a time.
Returns top 5 changes that reach 670+ score.
"""

import logging
from typing import Dict, Any, List
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Feature names from credit_risk_dataset
FEATURE_NAMES = [
    "person_age", "person_income", "person_home_ownership",
    "person_emp_length", "loan_intent", "loan_grade",
    "loan_amnt", "loan_int_rate", "loan_percent_income",
    "cb_person_default_on_file", "cb_person_cred_hist_length"
]


class CounterfactualInput(BaseModel):
    """Input schema for Counterfactual Generator."""
    person_age: float = Field(description="Applicant age")
    person_income: float = Field(description="Annual income")
    person_home_ownership: str = Field(description="Home ownership")
    person_emp_length: float = Field(description="Employment length")
    loan_intent: str = Field(description="Loan intent")
    loan_grade: str = Field(description="Loan grade")
    loan_amnt: float = Field(description="Loan amount")
    loan_int_rate: float = Field(description="Interest rate")
    loan_percent_income: float = Field(description="Loan % of income")
    cb_person_default_on_file: str = Field(description="Default on file")
    cb_person_cred_hist_length: float = Field(description="Credit history")


class CounterfactualGenerator(BaseTool):
    """
    Counterfactual generator - exact from run_counterfactuals() in notebook.

    Perturbs one feature at a time.
    Tests specific changes to 6 features.
    Returns top 5 single-feature changes that reach 670+.
    """

    def __init__(self, model=None):
        super().__init__()
        self.xgb_model = model

    @staticmethod
    def prob_to_score(p: float) -> int:
        """Convert probability to score (same as credit_score_model)."""
        return int(850 - p * 550)

    @staticmethod
    def score_band(score: int) -> str:
        """Get score band (same as credit_score_model)."""
        if score >= 800: return "Exceptional"
        if score >= 740: return "Very Good"
        if score >= 670: return "Good"
        if score >= 580: return "Fair"
        return "Poor"

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
        Generate counterfactuals - exact from run_counterfactuals() in notebook.

        Returns list of dicts with action, feature, current, target, delta, new_score, new_band.
        """
        try:
            if not self.xgb_model:
                return {
                    "success": False,
                    "message": "Counterfactuals require trained XGBoost model"
                }

            from sklearn.preprocessing import LabelEncoder

            # Build row
            row = pd.Series({
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
            })

            # Encode categoricals (same as credit_score_model)
            le = LabelEncoder()
            for col in ["person_home_ownership", "loan_intent", "loan_grade", "cb_person_default_on_file"]:
                if col in row and isinstance(row[col], str):
                    if col == "person_home_ownership":
                        le.fit(["RENT", "OWN", "MORTGAGE", "OTHER"])
                    elif col == "loan_intent":
                        le.fit(["PERSONAL", "EDUCATION", "MEDICAL", "VENTURE", "HOMEIMPROVEMENT", "DEBTCONSOLIDATION"])
                    elif col == "loan_grade":
                        le.fit(["A", "B", "C", "D", "E", "F", "G"])
                    elif col == "cb_person_default_on_file":
                        le.fit(["N", "Y"])
                    row[col] = le.transform([row[col]])[0]

            # Perturbations (exact from notebook)
            perturbations = {
                "loan_amnt": [row["loan_amnt"] * 0.7, row["loan_amnt"] * 0.5],
                "person_income": [row["person_income"] * 1.3, row["person_income"] * 1.6],
                "loan_int_rate": [row["loan_int_rate"] * 0.8, row["loan_int_rate"] * 0.6],
                "loan_percent_income": [row["loan_percent_income"] * 0.7, row["loan_percent_income"] * 0.5],
                "person_emp_length": [row["person_emp_length"] + 2, row["person_emp_length"] + 4],
                "cb_person_cred_hist_length": [row["cb_person_cred_hist_length"] + 2, row["cb_person_cred_hist_length"] + 4],
            }

            cfs = []
            for feat, values in perturbations.items():
                if feat not in FEATURE_NAMES:
                    continue
                for new_val in values:
                    candidate = row[FEATURE_NAMES].copy()
                    candidate[feat] = new_val
                    new_prob = float(self.xgb_model.predict_proba(candidate.values.reshape(1, -1))[0, 1])
                    new_score = self.prob_to_score(new_prob)
                    if new_score >= 670:
                        delta = new_val - row[feat]
                        cfs.append({
                            "action": f"{'Increase' if delta > 0 else 'Decrease'} {feat.replace('_', ' ')}",
                            "feature": feat,
                            "current": round(float(row[feat]), 2),
                            "target": round(float(new_val), 2),
                            "delta": round(float(delta), 2),
                            "new_score": new_score,
                            "new_band": self.score_band(new_score),
                        })
                        break

            return {
                "success": True,
                "counterfactuals": cfs[:5],
                "message": f"Found {len(cfs[:5])} counterfactual paths to approval"
            }

        except Exception as e:
            logger.error(f"Counterfactual generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate counterfactuals: {str(e)}"
            }


# Create singleton instance
counterfactual_generator = CounterfactualGenerator()
