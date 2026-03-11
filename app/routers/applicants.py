"""
Applicant API endpoints for the frontend profile panel.

Provides:
- GET /api/applicants/samples — curated list of 20 diverse test applicants
- GET /api/applicants/{id} — full profile for a single applicant
"""

import logging
import math
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
import numpy as np
import pandas as pd

from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/applicants", tags=["applicants"])

# Human-readable labels for key features shown in the sidebar
DISPLAY_FIELDS = {
    "AMT_INCOME_TOTAL": {"label": "Annual Income", "format": "currency"},
    "AMT_CREDIT": {"label": "Loan Amount", "format": "currency"},
    "AMT_ANNUITY": {"label": "Monthly Payment", "format": "currency"},
    "AMT_GOODS_PRICE": {"label": "Goods Price", "format": "currency"},
    "age_years": {"label": "Age", "format": "years"},
    "employment_years": {"label": "Employment", "format": "years"},
    "CNT_CHILDREN": {"label": "Children", "format": "integer"},
    "CNT_FAM_MEMBERS": {"label": "Family Members", "format": "integer"},
    "credit_income_ratio": {"label": "Loan-to-Income Ratio", "format": "ratio"},
    "annuity_income_ratio": {"label": "Payment-to-Income Ratio", "format": "ratio"},
    "EXT_SOURCE_1": {"label": "External Score 1", "format": "score"},
    "EXT_SOURCE_2": {"label": "External Score 2", "format": "score"},
    "EXT_SOURCE_3": {"label": "External Score 3", "format": "score"},
    "ext_source_mean": {"label": "Avg External Score", "format": "score"},
    "OWN_CAR_AGE": {"label": "Car Age", "format": "years"},
    "bureau_active_count": {"label": "Active Credit Lines", "format": "integer"},
    "bureau_debt_sum": {"label": "Total Outstanding Debt", "format": "currency"},
    "prev_approval_rate": {"label": "Previous Approval Rate", "format": "percent"},
    "DAYS_BIRTH": {"label": "Days Since Birth", "format": "hidden"},
    "DAYS_EMPLOYED": {"label": "Days Employed", "format": "hidden"},
}


def _safe_val(v):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _format_value(val, fmt: str) -> str:
    """Format a value for display."""
    if val is None:
        return "N/A"
    if fmt == "currency":
        return f"${val:,.0f}" if abs(val) >= 1 else f"${val:.4f}"
    if fmt == "years":
        return f"{val:.1f}" if isinstance(val, float) else str(int(val))
    if fmt == "integer":
        return str(int(val))
    if fmt == "ratio":
        return f"{val:.2f}"
    if fmt == "score":
        return f"{val:.3f}"
    if fmt == "percent":
        return f"{val * 100:.0f}%" if val <= 1 else f"{val:.0f}%"
    return str(val)


def _build_profile(applicant_id: int, row: pd.Series) -> Dict[str, Any]:
    """Build a display-friendly profile dict for one applicant."""
    # Compute derived fields if not present
    data = row.to_dict()

    # Derive age_years from DAYS_BIRTH if available
    if "DAYS_BIRTH" in data and data.get("DAYS_BIRTH") is not None:
        days = data["DAYS_BIRTH"]
        if not (isinstance(days, float) and math.isnan(days)):
            data["age_years"] = abs(float(days)) / 365.25

    # Derive employment_years from DAYS_EMPLOYED if available
    if "DAYS_EMPLOYED" in data and data.get("DAYS_EMPLOYED") is not None:
        days = data["DAYS_EMPLOYED"]
        if not (isinstance(days, float) and math.isnan(days)):
            emp = abs(float(days)) / 365.25
            # DAYS_EMPLOYED = 365243 is a sentinel for unemployed/retired
            data["employment_years"] = emp if emp < 100 else 0

    # Build display fields
    display = []
    for feat, meta in DISPLAY_FIELDS.items():
        if meta["format"] == "hidden":
            continue
        raw = data.get(feat)
        val = _safe_val(raw)
        display.append({
            "key": feat,
            "label": meta["label"],
            "value": val,
            "display": _format_value(val, meta["format"]),
            "format": meta["format"],
        })

    # Predict score
    score = None
    score_band = None
    default_prob = None
    if artifacts.model is not None and artifacts.feature_names is not None:
        try:
            features = []
            medians = artifacts.X_train.median() if artifacts.X_train is not None else None
            for feat in artifacts.feature_names:
                v = data.get(feat)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    v = float(medians[feat]) if medians is not None and feat in medians else 0.0
                features.append(float(v))
            prob = float(artifacts.model.predict_proba(
                np.array(features).reshape(1, -1)
            )[0, 1])
            default_prob = round(prob, 4)
            score = int(850 - prob * 550)
            if score >= 800:
                score_band = "Exceptional"
            elif score >= 740:
                score_band = "Very Good"
            elif score >= 670:
                score_band = "Good"
            elif score >= 580:
                score_band = "Fair"
            else:
                score_band = "Poor"
        except Exception as e:
            logger.warning(f"Score prediction failed for #{applicant_id}: {e}")

    # Get actual default label
    actual_default = None
    if artifacts.y_test is not None and applicant_id in artifacts.y_test.index:
        actual_default = int(artifacts.y_test.loc[applicant_id])

    return {
        "id": str(applicant_id),
        "label": f"Applicant #{applicant_id}",
        "fields": display,
        "score": score,
        "score_band": score_band,
        "default_probability": default_prob,
        "actual_default": actual_default,
    }


# Cache the sample list so we don't recompute on every request
_cached_samples = None


def _find_sample_applicants() -> List[Dict[str, Any]]:
    """Find 20 diverse applicants across score bands."""
    global _cached_samples
    if _cached_samples is not None:
        return _cached_samples

    if artifacts.X_test is None or artifacts.model is None:
        return []

    X = artifacts.X_test
    feature_names = artifacts.feature_names

    # Impute NaN with training medians (same as scoring pipeline)
    medians = artifacts.X_train.median() if artifacts.X_train is not None else None
    X_filled = X[feature_names].copy()
    if medians is not None:
        X_filled = X_filled.fillna(medians[feature_names])
    X_filled = X_filled.fillna(0)

    # Predict all scores
    probs = artifacts.model.predict_proba(X_filled.values.astype(float))[:, 1]
    scores = (850 - probs * 550).astype(int)

    # Create a DataFrame for selection
    df = pd.DataFrame({"score": scores, "prob": probs}, index=X.index)
    if artifacts.y_test is not None:
        df["actual"] = artifacts.y_test

    # Pick applicants across score bands for diverse testing
    targets = [
        # Poor (< 580) — declined, counterfactuals useful
        ("Poor — Declined", df[df["score"] < 580], 3),
        # Fair (580-669) — manual review, near threshold, counterfactuals interesting
        ("Fair — Manual Review", df[(df["score"] >= 580) & (df["score"] < 670)], 5),
        # Near threshold (660-679) — most interesting for demo
        ("Near Threshold", df[(df["score"] >= 660) & (df["score"] < 680)], 4),
        # Good (670-739) — approved with conditions
        ("Good — Approved", df[(df["score"] >= 670) & (df["score"] < 740)], 3),
        # Very Good (740-799)
        ("Very Good", df[(df["score"] >= 740) & (df["score"] < 800)], 3),
        # Exceptional (800+)
        ("Exceptional", df[df["score"] >= 800], 2),
    ]

    samples = []
    used_ids = set()

    for band_label, band_df, count in targets:
        if len(band_df) == 0:
            continue
        # Pick random sample from this band
        n = min(count, len(band_df))
        picked = band_df.sample(n=n, random_state=42)
        for idx in picked.index:
            if idx in used_ids:
                continue
            used_ids.add(idx)
            profile = _build_profile(int(idx), X.loc[idx])
            profile["band_category"] = band_label
            samples.append(profile)

    # Sort by score descending
    samples.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)

    _cached_samples = samples
    logger.info(f"Cached {len(samples)} sample applicants")
    return samples


@router.get("/samples")
async def get_sample_applicants():
    """Return curated list of ~20 diverse test applicants with scores."""
    try:
        samples = _find_sample_applicants()
        return {"success": True, "applicants": samples, "count": len(samples)}
    except Exception as e:
        logger.error(f"Failed to get sample applicants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{applicant_id}")
async def get_applicant_profile(applicant_id: int):
    """Return full profile for a single applicant."""
    if artifacts.X_test is None:
        raise HTTPException(status_code=503, detail="Test data not loaded")

    if applicant_id not in artifacts.X_test.index:
        valid_min = int(artifacts.X_test.index.min())
        valid_max = int(artifacts.X_test.index.max())
        raise HTTPException(
            status_code=404,
            detail=f"Applicant #{applicant_id} not found. Valid range: {valid_min}-{valid_max}"
        )

    row = artifacts.X_test.loc[applicant_id]
    profile = _build_profile(applicant_id, row)
    return {"success": True, **profile}
