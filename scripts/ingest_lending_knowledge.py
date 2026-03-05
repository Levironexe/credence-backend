"""
Knowledge Base Ingestion Script

Populates the pgvector database with lending regulations and policies.
Run this once to set up the RAG knowledge base.

Usage:
    python scripts/ingest_lending_knowledge.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from app.services.rag_service import rag_service
from app.config import get_settings

settings = get_settings()


# Sample lending knowledge (production would load from files/APIs)
LENDING_KNOWLEDGE = [
    {
        "content": """
Basel III Capital Requirements for SME Lending

Under Basel III, banks must maintain minimum capital ratios when extending credit to SMEs:
- Common Equity Tier 1 (CET1) ratio: 4.5%
- Tier 1 capital ratio: 6%
- Total capital ratio: 8%
- Capital conservation buffer: 2.5%

For SME exposures under €1 million, banks may apply a reduced risk weight of 75% instead of 100%.
This regulatory capital relief incentivizes lending to small businesses.

SME loans with strong collateral (real estate, equipment) may qualify for lower risk weights
under the standardized approach, reducing capital requirements.
""",
        "metadata": {
            "source": "Basel III",
            "title": "SME Capital Requirements",
            "category": "regulation",
            "jurisdiction": "international"
        }
    },
    {
        "content": """
Fair Credit Reporting Act (FCRA) - Credit Decision Disclosure

When denying credit or offering less favorable terms based on credit reports:

1. Adverse Action Notice: Must provide written notice within 30 days
2. Credit Bureau Information: Name, address, phone of reporting agency
3. Right to Dispute: Inform applicant of right to obtain free credit report
4. Specific Reasons: List specific reasons for denial (e.g., "debt-to-income ratio too high")

For automated decisions (including AI/ML models):
- Must still provide specific reasons, not generic explanations
- "Credit score too low" is insufficient - must cite factors affecting score
- Applicants have right to know which factors most influenced decision

FCRA Section 615(a) applies to all creditors, including fintech lenders using alternative data.
""",
        "metadata": {
            "source": "FCRA",
            "title": "Adverse Action Requirements",
            "category": "regulation",
            "jurisdiction": "united_states"
        }
    },
    {
        "content": """
Equal Credit Opportunity Act (ECOA) - Prohibited Basis

Creditors cannot discriminate based on:
- Race or color
- Religion
- National origin
- Sex (including gender identity and sexual orientation)
- Marital status
- Age (except to determine if applicant can enter binding contract)
- Receipt of public assistance

Applies to all credit decisions: approval, terms, conditions, interest rates.

For AI/ML credit models:
- Must validate model doesn't have disparate impact on protected classes
- Cannot use proxy variables that correlate with prohibited basis
- Required to monitor outcomes by demographic group
- Counterfactual fairness: Changing protected attributes shouldn't change decision

Penalties: Up to $10,000 per violation + punitive damages.
""",
        "metadata": {
            "source": "ECOA",
            "title": "Anti-Discrimination Requirements",
            "category": "regulation",
            "jurisdiction": "united_states"
        }
    },
    {
        "content": """
Dodd-Frank Act - Ability-to-Repay Requirements

Creditors must make reasonable determination that borrower can repay the loan.

Minimum verification requirements:
1. Current or reasonably expected income/assets
2. Current employment status
3. Monthly debt obligations
4. Debt-to-income ratio (DTI)
5. Credit history

For SME loans:
- Review business revenue (12-24 months recommended)
- Analyze cash flow statements
- Consider seasonal fluctuations
- Evaluate industry-specific risks
- Review owner's personal credit history

"Ability to repay" means borrower can meet loan obligations while maintaining reasonable
living expenses and existing debt payments.

Failure to properly assess ability to repay may result in loan being deemed "unenforceable"
and creditor liable for damages.
""",
        "metadata": {
            "source": "Dodd-Frank Act",
            "title": "Ability-to-Repay Rule",
            "category": "regulation",
            "jurisdiction": "united_states"
        }
    },
    {
        "content": """
SME Lending Best Practices - Financial Ratio Analysis

Key financial ratios for SME creditworthiness:

Liquidity Ratios:
- Current Ratio = Current Assets / Current Liabilities
  * Healthy: > 1.5
  * Warning: < 1.0
- Quick Ratio = (Current Assets - Inventory) / Current Liabilities
  * Healthy: > 1.0

Leverage Ratios:
- Debt-to-Equity = Total Debt / Shareholders' Equity
  * Low risk: < 1.0
  * Medium risk: 1.0-2.0
  * High risk: > 2.0
- Debt Service Coverage Ratio (DSCR) = Operating Income / Debt Payments
  * Strong: > 1.5
  * Minimum: > 1.25

Profitability Ratios:
- Gross Profit Margin = (Revenue - COGS) / Revenue
  * Healthy: > 30%
- Net Profit Margin = Net Income / Revenue
  * Healthy: > 10%
- Return on Equity (ROE) = Net Income / Shareholders' Equity
  * Excellent: > 20%
  * Good: 15-20%

Industry benchmarks vary significantly - compare applicant to industry averages.
""",
        "metadata": {
            "source": "Lending Best Practices",
            "title": "Financial Ratio Guidelines",
            "category": "best_practice",
            "jurisdiction": "general"
        }
    },
    {
        "content": """
SME Default Risk Factors

Primary indicators of elevated default risk:

Financial Red Flags:
- Declining revenue (>15% YoY decline)
- Negative cash flow for 3+ consecutive months
- Current ratio < 1.0
- Debt-to-equity > 2.5
- Missing financial statements or incomplete records
- Frequent overdrafts

Business Red Flags:
- Less than 12 months in operation (startup risk)
- Frequent address changes
- Industry in decline (e.g., retail during e-commerce disruption)
- Heavy customer concentration (>50% revenue from single customer)
- Legal disputes or liens
- Changes in ownership/management

Alternative Data Signals:
- Declining transaction volume (if merchant data available)
- Negative online reviews trend
- Decreased social media engagement
- Website traffic decline

Positive Mitigating Factors:
- Strong personal guarantee from creditworthy owner
- High-quality collateral (equipment, real estate)
- Long-term contracts with stable customers
- Proven recession resilience in previous downturns

Risk mitigation strategies:
- Require monthly financial reporting for high-risk borrowers
- Implement financial covenants (minimum DSCR, maximum DTI)
- Shorter loan terms to reduce exposure
""",
        "metadata": {
            "source": "Risk Management",
            "title": "SME Default Risk Indicators",
            "category": "risk_assessment",
            "jurisdiction": "general"
        }
    },
    {
        "content": """
Alternative Data for Credit Assessment

Non-traditional data sources for SME credit evaluation:

Merchant Services Data:
- Transaction volume and frequency
- Average transaction size
- Chargebacks and refunds
- Seasonal patterns
- Payment processing velocity

Accounting Software Data:
- Real-time cash flow
- Accounts receivable aging
- Inventory turnover
- Expense categorization
- Invoice payment timing

Utility and Rent Payments:
- Payment history (on-time vs. late)
- Can improve credit scores by 10-30 points for thin-file applicants

Digital Footprint:
- Website traffic and engagement
- Social media presence
- Online reviews and ratings
- App store ratings (if applicable)

Regulatory Considerations:
- Must obtain applicant consent for alternative data usage
- Data must be verifiable and reliable
- Cannot use data that creates disparate impact on protected classes
- Must provide adverse action explanations if alternative data influences decision

Alternative data most valuable for:
- Startups with limited credit history
- Businesses in cash-heavy industries
- Immigrant-owned businesses
- Applicants with thin credit files
""",
        "metadata": {
            "source": "Alternative Credit Data",
            "title": "Non-Traditional Data Sources",
            "category": "assessment_methodology",
            "jurisdiction": "general"
        }
    },
    {
        "content": """
Credit Score Interpretation for SME Lending

FICO Score Bands and Loan Terms:

Exceptional (800-850):
- Auto-approve for most loan amounts
- Best interest rates (Prime - 1% to Prime)
- Minimal documentation required
- Default probability: 0.5-2%

Very Good (740-799):
- Standard approval
- Competitive rates (Prime to Prime + 2%)
- Standard documentation
- Default probability: 2-5%

Good (670-739):
- Approval with review
- Moderate rates (Prime + 2% to Prime + 4%)
- Full documentation required
- Default probability: 5-10%

Fair (580-669):
- Manual review required
- Higher rates (Prime + 4% to Prime + 8%)
- May require collateral or personal guarantee
- Default probability: 10-20%

Poor (300-579):
- Likely decline or require significant mitigation
- Maximum rates if approved
- Strong collateral and personal guarantee required
- Default probability: 20-40%

Important: Credit score is only one factor. Must also consider:
- Business tenure (prefer 2+ years)
- Industry risk
- Loan-to-revenue ratio
- Debt service coverage ratio
- Collateral quality

For AI/ML models: Validate score bands align with observed default rates in your portfolio.
Recalibrate annually based on performance data.
""",
        "metadata": {
            "source": "Credit Scoring Guidelines",
            "title": "Score Band Interpretation",
            "category": "assessment_methodology",
            "jurisdiction": "general"
        }
    }
]


async def ingest_knowledge():
    """Ingest lending knowledge into pgvector."""
    print("Starting knowledge base ingestion...")

    # Initialize RAG service
    await rag_service.initialize()
    print("✓ RAG service initialized")

    # Create text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    # Process and split documents
    all_chunks = []
    for item in LENDING_KNOWLEDGE:
        # Split content into chunks
        chunks = text_splitter.split_text(item["content"])

        # Create Document objects
        for i, chunk in enumerate(chunks):
            metadata = item["metadata"].copy()
            metadata["chunk_index"] = i
            metadata["total_chunks"] = len(chunks)

            doc = Document(
                page_content=chunk.strip(),
                metadata=metadata
            )
            all_chunks.append(doc)

    print(f"✓ Created {len(all_chunks)} document chunks from {len(LENDING_KNOWLEDGE)} sources")

    # Add to vector store
    try:
        ids = await rag_service.add_documents(all_chunks)
        print(f"✓ Successfully ingested {len(ids)} chunks into pgvector")

        # Test retrieval
        test_query = "What are the capital requirements for SME lending?"
        docs = await rag_service.retrieve(test_query, k=3)
        print(f"\n✓ Test retrieval successful - found {len(docs)} relevant documents")
        print(f"  Query: '{test_query}'")
        if docs:
            print(f"  Top result: {docs[0].metadata.get('title')} ({docs[0].metadata.get('source')})")

        print("\n✅ Knowledge base ingestion complete!")
        print(f"\nKnowledge base contents:")
        print(f"  - Basel III capital requirements")
        print(f"  - FCRA adverse action rules")
        print(f"  - ECOA anti-discrimination requirements")
        print(f"  - Dodd-Frank ability-to-repay rules")
        print(f"  - Financial ratio best practices")
        print(f"  - Default risk indicators")
        print(f"  - Alternative data guidelines")
        print(f"  - Credit score interpretation")

    except Exception as e:
        print(f"❌ Ingestion failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(ingest_knowledge())
