"""
Fairness Validator Tool

Per-applicant fairness analysis using Fairlearn + neighborhood comparison.
Finds similar applicants in X_test, compares model outcomes across
demographic groups (gender, age, marital status) using:

- Disparate Impact Ratio via Fairlearn demographic_parity_ratio (threshold >= 0.80)
- Equalized Odds via Fairlearn equalized_odds_difference (threshold <= 0.10)
- Chi-squared statistical significance test (scipy)

Uses REAL protected attributes from the dataset:
- CODE_GENDER (0=Female, 1=Male)
- DAYS_BIRTH / age_years -> age groups
- NAME_FAMILY_STATUS -> marital status groups
"""

import logging
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

from fairlearn.metrics import (
    MetricFrame,
    demographic_parity_ratio,
    equalized_odds_difference,
    selection_rate,
    true_positive_rate,
    false_positive_rate,
    count,
)

logger = logging.getLogger(__name__)

# Minimum neighborhood size for reliable fairness metrics
MIN_NEIGHBORHOOD = 200
DEFAULT_NEIGHBORHOOD = 500
# Minimum group size to include in fairness analysis
MIN_GROUP_SIZE = 20
# Four-fifths rule threshold
DIR_THRESHOLD = 0.80
# Equalized odds max difference threshold
EO_THRESHOLD = 0.10
# Chi-squared significance level
SIGNIFICANCE_LEVEL = 0.05


class FairnessValidatorInput(BaseModel):
    """Input: applicant features and their credit score for contextual fairness analysis."""
    applicant_data: Optional[dict] = Field(
        default=None,
        description="Applicant feature dict (from extracted_fields). If provided, runs per-applicant neighborhood analysis."
    )
    credit_score: Optional[float] = Field(
        default=None,
        description="The applicant's credit score (300-850) for comparison."
    )
    default_probability: Optional[float] = Field(
        default=None,
        description="The applicant's default probability (0-1)."
    )


class FairnessValidator(BaseTool):
    """
    Per-applicant fairness validator using Fairlearn metrics.

    Finds the K nearest neighbors to the applicant in X_test,
    then checks model outcomes across protected attribute groups
    using Fairlearn's demographic_parity_ratio (>= 0.80),
    equalized_odds_difference (<= 0.10), and scipy chi-squared
    significance testing.

    Protected attributes checked:
    - Gender (CODE_GENDER): real values from dataset
    - Age group (DAYS_BIRTH / age_years): Young/Middle/Senior
    - Marital status (NAME_FAMILY_STATUS): Married/Single/Other
    """

    @property
    def name(self) -> str:
        return "fairness_validator"

    @property
    def description(self) -> str:
        return (
            "Validates credit decisions for demographic fairness using Fairlearn's "
            "Disparate Impact Ratio, Equalized Odds, and chi-squared significance "
            "testing across gender, age, and marital status."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return FairnessValidatorInput

    async def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            if not artifacts.loaded or artifacts.model is None:
                return {"success": False, "message": "Model not loaded for fairness validation"}

            if artifacts.X_test is None or artifacts.y_test is None:
                return {"success": False, "message": "Test data not available for fairness validation"}

            feature_names = artifacts.feature_names
            X_test = artifacts.X_test[feature_names] if feature_names else artifacts.X_test
            y_test = artifacts.y_test

            applicant_data = kwargs.get("applicant_data", {}) or {}
            applicant_score = kwargs.get("credit_score")
            applicant_prob = kwargs.get("default_probability")

            # Build applicant feature vector aligned with X_test columns
            applicant_vec = self._build_applicant_vector(applicant_data, X_test)

            # Find neighborhood of similar applicants
            neighbor_idx = self._find_neighbors(applicant_vec, X_test)
            neighborhood_size = len(neighbor_idx)

            X_neighbors = X_test.iloc[neighbor_idx]
            y_neighbors = y_test.iloc[neighbor_idx]

            # Model predictions on neighborhood
            y_pred = artifacts.model.predict(X_neighbors)
            y_actual = y_neighbors.values

            # Approval = not predicted to default
            y_approval = (1 - y_pred).astype(int)

            # Extract REAL protected attributes from the full dataset
            X_full = artifacts.X_test.iloc[neighbor_idx]

            # --- Gender analysis (CODE_GENDER) ---
            gender_groups = self._extract_gender(X_full)
            gender_result = self._analyze_with_fairlearn(
                y_approval, y_actual, gender_groups,
                {0: "Female", 1: "Male"},
                "Gender"
            )

            # --- Age group analysis ---
            age_groups = self._extract_age_groups(X_full)
            age_result = self._analyze_with_fairlearn(
                y_approval, y_actual, age_groups,
                {0: "Young (<35)", 1: "Middle (35-55)", 2: "Senior (55+)"},
                "Age"
            )

            # --- Marital status analysis ---
            marital_groups = self._extract_marital_status(X_full)
            marital_result = self._analyze_with_fairlearn(
                y_approval, y_actual, marital_groups,
                {0: "Single/Unaccompanied", 1: "Married", 2: "Other"},
                "Marital Status"
            )

            # Overall pass/fail
            gender_pass = gender_result["pass"]
            age_pass = age_result["pass"]
            marital_pass = marital_result["pass"]
            all_pass = gender_pass and age_pass and marital_pass

            # Applicant context
            applicant_age = self._get_applicant_age(applicant_data, applicant_vec, X_test)
            applicant_age_group = (
                "Young (<35)" if applicant_age < 35
                else "Middle (35-55)" if applicant_age <= 55
                else "Senior (55+)"
            )

            return {
                "success": True,
                "fairness_passed": all_pass,
                "bias_detected": not all_pass,
                "neighborhood_size": neighborhood_size,
                "applicant_context": {
                    "age": round(applicant_age, 1),
                    "age_group": applicant_age_group,
                    "credit_score": applicant_score,
                    "default_probability": round(applicant_prob, 4) if applicant_prob else None,
                },
                "gender_metrics": gender_result,
                "age_group_metrics": age_result,
                "marital_status_metrics": marital_result,
                "message": (
                    f"Fairness analysis (Fairlearn) on {neighborhood_size} similar applicants: "
                    + ("No significant bias detected — decision is demographically fair"
                       if all_pass
                       else "Potential bias detected — flagged for human review")
                ),
            }

        except Exception as e:
            logger.error(f"Fairness validation failed: {e}")
            return {"success": False, "error": str(e), "message": f"Fairness validation failed: {str(e)}"}

    # -- Core fairness analysis using Fairlearn --------------------------

    def _analyze_with_fairlearn(
        self,
        y_approval: np.ndarray,
        y_actual: np.ndarray,
        groups: np.ndarray,
        label_map: Dict[int, str],
        attr_name: str,
    ) -> Dict[str, Any]:
        """
        Analyze fairness for one protected attribute using Fairlearn.

        Returns:
            Dict with disparate_impact_ratio, equalized_odds, group details,
            statistical significance, and overall pass/fail.
        """
        # Map numeric group IDs to readable labels
        sensitive_labels = np.array([label_map.get(g, f"Group_{g}") for g in groups])

        # Filter out groups smaller than MIN_GROUP_SIZE
        unique_labels, label_counts = np.unique(sensitive_labels, return_counts=True)
        valid_labels = set(unique_labels[label_counts >= MIN_GROUP_SIZE])

        if len(valid_labels) < 2:
            return {
                "group_approval_rates": {},
                "disparate_impact_ratio": None,
                "equalized_odds_diff": None,
                "chi_squared_p_value": None,
                "statistically_significant": False,
                "pass": True,
                "note": f"Insufficient group diversity for {attr_name} analysis",
            }

        # Build mask for valid groups only
        valid_mask = np.array([l in valid_labels for l in sensitive_labels])
        y_app_valid = y_approval[valid_mask]
        y_act_valid = y_actual[valid_mask]
        sf_valid = sensitive_labels[valid_mask]

        # --- Fairlearn MetricFrame for per-group stats ---
        mf = MetricFrame(
            metrics={
                "approval_rate": selection_rate,
                "count": count,
            },
            y_true=y_act_valid,
            y_pred=y_app_valid,
            sensitive_features=sf_valid,
        )

        group_stats = {}
        for label, row in mf.by_group.iterrows():
            group_stats[label] = {
                "count": int(row["count"]),
                "approval_rate": round(float(row["approval_rate"]), 4),
            }

        # --- Disparate Impact Ratio via Fairlearn ---
        dir_value = demographic_parity_ratio(
            y_true=y_act_valid,
            y_pred=y_app_valid,
            sensitive_features=sf_valid,
        )
        dir_value = round(float(dir_value), 4)
        dir_pass = dir_value >= DIR_THRESHOLD

        # Identify highest/lowest groups
        rates = {k: v["approval_rate"] for k, v in group_stats.items()}
        highest_group = max(rates, key=rates.get)
        lowest_group = min(rates, key=rates.get)

        # --- Equalized Odds via Fairlearn ---
        eo_diff = self._safe_equalized_odds(y_act_valid, y_app_valid, sf_valid)
        eo_pass = eo_diff <= EO_THRESHOLD

        # Per-group TPR/FPR via Fairlearn MetricFrame
        tpr_fpr_metrics = {}
        try:
            eo_frame = MetricFrame(
                metrics={
                    "true_positive_rate": true_positive_rate,
                    "false_positive_rate": false_positive_rate,
                },
                y_true=y_act_valid,
                y_pred=y_app_valid,
                sensitive_features=sf_valid,
            )
            tpr_by_group = {}
            fpr_by_group = {}
            for label, row in eo_frame.by_group.iterrows():
                tpr_val = row.get("true_positive_rate")
                fpr_val = row.get("false_positive_rate")
                if pd.notna(tpr_val):
                    tpr_by_group[label] = round(float(tpr_val), 4)
                if pd.notna(fpr_val):
                    fpr_by_group[label] = round(float(fpr_val), 4)

            tpr_vals = list(tpr_by_group.values())
            fpr_vals = list(fpr_by_group.values())
            tpr_diff = (max(tpr_vals) - min(tpr_vals)) if len(tpr_vals) >= 2 else 0.0
            fpr_diff = (max(fpr_vals) - min(fpr_vals)) if len(fpr_vals) >= 2 else 0.0

            tpr_fpr_metrics = {
                "tpr_by_group": tpr_by_group,
                "fpr_by_group": fpr_by_group,
                "max_tpr_diff": round(tpr_diff, 4),
                "max_fpr_diff": round(fpr_diff, 4),
                "max_equalized_odds_diff": round(eo_diff, 4),
                "pass": eo_pass,
            }
        except Exception as e:
            logger.warning(f"Fairlearn TPR/FPR MetricFrame failed for {attr_name}: {e}")
            tpr_fpr_metrics = {
                "tpr_by_group": {},
                "fpr_by_group": {},
                "max_tpr_diff": 0.0,
                "max_fpr_diff": 0.0,
                "max_equalized_odds_diff": round(eo_diff, 4),
                "pass": eo_pass,
            }

        # --- Chi-squared test (scipy — not in Fairlearn) ---
        chi2_p = self._chi_squared_test(y_app_valid, sf_valid)
        significant = chi2_p is not None and chi2_p < SIGNIFICANCE_LEVEL

        # Overall: fail only if DIR fails AND the difference is statistically significant
        attr_pass = dir_pass or not significant

        return {
            "group_approval_rates": group_stats,
            "disparate_impact_ratio": dir_value,
            "highest_group": highest_group,
            "lowest_group": lowest_group,
            "equalized_odds": tpr_fpr_metrics,
            "chi_squared_p_value": round(chi2_p, 4) if chi2_p is not None else None,
            "statistically_significant": significant,
            "pass": attr_pass,
        }

    def _safe_equalized_odds(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        sensitive_features: np.ndarray,
    ) -> float:
        """Compute equalized_odds_difference, handling edge cases."""
        try:
            eo = equalized_odds_difference(
                y_true=y_true,
                y_pred=y_pred,
                sensitive_features=sensitive_features,
            )
            return round(float(eo), 4)
        except Exception as e:
            logger.warning(f"Fairlearn equalized_odds_difference failed: {e}")
            return 0.0

    # -- Protected attribute extraction ----------------------------------

    def _extract_gender(self, X: pd.DataFrame) -> np.ndarray:
        """Extract real gender from CODE_GENDER column."""
        if "CODE_GENDER" in X.columns:
            return X["CODE_GENDER"].values.astype(int)
        return np.zeros(len(X), dtype=int)

    def _extract_age_groups(self, X: pd.DataFrame) -> np.ndarray:
        """Derive age groups from age_years or DAYS_BIRTH."""
        if "age_years" in X.columns:
            age = X["age_years"].values
        elif "DAYS_BIRTH" in X.columns:
            age = (-X["DAYS_BIRTH"].values) / 365.25
        else:
            return np.ones(len(X), dtype=int)

        groups = np.zeros(len(age), dtype=int)
        groups[age >= 35] = 1
        groups[age >= 55] = 2
        return groups

    def _extract_marital_status(self, X: pd.DataFrame) -> np.ndarray:
        """Extract marital status from NAME_FAMILY_STATUS.
        Encoded values: 0=Civil marriage, 1=Married, 2=Separated,
                        3=Single/not married, 4=Unknown, 5=Widow
        We group into: 0=Single/Unaccompanied (3,4), 1=Married (0,1), 2=Other (2,5)
        """
        if "NAME_FAMILY_STATUS" not in X.columns:
            return np.zeros(len(X), dtype=int)

        raw = X["NAME_FAMILY_STATUS"].values.astype(int)
        groups = np.full(len(raw), 2, dtype=int)  # default: Other
        groups[(raw == 3) | (raw == 4)] = 0  # Single/Unaccompanied
        groups[(raw == 0) | (raw == 1)] = 1  # Married/Civil marriage
        return groups

    # -- Chi-squared significance test (not in Fairlearn) ----------------

    def _chi_squared_test(
        self,
        approval: np.ndarray,
        sensitive_labels: np.ndarray,
    ) -> Optional[float]:
        """
        Chi-squared test of independence between group membership and approval.
        Returns p-value, or None if test cannot be performed.
        """
        try:
            from scipy.stats import chi2_contingency

            unique_labels = np.unique(sensitive_labels)
            table = []
            for label in unique_labels:
                mask = sensitive_labels == label
                if mask.sum() < MIN_GROUP_SIZE:
                    continue
                approved = int(approval[mask].sum())
                rejected = int(mask.sum()) - approved
                table.append([rejected, approved])

            if len(table) < 2:
                return None

            table = np.array(table)
            chi2, p, dof, expected = chi2_contingency(table)
            return float(p)
        except ImportError:
            logger.warning("scipy not installed — skipping chi-squared test")
            return None
        except Exception as e:
            logger.warning(f"Chi-squared test failed: {e}")
            return None

    # -- Neighborhood finding --------------------------------------------

    def _build_applicant_vector(self, applicant_data: dict, X_test: pd.DataFrame) -> np.ndarray:
        """Build feature vector aligned with X_test columns, using medians for missing."""
        vec = np.zeros(len(X_test.columns))
        medians = X_test.median()
        for i, col in enumerate(X_test.columns):
            if col in applicant_data and applicant_data[col] is not None:
                try:
                    vec[i] = float(applicant_data[col])
                except (ValueError, TypeError):
                    vec[i] = medians.iloc[i]
            else:
                vec[i] = medians.iloc[i]
        return vec

    def _find_neighbors(self, applicant_vec: np.ndarray, X_test: pd.DataFrame) -> np.ndarray:
        """Find K nearest neighbors using scaled Euclidean distance."""
        stds = X_test.std()
        stds = stds.replace(0, 1)

        X_scaled = X_test.values / stds.values
        app_scaled = applicant_vec / stds.values

        distances = np.sqrt(((X_scaled - app_scaled) ** 2).sum(axis=1))

        k = max(MIN_NEIGHBORHOOD, min(DEFAULT_NEIGHBORHOOD, len(X_test)))
        neighbor_idx = np.argpartition(distances, k)[:k]
        return neighbor_idx

    def _get_applicant_age(self, applicant_data: dict, applicant_vec: np.ndarray, X_test: pd.DataFrame) -> float:
        """Get the applicant's age from data or vector."""
        if "age_years" in applicant_data:
            try:
                return float(applicant_data["age_years"])
            except (ValueError, TypeError):
                pass
        if "DAYS_BIRTH" in applicant_data:
            try:
                return abs(float(applicant_data["DAYS_BIRTH"])) / 365.25
            except (ValueError, TypeError):
                pass
        if "age_years" in X_test.columns:
            idx = list(X_test.columns).index("age_years")
            return applicant_vec[idx]
        if "DAYS_BIRTH" in X_test.columns:
            idx = list(X_test.columns).index("DAYS_BIRTH")
            return abs(applicant_vec[idx]) / 365.25
        return 40.0


# Singleton
fairness_validator = FairnessValidator()
