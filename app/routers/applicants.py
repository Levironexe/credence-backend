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
    # Personal
    "code_gender": {"label": "Gender", "format": "text", "options": ["F", "M"]},
    "age_years": {"label": "Age", "format": "years"},
    "name_family_status": {"label": "Family Status", "format": "text", "options": [
        "Civil marriage", "Married", "Separated", "Single / not married", "Widow",
    ]},
    "name_education_type": {"label": "Education", "format": "text", "options": [
        "Academic degree", "Higher education", "Incomplete higher",
        "Lower secondary", "Secondary / secondary special",
    ]},
    "cnt_children": {"label": "Children", "format": "integer"},
    "cnt_fam_members": {"label": "Family Members", "format": "integer"},
    # Employment
    "name_income_type": {"label": "Income Type", "format": "text", "options": [
        "Businessman", "Commercial associate", "Maternity leave",
        "Pensioner", "State servant", "Student", "Unemployed", "Working",
    ]},
    "occupation_type": {"label": "Occupation", "format": "text", "options": [
        "Accountants", "Cleaning staff", "Cooking staff", "Core staff",
        "Drivers", "HR staff", "High skill tech staff", "IT staff",
        "Laborers", "Low-skill Laborers", "Managers", "Medicine staff",
        "Private service staff", "Realty agents", "Sales staff",
        "Secretaries", "Security staff", "Waiters/barmen staff",
    ]},
    "organization_type": {"label": "Organization", "format": "text", "options": [
        "Advertising", "Agriculture", "Bank", "Business Entity Type 1",
        "Business Entity Type 2", "Business Entity Type 3", "Cleaning",
        "Construction", "Culture", "Electricity", "Emergency", "Government",
        "Hotel", "Housing", "Industry: type 1", "Industry: type 2",
        "Industry: type 3", "Industry: type 4", "Industry: type 5",
        "Industry: type 6", "Industry: type 7", "Industry: type 8",
        "Industry: type 9", "Industry: type 10", "Industry: type 11",
        "Industry: type 12", "Industry: type 13", "Insurance", "Kindergarten",
        "Legal Services", "Medicine", "Military", "Mobile", "Other",
        "Police", "Postal", "Realtor", "Religion", "Restaurant",
        "School", "Security", "Security Ministries", "Self-employed",
        "Services", "Telecom", "Trade: type 1", "Trade: type 2",
        "Trade: type 3", "Trade: type 4", "Trade: type 5", "Trade: type 6",
        "Trade: type 7", "Transport: type 1", "Transport: type 2",
        "Transport: type 3", "Transport: type 4", "University", "XNA",
    ]},
    "employment_years": {"label": "Employment", "format": "years"},
    # Financials
    "amt_income_total": {"label": "Annual Income", "format": "currency"},
    "amt_credit": {"label": "Loan Amount", "format": "currency"},
    "amt_annuity": {"label": "Monthly Payment", "format": "currency"},
    "amt_goods_price": {"label": "Goods Price", "format": "currency"},
    "name_contract_type": {"label": "Contract Type", "format": "text", "options": [
        "Cash loans", "Revolving loans",
    ]},
    "credit_income_ratio": {"label": "Loan-to-Income Ratio", "format": "ratio"},
    "annuity_income_ratio": {"label": "Payment-to-Income Ratio", "format": "ratio"},
    # Assets
    "flag_own_car": {"label": "Owns Car", "format": "boolean", "options": [
        {"value": 1, "label": "Yes"},
        {"value": 0, "label": "No"},
    ]},
    "flag_own_realty": {"label": "Owns Property", "format": "boolean", "options": [
        {"value": 1, "label": "Yes"},
        {"value": 0, "label": "No"},
    ]},
    "own_car_age": {"label": "Car Age", "format": "years"},
    "name_housing_type": {"label": "Housing", "format": "text", "options": [
        "Co-op apartment", "House / apartment", "Municipal apartment",
        "Office apartment", "Rented apartment", "With parents",
    ]},
    # External scores
    "ext_source_1": {"label": "External Score 1", "format": "score"},
    "ext_source_2": {"label": "External Score 2", "format": "score"},
    "ext_source_3": {"label": "External Score 3", "format": "score"},
    "ext_source_mean": {"label": "Avg External Score", "format": "score"},
    # Bureau data
    "bureau_active_count": {"label": "Active Credit Lines", "format": "integer"},
    "bureau_loan_count": {"label": "Total Bureau Loans", "format": "integer"},
    "bureau_debt_sum": {"label": "Outstanding Debt", "format": "currency"},
    "bureau_credit_sum": {"label": "Total Credit Limit", "format": "currency"},
    # Previous applications
    "prev_approved_count": {"label": "Previous Approvals", "format": "integer"},
    "prev_refused_count": {"label": "Previous Refusals", "format": "integer"},
    "prev_approval_rate": {"label": "Approval Rate", "format": "percent"},
}

# Map DB column names (lowercase) to model feature names
DB_TO_FEATURE = {
    # Core financial
    "amt_income_total": "AMT_INCOME_TOTAL",
    "amt_credit": "AMT_CREDIT",
    "amt_annuity": "AMT_ANNUITY",
    "amt_goods_price": "AMT_GOODS_PRICE",
    # Demographics
    "code_gender": "CODE_GENDER",
    "cnt_children": "CNT_CHILDREN",
    "cnt_fam_members": "CNT_FAM_MEMBERS",
    "name_family_status": "NAME_FAMILY_STATUS",
    "name_education_type": "NAME_EDUCATION_TYPE",
    "name_income_type": "NAME_INCOME_TYPE",
    "name_housing_type": "NAME_HOUSING_TYPE",
    "occupation_type": "OCCUPATION_TYPE",
    "organization_type": "ORGANIZATION_TYPE",
    # Loan details
    "name_contract_type": "NAME_CONTRACT_TYPE",
    # Time
    "days_birth": "DAYS_BIRTH",
    "days_employed": "DAYS_EMPLOYED",
    "age_years": "age_years",
    "employment_years": "employment_years",
    # External scores
    "ext_source_1": "EXT_SOURCE_1",
    "ext_source_2": "EXT_SOURCE_2",
    "ext_source_3": "EXT_SOURCE_3",
    "ext_source_mean": "ext_source_mean",
    # Bureau data
    "bureau_active_count": "bureau_active_count",
    "bureau_debt_sum": "bureau_debt_sum",
    "bureau_credit_sum": "bureau_credit_sum",
    "bureau_loan_count": "bureau_loan_count",
    # Previous applications
    "prev_app_count": "prev_app_count",
    "prev_approved_count": "prev_approved_count",
    "prev_refused_count": "prev_refused_count",
    "prev_amt_credit_mean": "prev_amt_credit_mean",
    "prev_amt_annuity_mean": "prev_amt_annuity_mean",
    # Derived ratios
    "credit_income_ratio": "credit_income_ratio",
    "annuity_income_ratio": "annuity_income_ratio",
    # Assets & flags
    "flag_own_car": "FLAG_OWN_CAR",
    "flag_own_realty": "FLAG_OWN_REALTY",
    "own_car_age": "OWN_CAR_AGE",
    "prev_approval_rate": "prev_approval_rate",
    # Registration & contact
    "days_registration": "DAYS_REGISTRATION",
    "days_id_publish": "DAYS_ID_PUBLISH",
    "days_last_phone_change": "DAYS_LAST_PHONE_CHANGE",
    "flag_work_phone": "FLAG_WORK_PHONE",
    "region_population_relative": "REGION_POPULATION_RELATIVE",
    # Social & credit inquiries
    "def_30_cnt_social_circle": "DEF_30_CNT_SOCIAL_CIRCLE",
    "amt_req_credit_bureau_qrt": "AMT_REQ_CREDIT_BUREAU_QRT",
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
    if fmt == "boolean":
        return "Yes" if val else "No"
    if fmt == "text":
        return str(val)
    return str(val)


def _build_profile_from_db(app: Applicant) -> Dict[str, Any]:
    """Build a display-friendly profile dict from DB Applicant row."""
    display = []
    for db_col, meta in DISPLAY_FIELDS.items():
        raw = getattr(app, db_col, None)
        val = _safe_val(raw)
        field = {
            "key": db_col,
            "label": meta["label"],
            "value": val,
            "display": _format_value(val, meta["format"]),
            "format": meta["format"],
        }
        if "options" in meta:
            field["options"] = meta["options"]
        display.append(field)

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
            if isinstance(val, str):
                features[model_feat] = val
            else:
                try:
                    features[model_feat] = float(val)
                except (ValueError, TypeError):
                    pass
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


# Derived ratio limits — the XGBoost model can't extrapolate beyond its
# training distribution. Individual fields (income, loan, etc.) have no
# limits, but the RATIOS between them must stay within the model's range.
# Based on 99th percentile of training data.
RATIO_LIMITS = {
    "credit_income_ratio": {
        "max": 12.0,
        "label": "Loan-to-Income",
        "fields": ["amt_credit", "amt_income_total"],
    },
    "annuity_income_ratio": {
        "max": 0.48,
        "label": "Payment-to-Income",
        "fields": ["amt_annuity", "amt_income_total"],
    },
    "credit_goods_ratio": {
        "max": 1.48,
        "label": "Loan-to-Goods Price",
        "fields": ["amt_credit", "amt_goods_price"],
    },
}


def _compute_ratio_warnings(fields: Dict[str, Any]) -> list:
    """Check if derived ratios from given field values exceed model limits."""
    warnings = []

    def _num(key):
        v = fields.get(key)
        if v is None or v == "" or v == "N/A":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    income = _num("amt_income_total")
    credit = _num("amt_credit")
    annuity = _num("amt_annuity")
    goods = _num("amt_goods_price")

    if credit is not None and income is not None and income > 0:
        ratio = credit / income
        limit = RATIO_LIMITS["credit_income_ratio"]
        if ratio > limit["max"]:
            warnings.append({
                "ratio": "credit_income_ratio",
                "label": limit["label"],
                "value": round(ratio, 2),
                "max": limit["max"],
                "message": f"Loan (${credit:,.0f}) is {ratio:.1f}x income (${income:,.0f}). Model reliable up to {int(limit['max'])}x.",
            })

    if annuity is not None and income is not None and income > 0:
        ratio = annuity / income
        limit = RATIO_LIMITS["annuity_income_ratio"]
        if ratio > limit["max"]:
            warnings.append({
                "ratio": "annuity_income_ratio",
                "label": limit["label"],
                "value": round(ratio, 4),
                "max": limit["max"],
                "message": f"Monthly payment (${annuity:,.0f}) is {ratio:.0%} of income. Model reliable up to {limit['max']:.0%}.",
            })

    if credit is not None and goods is not None and goods > 0:
        ratio = credit / goods
        limit = RATIO_LIMITS["credit_goods_ratio"]
        if ratio > limit["max"]:
            warnings.append({
                "ratio": "credit_goods_ratio",
                "label": limit["label"],
                "value": round(ratio, 2),
                "max": limit["max"],
                "message": f"Loan (${credit:,.0f}) is {ratio:.2f}x goods price (${goods:,.0f}). Model reliable up to {limit['max']}x.",
            })

    return warnings


@router.post("/validate")
async def validate_fields(body: Dict[str, Any]):
    """Check if field values produce ratios within the model's reliable range."""
    warnings = _compute_ratio_warnings(body)
    return {"success": True, "warnings": warnings, "valid": len(warnings) == 0}


# Editable fields — only fields shown in sidebar can be updated
EDITABLE_FIELDS = {
    # Numeric fields
    "amt_income_total", "amt_credit", "amt_annuity", "amt_goods_price",
    "age_years", "employment_years", "cnt_children", "cnt_fam_members",
    "ext_source_1", "ext_source_2", "ext_source_3", "ext_source_mean",
    "own_car_age", "bureau_active_count", "bureau_debt_sum", "prev_approval_rate",
    "bureau_credit_sum", "bureau_loan_count",
    "prev_approved_count", "prev_refused_count",
    "flag_own_car", "flag_own_realty",
}
# String fields that accept text values
EDITABLE_TEXT_FIELDS = {
    "code_gender", "name_family_status", "name_education_type",
    "name_income_type", "name_housing_type", "occupation_type",
    "organization_type", "name_contract_type",
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
        if key in EDITABLE_TEXT_FIELDS:
            if value is None or value == "" or value == "N/A":
                setattr(app, key, None)
            else:
                setattr(app, key, str(value))
            updated.append(key)
        elif key in EDITABLE_FIELDS:
            if value is None or value == "" or value == "N/A":
                setattr(app, key, None)
                updated.append(key)
            else:
                try:
                    setattr(app, key, float(value))
                    updated.append(key)
                except (ValueError, TypeError):
                    continue
        else:
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

    await db.commit()
    await db.refresh(app)

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
    await db.commit()

    return {
        "success": True,
        "applicant_id": applicant_id,
        "credit_score": credit_score,
        "score_band": score_result["score_band"],
        "default_probability": score_result["default_probability"],
        "decision": score_result["decision"],
        "risk_level": risk_level,
    }
