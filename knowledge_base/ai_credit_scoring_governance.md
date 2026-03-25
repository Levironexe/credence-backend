# AI/ML in Credit Decisions — Regulatory Requirements and Best Practices

**Jurisdiction:** Vietnam
**Relevant regulations:** Decree 94/2025/ND-CP, Law 19/2023/QH15, Circular 31/2024/TT-NHNN

## Explainability Requirements

Every credit decision must be explainable to the applicant.

"The model said no" is NOT an acceptable explanation.

Must provide specific factors that contributed to the decision.

SHAP (SHapley Additive exPlanations) is the industry-standard method for model explainability.

Explanation must be in plain language, not technical jargon.

### Credence Implementation

1. SHAP waterfall plots showing factor contributions
2. Natural language summaries (e.g., "Your loan-to-income ratio of 3.5x is the primary negative factor")
3. Feature importance rankings with direction (positive/negative)

## Fairness and Bias Requirements

Models must not discriminate based on: gender, age, ethnicity, religion, marital status.

Disparate impact testing required: check if approval rates differ significantly across groups.

Metrics tracked: Demographic Parity, Equalized Odds, Predictive Equality.

## Counterfactual Explanations

When declining a loan, best practice is to provide actionable improvement paths.

Example: "If your loan amount were reduced from VND 500M to VND 350M, the model would approve."

Counterfactuals must change only actionable features (not age, gender, etc.).

## Model Governance

- Models must be validated before deployment and at least annually thereafter
- Must maintain model documentation: training data, feature engineering, performance metrics
- Must track model drift: compare current performance against training baseline
- Must have a model risk management policy approved by the Board of Directors
- Must maintain an audit trail of all credit decisions

## Data Quality Requirements

- Input data must be verified and from reliable sources
- Missing data must be handled transparently (imputation methods documented)
- Feature engineering must be documented and reproducible
- Training data must be representative of the target population

## Regulatory Sandbox Compliance (Decree 94/2025)

Companies using AI for credit scoring in the sandbox must:
- Document the model methodology in detail
- Demonstrate model explainability
- Test for bias across demographic groups
- Report model performance quarterly to SBV
- Maintain a human-in-the-loop for final credit decisions

## Credence Score Methodology

Credence uses an XGBoost gradient boosting model trained on the Home Credit Default Risk dataset.

### Score Scale: 300-850

- 800-850 (Exceptional): Auto-approve eligible, default probability <2%
- 740-799 (Very Good): Standard approval, default probability 2-5%
- 670-739 (Good): Approval with review, default probability 5-10%
- 580-669 (Fair): Manual review required, default probability 10-20%
- 300-579 (Poor): Likely decline, default probability >20%

### Model Performance

- AUC-ROC: 0.7705
- Gini Coefficient: 0.5411
- Recall: 68.6%
- Cross-validation standard deviation: 0.003

### Key Design: Ratio Features

The model uses ratio-based features instead of raw monetary amounts:
- credit_income_ratio = AMT_CREDIT / AMT_INCOME_TOTAL
- annuity_income_ratio = AMT_ANNUITY / AMT_INCOME_TOTAL
- employment_to_age_ratio = DAYS_EMPLOYED / DAYS_BIRTH

Rationale: In emerging markets like Vietnam with significant inflation, absolute VND amounts degrade over time. Ratios remain meaningful regardless of currency changes.
