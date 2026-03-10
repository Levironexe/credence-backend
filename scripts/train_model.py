"""
Train XGBoost model on credit_risk_dataset and save for backend tools.

This script trains the model exactly as in streamlit_demo.py and saves:
- xgboost_model.pkl
- X_train.parquet, X_test.parquet
- y_train.parquet, y_test.parquet

Run from project root:
    cd credence-backend
    python scripts/train_model.py
"""

import sys
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

# Feature names from credit_risk_dataset
FEATURE_NAMES = [
    "person_age", "person_income", "person_home_ownership",
    "person_emp_length", "loan_intent", "loan_grade",
    "loan_amnt", "loan_int_rate", "loan_percent_income",
    "cb_person_default_on_file", "cb_person_cred_hist_length"
]

def main():
    print("=" * 60)
    print("Training XGBoost Credit Risk Model")
    print("=" * 60)

    # Load data
    data_path = Path(__file__).parent.parent.parent / "jupyter-notebook" / "data" / "credit_risk_dataset.csv"
    print(f"\n📂 Loading data from: {data_path}")

    if not data_path.exists():
        print(f"❌ Error: Data file not found at {data_path}")
        sys.exit(1)

    data = pd.read_csv(data_path)
    print(f"✓ Loaded {len(data)} rows")

    # Fix numeric conversion
    for col in data.columns:
        try:
            data[col] = pd.to_numeric(data[col])
        except (ValueError, TypeError):
            pass

    # Ensure numeric columns
    numeric_cols = [
        "person_age", "person_income", "person_emp_length",
        "loan_amnt", "loan_int_rate", "loan_percent_income",
        "cb_person_cred_hist_length", "loan_status"
    ]
    for col in numeric_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    # Fill missing values
    print("\n🔧 Preprocessing...")
    data["person_age"] = data["person_age"].fillna(data["person_age"].median())
    data["person_emp_length"] = data["person_emp_length"].fillna(data["person_emp_length"].median())
    data["loan_int_rate"] = data["loan_int_rate"].fillna(data["loan_int_rate"].median())
    data = data.dropna(subset=["loan_status"])

    # Prepare features and target
    X = data[FEATURE_NAMES].copy()
    y = data["loan_status"].astype(int)

    # Encode categoricals
    print("   Encoding categorical features...")
    le = LabelEncoder()
    for col in ["person_home_ownership", "loan_intent", "loan_grade", "cb_person_default_on_file"]:
        if col in X.columns:
            X[col] = le.fit_transform(X[col].astype(str))

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"✓ Train: {len(X_train)} samples, Test: {len(X_test)} samples")

    # Train model
    print("\n🤖 Training XGBoost model...")
    model = XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        eval_metric='logloss'
    )
    model.fit(X_train, y_train)

    # Evaluate
    train_score = model.score(X_train, y_train)
    test_score = model.score(X_test, y_test)
    print(f"✓ Train accuracy: {train_score:.4f}")
    print(f"✓ Test accuracy:  {test_score:.4f}")

    # Save model and data
    output_dir = Path(__file__).parent.parent / "ml_models" / "credit_scoring"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n💾 Saving to: {output_dir}")

    # Save model
    model_path = output_dir / "xgboost_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"✓ Saved model: {model_path.name}")

    # Save training data
    X_train.to_parquet(output_dir / "X_train.parquet")
    X_test.to_parquet(output_dir / "X_test.parquet")
    y_train.to_frame(name="loan_status").to_parquet(output_dir / "y_train.parquet")
    y_test.to_frame(name="loan_status").to_parquet(output_dir / "y_test.parquet")
    print("✓ Saved train/test data")

    print("\n✅ Training complete!")
    print("\nModel files saved:")
    for file in output_dir.glob("*"):
        print(f"   - {file.name}")

if __name__ == "__main__":
    main()
