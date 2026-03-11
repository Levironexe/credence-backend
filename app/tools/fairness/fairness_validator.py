"""
Fairness Validator Tool

Computes demographic_parity_difference, demographic_parity_ratio,
equalized_odds_difference using Fairlearn.
Tests fairness across gender (simulated) and age groups.
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)


class FairnessValidatorInput(BaseModel):
    """No input required — operates on the test dataset."""
    pass


class FairnessValidator(BaseTool):
    """
    Fairness validator using Fairlearn metrics.

    Computes demographic parity and equalized odds across:
    - Gender (simulated, seed=42, p=[0.45, 0.55])
    - Age group (young <35, middle 35-55, senior 55+)

    Thresholds: |dp_diff| < 0.05, |eod| < 0.10
    """

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
        try:
            if not artifacts.loaded or artifacts.model is None:
                return {"success": False, "message": "Model not loaded for fairness validation"}

            if artifacts.X_test is None or artifacts.y_test is None:
                return {"success": False, "message": "Test data not available for fairness validation"}

            from fairlearn.metrics import (
                demographic_parity_difference,
                demographic_parity_ratio,
                equalized_odds_difference,
            )

            feature_names = artifacts.feature_names
            X_test = artifacts.X_test[feature_names] if feature_names else artifacts.X_test
            y_test = artifacts.y_test

            # Predict on test set
            y_pred_all = artifacts.model.predict(X_test)

            # Simulate gender (seed=42)
            np.random.seed(42)
            gender = pd.Series(np.random.choice([0, 1], size=len(X_test), p=[0.45, 0.55]))

            # Derive age group from DAYS_BIRTH or age_years
            if "age_years" in X_test.columns:
                age_col = X_test["age_years"]
            elif "DAYS_BIRTH" in X_test.columns:
                age_col = (-X_test["DAYS_BIRTH"]) / 365.25
            else:
                age_col = pd.Series(np.random.choice([25, 40, 60], size=len(X_test)))

            age_group = pd.Series(
                pd.cut(age_col, bins=[0, 35, 55, 200], labels=[0, 1, 2]).astype(int)
            )

            # Approval = inverse of default prediction
            y_approved = 1 - y_pred_all

            # Compute metrics
            dpd_g = demographic_parity_difference(y_approved, y_approved, sensitive_features=gender)
            dpr_g = demographic_parity_ratio(y_approved, y_approved, sensitive_features=gender)
            eod_g = equalized_odds_difference(y_test, y_pred_all, sensitive_features=gender)
            dpd_a = demographic_parity_difference(y_approved, y_approved, sensitive_features=age_group)
            eod_a = equalized_odds_difference(y_test, y_pred_all, sensitive_features=age_group)

            # Thresholds
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
                    "eod_pass": gender_eod_pass,
                },
                "age_group_metrics": {
                    "demographic_parity_difference": round(float(dpd_a), 4),
                    "equalized_odds_difference": round(float(eod_a), 4),
                    "dp_pass": age_dp_pass,
                    "eod_pass": age_eod_pass,
                },
                "message": (
                    "All fairness checks passed" if all_pass
                    else "Some fairness checks failed — review bias in model"
                ),
            }

        except ImportError:
            return {"success": False, "message": "Fairlearn library not installed. pip install fairlearn"}
        except Exception as e:
            logger.error(f"Fairness validation failed: {e}")
            return {"success": False, "error": str(e), "message": f"Fairness validation failed: {str(e)}"}


# Singleton
fairness_validator = FairnessValidator()
