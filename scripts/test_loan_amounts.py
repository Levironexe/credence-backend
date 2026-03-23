"""Test applicant #4 with 5 different loan amounts within model's reliable range."""

import asyncio
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

MODEL_DIR = Path(__file__).parent.parent / "ml_models" / "credit_scoring"

with open(MODEL_DIR / "xgboost_model.pkl", "rb") as f:
    model = pickle.load(f)
with open(MODEL_DIR / "feature_names.pkl", "rb") as f:
    feature_names = pickle.load(f)
with open(MODEL_DIR / "label_encoders.pkl", "rb") as f:
    label_encoders = pickle.load(f)
X_train = pd.read_parquet(MODEL_DIR / "X_train.parquet")


async def get_applicant(app_id):
    from app.database import AsyncSessionLocal
    from app.models.applicant import Applicant
    from app.routers.applicants import map_db_to_features
    from sqlalchemy import select as sa_select

    async with AsyncSessionLocal() as db:
        result = await db.execute(sa_select(Applicant).where(Applicant.id == app_id))
        app = result.scalar_one_or_none()
        if app:
            return map_db_to_features(app)
    return None


def score_with_loan(loan_amount, base_data):
    d = dict(base_data)
    d["AMT_CREDIT"] = loan_amount

    row = pd.Series(index=feature_names, dtype=object)
    for feat in feature_names:
        if feat in d:
            row[feat] = d[feat]

    # Compute derived features
    credit = loan_amount
    inc = d.get("AMT_INCOME_TOTAL")
    annuity = d.get("AMT_ANNUITY")
    goods = d.get("AMT_GOODS_PRICE")
    fam = d.get("CNT_FAM_MEMBERS")
    days_birth = d.get("DAYS_BIRTH")
    days_emp = d.get("DAYS_EMPLOYED")
    ext1 = d.get("EXT_SOURCE_1")
    ext2 = d.get("EXT_SOURCE_2")
    ext3 = d.get("EXT_SOURCE_3")
    ba = d.get("bureau_active_count")
    bl = d.get("bureau_loan_count")
    bd = d.get("bureau_debt_sum")
    bc = d.get("bureau_credit_sum")
    pa = d.get("prev_approved_count")
    pp = d.get("prev_app_count")

    if credit is not None and inc is not None:
        row["credit_income_ratio"] = credit / (inc + 1)
    if annuity is not None and inc is not None:
        row["annuity_income_ratio"] = annuity / (inc + 1)
    if credit is not None and goods is not None:
        row["credit_goods_ratio"] = credit / (goods + 1)
    if annuity is not None and credit is not None:
        row["annuity_credit_ratio"] = annuity / (credit + 1)
    if inc is not None and fam is not None:
        row["income_per_person"] = inc / (fam + 1)
    if days_birth is not None:
        row["age_years"] = (-days_birth) / 365.25
    if days_emp is not None:
        row["employment_years"] = (-days_emp) / 365.25
    if days_emp is not None and days_birth is not None:
        row["employed_to_birth_ratio"] = days_emp / (days_birth + 1)
    if ba is not None and bl is not None:
        row["bureau_active_ratio"] = ba / (bl + 1)
    if bd is not None and bc is not None:
        row["bureau_debt_credit_ratio"] = bd / (bc + 1)
    if pa is not None and pp is not None:
        row["prev_approval_rate"] = pa / (pp + 1)
    exts = [v for v in [ext1, ext2, ext3] if v is not None]
    if exts:
        row["ext_source_mean"] = np.mean(exts)
        row["ext_source_std"] = np.std(exts, ddof=1) if len(exts) > 1 else 0.0
    if ext1 is not None and ext2 is not None and ext3 is not None:
        row["ext_source_product"] = ext1 * ext2 * ext3

    # Encode categoricals
    for col, le in label_encoders.items():
        if col in row.index and isinstance(row.get(col), str):
            try:
                row[col] = le.transform([row[col]])[0]
            except ValueError:
                row[col] = np.nan

    # Impute missing
    for feat in feature_names:
        if pd.isna(row.get(feat)):
            if feat in X_train.columns:
                row[feat] = float(X_train[feat].median())
            else:
                row[feat] = 0.0

    X = row[feature_names].values.astype(float).reshape(1, -1)
    prob = float(model.predict_proba(X)[0, 1])
    score = int(850 - prob * 550)
    return score, prob


async def main():
    for app_id in [4, 13]:
        data = await get_applicant(app_id)
        if not data:
            print(f"Applicant #{app_id} not found in DB")
            continue

        income = data["AMT_INCOME_TOTAL"]
        ext_mean = data.get("ext_source_mean", 0)
        print(f"=== Applicant #{app_id} ===")
        print(f"  Income: ${income:,.0f}  |  Ext Score Mean: {ext_mean:.4f}")
        print(f"  Current Loan: ${data.get('AMT_CREDIT', 0):,.0f}")
        print(f"  Max reliable loan (13x): ${income * 13:,.0f}")
        print()

        test_loans = [
            (income * 1, "1x income"),
            (income * 3, "3x income"),
            (income * 5, "5x income"),
            (income * 10, "10x income"),
            (income * 13, "13x (limit)"),
        ]

        header = f"{'Loan Amount':>15}  {'Ratio':>14}  {'Score':>6}  {'Default%':>9}  {'Band':>12}  Decision"
        print(header)
        print("-" * len(header))

        for loan, label in test_loans:
            score, prob = score_with_loan(loan, data)
            if score >= 800:
                band = "Exceptional"
            elif score >= 740:
                band = "Very Good"
            elif score >= 670:
                band = "Good"
            elif score >= 580:
                band = "Fair"
            else:
                band = "Poor"
            decision = (
                "AUTO-APPROVE" if score >= 800
                else "APPROVE" if score >= 670
                else "REVIEW" if score >= 580
                else "DECLINE"
            )
            print(f"${loan:>14,.0f}  {label:>14}  {score:>6}  {prob:>8.1%}  {band:>12}  {decision}")

        print()


if __name__ == "__main__":
    asyncio.run(main())
