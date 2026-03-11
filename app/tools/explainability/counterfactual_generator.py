"""
Counterfactual Explanation Generator

Uses DiCE (Diverse Counterfactual Explanations) with genetic optimization
to generate actionable "what-if" scenarios for denied applicants.

Only varies actionable features (loan amount, income, employment, debt)
with realistic permitted ranges.
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)

# Permitted ranges for actionable features
PERMITTED_RANGES = {
    "AMT_INCOME_TOTAL": [50000, 1000000],
    "AMT_CREDIT": [45000, 2000000],
    "AMT_ANNUITY": [5000, 80000],
    "AMT_GOODS_PRICE": [40000, 2000000],
    "DAYS_EMPLOYED": [-7300, -30],
    "bureau_debt_sum": [0, 5000000],
    "bureau_active_count": [0, 10],
    "credit_income_ratio": [0.1, 10],
    "annuity_income_ratio": [0.01, 0.5],
    "bureau_debt_credit_ratio": [0, 1],
}

# Human-readable labels
DEFAULT_LABELS = {
    "AMT_CREDIT": "Loan amount",
    "AMT_ANNUITY": "Monthly payment",
    "AMT_GOODS_PRICE": "Purchase price",
    "AMT_INCOME_TOTAL": "Annual income",
    "DAYS_EMPLOYED": "Employment duration",
    "bureau_debt_sum": "Total outstanding debt",
    "bureau_active_count": "Active credit lines",
    "credit_income_ratio": "Loan-to-income ratio",
    "annuity_income_ratio": "Payment-to-income ratio",
    "bureau_debt_credit_ratio": "Debt-to-credit ratio",
}


class CounterfactualInput(BaseModel):
    """Input: applicant data as a flat dictionary."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features for counterfactual generation."
    )
    total_CFs: int = Field(default=3, description="Number of counterfactual paths to generate")


class CounterfactualGenerator(BaseTool):
    """
    DiCE counterfactual generator.

    Uses genetic optimization to find minimal, diverse changes to actionable
    features that would flip a denied applicant to approved.
    """

    @staticmethod
    def prob_to_score(p: float) -> int:
        return int(850 - p * 550)

    @staticmethod
    def score_band(score: int) -> str:
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
            "Generates 'what-if' scenarios showing minimal changes to get a loan approved. "
            "Uses DiCE with genetic optimization to find diverse actionable paths. "
            "Only suggests changes to features the applicant can realistically influence "
            "(loan amount, income, employment, debt)."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CounterfactualInput

    async def execute(self, applicant_data: Dict[str, Any] = None, total_CFs: int = 3, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.model is None:
                return {"success": False, "message": "Model not loaded for counterfactual generation"}

            if artifacts.dice_explainer is None:
                return await self._fallback_perturbation(applicant_data)

            return await self._generate_dice(applicant_data, total_CFs)

        except Exception as e:
            logger.error(f"Counterfactual generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate counterfactuals: {str(e)}"
            }

    async def _generate_dice(self, data: Dict[str, Any], total_CFs: int) -> Dict[str, Any]:
        """Generate counterfactuals using DiCE."""
        feature_names = artifacts.feature_names
        row = pd.Series(index=feature_names, dtype=object)

        for feat in feature_names:
            if feat in data:
                row[feat] = data[feat]

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

        # Check if applicant has NaN (DiCE requirement)
        query = pd.DataFrame([row[feature_names].values.astype(float)], columns=feature_names)
        if query.isna().any().any():
            return {"success": False, "message": "Applicant data has missing values that could not be imputed"}

        # Get original prediction
        orig_prob = float(artifacts.model.predict_proba(query.values)[0, 1])
        orig_score = self.prob_to_score(orig_prob)

        # If already approved, no counterfactuals needed
        if orig_score >= 670:
            return {
                "success": True,
                "counterfactuals": [],
                "original_score": orig_score,
                "message": f"Applicant already qualifies (score: {orig_score}). No changes needed."
            }

        # Determine actionable features
        actionable = artifacts.actionable_features or list(PERMITTED_RANGES.keys())
        actionable = [f for f in actionable if f in feature_names]

        # Build permitted ranges for features that exist
        permitted = {f: v for f, v in PERMITTED_RANGES.items() if f in actionable}

        # Generate counterfactuals
        try:
            cf = artifacts.dice_explainer.generate_counterfactuals(
                query_instances=query,
                total_CFs=total_CFs,
                desired_class="opposite",
                features_to_vary=actionable,
                permitted_range=permitted,
            )
        except Exception as e:
            logger.warning(f"DiCE generation failed: {e}, falling back to perturbation")
            return await self._fallback_perturbation(data)

        # Parse results
        cf_df = cf.cf_examples_list[0].final_cfs_df
        if cf_df is None or len(cf_df) == 0:
            return {
                "success": True,
                "counterfactuals": [],
                "original_score": orig_score,
                "original_probability": round(orig_prob, 4),
                "message": "No actionable path to approval found. Risk factors are in immutable features."
            }

        labels = artifacts.feature_labels or DEFAULT_LABELS
        paths = []

        for i, (_, cf_row) in enumerate(cf_df.iterrows()):
            changes = []
            for col in actionable:
                orig_val = float(query[col].values[0])
                cf_val = float(cf_row[col])
                if abs(orig_val - cf_val) > 1e-6:
                    label = labels.get(col, col)
                    if col == "DAYS_EMPLOYED":
                        changes.append({
                            "feature": col,
                            "label": label,
                            "current": f"{abs(orig_val)/365.25:.1f} years",
                            "suggested": f"{abs(cf_val)/365.25:.1f} years",
                        })
                    elif orig_val > 1000:
                        changes.append({
                            "feature": col,
                            "label": label,
                            "current": round(orig_val, 0),
                            "suggested": round(cf_val, 0),
                        })
                    else:
                        changes.append({
                            "feature": col,
                            "label": label,
                            "current": round(orig_val, 3),
                            "suggested": round(cf_val, 3),
                        })

            new_prob = float(artifacts.model.predict_proba(
                cf_row[feature_names].values.astype(float).reshape(1, -1)
            )[0, 1])
            new_score = self.prob_to_score(new_prob)

            if changes:
                paths.append({
                    "path_number": i + 1,
                    "changes": changes,
                    "new_probability": round(new_prob, 4),
                    "new_score": new_score,
                    "new_band": self.score_band(new_score),
                })

        return {
            "success": True,
            "method": "DiCE (genetic)",
            "original_probability": round(orig_prob, 4),
            "original_score": orig_score,
            "original_band": self.score_band(orig_score),
            "counterfactuals": paths,
            "message": f"Found {len(paths)} actionable paths to improve credit score"
        }

    async def _fallback_perturbation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Simple perturbation fallback when DiCE is not available."""
        feature_names = artifacts.feature_names
        row = pd.Series(index=feature_names, dtype=object)

        for feat in feature_names:
            if feat in data:
                row[feat] = data[feat]

        if artifacts.label_encoders:
            for col, le in artifacts.label_encoders.items():
                if col in row.index and isinstance(row.get(col), str):
                    try:
                        row[col] = le.transform([row[col]])[0]
                    except ValueError:
                        row[col] = np.nan

        if artifacts.X_train is not None:
            for feat in feature_names:
                if pd.isna(row.get(feat)):
                    if feat in artifacts.X_train.columns:
                        row[feat] = float(artifacts.X_train[feat].median())
                    else:
                        row[feat] = 0.0

        X = row[feature_names].values.astype(float).reshape(1, -1)
        orig_prob = float(artifacts.model.predict_proba(X)[0, 1])
        orig_score = self.prob_to_score(orig_prob)

        perturbations = {
            "AMT_CREDIT": [0.7, 0.5],
            "AMT_INCOME_TOTAL": [1.3, 1.6],
            "AMT_ANNUITY": [0.7, 0.5],
            "credit_income_ratio": [0.7, 0.5],
        }

        paths = []
        for feat, multipliers in perturbations.items():
            if feat not in feature_names:
                continue
            for mult in multipliers:
                candidate = row[feature_names].copy().astype(float)
                candidate[feat] = candidate[feat] * mult
                new_prob = float(artifacts.model.predict_proba(candidate.values.reshape(1, -1))[0, 1])
                new_score = self.prob_to_score(new_prob)
                if new_score > orig_score:
                    label = DEFAULT_LABELS.get(feat, feat)
                    paths.append({
                        "path_number": len(paths) + 1,
                        "changes": [{
                            "feature": feat,
                            "label": label,
                            "current": round(float(row[feat]), 2),
                            "suggested": round(float(candidate[feat]), 2),
                        }],
                        "new_probability": round(new_prob, 4),
                        "new_score": new_score,
                        "new_band": self.score_band(new_score),
                    })
                    break

        return {
            "success": True,
            "method": "perturbation (fallback)",
            "original_probability": round(orig_prob, 4),
            "original_score": orig_score,
            "counterfactuals": paths[:5],
            "message": f"Found {len(paths[:5])} paths (perturbation fallback, DiCE not available)"
        }


# Singleton
counterfactual_generator = CounterfactualGenerator()
