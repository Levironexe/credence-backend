-- Migration: Add new columns to Applicants table
-- Date: 2026-03-23
-- Description: Add demographic, bureau, previous application, and asset fields
--              to support all 128 XGBoost model features

-- Demographics
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS code_gender VARCHAR(10);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS name_family_status VARCHAR(50);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS name_education_type VARCHAR(100);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS name_income_type VARCHAR(100);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS name_housing_type VARCHAR(100);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS occupation_type VARCHAR(100);
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS organization_type VARCHAR(100);

-- Loan details
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS name_contract_type VARCHAR(50);

-- Bureau data (expanded)
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS bureau_credit_sum FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS bureau_loan_count FLOAT;

-- Previous application history
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS prev_app_count FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS prev_approved_count FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS prev_refused_count FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS prev_amt_credit_mean FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS prev_amt_annuity_mean FLOAT;

-- Assets & flags
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS flag_own_car INTEGER;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS flag_own_realty INTEGER;

-- Registration & contact
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS days_registration FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS days_id_publish FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS days_last_phone_change FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS flag_work_phone INTEGER;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS region_population_relative FLOAT;

-- Social & credit bureau inquiries
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS def_30_cnt_social_circle FLOAT;
ALTER TABLE "Applicants" ADD COLUMN IF NOT EXISTS amt_req_credit_bureau_qrt FLOAT;
