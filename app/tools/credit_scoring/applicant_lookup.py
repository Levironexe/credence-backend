"""
Applicant Lookup Tool

Simulates platform/SoBanHang integration by loading a real applicant
from the Home Credit test set (X_test). Returns all 128 features
pre-populated — no imputation needed.
"""

import logging
from typing import Dict, Any
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)


class ApplicantLookupInput(BaseModel):
    """Input: applicant ID from the test set."""
    applicant_id: int = Field(
        description="Applicant ID from the Home Credit test set (index range: 261384-307510)"
    )


class ApplicantLookup(BaseTool):
    """
    Look up a sample applicant from the Home Credit test dataset.

    Simulates a real platform integration (e.g. SoBanHang) where applicant
    data is pulled from an existing system. Returns a complete row of 128
    features ready for credit scoring — no manual input needed.
    """

    @property
    def name(self) -> str:
        return "applicant_lookup"

    @property
    def description(self) -> str:
        return (
            "Look up a sample applicant by ID from the Home Credit test dataset. "
            "Returns all 128 features for the applicant, ready for credit scoring. "
            "Valid IDs are in the range 261384-307510 (46,127 real applicants)."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return ApplicantLookupInput

    async def execute(self, applicant_id: int = None, **kwargs) -> Dict[str, Any]:
        if applicant_id is None:
            applicant_id = kwargs.get("applicant_id")

        if applicant_id is None:
            return {"success": False, "error": "applicant_id is required"}

        if artifacts.X_test is None or artifacts.y_test is None:
            return {
                "success": False,
                "error": "Test data not loaded. Ensure X_test.parquet and y_test.parquet exist."
            }

        if applicant_id not in artifacts.X_test.index:
            valid_min = int(artifacts.X_test.index.min())
            valid_max = int(artifacts.X_test.index.max())
            return {
                "success": False,
                "error": f"Applicant #{applicant_id} not found. Valid range: {valid_min}-{valid_max}"
            }

        row = artifacts.X_test.loc[applicant_id]
        features = row.to_dict()

        # Get actual default label for comparison
        actual_default = int(artifacts.y_test.loc[applicant_id])

        logger.info(f"Loaded applicant #{applicant_id}: {len(features)} features, actual_default={actual_default}")

        return {
            "success": True,
            "applicant_id": applicant_id,
            "features": features,
            "features_count": len(features),
            "actual_default": actual_default,
            "message": f"Loaded applicant #{applicant_id} with {len(features)} features"
        }


# Singleton
applicant_lookup = ApplicantLookup()
