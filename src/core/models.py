"""Pydantic models for expense data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Tuple, Any, List
from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass
import json


class ExtractedExpense(BaseModel):
    """Data extracted from receipt by LLM."""

    provider: str = Field(..., description="Provider name")
    provider_address: str = Field(..., description="Provider address")
    date_of_service: date = Field(..., description="Date of service")
    amount_to_claim: Decimal = Field(..., description="Amount paid by patient (not insurance)", gt=0)

    @field_validator('amount_to_claim', mode='before')
    @classmethod
    def parse_amount(cls, v):
        """Parse amount from various formats, cleaning currency symbols."""
        import re

        if isinstance(v, (int, float)):
            return Decimal(str(v))

        if isinstance(v, Decimal):
            return v

        if isinstance(v, str):
            original = v
            # Remove common currency symbols
            v = v.strip()
            v = re.sub(r'[$€£¥₹¢]', '', v)
            # Remove currency codes like USD, EUR, etc.
            v = re.sub(r'\b[A-Z]{3}\b', '', v)
            # Remove commas used as thousands separators
            v = v.replace(',', '')
            # Remove whitespace
            v = v.strip()

            # If nothing left, raise error with original value
            if not v:
                raise ValueError(f"Amount field is empty or contains only currency symbols: '{original}'")

            # Check if it contains non-numeric characters (except decimal point and minus)
            if re.search(r'[^\d.\-]', v):
                raise ValueError(f"Amount contains invalid characters: '{original}' (cleaned: '{v}')")

            try:
                return Decimal(v)
            except Exception as e:
                raise ValueError(f"Cannot convert amount to decimal: '{original}' (cleaned: '{v}'). Error: {e}")

        raise ValueError(f"Amount must be a number or string, got {type(v)}: {v}")


class ExpenseRecord(BaseModel):
    """Full record stored in CSV."""

    provider: str
    provider_address: str
    date_of_service: date
    file_name: str = Field(..., description="Original PDF filename (unique key)")
    amount_to_claim: Decimal
    claimed: bool = False
    processing_timestamp: datetime
    claim_timestamp: Optional[datetime] = None
    claim_confirmation_id: Optional[str] = None
    error_history: str = Field(default="[]", description="JSON-encoded list of errors")

    @classmethod
    def from_extracted(cls, extracted: ExtractedExpense, file_name: str) -> "ExpenseRecord":
        """Create ExpenseRecord from ExtractedExpense.

        Args:
            extracted: Extracted expense data
            file_name: Original PDF filename

        Returns:
            ExpenseRecord instance
        """
        return cls(
            provider=extracted.provider,
            provider_address=extracted.provider_address,
            date_of_service=extracted.date_of_service,
            file_name=file_name,
            amount_to_claim=extracted.amount_to_claim,
            processing_timestamp=datetime.now(),
        )

    def add_error(self, error: str) -> None:
        """Add an error to the error history.

        Args:
            error: Error message to add
        """
        errors = json.loads(self.error_history)
        errors.append({
            "timestamp": datetime.now().isoformat(),
            "error": error
        })
        self.error_history = json.dumps(errors)

    def to_csv_dict(self) -> dict:
        """Convert to dictionary for CSV writing.

        Returns:
            Dictionary with CSV-compatible values
        """
        return {
            "provider": self.provider,
            "provider_address": self.provider_address,
            "date_of_service": self.date_of_service.isoformat(),
            "file_name": self.file_name,
            "amount_to_claim": str(self.amount_to_claim),
            "claimed": str(self.claimed),
            "processing_timestamp": self.processing_timestamp.isoformat(),
            "claim_timestamp": self.claim_timestamp.isoformat() if self.claim_timestamp else "",
            "claim_confirmation_id": self.claim_confirmation_id or "",
            "error_history": self.error_history,
        }


@dataclass
class ValidationResult:
    """Result of validating a single receipt."""
    file_name: str
    passed: bool
    original: ExpenseRecord
    verified: ExtractedExpense
    mismatches: Dict[str, Tuple[Any, Any]]  # field_name -> (original_value, verified_value)
    error: Optional[str] = None  # Set if extraction failed


@dataclass
class ValidationSummary:
    """Summary of validation run."""
    total: int
    validated: int
    passed: int
    failed: int
    skipped: int  # Missing PDFs
    results: List[ValidationResult]
