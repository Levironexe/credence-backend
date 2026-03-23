from sqlalchemy import Column, Integer, Float, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime
from app.database import Base


class Applicant(Base):
    __tablename__ = "Applicants"

    id = Column(Integer, primary_key=True, index=True)

    # Core financial features
    amt_income_total = Column(Float, nullable=True)
    amt_credit = Column(Float, nullable=True)
    amt_annuity = Column(Float, nullable=True)
    amt_goods_price = Column(Float, nullable=True)

    # Demographics
    code_gender = Column(String(10), nullable=True)
    days_birth = Column(Float, nullable=True)
    days_employed = Column(Float, nullable=True)
    age_years = Column(Float, nullable=True)
    employment_years = Column(Float, nullable=True)
    cnt_children = Column(Integer, nullable=True)
    cnt_fam_members = Column(Integer, nullable=True)
    name_family_status = Column(String(50), nullable=True)
    name_education_type = Column(String(100), nullable=True)
    name_income_type = Column(String(100), nullable=True)
    name_housing_type = Column(String(100), nullable=True)
    occupation_type = Column(String(100), nullable=True)
    organization_type = Column(String(100), nullable=True)

    # Loan details
    name_contract_type = Column(String(50), nullable=True)

    # External scores
    ext_source_1 = Column(Float, nullable=True)
    ext_source_2 = Column(Float, nullable=True)
    ext_source_3 = Column(Float, nullable=True)
    ext_source_mean = Column(Float, nullable=True)

    # Bureau data
    bureau_active_count = Column(Float, nullable=True)
    bureau_debt_sum = Column(Float, nullable=True)
    bureau_credit_sum = Column(Float, nullable=True)
    bureau_loan_count = Column(Float, nullable=True)

    # Previous application history
    prev_app_count = Column(Float, nullable=True)
    prev_approved_count = Column(Float, nullable=True)
    prev_refused_count = Column(Float, nullable=True)
    prev_amt_credit_mean = Column(Float, nullable=True)
    prev_amt_annuity_mean = Column(Float, nullable=True)

    # Derived ratios
    credit_income_ratio = Column(Float, nullable=True)
    annuity_income_ratio = Column(Float, nullable=True)

    # Assets & flags
    flag_own_car = Column(Integer, nullable=True)
    flag_own_realty = Column(Integer, nullable=True)
    own_car_age = Column(Float, nullable=True)
    prev_approval_rate = Column(Float, nullable=True)

    # Registration & contact
    days_registration = Column(Float, nullable=True)
    days_id_publish = Column(Float, nullable=True)
    days_last_phone_change = Column(Float, nullable=True)
    flag_work_phone = Column(Integer, nullable=True)
    region_population_relative = Column(Float, nullable=True)

    # Social & credit bureau inquiries
    def_30_cnt_social_circle = Column(Float, nullable=True)
    amt_req_credit_bureau_qrt = Column(Float, nullable=True)

    def __repr__(self):
        return f"<Applicant(id={self.id})>"


class ApplicantResult(Base):
    __tablename__ = "ApplicantResults"

    id = Column(Integer, primary_key=True, autoincrement=True)
    applicant_id = Column(Integer, nullable=False, index=True)
    credit_score = Column(Integer, nullable=True)
    score_band = Column(String(50), nullable=True)
    default_probability = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True)
    decision = Column(String(50), nullable=True)
    shap_explanations = Column(JSONB, nullable=True)
    fairness_results = Column(JSONB, nullable=True)
    counterfactuals = Column(JSONB, nullable=True)
    full_report = Column(Text, nullable=True)
    scored_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    chat_id = Column(UUID(as_uuid=True), nullable=True)

    def __repr__(self):
        return f"<ApplicantResult(applicant_id={self.applicant_id}, score={self.credit_score})>"
