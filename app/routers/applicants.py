"""
Applicant API endpoints.

Provides:
- GET /api/applicants/samples — all applicants from DB with cached scores
- GET /api/applicants/{id} — full profile for a single applicant
- PUT /api/applicants/{id} — update applicant fields
- POST /api/applicants/{id}/score — run XGBoost scoring, save result to DB
"""

import logging
import math
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from app.database import get_db
from app.models.applicant import Applicant, ApplicantResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/applicants", tags=["applicants"])

# Human-readable labels for key features shown in the sidebar
DISPLAY_FIELDS = {
    "amt_income_total": {"label": "Annual Income", "format": "currency"},
    "amt_credit": {"label": "Loan Amount", "format": "currency"},
    "amt_annuity": {"label": "Monthly Payment", "format": "currency"},
    "amt_goods_price": {"label": "Goods Price", "format": "currency"},
    "age_years": {"label": "Age", "format": "years"},
    "employment_years": {"label": "Employment", "format": "years"},
    "cnt_children": {"label": "Children", "format": "integer"},
    "cnt_fam_members": {"label": "Family Members", "format": "integer"},
    "credit_income_ratio": {"label": "Loan-to-Income Ratio", "format": "ratio"},
    "annuity_income_ratio": {"label": "Payment-to-Income Ratio", "format": "ratio"},
    "ext_source_1": {"label": "External Score 1", "format": "score"},
    "ext_source_2": {"label": "External Score 2", "format": "score"},
    "ext_source_3": {"label": "External Score 3", "format": "score"},
    "ext_source_mean": {"label": "Avg External Score", "format": "score"},
    "own_car_age": {"label": "Car Age", "format": "years"},
    "bureau_active_count": {"label": "Active Credit Lines", "format": "integer"},
    "bureau_debt_sum": {"label": "Total Outstanding Debt", "format": "currency"},
    "prev_approval_rate": {"label": "Previous Approval Rate", "format": "percent"},
}

# Map DB column names (lowercase) to model feature names
DB_TO_FEATURE = {
    "amt_income_total": "AMT_INCOME_TOTAL",
    "amt_credit": "AMT_CREDIT",
    "amt_annuity": "AMT_ANNUITY",
    "amt_goods_price": "AMT_GOODS_PRICE",
    "cnt_children": "CNT_CHILDREN",
    "cnt_fam_members": "CNT_FAM_MEMBERS",
    "ext_source_1": "EXT_SOURCE_1",
    "ext_source_2": "EXT_SOURCE_2",
    "ext_source_3": "EXT_SOURCE_3",
    "ext_source_mean": "ext_source_mean",
    "own_car_age": "OWN_CAR_AGE",
    "bureau_active_count": "bureau_active_count",
    "bureau_debt_sum": "bureau_debt_sum",
    "prev_approval_rate": "prev_approval_rate",
    "credit_income_ratio": "credit_income_ratio",
    "annuity_income_ratio": "annuity_income_ratio",
    "age_years": "age_years",
    "employment_years": "employment_years",
    "days_birth": "DAYS_BIRTH",
    "days_employed": "DAYS_EMPLOYED",
}


def _safe_val(v):
    """Convert numpy/Decimal types to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(float(v), 4)
    # Handle Decimal
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
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


def _build_profile_from_db(app: Applicant) -> Dict[str, Any]:
    """Build a display-friendly profile dict from DB Applicant row."""
    display = []
    for db_col, meta in DISPLAY_FIELDS.items():
        raw = getattr(app, db_col, None)
        val = _safe_val(raw)
        display.append({
            "key": db_col,
            "label": meta["label"],
            "value": val,
            "display": _format_value(val, meta["format"]),
            "format": meta["format"],
        })

    return {
        "id": str(app.id),
        "label": f"Applicant #{app.id}",
        "fields": display,
        "score": None,
        "score_band": None,
        "default_probability": None,
    }


def map_db_to_features(app: Applicant) -> dict:
    """Map DB Applicant columns to XGBoost model feature names."""
    features = {}
    for db_col, model_feat in DB_TO_FEATURE.items():
        val = getattr(app, db_col, None)
        if val is not None:
            features[model_feat] = float(val)
    return features


@router.get("/samples")
async def get_sample_applicants(db: AsyncSession = Depends(get_db)):
    """Return all applicants from DB with their latest score if exists."""
    try:
        result = await db.execute(select(Applicant).order_by(Applicant.id))
        applicants = result.scalars().all()

        samples = []
        for app in applicants:
            profile = _build_profile_from_db(app)

            # Check for existing score
            score_result = await db.execute(
                select(ApplicantResult)
                .where(ApplicantResult.applicant_id == app.id)
                .order_by(ApplicantResult.scored_at.desc())
                .limit(1)
            )
            score = score_result.scalar_one_or_none()
            if score:
                profile["score"] = int(score.credit_score) if score.credit_score else None
                profile["score_band"] = score.score_band
                profile["default_probability"] = float(score.default_probability) if score.default_probability else None

            samples.append(profile)

        return {"success": True, "applicants": samples, "count": len(samples)}
    except Exception as e:
        logger.error(f"Failed to get sample applicants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{applicant_id}")
async def get_applicant_profile(applicant_id: int, db: AsyncSession = Depends(get_db)):
    """Return full profile for a single applicant."""
    result = await db.execute(select(Applicant).where(Applicant.id == applicant_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Applicant #{applicant_id} not found")

    profile = _build_profile_from_db(app)

    # Get latest score
    score_result = await db.execute(
        select(ApplicantResult)
        .where(ApplicantResult.applicant_id == applicant_id)
        .order_by(ApplicantResult.scored_at.desc())
        .limit(1)
    )
    score = score_result.scalar_one_or_none()
    if score:
        profile["score"] = int(score.credit_score) if score.credit_score else None
        profile["score_band"] = score.score_band
        profile["default_probability"] = float(score.default_probability) if score.default_probability else None

    return {"success": True, **profile}


# Editable fields — only fields shown in sidebar can be updated
EDITABLE_FIELDS = {
    "amt_income_total", "amt_credit", "amt_annuity", "amt_goods_price",
    "age_years", "employment_years", "cnt_children", "cnt_fam_members",
    "ext_source_1", "ext_source_2", "ext_source_3", "ext_source_mean",
    "own_car_age", "bureau_active_count", "bureau_debt_sum", "prev_approval_rate",
}


class ApplicantUpdate(BaseModel):
    fields: Dict[str, Any]


@router.put("/{applicant_id}")
async def update_applicant(applicant_id: int, body: ApplicantUpdate, db: AsyncSession = Depends(get_db)):
    """Update editable fields on an applicant profile."""
    result = await db.execute(select(Applicant).where(Applicant.id == applicant_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Applicant #{applicant_id} not found")

    updated = []
    for key, value in body.fields.items():
        if key not in EDITABLE_FIELDS:
            continue
        # Convert to proper type
        if value is None or value == "" or value == "N/A":
            setattr(app, key, None)
            updated.append(key)
        else:
            try:
                setattr(app, key, float(value))
                updated.append(key)
            except (ValueError, TypeError):
                continue

    # Recompute derived fields
    if app.amt_income_total and app.amt_income_total > 0:
        if app.amt_credit is not None:
            app.credit_income_ratio = app.amt_credit / app.amt_income_total
        if app.amt_annuity is not None:
            app.annuity_income_ratio = app.amt_annuity / app.amt_income_total
    if app.age_years is not None:
        app.days_birth = -app.age_years * 365.25
    if app.employment_years is not None:
        app.days_employed = -app.employment_years * 365.25

    await db.flush()

    profile = _build_profile_from_db(app)
    logger.info(f"Updated applicant #{applicant_id}: {updated}")
    return {"success": True, "updated": updated, **profile}


@router.post("/{applicant_id}/score")
async def score_applicant(applicant_id: int, db: AsyncSession = Depends(get_db)):
    """Score an applicant using XGBoost model and save result to DB."""
    # Fetch applicant
    result = await db.execute(select(Applicant).where(Applicant.id == applicant_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Applicant #{applicant_id} not found")

    # Map to model features
    features = map_db_to_features(app)

    # Run credit score model
    from app.tools.credit_scoring.credit_score_model import credit_score_model
    score_result = await credit_score_model.execute(applicant_data=features)

    if not score_result.get("success"):
        raise HTTPException(status_code=500, detail=score_result.get("message", "Scoring failed"))

    credit_score = score_result["credit_score"]

    # Determine risk level
    if credit_score >= 670:
        risk_level = "low"
    elif credit_score >= 580:
        risk_level = "medium"
    else:
        risk_level = "high"

    # Save to DB
    new_result = ApplicantResult(
        applicant_id=applicant_id,
        credit_score=credit_score,
        score_band=score_result["score_band"],
        default_probability=score_result["default_probability"],
        risk_level=risk_level,
        decision=score_result["decision"],
    )
    db.add(new_result)
    await db.flush()

    return {
        "success": True,
        "applicant_id": applicant_id,
        "credit_score": credit_score,
        "score_band": score_result["score_band"],
        "default_probability": score_result["default_probability"],
        "decision": score_result["decision"],
        "risk_level": risk_level,
    }
