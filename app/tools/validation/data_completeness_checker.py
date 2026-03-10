"""
Data Completeness Checker Tool

Exact implementation from run_completeness() in streamlit_demo.py.
Uses mean_abs_shap to rank missing fields by importance.
"""

import logging
from typing import Dict, Any, Optional
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


class DataCompletenessInput(BaseModel):
    """Input schema for Data Completeness Checker."""
    person_age: Optional[float] = Field(default=None, description="Applicant age")
    person_income: Optional[float] = Field(default=None, description="Annual income")
    person_home_ownership: Optional[str] = Field(default=None, description="Home ownership")
    person_emp_length: Optional[float] = Field(default=None, description="Employment length")
    loan_intent: Optional[str] = Field(default=None, description="Loan intent")
    loan_grade: Optional[str] = Field(default=None, description="Loan grade")
    loan_amnt: Optional[float] = Field(default=None, description="Loan amount")
    loan_int_rate: Optional[float] = Field(default=None, description="Interest rate")
    loan_percent_income: Optional[float] = Field(default=None, description="Loan % of income")
    cb_person_default_on_file: Optional[str] = Field(default=None, description="Default on file")
    cb_person_cred_hist_length: Optional[float] = Field(default=None, description="Credit history")


class DataCompletenessChecker(BaseTool):
    """
    Data completeness checker - exact from run_completeness() in notebook.

    Uses mean_abs_shap computed from SHAP explainer.
    Threshold: 0.60 (60%) to proceed.
    Returns missing fields ranked by SHAP importance.
    """

    def __init__(self, mean_abs_shap=None, X_train=None):
        super().__init__()
        self.mean_abs_shap = mean_abs_shap
        self.X_train = X_train

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
        person_age: Optional[float] = None,
        person_income: Optional[float] = None,
        person_home_ownership: Optional[str] = None,
        person_emp_length: Optional[float] = None,
        loan_intent: Optional[str] = None,
        loan_grade: Optional[str] = None,
        loan_amnt: Optional[float] = None,
        loan_int_rate: Optional[float] = None,
        loan_percent_income: Optional[float] = None,
        cb_person_default_on_file: Optional[str] = None,
        cb_person_cred_hist_length: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Check completeness - exact from run_completeness() in notebook.

        Returns:
            - completeness_score: present_imp / total_imp
            - missing_fields: Dict ranked by SHAP importance
            - imputed_row: Row with median imputation
            - can_proceed: score >= 0.60
        """
        try:
            import pandas as pd

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

            # Find missing and present (exact from notebook)
            missing = [f for f in FEATURE_NAMES if pd.isna(row.get(f, None))]
            present = [f for f in FEATURE_NAMES if not pd.isna(row.get(f, None))]

            # Use mean_abs_shap if available, otherwise equal weights
            if self.mean_abs_shap is not None:
                total_imp = self.mean_abs_shap.sum()
                present_imp = self.mean_abs_shap[present].sum() if present else 0.0
            else:
                total_imp = len(FEATURE_NAMES)
                present_imp = len(present)

            score = float(present_imp / total_imp) if total_imp > 0 else 1.0

            # Impute missing with median (exact from notebook)
            imputed = row.copy()
            if self.X_train is not None:
                for f in missing:
                    imputed[f] = float(self.X_train[f].median())

            # Rank missing fields by SHAP importance
            if self.mean_abs_shap is not None and missing:
                missing_ranked = self.mean_abs_shap[missing].sort_values(ascending=False).to_dict()
            else:
                missing_ranked = {}

            return {
                "success": True,
                "completeness_score": round(score, 3),
                "missing_fields": missing_ranked,
                "imputed_row": imputed.to_dict(),
                "can_proceed": score >= 0.60,
                "message": f"Completeness: {score:.1%}, Can proceed: {score >= 0.60}"
            }

        except Exception as e:
            logger.error(f"Data completeness check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to check completeness: {str(e)}"
            }


# Create singleton instance
data_completeness_checker = DataCompletenessChecker()
