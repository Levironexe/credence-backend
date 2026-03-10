"""
SHAP Explainer Tool

Exact implementation from streamlit_demo.py - build_explainer() and run_shap().
Uses TreeSHAP to explain credit decisions with feature importance.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Feature names from credit_risk_dataset (must match credit_score_model)
FEATURE_NAMES = [
    "person_age", "person_income", "person_home_ownership",
    "person_emp_length", "loan_intent", "loan_grade",
    "loan_amnt", "loan_int_rate", "loan_percent_income",
    "cb_person_default_on_file", "cb_person_cred_hist_length"
]


class SHAPExplainerInput(BaseModel):
    """Input schema for SHAP Explainer - matches credit_risk_dataset."""
    person_age: float = Field(description="Applicant age")
    person_income: float = Field(description="Annual income")
    person_home_ownership: str = Field(description="Home ownership")
    person_emp_length: float = Field(description="Employment length")
    loan_intent: str = Field(description="Loan intent")
    loan_grade: str = Field(description="Loan grade")
    loan_amnt: float = Field(description="Loan amount")
    loan_int_rate: float = Field(description="Interest rate")
    loan_percent_income: float = Field(description="Loan as % of income")
    cb_person_default_on_file: str = Field(description="Default on file")
    cb_person_cred_hist_length: float = Field(description="Credit history length")


class SHAPExplainer(BaseTool):
    """
    SHAP explainer - exact from build_explainer() and run_shap() in notebook.

    Initialized with model and X_train.
    Pre-computes mean_abs_shap for importance ranking.
    Returns top-k features with direction labels.
    """

    def __init__(self, model=None, X_train=None):
        super().__init__()
        self.xgb_model = model
        self.X_train = X_train
        self.feature_names = FEATURE_NAMES
        self.shap_explainer = None
        self.mean_abs_shap = None
        self.use_ml_model = model is not None

        if self.use_ml_model and X_train is not None:
            self._build_explainer()
        else:
            self._load_model()

    def _build_explainer(self):
        """Build SHAP explainer - exact from build_explainer() in notebook."""
        try:
            import shap
            self.shap_explainer = shap.TreeExplainer(self.xgb_model)
            shap_values = self.shap_explainer.shap_values(self.X_train)
            self.mean_abs_shap = pd.Series(
                np.abs(shap_values).mean(axis=0),
                index=FEATURE_NAMES
            ).sort_values(ascending=False)
            logger.info("✓ Built SHAP explainer with pre-computed mean_abs_shap")
        except ImportError:
            logger.warning("SHAP library not available")
            self.use_ml_model = False
        except Exception as e:
            logger.warning(f"Failed to build SHAP explainer: {e}")
            self.use_ml_model = False

    def _load_model(self):
        """Load trained XGBoost model and build SHAP explainer."""
        try:
            model_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "xgboost_model.pkl"
            train_path = Path(__file__).parent.parent.parent.parent / "ml_models" / "credit_scoring" / "X_train.parquet"

            if model_path.exists() and train_path.exists():
                with open(model_path, "rb") as f:
                    self.xgb_model = pickle.load(f)
                self.X_train = pd.read_parquet(train_path)
                self._build_explainer()
                self.use_ml_model = True
                logger.info("✓ Loaded SHAP explainer from saved model")
            else:
                logger.info("Model not found - SHAP explanations unavailable")
                self.use_ml_model = False

        except Exception as e:
            logger.warning(f"Failed to load SHAP explainer: {e}")
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
        top_k: int = 7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate SHAP explanations - exact from run_shap() in notebook.

        Returns DataFrame with feature, value, shap_value, direction, abs_shap.
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

            if self.use_ml_model and self.shap_explainer is not None:
                return await self._explain_ml_model(features, top_k)
            else:
                return await self._explain_rule_based(features)

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate explanations: {str(e)}"
            }

    async def _explain_ml_model(self, features: Dict[str, Any], top_k: int) -> Dict[str, Any]:
        """Generate SHAP explanations - exact from run_shap() in notebook."""
        from sklearn.preprocessing import LabelEncoder

        # Preprocess features
        row = pd.Series(features)

        # Encode categorical columns (same as credit_score_model)
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

        # Compute SHAP values (exact from notebook)
        sv = self.shap_explainer.shap_values(row[FEATURE_NAMES].values.reshape(1, -1))[0]

        # Build dataframe (exact from notebook)
        df = pd.DataFrame({
            "feature": FEATURE_NAMES,
            "value": row[FEATURE_NAMES].values,
            "shap_value": sv,
        })
        df["abs_shap"] = df["shap_value"].abs()
        df["direction"] = df["shap_value"].apply(
            lambda v: "↑ increases risk" if v > 0 else "↓ decreases risk"
        )

        # Sort and return top-k
        df = df.sort_values("abs_shap", ascending=False).head(top_k).reset_index(drop=True)

        return {
            "success": True,
            "method": "TreeSHAP",
            "explanations": df.to_dict("records"),
            "message": f"Generated SHAP explanations with top {top_k} features"
        }

    async def _explain_rule_based(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback when SHAP not available."""
        return {
            "success": False,
            "method": "none",
            "message": "SHAP explainer requires trained XGBoost model"
        }


# Create singleton instance
shap_explainer = SHAPExplainer()
