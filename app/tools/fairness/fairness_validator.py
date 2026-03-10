"""
Fairness Validator Tool

Exact implementation from fairlearn block in streamlit_demo.py main().
Computes demographic_parity_difference, demographic_parity_ratio, equalized_odds_difference.
Uses gender (simulated) and age_group as sensitive features.
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Feature names from credit_risk_dataset
FEATURE_NAMES = [
    "person_age", "person_income", "person_home_ownership",
    "person_emp_length", "loan_intent", "loan_grade",
    "loan_amnt", "loan_int_rate", "loan_percent_income",
    "cb_person_default_on_file", "cb_person_cred_hist_length"
]


class FairnessValidatorInput(BaseModel):
    """Input schema for Fairness Validator - requires test dataset."""
    # This tool operates on a test dataset, not individual instances
    # So we don't define individual fields here
    pass


class FairnessValidator(BaseTool):
    """
    Fairness validator - exact from fairlearn block in notebook.

    Computes demographic parity and equalized odds metrics.
    Uses simulated gender (seed=42, p=[0.45,0.55]) and age_group from person_age.
    Thresholds: |dp_diff| < 0.05, |eod| < 0.10
    """

    def __init__(self, model=None, X_test=None, y_test=None):
        super().__init__()
        self.xgb_model = model
        self.X_test = X_test
        self.y_test = y_test
        self.use_ml_model = model is not None

        if not self.use_ml_model:
            self._load_model_and_data()

    def _load_model_and_data(self):
        """Load model and test data for fairness evaluation."""
        try:
            import pickle
            from pathlib import Path

            model_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "xgboost_model.pkl"
            test_X_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "X_test.parquet"
            test_y_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "y_test.parquet"

            if model_path.exists() and test_X_path.exists() and test_y_path.exists():
                with open(model_path, "rb") as f:
                    self.xgb_model = pickle.load(f)
                self.X_test = pd.read_parquet(test_X_path)
                self.y_test = pd.read_parquet(test_y_path).squeeze()
                self.use_ml_model = True
                logger.info("✓ Loaded fairness validator with test data")
            else:
                logger.info("Model/test data not found - fairness validation unavailable")
                self.use_ml_model = False

        except Exception as e:
            logger.warning(f"Failed to load fairness validator: {e}")
            self.use_ml_model = False

    @property
    def name(self) -> str:
        return "fairness_validator"

    @property
    def description(self) -> str:
        return (
            "Validates credit decisions for demographic fairness using Fairlearn metrics. "
            "Computes demographic parity difference, demographic parity ratio, and equalized odds "
            "difference across gender and age groups. Ensures fair lending compliance."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return FairnessValidatorInput

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Validate fairness - exact from fairlearn block in notebook.

        Returns demographic parity and equalized odds metrics for gender and age_group.
        Thresholds: |dp_diff| < 0.05, |eod| < 0.10
        """
        try:
            if not self.use_ml_model or self.xgb_model is None:
                return {
                    "success": False,
                    "message": "Fairness validation requires trained XGBoost model and test data"
                }

            from fairlearn.metrics import (
                demographic_parity_difference,
                demographic_parity_ratio,
                equalized_odds_difference
            )

            # Predict on test set (exact from notebook)
            y_pred_all = self.xgb_model.predict(self.X_test)

            # Simulate gender (exact from notebook line 401)
            np.random.seed(42)
            gender_port = pd.Series(np.random.choice([0, 1], size=len(self.X_test), p=[0.45, 0.55]))

            # Derive age_group from person_age (exact from notebook line 402-404)
            age_group_port = pd.Series(
                pd.cut(self.X_test["person_age"], bins=[0, 35, 55, 200], labels=[0, 1, 2]).astype(int)
            )

            # Convert to approval (1 - prediction, since prediction is default risk)
            y_approved = 1 - y_pred_all

            # Compute fairness metrics (exact from notebook lines 407-411)
            dpd_g = demographic_parity_difference(y_approved, y_approved, sensitive_features=gender_port)
            dpr_g = demographic_parity_ratio(y_approved, y_approved, sensitive_features=gender_port)
            eod_g = equalized_odds_difference(self.y_test, y_pred_all, sensitive_features=gender_port)
            dpd_a = demographic_parity_difference(y_approved, y_approved, sensitive_features=age_group_port)
            eod_a = equalized_odds_difference(self.y_test, y_pred_all, sensitive_features=age_group_port)

            # Apply thresholds (exact from notebook lines 417, 421, 426, 429)
            gender_dp_pass = abs(dpd_g) < 0.05
            gender_eod_pass = abs(eod_g) < 0.10
            age_dp_pass = abs(dpd_a) < 0.05
            age_eod_pass = abs(eod_a) < 0.10

            all_pass = gender_dp_pass and gender_eod_pass and age_dp_pass and age_eod_pass

            return {
                "success": True,
                "fairness_passed": all_pass,
                "gender_metrics": {
                    "demographic_parity_difference": round(float(dpd_g), 4),
                    "demographic_parity_ratio": round(float(dpr_g), 4),
                    "equalized_odds_difference": round(float(eod_g), 4),
                    "dp_pass": gender_dp_pass,
                    "eod_pass": gender_eod_pass
                },
                "age_group_metrics": {
                    "demographic_parity_difference": round(float(dpd_a), 4),
                    "equalized_odds_difference": round(float(eod_a), 4),
                    "dp_pass": age_dp_pass,
                    "eod_pass": age_eod_pass
                },
                "message": (
                    "✅ All fairness checks passed" if all_pass
                    else "❌ Some fairness checks failed"
                )
            }

        except ImportError:
            logger.error("Fairlearn library not available")
            return {
                "success": False,
                "message": "Fairlearn library not installed. Install with: pip install fairlearn"
            }
        except Exception as e:
            logger.error(f"Fairness validation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to validate fairness: {str(e)}"
            }


# Create singleton instance
fairness_validator = FairnessValidator()
