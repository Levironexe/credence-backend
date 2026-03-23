"""Classify all 128 model features by data source and null rate."""

import pickle
import pandas as pd
from pathlib import Path

MODEL_DIR = Path(__file__).parent.parent / "ml_models" / "credit_scoring"

with open(MODEL_DIR / "feature_names.pkl", "rb") as f:
    feature_names = pickle.load(f)
X_train = pd.read_parquet(MODEL_DIR / "X_train.parquet")


def classify(feat):
    non_null_pct = X_train[feat].notna().mean() * 100

    # Applicant-provided: things a person knows about themselves
    if feat == "AMT_INCOME_TOTAL":
        return "applicant", "Loan Application", True, "Total annual income", non_null_pct
    if feat == "AMT_CREDIT":
        return "applicant", "Loan Application", True, "Loan amount requested", non_null_pct
    if feat == "AMT_ANNUITY":
        return "applicant", "Loan Application", True, "Monthly payment amount", non_null_pct
    if feat == "AMT_GOODS_PRICE":
        return "applicant", "Loan Application", True, "Price of goods being purchased", non_null_pct
    if feat == "NAME_CONTRACT_TYPE":
        return "applicant", "Loan Application", True, "Cash loan or Revolving", non_null_pct
    if feat == "CODE_GENDER":
        return "applicant", "Personal", True, "Gender (M/F)", non_null_pct
    if feat == "CNT_CHILDREN":
        return "applicant", "Personal", True, "Number of children", non_null_pct
    if feat == "CNT_FAM_MEMBERS":
        return "applicant", "Personal", True, "Family members count", non_null_pct
    if feat == "DAYS_BIRTH":
        return "applicant", "Personal", True, "Date of birth (age)", non_null_pct
    if feat == "NAME_EDUCATION_TYPE":
        return "applicant", "Personal", True, "Education level", non_null_pct
    if feat == "NAME_FAMILY_STATUS":
        return "applicant", "Personal", True, "Marital status", non_null_pct
    if feat == "NAME_HOUSING_TYPE":
        return "applicant", "Personal", True, "Housing (own/rent/parents)", non_null_pct
    if feat == "DAYS_ID_PUBLISH":
        return "applicant", "Personal", True, "When ID document was issued", non_null_pct
    if feat == "DAYS_EMPLOYED":
        return "applicant", "Employment", True, "Employment start date", non_null_pct
    if feat == "NAME_INCOME_TYPE":
        return "applicant", "Employment", True, "Income type (Working/Pensioner)", non_null_pct
    if feat == "OCCUPATION_TYPE":
        return "applicant", "Employment", True, "Job title/type", non_null_pct
    if feat == "ORGANIZATION_TYPE":
        return "applicant", "Employment", True, "Employer industry", non_null_pct
    if feat == "FLAG_OWN_CAR":
        return "applicant", "Assets", True, "Owns a car?", non_null_pct
    if feat == "FLAG_OWN_REALTY":
        return "applicant", "Assets", True, "Owns property?", non_null_pct
    if feat == "OWN_CAR_AGE":
        return "applicant", "Assets", True, "Car age (years)", non_null_pct
    if feat == "NAME_TYPE_SUITE":
        return "applicant", "Loan Application", True, "Who accompanied applicant", non_null_pct
    if feat == "FLAG_MOBIL":
        return "applicant", "Contact", True, "Has mobile phone?", non_null_pct
    if feat == "FLAG_EMP_PHONE":
        return "applicant", "Contact", True, "Has employer phone?", non_null_pct
    if feat == "FLAG_WORK_PHONE":
        return "applicant", "Contact", True, "Has work phone?", non_null_pct
    if feat == "FLAG_CONT_MOBILE":
        return "applicant", "Contact", True, "Mobile reachable?", non_null_pct
    if feat == "FLAG_PHONE":
        return "applicant", "Contact", True, "Has home phone?", non_null_pct
    if feat == "FLAG_EMAIL":
        return "applicant", "Contact", True, "Has email?", non_null_pct
    if feat.startswith("REG_") or feat.startswith("LIVE_"):
        return "applicant", "Location", True, "Address mismatch flag", non_null_pct

    # External credit scores
    if feat.startswith("EXT_SOURCE"):
        return "bureau", "External Credit Scores", False, f"External credit score ({feat[-1]})", non_null_pct

    # Bureau data
    if feat.startswith("bureau_"):
        return "bureau", "Bureau Data", False, "Credit bureau data", non_null_pct
    if feat.startswith("AMT_REQ_CREDIT_BUREAU"):
        return "bureau", "Bureau Inquiries", False, "Credit bureau inquiry count", non_null_pct
    if feat.startswith("OBS_") or feat.startswith("DEF_"):
        return "bureau", "Social Circle", False, "Social circle default count", non_null_pct

    # Previous application history (bank internal)
    if feat.startswith("prev_"):
        return "bank", "Previous Applications", False, "Previous application history", non_null_pct

    # Bank/system
    if feat in ("REGION_POPULATION_RELATIVE", "REGION_RATING_CLIENT", "REGION_RATING_CLIENT_W_CITY"):
        return "bank", "Location", False, "Region rating/population", non_null_pct
    if feat == "DAYS_REGISTRATION":
        return "bank", "Registration", False, "Days since bank registration", non_null_pct
    if feat == "DAYS_LAST_PHONE_CHANGE":
        return "bank", "Contact", False, "Days since phone changed", non_null_pct
    if feat in ("WEEKDAY_APPR_PROCESS_START", "HOUR_APPR_PROCESS_START"):
        return "system", "System", False, "Application submission time", non_null_pct

    # Property/building data
    if any(feat.startswith(p) for p in [
        "APARTMENTS", "BASEMENT", "YEARS_BEGIN", "YEARS_BUILD", "COMMON",
        "ELEVATOR", "ENTRANCE", "FLOORS", "LAND", "LIVING", "NONLIVING",
    ]):
        return "property", "Building Data", False, "Building characteristic", non_null_pct
    if feat in ("TOTALAREA_MODE", "FONDKAPREMONT_MODE", "HOUSETYPE_MODE",
                "WALLSMATERIAL_MODE", "EMERGENCYSTATE_MODE"):
        return "property", "Building Data", False, "Building characteristic", non_null_pct

    # Derived/computed
    if feat in ("credit_income_ratio", "annuity_income_ratio", "credit_goods_ratio",
                "annuity_credit_ratio", "income_per_person", "age_years", "employment_years",
                "employed_to_birth_ratio", "bureau_active_ratio", "bureau_debt_credit_ratio",
                "ext_source_product", "ext_source_mean", "ext_source_std"):
        return "derived", "Derived (computed)", False, "Computed from other features", non_null_pct

    return "unknown", "Unknown", False, feat, non_null_pct


rows = []
for feat in feature_names:
    source, category, user_provides, desc, non_null_pct = classify(feat)
    rows.append({
        "feature": feat,
        "source": source,
        "category": category,
        "user_provides": user_provides,
        "desc": desc,
        "non_null_pct": non_null_pct,
    })

df = pd.DataFrame(rows)

print("=" * 90)
print("APPLICANT-PROVIDED (user fills in the form)")
print("=" * 90)
applicant = df[df["source"] == "applicant"].sort_values("non_null_pct", ascending=False)
for _, r in applicant.iterrows():
    print(f"  {r['feature']:<40} {r['non_null_pct']:>5.0f}% non-null  {r['desc']}")

print()
print("=" * 90)
print("THIRD-PARTY / SYSTEM (NOT from applicant)")
print("=" * 90)
for source in ["bureau", "bank", "property", "system", "derived"]:
    group = df[df["source"] == source]
    if len(group) == 0:
        continue
    print(f"\n  --- {source.upper()} ({len(group)} features) ---")
    for _, r in group.sort_values("non_null_pct", ascending=False).iterrows():
        print(f"  {r['feature']:<40} {r['non_null_pct']:>5.0f}% non-null  {r['desc']}")

print()
print("=" * 90)
print("SUMMARY")
print("=" * 90)
for source in ["applicant", "bureau", "bank", "property", "system", "derived"]:
    count = len(df[df["source"] == source])
    print(f"  {source:<20} {count:>3} features")
print(f"  {'TOTAL':<20} {len(df):>3} features")
