-- Migration: Create Loan Assessment Tables
-- Date: 2026-03-05
-- Description: Create tables for SME loan assessment system

-- Create LoanAssessment table
CREATE TABLE IF NOT EXISTS "LoanAssessment" (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "createdAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "userId" UUID NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    "applicantName" VARCHAR(255) NOT NULL,
    "businessName" VARCHAR(255),
    "loanAmount" FLOAT,
    "creditScore" FLOAT,
    "riskLevel" VARCHAR(20),
    "defaultProbability" FLOAT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    recommendation VARCHAR(50),
    "decisionReason" TEXT,
    "approvedAmount" FLOAT,
    "interestRate" FLOAT,
    "loanTermMonths" INTEGER,
    "financialRatios" JSONB,
    "shapExplanations" JSONB,
    counterfactuals JSONB,
    "fairnessCheckResults" JSONB,
    "lastContext" JSONB,
    visibility VARCHAR(10) NOT NULL DEFAULT 'private'
);

-- Create FinancialDocument table
CREATE TABLE IF NOT EXISTS "FinancialDocument" (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "assessmentId" UUID NOT NULL REFERENCES "LoanAssessment"(id) ON DELETE CASCADE,
    "documentType" VARCHAR(50) NOT NULL,
    "fileName" VARCHAR(255) NOT NULL,
    "filePath" TEXT NOT NULL,
    "fileSize" INTEGER,
    "mimeType" VARCHAR(100),
    "extractedData" JSONB,
    "fiscalYear" VARCHAR(10),
    "extractionConfidence" FLOAT,
    "uploadedAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "processedAt" TIMESTAMP
);

-- Create AssessmentInteraction table
CREATE TABLE IF NOT EXISTS "AssessmentInteraction" (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "assessmentId" UUID NOT NULL REFERENCES "LoanAssessment"(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    parts JSONB NOT NULL,
    attachments JSONB,
    provider VARCHAR(20),
    "toolsUsed" JSONB,
    "createdAt" TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_loan_assessment_user ON "LoanAssessment"("userId");
CREATE INDEX IF NOT EXISTS idx_loan_assessment_status ON "LoanAssessment"(status);
CREATE INDEX IF NOT EXISTS idx_loan_assessment_created ON "LoanAssessment"("createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_financial_document_assessment ON "FinancialDocument"("assessmentId");
CREATE INDEX IF NOT EXISTS idx_assessment_interaction_assessment ON "AssessmentInteraction"("assessmentId");
CREATE INDEX IF NOT EXISTS idx_assessment_interaction_created ON "AssessmentInteraction"("createdAt");

-- Add comments for documentation
COMMENT ON TABLE "LoanAssessment" IS 'SME loan assessment sessions with credit scores and decisions';
COMMENT ON TABLE "FinancialDocument" IS 'Financial documents uploaded for loan assessment';
COMMENT ON TABLE "AssessmentInteraction" IS 'Conversation messages between loan officer and AI agent';

-- Insert sample data for testing (optional)
-- INSERT INTO "LoanAssessment" ("userId", "applicantName", "businessName", "loanAmount")
-- VALUES ('existing-user-uuid', 'Coffee Shop Co.', 'Morning Brew Cafe', 5000);
