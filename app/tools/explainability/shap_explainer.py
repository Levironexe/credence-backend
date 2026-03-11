"""
SHAP Explainer Tool

Uses TreeSHAP to explain credit decisions with per-feature importance.
Loads the shared model artifacts (stable XGBoost, 128 features).
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)


class SHAPExplainerInput(BaseModel):
    """Input: applicant data as a flat dictionary."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features to explain."
    )
    top_k: int = Field(default=7, description="Number of top features to return")


class SHAPExplainer(BaseTool):
    """
    SHAP explainer for credit scoring decisions.

    For each applicant, returns the top-k features that most influenced
    the prediction, with direction labels (increases/decreases risk).
    """

    @property
    def name(self) -> str:
        return "shap_explainer"

    @property
    def description(self) -> str:
        return (
            "Explains credit score decisions using SHAP feature importance. "
            "Shows which factors most influenced the score and in which direction. "
            "Helps loan officers understand and justify credit decisions."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return SHAPExplainerInput

    async def execute(self, applicant_data: Dict[str, Any] = None, top_k: int = 7, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.shap_explainer is None:
                return {
                    "success": False,
                    "message": "SHAP explainer not available. Model or SHAP library not loaded."
                }

            feature_names = artifacts.feature_names
            row = pd.Series(index=feature_names, dtype=object)

            # Fill provided values
            for feat in feature_names:
                if feat in applicant_data:
                    row[feat] = applicant_data[feat]

            # Encode categoricals
            if artifacts.label_encoders:
                for col, le in artifacts.label_encoders.items():
                    if col in row.index and isinstance(row.get(col), str):
                        try:
                            row[col] = le.transform([row[col]])[0]
                        except ValueError:
                            row[col] = np.nan

            # Impute missing
            if artifacts.X_train is not None:
                for feat in feature_names:
                    if pd.isna(row.get(feat)):
                        if feat in artifacts.X_train.columns:
                            row[feat] = float(artifacts.X_train[feat].median())
                        else:
                            row[feat] = 0.0

            # Compute SHAP values
            X = row[feature_names].values.astype(float).reshape(1, -1)
            sv = artifacts.shap_explainer.shap_values(X)[0]

            # Build explanation dataframe
            df = pd.DataFrame({
                "feature": feature_names,
                "value": row[feature_names].values.astype(float),
                "shap_value": sv,
            })
            df["abs_shap"] = df["shap_value"].abs()
            df["direction"] = df["shap_value"].apply(
                lambda v: "increases risk" if v > 0 else "decreases risk"
            )

            # Get human-readable labels if available
            if artifacts.feature_labels:
                df["label"] = df["feature"].map(artifacts.feature_labels).fillna(df["feature"])
            else:
                df["label"] = df["feature"]

            # Sort and return top-k
            df = df.sort_values("abs_shap", ascending=False).head(top_k).reset_index(drop=True)

            return {
                "success": True,
                "method": "TreeSHAP",
                "explanations": df.to_dict("records"),
                "base_value": float(artifacts.shap_explainer.expected_value),
                "message": f"Top {top_k} features explaining this credit decision"
            }

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate explanations: {str(e)}"
            }


# Singleton
shap_explainer = SHAPExplainer()
