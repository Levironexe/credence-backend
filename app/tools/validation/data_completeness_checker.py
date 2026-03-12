"""
Data Completeness Checker Tool

Checks how complete an applicant's data is, ranks missing fields by SHAP
importance, and determines if there's enough data to proceed with scoring.
"""

import logging
from typing import Dict, Any, Optional
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)


class DataCompletenessInput(BaseModel):
    """Input: applicant data as a flat dictionary (can have missing fields)."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features. Missing fields will be identified and ranked."
    )


class DataCompletenessChecker(BaseTool):
    """
    Data completeness checker using SHAP-weighted importance.

    Identifies missing fields, ranks them by SHAP importance (most impactful first),
    computes a completeness score, and determines if scoring can proceed.

    Threshold: 60% completeness (weighted by SHAP importance) to proceed.
    """

    @property
    def name(self) -> str:
        return "data_completeness_checker"

    @property
    def description(self) -> str:
        return (
            "Checks data completeness for loan applications and ranks missing fields "
            "by importance using SHAP feature importance. Guides loan officers to request "
            "the most valuable missing data first. Returns completeness score and missing field list."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return DataCompletenessInput

    async def execute(self, applicant_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.feature_names is None:
                return {"success": False, "message": "Model not loaded for completeness check"}

            feature_names = artifacts.feature_names

            # Find present and missing features
            present = [f for f in feature_names if f in applicant_data and applicant_data[f] is not None]
            missing = [f for f in feature_names if f not in present]

            # Compute SHAP-weighted completeness score
            if artifacts.mean_abs_shap is not None:
                total_imp = artifacts.mean_abs_shap.sum()
                present_imp = sum(
                    artifacts.mean_abs_shap.get(f, 0) for f in present
                )
                score = float(present_imp / total_imp) if total_imp > 0 else 1.0

                # Rank missing by SHAP importance
                missing_ranked = {}
                for f in missing:
                    imp = float(artifacts.mean_abs_shap.get(f, 0))
                    from app.tools.explainability.shap_explainer import FEATURE_LABELS
                    label = {**FEATURE_LABELS, **(artifacts.feature_labels or {})}.get(f, f)
                    missing_ranked[f] = {"importance": round(imp, 4), "label": label}

                # Sort by importance descending
                missing_ranked = dict(
                    sorted(missing_ranked.items(), key=lambda x: x[1]["importance"], reverse=True)
                )
            else:
                total_imp = len(feature_names)
                present_imp = len(present)
                score = present_imp / total_imp if total_imp > 0 else 1.0
                missing_ranked = {f: {"importance": 0, "label": f} for f in missing}

            can_proceed = score >= 0.60

            # Impute missing with median for potential scoring
            imputed = {}
            if artifacts.X_train is not None:
                for f in missing:
                    if f in artifacts.X_train.columns:
                        imputed[f] = float(artifacts.X_train[f].median())

            return {
                "success": True,
                "completeness_score": round(score, 3),
                "fields_present": len(present),
                "fields_missing": len(missing),
                "fields_total": len(feature_names),
                "missing_fields": missing_ranked,
                "can_proceed": can_proceed,
                "imputed_values": imputed,
                "message": (
                    f"Completeness: {score:.1%} ({len(present)}/{len(feature_names)} fields). "
                    + ("Sufficient data to proceed." if can_proceed
                       else f"Need more data. Top missing: {', '.join(list(missing_ranked.keys())[:3])}")
                ),
            }

        except Exception as e:
            logger.error(f"Data completeness check failed: {e}")
            return {"success": False, "error": str(e), "message": f"Completeness check failed: {str(e)}"}


# Singleton
data_completeness_checker = DataCompletenessChecker()
