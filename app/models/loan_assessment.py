"""
Loan Assessment Database Models

Models for SME loan assessment sessions, financial documents, and credit decisions.
"""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base


class LoanAssessment(Base):
    """
    Loan assessment session (replaces Chat for financial context).

    Stores the overall loan application assessment, including credit score,
    risk level, and final decision.
    """
    __tablename__ = "LoanAssessment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Loan officer (user who created assessment)
    userId = Column(UUID(as_uuid=True), ForeignKey("User.id"), nullable=False)

    # Applicant information
    applicantName = Column(String(255), nullable=False)
    businessName = Column(String(255), nullable=True)
    loanAmount = Column(Float, nullable=True)  # Requested loan amount

    # Assessment results
    creditScore = Column(Float, nullable=True)  # 300-850 scale
    riskLevel = Column(String(20), nullable=True)  # low, medium, high, critical
    defaultProbability = Column(Float, nullable=True)  # 0-1
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected, manual_review

    # Decision
    recommendation = Column(String(50), nullable=True)  # approve, decline, manual_review
    decisionReason = Column(Text, nullable=True)  # Explanation for decision
    approvedAmount = Column(Float, nullable=True)  # Approved loan amount (may differ from requested)
    interestRate = Column(Float, nullable=True)  # Approved interest rate
    loanTermMonths = Column(Integer, nullable=True)  # Loan term in months

    # Financial metrics (JSONB for flexibility)
    financialRatios = Column(JSONB, nullable=True)  # {debt_to_equity, current_ratio, etc.}
    shapExplanations = Column(JSONB, nullable=True)  # SHAP feature importance
    counterfactuals = Column(JSONB, nullable=True)  # Counterfactual improvement paths
    fairnessCheckResults = Column(JSONB, nullable=True)  # Fairness validation results

    # Context and metadata
    lastContext = Column(JSONB, nullable=True)  # Conversation context
    visibility = Column(String(10), nullable=False, default="private")  # public, private

    # Relationships
    documents = relationship("FinancialDocument", back_populates="assessment", cascade="all, delete-orphan")
    interactions = relationship("AssessmentInteraction", back_populates="assessment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<LoanAssessment(id={self.id}, applicant={self.applicantName}, status={self.status})>"


class FinancialDocument(Base):
    """
    Financial documents uploaded for loan assessment.

    Stores metadata and extracted data from balance sheets, P&L statements,
    bank statements, etc.
    """
    __tablename__ = "FinancialDocument"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessmentId = Column(UUID(as_uuid=True), ForeignKey("LoanAssessment.id"), nullable=False)

    # Document metadata
    documentType = Column(String(50), nullable=False)  # balance_sheet, income_statement, cash_flow, bank_statement
    fileName = Column(String(255), nullable=False)
    filePath = Column(Text, nullable=False)  # S3 path or local filesystem path
    fileSize = Column(Integer, nullable=True)  # File size in bytes
    mimeType = Column(String(100), nullable=True)  # application/pdf, application/vnd.ms-excel, etc.

    # Extracted data
    extractedData = Column(JSONB, nullable=True)  # Parsed financial data
    fiscalYear = Column(String(10), nullable=True)  # e.g., "2024"
    extractionConfidence = Column(Float, nullable=True)  # 0-1 confidence score

    # Timestamps
    uploadedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    processedAt = Column(DateTime, nullable=True)  # When extraction completed

    # Relationships
    assessment = relationship("LoanAssessment", back_populates="documents")

    def __repr__(self):
        return f"<FinancialDocument(id={self.id}, type={self.documentType}, file={self.fileName})>"


class AssessmentInteraction(Base):
    """
    Interaction messages during loan assessment (replaces Message).

    Stores conversation history between loan officer and AI agent.
    """
    __tablename__ = "AssessmentInteraction"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessmentId = Column(UUID(as_uuid=True), ForeignKey("LoanAssessment.id"), nullable=False)

    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    parts = Column(JSONB, nullable=False)  # Array of message parts (text, tool_call, tool_result)
    attachments = Column(JSONB, nullable=True)  # Array of attachments

    # Metadata
    provider = Column(String(20), nullable=True)  # Model provider (anthropic, openai, google)
    toolsUsed = Column(JSONB, nullable=True)  # List of tools invoked in this interaction

    # Timestamps
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    assessment = relationship("LoanAssessment", back_populates="interactions")

    def __repr__(self):
        return f"<AssessmentInteraction(id={self.id}, assessmentId={self.assessmentId}, role={self.role})>"
