"""
Seed the Applicants table with diverse sample applicants from the test dataset.

Picks 10 applicants spanning all credit score bands (Exceptional to Poor)
with varied demographics, income levels, and risk profiles.

Usage:
    python scripts/seed_applicants.py
"""

import asyncio
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

MODEL_DIR = Path(__file__).parent.parent / "ml_models" / "credit_scoring"


def load_artifacts():
    with open(MODEL_DIR / "xgboost_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open(MODEL_DIR / "feature_names.pkl", "rb") as f:
        feature_names = pickle.load(f)
    with open(MODEL_DIR / "label_encoders.pkl", "rb") as f:
        label_encoders = pickle.load(f)
    X_test = pd.read_parquet(MODEL_DIR / "X_test.parquet")
    y_test = pd.read_parquet(MODEL_DIR / "y_test.parquet").squeeze()
    return model, feature_names, label_encoders, X_test, y_test


def reverse_encode(label_encoders):
    """Build reverse maps: encoded int -> original string."""
    reverse = {}
    for col, le in label_encoders.items():
        reverse[col] = {i: c for i, c in enumerate(le.classes_)}
    return reverse


def decode_value(col, val, reverse_maps):
    """Convert an encoded numeric value back to its original string."""
    if col in reverse_maps and not pd.isna(val):
        decoded = reverse_maps[col].get(int(val))
        if decoded and decoded != "nan":
            return decoded
    return None


def select_diverse_applicants(model, feature_names, X_test, y_test):
    """Pick 10 applicants across all score bands."""
    np.random.seed(42)

    X = X_test[feature_names].values.astype(float)
    probs = model.predict_proba(X)[:, 1]
    scores = (850 - probs * 550).astype(int)

    df = X_test.copy()
    df["_score"] = scores
    df["_default"] = y_test.values

    bands = [
        ("Exceptional", 800, 851, 2),
        ("Very Good", 740, 800, 2),
        ("Good", 670, 740, 2),
        ("Fair", 580, 670, 2),
        ("Poor", 300, 580, 2),
    ]

    selected = []
    for label, lo, hi, n in bands:
        band_df = df[(df["_score"] >= lo) & (df["_score"] < hi)]
        if len(band_df) >= n:
            picked = band_df.sample(n, random_state=42)
        else:
            picked = band_df
        selected.append(picked)
        print(f"  {label} ({lo}-{hi}): picked {len(picked)} from {len(band_df)} available")

    return pd.concat(selected)


# Mapping from model feature names -> DB column names
FEATURE_TO_DB = {
    "AMT_INCOME_TOTAL": "amt_income_total",
    "AMT_CREDIT": "amt_credit",
    "AMT_ANNUITY": "amt_annuity",
    "AMT_GOODS_PRICE": "amt_goods_price",
    "CODE_GENDER": "code_gender",
    "DAYS_BIRTH": "days_birth",
    "DAYS_EMPLOYED": "days_employed",
    "CNT_CHILDREN": "cnt_children",
    "CNT_FAM_MEMBERS": "cnt_fam_members",
    "NAME_FAMILY_STATUS": "name_family_status",
    "NAME_EDUCATION_TYPE": "name_education_type",
    "NAME_INCOME_TYPE": "name_income_type",
    "NAME_HOUSING_TYPE": "name_housing_type",
    "OCCUPATION_TYPE": "occupation_type",
    "ORGANIZATION_TYPE": "organization_type",
    "NAME_CONTRACT_TYPE": "name_contract_type",
    "EXT_SOURCE_1": "ext_source_1",
    "EXT_SOURCE_2": "ext_source_2",
    "EXT_SOURCE_3": "ext_source_3",
    "OWN_CAR_AGE": "own_car_age",
    "FLAG_OWN_CAR": "flag_own_car",
    "FLAG_OWN_REALTY": "flag_own_realty",
    "bureau_active_count": "bureau_active_count",
    "bureau_debt_sum": "bureau_debt_sum",
    "bureau_credit_sum": "bureau_credit_sum",
    "bureau_loan_count": "bureau_loan_count",
    "prev_app_count": "prev_app_count",
    "prev_approved_count": "prev_approved_count",
    "prev_refused_count": "prev_refused_count",
    "prev_amt_credit_mean": "prev_amt_credit_mean",
    "prev_amt_annuity_mean": "prev_amt_annuity_mean",
    "prev_approval_rate": "prev_approval_rate",
    "DAYS_REGISTRATION": "days_registration",
    "DAYS_ID_PUBLISH": "days_id_publish",
    "DAYS_LAST_PHONE_CHANGE": "days_last_phone_change",
    "FLAG_WORK_PHONE": "flag_work_phone",
    "REGION_POPULATION_RELATIVE": "region_population_relative",
    "DEF_30_CNT_SOCIAL_CIRCLE": "def_30_cnt_social_circle",
    "AMT_REQ_CREDIT_BUREAU_QRT": "amt_req_credit_bureau_qrt",
}

# Categorical features that need reverse label encoding
CATEGORICAL_FEATURES = {
    "CODE_GENDER", "NAME_CONTRACT_TYPE", "NAME_INCOME_TYPE",
    "NAME_EDUCATION_TYPE", "NAME_FAMILY_STATUS", "NAME_HOUSING_TYPE",
    "OCCUPATION_TYPE", "ORGANIZATION_TYPE",
}

# Flag features stored as 0/1 in training but originally Y/N
FLAG_FEATURES = {"FLAG_OWN_CAR", "FLAG_OWN_REALTY"}


def build_applicant_dict(row, reverse_maps):
    """Convert a test data row to DB column dict."""
    data = {}
    for model_feat, db_col in FEATURE_TO_DB.items():
        val = row.get(model_feat)
        if pd.isna(val):
            continue

        if model_feat in CATEGORICAL_FEATURES:
            decoded = decode_value(model_feat, val, reverse_maps)
            if decoded:
                data[db_col] = decoded
        elif model_feat in FLAG_FEATURES:
            # Training data has 0/1 (encoded from N/Y)
            data[db_col] = int(val)
        else:
            data[db_col] = float(val)

    # Compute human-friendly derived fields
    if "days_birth" in data:
        data["age_years"] = round(abs(data["days_birth"]) / 365.25, 1)
    if "days_employed" in data:
        data["employment_years"] = round(abs(data["days_employed"]) / 365.25, 1)
    if "amt_credit" in data and "amt_income_total" in data and data["amt_income_total"] > 0:
        data["credit_income_ratio"] = round(data["amt_credit"] / data["amt_income_total"], 4)
    if "amt_annuity" in data and "amt_income_total" in data and data["amt_income_total"] > 0:
        data["annuity_income_ratio"] = round(data["amt_annuity"] / data["amt_income_total"], 4)

    # Compute ext_source_mean
    exts = [data.get("ext_source_1"), data.get("ext_source_2"), data.get("ext_source_3")]
    exts = [e for e in exts if e is not None]
    if exts:
        data["ext_source_mean"] = round(np.mean(exts), 4)

    return data


async def seed():
    print("Loading model artifacts...")
    model, feature_names, label_encoders, X_test, y_test = load_artifacts()
    reverse_maps = reverse_encode(label_encoders)

    print("Selecting diverse applicants...")
    selected = select_diverse_applicants(model, feature_names, X_test, y_test)

    print(f"\nPreparing {len(selected)} applicants for DB insertion...")

    from app.database import AsyncSessionLocal
    from app.models.applicant import Applicant
    from sqlalchemy import select, text

    async with AsyncSessionLocal() as session:
        # Clear existing data (results first due to foreign key)
        existing = await session.execute(select(Applicant))
        count = len(existing.scalars().all())
        if count > 0:
            print(f"  Clearing {count} existing applicants and their results...")
            await session.execute(text('DELETE FROM "ApplicantResults"'))
            await session.execute(text('DELETE FROM "Applicants"'))
            await session.commit()

        # Insert new applicants
        for i, (idx, row) in enumerate(selected.iterrows()):
            data = build_applicant_dict(row, reverse_maps)
            applicant = Applicant(**data)
            session.add(applicant)

            gender = data.get("code_gender", "?")
            age = data.get("age_years", "?")
            income = data.get("amt_income_total", 0)
            credit = data.get("amt_credit", 0)
            education = data.get("name_education_type", "?")
            occupation = data.get("occupation_type", "?")
            fields_count = len(data)

            print(f"  #{i+1}: {gender}, age {age}, {education}, {occupation}")
            print(f"       income=${income:,.0f}, loan=${credit:,.0f}, {fields_count} fields")

        await session.commit()
        print(f"\nSeeded {len(selected)} applicants successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
