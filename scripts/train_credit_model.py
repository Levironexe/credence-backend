"""
Credit Scoring Model Training Script

Trains an XGBoost classifier for credit risk prediction.
Production version would use Home Credit Default Risk dataset (307K rows).

This script uses synthetic training data for demonstration.

Usage:
    python scripts/train_credit_model.py
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report, confusion_matrix
import xgboost as xgb
import pickle

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_synthetic_data(n_samples=5000):
    """
    Generate synthetic SME loan data for training.

    Production: Replace with actual Home Credit dataset or proprietary data.
    """
    np.random.seed(42)

    # Generate features
    data = {
        # Core features
        "loan_amount": np.random.uniform(500, 50000, n_samples),
        "monthly_revenue": np.random.uniform(1000, 100000, n_samples),
        "business_tenure_months": np.random.randint(1, 120, n_samples),

        # Financial ratios
        "total_assets": np.random.uniform(10000, 500000, n_samples),
        "total_liabilities": np.random.uniform(5000, 400000, n_samples),
        "net_income": np.random.uniform(-10000, 50000, n_samples),
        "current_assets": np.random.uniform(5000, 200000, n_samples),
        "current_liabilities": np.random.uniform(2000, 150000, n_samples),

        # Alternative data
        "activity_rate": np.random.uniform(0.3, 1.0, n_samples),
        "payment_history_score": np.random.uniform(0.0, 1.0, n_samples),
        "num_dependents": np.random.randint(0, 8, n_samples),

        # Business context
        "owner_age": np.random.randint(25, 70, n_samples),
        "num_credit_inquiries": np.random.randint(0, 20, n_samples),
    }

    df = pd.DataFrame(data)

    # Derive features
    df["loan_to_revenue_ratio"] = df["loan_amount"] / (df["monthly_revenue"] * 12)
    df["debt_to_equity"] = df["total_liabilities"] / (df["total_assets"] - df["total_liabilities"] + 1)
    df["current_ratio"] = df["current_assets"] / (df["current_liabilities"] + 1)
    df["profit_margin"] = df["net_income"] / (df["monthly_revenue"] * 12 + 1)

    # Generate target (default = 1, no default = 0)
    # Higher risk if:
    # - High loan-to-revenue ratio
    # - Short business tenure
    # - High debt-to-equity
    # - Low current ratio
    # - Negative profit margin

    risk_score = (
        (df["loan_to_revenue_ratio"] > 0.3).astype(int) * 0.25 +
        (df["business_tenure_months"] < 24).astype(int) * 0.20 +
        (df["debt_to_equity"] > 2.0).astype(int) * 0.15 +
        (df["current_ratio"] < 1.0).astype(int) * 0.15 +
        (df["profit_margin"] < 0).astype(int) * 0.10 +
        (df["activity_rate"] < 0.6).astype(int) * 0.08 +
        (df["payment_history_score"] < 0.5).astype(int) * 0.07
    )

    # Convert risk score to binary default (with some noise)
    default_probability = risk_score + np.random.normal(0, 0.1, n_samples)
    df["default"] = (default_probability > 0.5).astype(int)

    return df


def train_model():
    """Train XGBoost credit scoring model."""
    print("=" * 60)
    print("Credit Scoring Model Training")
    print("=" * 60)

    # Generate training data
    print("\n[1/5] Generating training data...")
    df = generate_synthetic_data(n_samples=5000)
    print(f"  Generated {len(df)} samples")
    print(f"  Default rate: {df['default'].mean():.2%}")

    # Select features
    feature_columns = [
        "loan_amount",
        "monthly_revenue",
        "business_tenure_months",
        "total_assets",
        "total_liabilities",
        "net_income",
        "activity_rate",
        "payment_history_score",
        "num_dependents",
        "owner_age",
        "num_credit_inquiries",
        "loan_to_revenue_ratio",
        "debt_to_equity",
        "current_ratio",
        "profit_margin"
    ]

    X = df[feature_columns]
    y = df["default"]

    # Train/test split
    print("\n[2/5] Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  Training set: {len(X_train)} samples")
    print(f"  Test set: {len(X_test)} samples")

    # Train XGBoost model
    print("\n[3/5] Training XGBoost model...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="auc"
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    print("  ✓ Model trained")

    # Evaluate model
    print("\n[4/5] Evaluating model...")
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)

    auc_score = roc_auc_score(y_test, y_pred_proba)
    print(f"  AUC-ROC: {auc_score:.4f}")

    print("\n  Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["No Default", "Default"]))

    print("\n  Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"    TN: {cm[0,0]:4d}  FP: {cm[0,1]:4d}")
    print(f"    FN: {cm[1,0]:4d}  TP: {cm[1,1]:4d}")

    # Feature importance
    print("\n  Top 10 Feature Importances:")
    feature_importance = pd.DataFrame({
        "feature": feature_columns,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)

    for idx, row in feature_importance.head(10).iterrows():
        print(f"    {row['feature']:30s} {row['importance']:.4f}")

    # Save model
    print("\n[5/5] Saving model...")
    model_dir = Path(__file__).parent.parent / "ml_models" / "credit_scoring"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "xgboost_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"  ✓ Model saved to: {model_path}")

    # Save feature names
    feature_path = model_dir / "feature_names.pkl"
    with open(feature_path, "wb") as f:
        pickle.dump(feature_columns, f)
    print(f"  ✓ Feature names saved to: {feature_path}")

    # Save feature importance
    importance_path = model_dir / "feature_importance.pkl"
    with open(importance_path, "wb") as f:
        pickle.dump(feature_importance.to_dict(), f)
    print(f"  ✓ Feature importance saved to: {importance_path}")

    print("\n" + "=" * 60)
    print("✅ Training complete!")
    print("=" * 60)
    print(f"\nModel Performance:")
    print(f"  AUC-ROC: {auc_score:.4f} {'(Target: >0.85)' if auc_score < 0.85 else '✓'}")
    print(f"  Precision (Default): {cm[1,1]/(cm[1,1]+cm[0,1]):.2%}")
    print(f"  Recall (Default): {cm[1,1]/(cm[1,1]+cm[1,0]):.2%}")
    print(f"\nNext steps:")
    print(f"  1. Integrate model into credit_score_model tool")
    print(f"  2. Test with real loan applications")
    print(f"  3. Monitor model performance over time")
    print(f"  4. Retrain with production data for better accuracy")


if __name__ == "__main__":
    train_model()
