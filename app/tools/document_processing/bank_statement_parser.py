"""
Bank Statement Parser Tool

Parses extracted bank statement text (Vietnamese or English) and maps
financial data to Home Credit model features.
"""

import re
import logging
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class BankStatementParserInput(BaseModel):
    """Input: raw text extracted from a bank statement PDF."""
    statement_text: str = Field(
        description="Raw text content extracted from a bank statement PDF"
    )
    loan_amount: float = Field(
        default=0.0,
        description="Requested loan amount (if known from conversation)"
    )


class BankStatementParser(BaseTool):
    """
    Parse bank statement text and extract financial features for credit scoring.

    Supports Vietnamese bank formats (Vietcombank, BIDV, Techcombank) and
    English-language statements. Extracts salary/income patterns, recurring
    payments, and balance information, then maps them to Home Credit features.
    """

    @property
    def name(self) -> str:
        return "bank_statement_parser"

    @property
    def description(self) -> str:
        return (
            "Parse bank statement text to extract financial data and map to credit scoring features. "
            "Detects salary deposits, recurring loan payments, and balance information. "
            "Returns extracted Home Credit features ready for the credit scoring model."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return BankStatementParserInput

    async def execute(self, statement_text: str = None, loan_amount: float = 0.0, **kwargs) -> Dict[str, Any]:
        if statement_text is None:
            statement_text = kwargs.get("statement_text", "")

        if not statement_text:
            return {"success": False, "error": "statement_text is required"}

        loan_amount = loan_amount or kwargs.get("loan_amount", 0.0)

        try:
            # Extract all financial data
            credits = self._extract_credits(statement_text)
            debits = self._extract_debits(statement_text)
            balances = self._extract_balances(statement_text)
            period = self._extract_period(statement_text)

            # Detect salary (recurring similar-amount credits)
            monthly_income = self._detect_salary(credits)

            # Detect loan payments (recurring equal debits)
            monthly_payment = self._detect_recurring_payments(debits)

            # Build Home Credit features
            features = {}
            summary_parts = []

            if monthly_income > 0:
                # AMT_INCOME_TOTAL is annual in the dataset
                features["AMT_INCOME_TOTAL"] = monthly_income * 12
                summary_parts.append(f"Monthly income: {monthly_income:,.0f}")

            if loan_amount > 0:
                features["AMT_CREDIT"] = loan_amount
                summary_parts.append(f"Loan amount: {loan_amount:,.0f}")

            if monthly_payment > 0:
                features["AMT_ANNUITY"] = monthly_payment
                summary_parts.append(f"Monthly payment: {monthly_payment:,.0f}")

            # Estimate employment from salary pattern
            if monthly_income > 0 and period:
                months_of_data = period.get("months", 3)
                # Conservative estimate: at least as long as statement period
                est_employment_years = max(months_of_data / 12, 1.0)
                features["DAYS_EMPLOYED"] = -est_employment_years * 365.25
                summary_parts.append(f"Est. employment: {est_employment_years:.1f}+ years")

            # Balance indicators
            if balances:
                avg_balance = sum(balances) / len(balances)
                summary_parts.append(f"Avg balance: {avg_balance:,.0f}")

            # Compute derived ratios
            if "AMT_CREDIT" in features and "AMT_INCOME_TOTAL" in features:
                features["credit_income_ratio"] = features["AMT_CREDIT"] / (features["AMT_INCOME_TOTAL"] + 1)
            if "AMT_ANNUITY" in features and "AMT_INCOME_TOTAL" in features:
                features["annuity_income_ratio"] = features["AMT_ANNUITY"] / (features["AMT_INCOME_TOTAL"] + 1)

            # Transaction activity stats
            total_credits = len(credits)
            total_debits = len(debits)
            summary_parts.append(f"Transactions: {total_credits} credits, {total_debits} debits")

            summary = "; ".join(summary_parts) if summary_parts else "No financial data extracted"

            logger.info(f"Parsed bank statement: {len(features)} features extracted")

            return {
                "success": True,
                "extracted_features": features,
                "features_count": len(features),
                "summary": summary,
                "details": {
                    "monthly_income": monthly_income,
                    "monthly_payment": monthly_payment,
                    "total_credits": total_credits,
                    "total_debits": total_debits,
                    "balances_found": len(balances),
                },
                "message": f"Extracted {len(features)} features from bank statement. {summary}"
            }

        except Exception as e:
            logger.error(f"Bank statement parsing failed: {e}")
            return {"success": False, "error": f"Parsing failed: {str(e)}"}

    def _extract_amounts(self, text: str, pattern: str) -> List[float]:
        """Extract monetary amounts matching a pattern."""
        amounts = []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                amount_str = match.group(1).replace(",", "").replace(".", "").strip()
                if amount_str:
                    amount = float(amount_str)
                    if amount > 0:
                        amounts.append(amount)
            except (ValueError, IndexError):
                continue
        return amounts

    def _extract_credits(self, text: str) -> List[float]:
        """Extract credit (deposit) amounts from statement text."""
        credits = []
        # Look for credit column amounts (Vietnamese: Ghi co)
        patterns = [
            r'(?:credit|ghi\s*c[oó]|deposit)[:\s]+([\d,\.]+)',
            # Table row pattern: amount in credit column (positive numbers after description)
            r'\d{2}[/-]\d{2}[/-]\d{2,4}\s+.*?\s+([\d,\.]+)\s*$',
        ]
        for pattern in patterns:
            credits.extend(self._extract_amounts(text, pattern))

        # Also try to find amounts in lines containing salary keywords
        for line in text.split("\n"):
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["salary", "luong", "lương", "wage", "payroll"]):
                amounts = re.findall(r'([\d,\.]{4,})', line)
                for amt_str in amounts:
                    try:
                        amt = float(amt_str.replace(",", "").replace(".", ""))
                        if amt > 100:  # Filter trivial amounts
                            credits.append(amt)
                    except ValueError:
                        continue

        return credits

    def _extract_debits(self, text: str) -> List[float]:
        """Extract debit (withdrawal) amounts from statement text."""
        debits = []
        patterns = [
            r'(?:debit|ghi\s*n[oợ]|withdrawal)[:\s]+([\d,\.]+)',
        ]
        for pattern in patterns:
            debits.extend(self._extract_amounts(text, pattern))

        # Look for recurring payment keywords
        for line in text.split("\n"):
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["payment", "tra no", "trả nợ", "installment", "repay"]):
                amounts = re.findall(r'([\d,\.]{4,})', line)
                for amt_str in amounts:
                    try:
                        amt = float(amt_str.replace(",", "").replace(".", ""))
                        if amt > 100:
                            debits.append(amt)
                    except ValueError:
                        continue

        return debits

    def _extract_balances(self, text: str) -> List[float]:
        """Extract balance amounts from statement text."""
        balances = []
        patterns = [
            r'(?:balance|so\s*du|số\s*dư|opening|closing|dau\s*ky|cuoi\s*ky)[:\s]+([\d,\.]+)',
        ]
        for pattern in patterns:
            balances.extend(self._extract_amounts(text, pattern))
        return balances

    def _extract_period(self, text: str) -> Dict[str, Any]:
        """Extract statement period dates."""
        # Look for date ranges
        date_pattern = r'(\d{2}[/-]\d{2}[/-]\d{2,4})\s*[-–to]+\s*(\d{2}[/-]\d{2}[/-]\d{2,4})'
        match = re.search(date_pattern, text)
        if match:
            return {"start": match.group(1), "end": match.group(2), "months": 3}  # default estimate

        # Look for month/year patterns
        month_pattern = r'(?:thang|tháng|month)\s*(\d{1,2})[/-](\d{2,4})'
        months_found = re.findall(month_pattern, text, re.IGNORECASE)
        if months_found:
            return {"months": len(months_found) or 3}

        return {"months": 3}  # default

    def _detect_salary(self, credits: List[float]) -> float:
        """Detect salary pattern from credits — recurring similar amounts."""
        if len(credits) < 2:
            return sum(credits) / max(len(credits), 1)

        # Group similar amounts (within 10% tolerance)
        groups: List[List[float]] = []
        for amount in sorted(credits, reverse=True):
            placed = False
            for group in groups:
                if abs(amount - group[0]) / (group[0] + 1) < 0.10:
                    group.append(amount)
                    placed = True
                    break
            if not placed:
                groups.append([amount])

        # Find the largest recurring group (2+ occurrences)
        recurring = [g for g in groups if len(g) >= 2]
        if recurring:
            largest_recurring = max(recurring, key=lambda g: sum(g) / len(g))
            return sum(largest_recurring) / len(largest_recurring)

        # Fallback: average of all credits
        return sum(credits) / len(credits)

    def _detect_recurring_payments(self, debits: List[float]) -> float:
        """Detect recurring payment pattern from debits — equal amounts."""
        if len(debits) < 2:
            return 0.0

        # Group identical or near-identical amounts
        groups: List[List[float]] = []
        for amount in sorted(debits, reverse=True):
            placed = False
            for group in groups:
                if abs(amount - group[0]) / (group[0] + 1) < 0.05:
                    group.append(amount)
                    placed = True
                    break
            if not placed:
                groups.append([amount])

        # Find recurring groups (2+ occurrences)
        recurring = [g for g in groups if len(g) >= 2]
        if recurring:
            # Return the most likely loan payment (largest recurring)
            largest_recurring = max(recurring, key=lambda g: sum(g) / len(g))
            return sum(largest_recurring) / len(largest_recurring)

        return 0.0


# Singleton
bank_statement_parser = BankStatementParser()
