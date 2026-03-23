# CreditAI Model Evaluation Report

**Model**: XGBoost Classifier
**Dataset**: Home Credit Default Risk (307K training samples, 128 features)
**Test Set**: 46,127 held-out applicant profiles (20% stratified split)
**Evaluation Date**: 2026-03-22

---

## 1. Discrimination Metrics

| Metric | Value | Proposal Target | Status |
|---|---|---|---|
| **AUC-ROC** | 0.7705 | > 0.85 | Below target |
| **KS Statistic** | 0.4032 | > 0.45 | Below target |
| **Gini Coefficient** | 0.5411 | — | — |
| **Average Precision** | 0.2516 | — | — |

**Note**: The proposal target of AUC > 0.85 assumes the full 200+ engineered features from the Home Credit relational tables (bureau history, previous applications, installment payments). The current model uses 128 features. Feature engineering from multi-table joins is the primary path to closing the gap.

AUC 0.77 is consistent with published baselines on this dataset without heavy feature engineering.

---

## 2. Classification Performance (threshold = 0.5)

| Metric | Value |
|---|---|
| Accuracy | 0.7128 |
| Precision | 0.1715 |
| Recall (Sensitivity) | 0.6858 |
| F1 Score | 0.2743 |

### Confusion Matrix

|  | Predicted Good | Predicted Default |
|---|---|---|
| **Actual Good** | 30,376 (TN) | 12,100 (FP) |
| **Actual Default** | 1,147 (FN) | 2,504 (TP) |

**Class distribution**: 7.92% default rate (3,651 defaults out of 46,127). The dataset is heavily imbalanced, which is typical for credit scoring.

---

## 3. Credit Score Distribution

Score = 850 - floor(default_probability x 550), mapped to FICO-equivalent bands.

| Score Band | Count | % of Total | Default Rate | CreditAI Decision |
|---|---|---|---|---|
| **Exceptional** (800-850) | 1,173 | 2.5% | 0.68% | Auto-approve |
| **Very Good** (740-799) | 7,518 | 16.3% | 1.53% | Approve, standard terms |
| **Good** (670-739) | 10,901 | 23.6% | 2.70% | Approve with conditions |
| **Fair** (580-669) | 11,493 | 24.9% | 6.05% | Manual review |
| **Poor** (300-579) | 15,042 | 32.6% | 16.88% | Decline + counterfactual |

### Key Observations

- **Score bands are well-separated**: default rates increase monotonically from 0.68% (Exceptional) to 16.88% (Poor) — a 25x gradient, confirming the model meaningfully ranks risk.
- **Approved population (score >= 670)**: 19,592 applicants (42.5%) with a default rate of only **2.13%** — strong credit quality among approvals.
- **Fair band captures borderline cases**: 6.05% default rate makes manual review appropriate.

---

## 4. Business Metrics

| Metric | Value |
|---|---|
| Total test applicants | 46,127 |
| Approved (score >= 670) | 19,592 (42.5%) |
| Default rate among approved | 2.13% |
| Declined (score < 670) | 26,535 (57.5%) |
| Default rate among declined | 12.43% |

The 6x difference in default rates between approved (2.13%) and declined (12.43%) populations confirms the model provides meaningful risk separation for lending decisions.

---

## 5. Top 10 Most Important Features

| Rank | Feature | Importance |
|---|---|---|
| 1 | ext_source_mean (External source score average) | 0.1096 |
| 2 | EXT_SOURCE_2 (External score 2) | 0.0271 |
| 3 | EXT_SOURCE_3 (External score 3) | 0.0269 |
| 4 | ext_source_product (External score product) | 0.0247 |
| 5 | NAME_EDUCATION_TYPE | 0.0246 |
| 6 | credit_goods_ratio | 0.0187 |
| 7 | CODE_GENDER | 0.0177 |
| 8 | DAYS_EMPLOYED (Employment duration) | 0.0172 |
| 9 | employment_years | 0.0157 |
| 10 | bureau_debt_credit_ratio | 0.0151 |

External source scores dominate, consistent with Home Credit competition findings. Employment stability and debt ratios are the top behavioral features.

---

## 6. Model Artifacts

All artifacts are stored in `ml_models/credit_scoring/`:

| File | Size | Description |
|---|---|---|
| `xgboost_model.pkl` | 848 KB | Trained XGBoost classifier |
| `X_train.parquet` | 35.7 MB | Training features (128 cols) |
| `X_test.parquet` | 8.7 MB | Test features (46,127 rows) |
| `y_train.parquet` | 163 KB | Training labels |
| `y_test.parquet` | 7.5 KB | Test labels |
| `dice_explainer.pkl` | 13.7 MB | Pre-fitted DiCE counterfactual explainer |
| `dice_data.pkl` | 3.7 MB | DiCE training data object |
| `feature_names.pkl` | 2.7 KB | 128 feature name list |
| `label_encoders.pkl` | 3.3 KB | Categorical encoders |
| `feature_labels.pkl` | 414 B | Human-readable feature labels |
| `actionable_features.pkl` | 208 B | Features allowed to vary in counterfactuals |
| `metrics.pkl` | 119 B | Saved training metrics |

---

## 7. Paths to Improve AUC

To reach the proposal target of AUC > 0.85:

1. **Multi-table feature engineering**: Join bureau history, previous applications, installment payments, and credit card balance tables from the Home Credit dataset to derive 200+ aggregated features (utilization ratios, payment punctuality scores, approval rates).
2. **Bayesian hyperparameter tuning**: Current model uses default/minimal tuning. Optuna or SageMaker Automatic Model Tuning could yield +0.02-0.03 AUC.
3. **Ensemble methods**: Blend XGBoost with LightGBM or CatBoost for diversity gain.
4. **Target encoding**: Replace label encoding of high-cardinality categoricals with target encoding.
