"""
SHAP Explainer Tool

Uses TreeSHAP to explain credit decisions with per-feature importance.
Generates waterfall plot image + structured data for LLM follow-ups.
"""

import base64
import io
import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from app.tools.base import BaseTool
from app.tools.model_loader import artifacts

logger = logging.getLogger(__name__)

# Human-readable labels for all 128 Home Credit features
FEATURE_LABELS: Dict[str, str] = {
    # Contract & identity
    "NAME_CONTRACT_TYPE": "Contract type",
    "CODE_GENDER": "Gender",
    "FLAG_OWN_CAR": "Owns a car",
    "FLAG_OWN_REALTY": "Owns property",
    "CNT_CHILDREN": "Number of children",
    # Financials
    "AMT_INCOME_TOTAL": "Annual income",
    "AMT_CREDIT": "Loan amount",
    "AMT_ANNUITY": "Monthly payment",
    "AMT_GOODS_PRICE": "Purchase price",
    # Demographics
    "NAME_TYPE_SUITE": "Accompanying person",
    "NAME_INCOME_TYPE": "Income type",
    "NAME_EDUCATION_TYPE": "Education level",
    "NAME_FAMILY_STATUS": "Family status",
    "NAME_HOUSING_TYPE": "Housing type",
    "REGION_POPULATION_RELATIVE": "Region population density",
    "DAYS_BIRTH": "Age (days)",
    "DAYS_EMPLOYED": "Employment duration (days)",
    "DAYS_REGISTRATION": "Registration age (days)",
    "DAYS_ID_PUBLISH": "ID document age (days)",
    "OWN_CAR_AGE": "Car age (years)",
    # Contact flags
    "FLAG_MOBIL": "Has mobile phone",
    "FLAG_EMP_PHONE": "Has work phone",
    "FLAG_WORK_PHONE": "Has landline at work",
    "FLAG_CONT_MOBILE": "Mobile reachable",
    "FLAG_PHONE": "Has home phone",
    "FLAG_EMAIL": "Has email",
    # Employment
    "OCCUPATION_TYPE": "Occupation",
    "CNT_FAM_MEMBERS": "Family members",
    "ORGANIZATION_TYPE": "Employer industry",
    # Region ratings
    "REGION_RATING_CLIENT": "Region rating",
    "REGION_RATING_CLIENT_W_CITY": "Region + city rating",
    "WEEKDAY_APPR_PROCESS_START": "Application day of week",
    "HOUR_APPR_PROCESS_START": "Application hour",
    # Address mismatch flags
    "REG_REGION_NOT_LIVE_REGION": "Registration ≠ living region",
    "REG_REGION_NOT_WORK_REGION": "Registration ≠ work region",
    "LIVE_REGION_NOT_WORK_REGION": "Living ≠ work region",
    "REG_CITY_NOT_LIVE_CITY": "Registration ≠ living city",
    "REG_CITY_NOT_WORK_CITY": "Registration ≠ work city",
    "LIVE_CITY_NOT_WORK_CITY": "Living ≠ work city",
    # External credit bureau scores
    "EXT_SOURCE_1": "External credit score 1",
    "EXT_SOURCE_2": "External credit score 2",
    "EXT_SOURCE_3": "External credit score 3",
    # Housing characteristics (AVG)
    "APARTMENTS_AVG": "Apartment size (avg)",
    "BASEMENTAREA_AVG": "Basement area (avg)",
    "YEARS_BEGINEXPLUATATION_AVG": "Building age (avg)",
    "YEARS_BUILD_AVG": "Construction year (avg)",
    "COMMONAREA_AVG": "Common area (avg)",
    "ELEVATORS_AVG": "Elevators (avg)",
    "ENTRANCES_AVG": "Entrances (avg)",
    "FLOORSMAX_AVG": "Max floors (avg)",
    "FLOORSMIN_AVG": "Min floors (avg)",
    "LANDAREA_AVG": "Land area (avg)",
    "LIVINGAPARTMENTS_AVG": "Living apartments (avg)",
    "LIVINGAREA_AVG": "Living area (avg)",
    "NONLIVINGAPARTMENTS_AVG": "Non-living units (avg)",
    "NONLIVINGAREA_AVG": "Non-living area (avg)",
    # Housing characteristics (MODE)
    "APARTMENTS_MODE": "Apartment size (mode)",
    "BASEMENTAREA_MODE": "Basement area (mode)",
    "YEARS_BEGINEXPLUATATION_MODE": "Building age (mode)",
    "YEARS_BUILD_MODE": "Construction year (mode)",
    "COMMONAREA_MODE": "Common area (mode)",
    "ELEVATORS_MODE": "Elevators (mode)",
    "ENTRANCES_MODE": "Entrances (mode)",
    "FLOORSMAX_MODE": "Max floors (mode)",
    "FLOORSMIN_MODE": "Min floors (mode)",
    "LANDAREA_MODE": "Land area (mode)",
    "LIVINGAPARTMENTS_MODE": "Living apartments (mode)",
    "LIVINGAREA_MODE": "Living area (mode)",
    "NONLIVINGAPARTMENTS_MODE": "Non-living units (mode)",
    "NONLIVINGAREA_MODE": "Non-living area (mode)",
    # Housing characteristics (MEDI)
    "APARTMENTS_MEDI": "Apartment size (median)",
    "BASEMENTAREA_MEDI": "Basement area (median)",
    "YEARS_BEGINEXPLUATATION_MEDI": "Building age (median)",
    "YEARS_BUILD_MEDI": "Construction year (median)",
    "COMMONAREA_MEDI": "Common area (median)",
    "ELEVATORS_MEDI": "Elevators (median)",
    "ENTRANCES_MEDI": "Entrances (median)",
    "FLOORSMAX_MEDI": "Max floors (median)",
    "FLOORSMIN_MEDI": "Min floors (median)",
    "LANDAREA_MEDI": "Land area (median)",
    "LIVINGAPARTMENTS_MEDI": "Living apartments (median)",
    "LIVINGAREA_MEDI": "Living area (median)",
    "NONLIVINGAPARTMENTS_MEDI": "Non-living units (median)",
    "NONLIVINGAREA_MEDI": "Non-living area (median)",
    # Housing categorical
    "FONDKAPREMONT_MODE": "Capital repair fund",
    "HOUSETYPE_MODE": "House type",
    "TOTALAREA_MODE": "Total area",
    "WALLSMATERIAL_MODE": "Wall material",
    "EMERGENCYSTATE_MODE": "Emergency state",
    # Social circle
    "OBS_30_CNT_SOCIAL_CIRCLE": "Social circle: 30-day observations",
    "DEF_30_CNT_SOCIAL_CIRCLE": "Social circle: 30-day defaults",
    "OBS_60_CNT_SOCIAL_CIRCLE": "Social circle: 60-day observations",
    "DEF_60_CNT_SOCIAL_CIRCLE": "Social circle: 60-day defaults",
    "DAYS_LAST_PHONE_CHANGE": "Days since phone change",
    # Credit bureau inquiries
    "AMT_REQ_CREDIT_BUREAU_HOUR": "Bureau inquiries (last hour)",
    "AMT_REQ_CREDIT_BUREAU_DAY": "Bureau inquiries (last day)",
    "AMT_REQ_CREDIT_BUREAU_WEEK": "Bureau inquiries (last week)",
    "AMT_REQ_CREDIT_BUREAU_MON": "Bureau inquiries (last month)",
    "AMT_REQ_CREDIT_BUREAU_QRT": "Bureau inquiries (last quarter)",
    "AMT_REQ_CREDIT_BUREAU_YEAR": "Bureau inquiries (last year)",
    # Bureau aggregates
    "bureau_loan_count": "Total bureau loans",
    "bureau_active_count": "Active credit lines",
    "bureau_closed_count": "Closed credit lines",
    "bureau_debt_sum": "Total outstanding debt",
    "bureau_credit_sum": "Total credit limit",
    "bureau_overdue_sum": "Total overdue amount",
    "bureau_days_credit_mean": "Avg bureau loan age (days)",
    "bureau_days_credit_enddate_mean": "Avg days to loan end",
    # Previous applications
    "prev_app_count": "Previous applications",
    "prev_approved_count": "Previously approved",
    "prev_refused_count": "Previously refused",
    "prev_amt_credit_mean": "Avg previous loan amount",
    "prev_amt_annuity_mean": "Avg previous payment",
    "prev_days_decision_mean": "Avg days since prev decision",
    # Derived ratios
    "credit_income_ratio": "Loan-to-income ratio",
    "annuity_income_ratio": "Payment-to-income ratio",
    "credit_goods_ratio": "Loan-to-purchase ratio",
    "income_per_person": "Income per family member",
    "employed_to_birth_ratio": "Employment-to-age ratio",
    "annuity_credit_ratio": "Payment-to-loan ratio",
    "age_years": "Age (years)",
    "employment_years": "Employment (years)",
    "bureau_active_ratio": "Active loan ratio",
    "bureau_debt_credit_ratio": "Debt-to-credit ratio",
    "prev_approval_rate": "Previous approval rate",
    "ext_source_product": "Combined external score (product)",
    "ext_source_mean": "Combined external score (avg)",
    "ext_source_std": "External score variance",
}


class SHAPExplainerInput(BaseModel):
    """Input: applicant data as a flat dictionary."""
    applicant_data: Dict[str, Any] = Field(
        description="Dictionary of applicant features to explain."
    )
    top_k: int = Field(default=10, description="Number of top features to return")


class SHAPExplainer(BaseTool):
    """
    SHAP explainer for credit scoring decisions.

    For each applicant, returns the top-k features that most influenced
    the prediction, with direction labels and a waterfall plot image.
    """

    @property
    def name(self) -> str:
        return "shap_explainer"

    @property
    def description(self) -> str:
        return (
            "Explains credit score decisions using SHAP feature importance. "
            "Shows which factors most influenced the score and in which direction. "
            "Generates a waterfall plot image for visual explanation."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return SHAPExplainerInput

    def _generate_waterfall_plot(self, shap_values, base_value, feature_names, feature_values, labels, top_k) -> str:
        """Generate a SHAP waterfall plot and return as base64 data URI."""
        import shap
        from shap.plots._style import style_context as _shap_style_context
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        BG_COLOR = "#0f0f0f"
        TEXT_COLOR = "#e4e4e7"       # zinc-200
        AXIS_COLOR = "#52525b"       # zinc-600
        CONNECTOR_COLOR = "#3f3f46"  # zinc-700

        POSITIVE_COLOR = np.array([239, 68, 68]) / 255      # #ef4444 red-500
        NEGATIVE_COLOR = np.array([16, 185, 129]) / 255      # #10b981 emerald-500
        LIGHT_POSITIVE = np.array([252, 165, 165]) / 255     # #fca5a5 red-300
        LIGHT_NEGATIVE = np.array([110, 231, 183]) / 255     # #6ee7b7 emerald-300

        explanation = shap.Explanation(
            values=shap_values,
            base_values=base_value,
            data=feature_values,
            feature_names=labels,
        )

        sorted_idx = np.argsort(np.abs(explanation.values))[::-1][:top_k]
        explanation_top = shap.Explanation(
            values=explanation.values[sorted_idx],
            base_values=explanation.base_values,
            data=explanation.data[sorted_idx],
            feature_names=[explanation.feature_names[i] for i in sorted_idx],
        )

        with plt.rc_context({
            "figure.facecolor": BG_COLOR,
            "axes.facecolor": BG_COLOR,
            "axes.edgecolor": AXIS_COLOR,
            "axes.labelcolor": TEXT_COLOR,
            "text.color": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "grid.color": AXIS_COLOR,
        }), _shap_style_context(
            primary_color_positive=POSITIVE_COLOR,
            primary_color_negative=NEGATIVE_COLOR,
            secondary_color_positive=LIGHT_POSITIVE,
            secondary_color_negative=LIGHT_NEGATIVE,
            text_color=TEXT_COLOR,
            tick_labels_color=AXIS_COLOR,
            hlines_color=CONNECTOR_COLOR,
            vlines_color=AXIS_COLOR,
        ):
            fig, ax = plt.subplots(figsize=(12, 7))
            shap.plots.waterfall(
                explanation_top,
                max_display=top_k,
                show=False,
            )

            ax = plt.gca()
            ax.set_facecolor(BG_COLOR)
            for spine in ax.spines.values():
                spine.set_color(AXIS_COLOR)

            plt.tight_layout()

        # Render to in-memory buffer and encode as base64
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=BG_COLOR, edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")

        logger.info("   Generated SHAP waterfall plot (base64)")
        return f"data:image/png;base64,{b64}"

    async def execute(self, applicant_data: Dict[str, Any] = None, top_k: int = 10, **kwargs) -> Dict[str, Any]:
        try:
            if applicant_data is None:
                applicant_data = kwargs

            if not artifacts.loaded or artifacts.shap_explainer is None:
                return {
                    "success": False,
                    "message": "SHAP explainer not available. Model or SHAP library not loaded."
                }

            feature_names = artifacts.feature_names
            row = pd.Series(index=feature_names, dtype=object)

            # Fill provided values
            for feat in feature_names:
                if feat in applicant_data:
                    row[feat] = applicant_data[feat]

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

            # Compute SHAP values
            X = row[feature_names].values.astype(float).reshape(1, -1)
            sv = artifacts.shap_explainer.shap_values(X)[0]

            # Get human-readable labels (merge pkl labels with built-in FEATURE_LABELS)
            merged_labels = {**FEATURE_LABELS}
            if artifacts.feature_labels:
                merged_labels.update(artifacts.feature_labels)
            labels = [merged_labels.get(f, f) for f in feature_names]

            feature_values = row[feature_names].values.astype(float)
            base_value = float(artifacts.shap_explainer.expected_value)

            # Generate waterfall plot as base64 data URI
            waterfall_plot = None
            try:
                waterfall_plot = self._generate_waterfall_plot(
                    sv, base_value, feature_names, feature_values, labels, top_k
                )
            except Exception as e:
                logger.warning(f"   Failed to generate waterfall plot: {e}")

            # Build explanation dataframe for structured data
            df = pd.DataFrame({
                "feature": feature_names,
                "value": feature_values,
                "shap_value": sv,
            })
            df["abs_shap"] = df["shap_value"].abs()
            df["direction"] = df["shap_value"].apply(
                lambda v: "Increases risk" if v > 0 else "Decreases risk"
            )
            df["label"] = [labels[i] for i in range(len(feature_names))]

            # Sort and return top-k
            df = df.sort_values("abs_shap", ascending=False).head(top_k).reset_index(drop=True)

            result = {
                "success": True,
                "method": "TreeSHAP",
                "explanations": df.to_dict("records"),
                "base_value": base_value,
                "message": f"Top {top_k} features explaining this credit decision"
            }

            if waterfall_plot:
                result["waterfall_plot"] = waterfall_plot

            return result

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to generate explanations: {str(e)}"
            }


# Singleton
shap_explainer = SHAPExplainer()
