"""
Counterfactual Explanation Generator

Generates actionable "what-if" scenarios for denied applicants using a hybrid
approach: DiCE (when it can find solutions) + greedy constraint-aware optimizer
(for hard cases where only 7 actionable features can't flip the DiCE genetic search).

Improvements over baseline DiCE:
1. Derived features (ratios) removed from features_to_vary -- recomputed after
2. Directional constraints -- income can't go down, debt can't go up
3. Effort-based ranking -- easiest changes shown first (Ustun et al. 2019)
4. Plausibility caps -- no 10x income suggestions
5. Greedy optimizer fallback -- handles cases DiCE can't solve with limited features
"""

import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts
from app.tools.explainability.shap_explainer import FEATURE_LABELS

logger = logging.getLogger(__name__)

# === BASE features allowed to vary (NOT derived ratios) ===
BASE_ACTIONABLE = [
    "AMT_CREDIT",          # Loan amount requested
    "AMT_ANNUITY",         # Monthly payment amount
    "AMT_GOODS_PRICE",     # Purchase price of goods
    "AMT_INCOME_TOTAL",    # Annual income
    "DAYS_EMPLOYED",       # Employment duration (negative = days in past)
    "bureau_debt_sum",     # Total outstanding debt across bureaus
    "bureau_active_count", # Number of active credit lines
]

# Derived ratio features -- recomputed from base features, NOT varied by DiCE
DERIVED_FEATURES = {
    "credit_income_ratio":      ("AMT_CREDIT", "AMT_INCOME_TOTAL"),
    "annuity_income_ratio":     ("AMT_ANNUITY", "AMT_INCOME_TOTAL"),
}

# Permitted ranges for base features
PERMITTED_RANGES = {
    "AMT_INCOME_TOTAL": [50000, 1000000],
    "AMT_CREDIT":       [45000, 2000000],
    "AMT_ANNUITY":      [5000, 80000],
    "AMT_GOODS_PRICE":  [40000, 2000000],
    "DAYS_EMPLOYED":    [-7300, -30],
    "bureau_debt_sum":  [0, 5000000],
    "bureau_active_count": [0, 10],
}

# === Directional constraints ===
DIRECTION_CONSTRAINTS = {
    "AMT_INCOME_TOTAL":  "up_only",
    "DAYS_EMPLOYED":     "more_negative",  # more negative = employed longer
    "bureau_debt_sum":   "down_only",
    "bureau_active_count": "down_only",
    "AMT_CREDIT":        "down_only",   # borrow less
    "AMT_ANNUITY":       None,          # either direction (shorter/longer term)
    "AMT_GOODS_PRICE":   "down_only",   # buy something cheaper
}

# === Plausibility caps (max change magnitude) ===
PLAUSIBILITY_CAPS = {
    "AMT_INCOME_TOTAL": {"max_increase_pct": 0.50},
    "DAYS_EMPLOYED":    {"max_change_abs": -3650},
    "bureau_debt_sum":  {"max_decrease_pct": 1.0},
    "bureau_active_count": {"max_decrease_abs": 10},
}

# === Effort tiers (Ustun et al. 2019, Verma et al. 2022) ===
EFFORT_TIERS = {
    "AMT_CREDIT":        (1, "immediate",  "Adjust loan amount"),
    "AMT_GOODS_PRICE":   (1, "immediate",  "Choose different purchase"),
    "AMT_ANNUITY":       (1, "immediate",  "Adjust repayment term"),
    "bureau_debt_sum":   (2, "short_term", "Pay down existing debt"),
    "bureau_active_count": (2, "short_term", "Close unused credit lines"),
    "AMT_INCOME_TOTAL":  (3, "long_term",  "Increase income"),
    "DAYS_EMPLOYED":     (3, "long_term",  "Build employment history"),
}

# Human-readable labels
DEFAULT_LABELS = {
    "AMT_CREDIT": "Loan amount",
    "AMT_ANNUITY": "Monthly payment",
    "AMT_GOODS_PRICE": "Purchase price",
    "AMT_INCOME_TOTAL": "Annual income",
    "DAYS_EMPLOYED": "Employment duration",
    "bureau_debt_sum": "Total outstanding debt",
    "bureau_active_count": "Active credit lines",
    "credit_income_ratio": "Loan-to-income ratio",
    "annuity_income_ratio": "Payment-to-income ratio",
    "bureau_debt_credit_ratio": "Debt-to-credit ratio",
}


class CounterfactualInput(BaseModel):
    """Input: applicant data as a flat dictionary."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features for counterfactual generation."
    )
    total_CFs: int = Field(default=5, description="Number of counterfactual paths to generate (before filtering)")


class CounterfactualGenerator(BaseTool):
    """
    Hybrid counterfactual generator: DiCE + greedy optimizer.

    Tries DiCE first. When DiCE can't find counterfactuals with only 7 actionable
    features (common when the model depends heavily on immutable features like
    EXT_SOURCE), falls back to a greedy optimizer that systematically explores
    actionable changes respecting directional constraints and plausibility caps.
    """

    @staticmethod
    def prob_to_score(p: float) -> int:
        return int(850 - p * 550)

    @staticmethod
    def score_band(score: int) -> str:
        if score >= 800: return "Exceptional"
        if score >= 740: return "Very Good"
        if score >= 670: return "Good"
        if score >= 580: return "Fair"
        return "Poor"

    @property
    def name(self) -> str:
        return "counterfactual_generator"

    @property
    def description(self) -> str:
        return (
            "Generates ranked 'what-if' scenarios showing minimal changes to get a loan approved. "
            "Uses DiCE with effort-based ranking: easiest changes first (loan terms), "
            "then short-term actions (pay debt), then long-term (income/employment). "
            "Enforces directional constraints and recomputes derived ratios."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CounterfactualInput

    async def execute(self, applicant_data: Dict[str, Any] = None, total_CFs: int = 5, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.model is None:
                return {"success": False, "message": "Model not loaded for counterfactual generation"}

            query = self._prepare_query(applicant_data)
            if query is None:
                return {"success": False, "message": "Applicant data has missing values that could not be imputed"}

            orig_prob = float(artifacts.model.predict_proba(query.values)[0, 1])
            orig_score = self.prob_to_score(orig_prob)

            if orig_score >= 670:
                return {
                    "success": True,
                    "counterfactuals": [],
                    "original_score": orig_score,
                    "message": f"Applicant already qualifies (score: {orig_score}). No changes needed."
                }

            # Try DiCE first (if available)
            paths = []
            if artifacts.dice_explainer is not None:
                paths = self._generate_dice(query, orig_score, total_CFs)

            # Fall back to greedy optimizer if DiCE produced no valid paths
            if not paths:
                logger.info("DiCE produced no valid paths — using greedy optimizer")
                paths = self._generate_greedy(query, orig_score)

            # Rank by effort (easiest first) and keep top 3
            paths = self._rank_paths(paths)[:3]

            if not paths:
                return {
                    "success": True,
                    "counterfactuals": [],
                    "original_score": orig_score,
                    "original_probability": round(orig_prob, 4),
                    "message": "No actionable path found. The risk factors are in immutable features."
                }

            return {
                "success": True,
                "method": paths[0].get("method", "greedy"),
                "original_probability": round(orig_prob, 4),
                "original_score": orig_score,
                "original_band": self.score_band(orig_score),
                "counterfactuals": paths,
                "message": f"Found {len(paths)} actionable paths to improve credit score (ranked by ease of implementation)"
            }

        except Exception as e:
            logger.error(f"Counterfactual generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate counterfactuals: {str(e)}"
            }

    def _prepare_query(self, data: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """Prepare a query DataFrame from applicant data."""
        feature_names = artifacts.feature_names
        row = pd.Series(index=feature_names, dtype=object)

        for feat in feature_names:
            if feat in data:
                row[feat] = data[feat]

        # Encode categoricals
        if artifacts.label_encoders:
            for col, le in artifacts.label_encoders.items():
                if col in row.index and isinstance(row.get(col), str):
                    try:
                        row[col] = le.transform([row[col]])[0]
                    except ValueError:
                        row[col] = np.nan

        # Impute missing
        if artifacts.X_train is not None:
            for feat in feature_names:
                if pd.isna(row.get(feat)):
                    if feat in artifacts.X_train.columns:
                        row[feat] = float(artifacts.X_train[feat].median())
                    else:
                        row[feat] = 0.0

        query = pd.DataFrame([row[feature_names].values.astype(float)], columns=feature_names)
        if query.isna().any().any():
            return None
        return query

    def _check_direction(self, feature: str, orig_val: float, cf_val: float) -> bool:
        """Check if a feature change respects directional constraints."""
        constraint = DIRECTION_CONSTRAINTS.get(feature)
        if constraint is None:
            return True
        diff = cf_val - orig_val
        if abs(diff) < 1e-6:
            return True
        if constraint == "up_only" and diff < 0:
            return False
        if constraint == "down_only" and diff > 0:
            return False
        if constraint == "more_negative" and diff > 0:
            return False
        return True

    def _apply_plausibility_cap(self, feature: str, orig_val: float, cf_val: float) -> float:
        """Clamp a counterfactual value to plausible bounds."""
        cap = PLAUSIBILITY_CAPS.get(feature)
        if cap is None:
            return cf_val

        if "max_increase_pct" in cap and cf_val > orig_val:
            max_val = orig_val * (1 + cap["max_increase_pct"])
            cf_val = min(cf_val, max_val)

        if "max_decrease_pct" in cap and cf_val < orig_val:
            min_val = orig_val * (1 - cap["max_decrease_pct"])
            cf_val = max(cf_val, min_val)

        if "max_change_abs" in cap:
            max_change = cap["max_change_abs"]
            if max_change < 0:
                cf_val = max(cf_val, orig_val + max_change)
            else:
                cf_val = min(cf_val, orig_val + max_change)

        if "max_decrease_abs" in cap and cf_val < orig_val:
            cf_val = max(cf_val, orig_val - cap["max_decrease_abs"])

        return cf_val

    def _recompute_derived(self, query: pd.DataFrame, cf_row: pd.Series) -> Dict[str, Dict]:
        """Recompute derived ratio features from base features and return changes."""
        derived_changes = {}
        feature_names = artifacts.feature_names

        for ratio_name, (numerator, denominator) in DERIVED_FEATURES.items():
            if ratio_name not in feature_names:
                continue
            if numerator not in feature_names or denominator not in feature_names:
                continue

            orig_num = float(query[numerator].values[0])
            orig_den = float(query[denominator].values[0])
            cf_num = float(cf_row[numerator])
            cf_den = float(cf_row[denominator])

            if abs(orig_den) > 1e-6 and abs(cf_den) > 1e-6:
                orig_ratio = orig_num / orig_den
                new_ratio = cf_num / cf_den

                if abs(orig_ratio - new_ratio) > 0.001:
                    derived_changes[ratio_name] = {
                        "feature": ratio_name,
                        "label": DEFAULT_LABELS.get(ratio_name, ratio_name),
                        "current": round(orig_ratio, 3),
                        "suggested": round(new_ratio, 3),
                        "is_derived": True,
                    }
                    cf_row[ratio_name] = new_ratio

        return derived_changes

    def _build_change_entry(self, col: str, orig_val: float, cf_val: float) -> Dict:
        """Build a change entry dict for a feature."""
        labels = {**FEATURE_LABELS, **(artifacts.feature_labels or {}), **DEFAULT_LABELS}
        tier_info = EFFORT_TIERS.get(col, (9, "unknown", ""))
        label = labels.get(col, col)

        entry = {
            "feature": col,
            "label": label,
            "effort": tier_info[1],
            "effort_description": tier_info[2],
        }

        if col == "DAYS_EMPLOYED":
            entry["current"] = f"{abs(orig_val)/365.25:.1f} years"
            entry["suggested"] = f"{abs(cf_val)/365.25:.1f} years"
        elif abs(orig_val) > 1000:
            entry["current"] = round(orig_val, 0)
            entry["suggested"] = round(cf_val, 0)
        else:
            entry["current"] = round(orig_val, 3)
            entry["suggested"] = round(cf_val, 3)

        return entry

    def _rank_paths(self, paths: List[Dict]) -> List[Dict]:
        """Rank counterfactual paths by effort (easiest first), then fewest changes, then highest score."""
        def sort_key(path):
            changes = path.get("changes", [])
            max_tier = 0
            for c in changes:
                feat = c.get("feature", "")
                tier_info = EFFORT_TIERS.get(feat)
                if tier_info:
                    max_tier = max(max_tier, tier_info[0])
            n_base_changes = sum(1 for c in changes if not c.get("is_derived"))
            score = path.get("new_score", 0)
            return (max_tier, n_base_changes, -score)

        paths.sort(key=sort_key)

        tier_labels = {1: "Easiest", 2: "Moderate", 3: "Requires time"}
        for i, path in enumerate(paths):
            changes = path.get("changes", [])
            max_tier = 0
            for c in changes:
                feat = c.get("feature", "")
                tier_info = EFFORT_TIERS.get(feat)
                if tier_info:
                    max_tier = max(max_tier, tier_info[0])
            path["path_number"] = i + 1
            path["effort_level"] = tier_labels.get(max_tier, "Unknown")

        return paths

    # ── DiCE-based generation ───────────────────────────────────────────

    def _generate_dice(self, query: pd.DataFrame, orig_score: int, total_CFs: int) -> List[Dict]:
        """Generate counterfactuals using DiCE with post-filtering."""
        feature_names = artifacts.feature_names
        actionable = [f for f in BASE_ACTIONABLE if f in feature_names]
        permitted = {f: v for f, v in PERMITTED_RANGES.items() if f in actionable}

        try:
            cf = artifacts.dice_explainer.generate_counterfactuals(
                query_instances=query,
                total_CFs=total_CFs,
                desired_class="opposite",
                features_to_vary=actionable,
                permitted_range=permitted,
            )
        except Exception as e:
            logger.warning(f"DiCE generation failed: {e}")
            return []

        cf_df = cf.cf_examples_list[0].final_cfs_df
        if cf_df is None or len(cf_df) == 0:
            return []

        paths = []
        for _, cf_row in cf_df.iterrows():
            cf_row = cf_row.copy()
            changes = []

            for col in actionable:
                orig_val = float(query[col].values[0])
                cf_val = float(cf_row[col])

                if abs(orig_val - cf_val) < 1e-6:
                    continue

                if not self._check_direction(col, orig_val, cf_val):
                    cf_row[col] = orig_val
                    continue

                cf_val = self._apply_plausibility_cap(col, orig_val, cf_val)
                cf_row[col] = cf_val

                if abs(orig_val - cf_val) < 1e-6:
                    continue

                changes.append(self._build_change_entry(col, orig_val, cf_val))

            derived_changes = self._recompute_derived(query, cf_row)
            changes.extend(derived_changes.values())

            if not changes:
                continue

            new_prob = float(artifacts.model.predict_proba(
                cf_row[feature_names].values.astype(float).reshape(1, -1)
            )[0, 1])
            new_score = self.prob_to_score(new_prob)

            if new_score <= orig_score:
                continue

            if any(p["new_score"] == new_score for p in paths):
                continue

            paths.append({
                "changes": changes,
                "new_probability": round(new_prob, 4),
                "new_score": new_score,
                "new_band": self.score_band(new_score),
                "score_improvement": new_score - orig_score,
                "method": "DiCE (genetic, effort-ranked)",
            })

        return paths

    # ── Greedy constraint-aware optimizer ────────────────────────────────

    def _generate_greedy(self, query: pd.DataFrame, orig_score: int) -> List[Dict]:
        """
        Generate counterfactuals by greedily applying the best actionable changes.

        Strategy: For each actionable feature, find the best plausible change.
        Then combine features into paths grouped by effort tier:
          Path 1: Tier 1 only (loan terms)
          Path 2: Tier 1 + Tier 2 (+ pay debt)
          Path 3: Tier 1 + Tier 2 + Tier 3 (+ income/employment)
        """
        feature_names = artifacts.feature_names
        actionable = [f for f in BASE_ACTIONABLE if f in feature_names]

        # Step 1: Find the best single-feature change for each actionable feature
        best_changes = {}  # feature -> (new_value, score_delta)

        for feat in actionable:
            orig_val = float(query[feat].values[0])
            constraint = DIRECTION_CONSTRAINTS.get(feat)
            pr = PERMITTED_RANGES.get(feat)

            # Determine candidate values to try
            candidates = self._get_candidates(feat, orig_val, constraint, pr)

            best_val = None
            best_delta = 0

            for cand_val in candidates:
                # Apply plausibility cap
                cand_val = self._apply_plausibility_cap(feat, orig_val, cand_val)
                if abs(cand_val - orig_val) < 1e-6:
                    continue

                # Score with this single change
                test_row = query.copy()
                test_row[feat] = cand_val

                # Recompute derived features
                for ratio_name, (num, den) in DERIVED_FEATURES.items():
                    if ratio_name in feature_names and num in feature_names and den in feature_names:
                        den_val = float(test_row[den].values[0])
                        if abs(den_val) > 1e-6:
                            test_row[ratio_name] = float(test_row[num].values[0]) / den_val

                new_prob = float(artifacts.model.predict_proba(test_row.values)[0, 1])
                new_score = self.prob_to_score(new_prob)
                delta = new_score - orig_score

                if delta > best_delta:
                    best_delta = delta
                    best_val = cand_val

            if best_val is not None and best_delta > 0:
                best_changes[feat] = (best_val, best_delta)

        if not best_changes:
            return []

        # Step 2: Build 3 cumulative paths (tier 1, tier 1+2, tier 1+2+3)
        paths = []
        tier_groups = {1: [], 2: [], 3: []}
        for feat, (new_val, delta) in best_changes.items():
            tier = EFFORT_TIERS.get(feat, (9,))[0]
            if tier in tier_groups:
                tier_groups[tier].append((feat, new_val, delta))

        # Sort within each tier by score impact (best first)
        for tier in tier_groups:
            tier_groups[tier].sort(key=lambda x: -x[2])

        cumulative_features = []
        for max_tier in [1, 2, 3]:
            # Add features from this tier
            for feat, new_val, _ in tier_groups.get(max_tier, []):
                cumulative_features.append((feat, new_val))

            if not cumulative_features:
                continue

            # Apply all cumulative changes and score
            test_row = query.copy()
            changes = []

            for feat, new_val in cumulative_features:
                orig_val = float(query[feat].values[0])
                test_row[feat] = new_val
                changes.append(self._build_change_entry(feat, orig_val, new_val))

            # Recompute derived features
            test_series = test_row.iloc[0].copy() if hasattr(test_row, 'iloc') else test_row.copy()
            derived_changes = self._recompute_derived(query, test_series)

            # Update test_row with recomputed derived values
            for ratio_name in derived_changes:
                if ratio_name in feature_names:
                    test_row[ratio_name] = test_series[ratio_name]

            changes.extend(derived_changes.values())

            new_prob = float(artifacts.model.predict_proba(test_row.values)[0, 1])
            new_score = self.prob_to_score(new_prob)

            if new_score <= orig_score:
                continue

            # Skip if this path has identical changes to an existing one
            n_base = sum(1 for c in changes if not c.get("is_derived"))
            if any(
                p["new_score"] == new_score
                and sum(1 for c in p["changes"] if not c.get("is_derived")) == n_base
                for p in paths
            ):
                continue

            paths.append({
                "changes": list(changes),
                "new_probability": round(new_prob, 4),
                "new_score": new_score,
                "new_band": self.score_band(new_score),
                "score_improvement": new_score - orig_score,
                "method": "greedy optimizer (effort-ranked)",
            })

        return paths

    def _get_candidates(self, feat: str, orig_val: float, constraint: Optional[str], pr: Optional[list]) -> List[float]:
        """Generate candidate values for a feature, respecting direction and range."""
        candidates = []
        lo = pr[0] if pr else orig_val * 0.1
        hi = pr[1] if pr else orig_val * 3.0

        if constraint == "up_only":
            # Try 10%, 25%, 50% increase
            for pct in [0.10, 0.25, 0.50]:
                v = orig_val * (1 + pct)
                if v <= hi:
                    candidates.append(v)
        elif constraint == "down_only":
            # Try 25%, 50%, 75%, 100% decrease
            for pct in [0.25, 0.50, 0.75, 1.0]:
                v = orig_val * (1 - pct)
                if v >= lo:
                    candidates.append(max(v, lo))
        elif constraint == "more_negative":
            # More negative = more employed
            for extra_years in [1, 3, 5, 10]:
                v = orig_val - extra_years * 365.25
                if v >= lo:
                    candidates.append(v)
        else:
            # Both directions (loan terms)
            for pct in [0.10, 0.25, 0.50]:
                v_down = orig_val * (1 - pct)
                v_up = orig_val * (1 + pct)
                if v_down >= lo:
                    candidates.append(v_down)
                if v_up <= hi:
                    candidates.append(v_up)
            # Also try specific good values (e.g., lower loan amount)
            if orig_val > lo:
                candidates.append(lo)

        return candidates


# Singleton
counterfactual_generator = CounterfactualGenerator()
