"""Receipt validation using verification model."""

import re
from decimal import Decimal
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import click
from src.core.csv_manager import CSVManager
from src.core.models import ExpenseRecord, ExtractedExpense, ValidationResult, ValidationSummary
from src.core.signal_handler import GracefulShutdown
from src.processors.llm_extractor import ReceiptExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReceiptValidator:
    """Validate existing expense records using verification model."""

    def __init__(
        self,
        receipts_folder: Path,
        csv_manager: CSVManager,
        verification_extractor: ReceiptExtractor,
    ):
        """Initialize the receipt validator.

        Args:
            receipts_folder: Path to folder containing receipt PDFs
            csv_manager: CSV manager instance
            verification_extractor: LLM extractor using verification model
        """
        self.receipts_folder = receipts_folder
        self.csv_manager = csv_manager
        self.verification_extractor = verification_extractor

    def _normalize_address(self, address: str) -> str:
        """Normalize address for comparison.

        Args:
            address: Address string

        Returns:
            Normalized address with single spaces
        """
        # Strip leading/trailing whitespace and normalize internal whitespace
        normalized = re.sub(r'\s+', ' ', address.strip())
        return normalized

    def _compare_expenses(
        self,
        original: ExpenseRecord,
        verified: ExtractedExpense
    ) -> Dict[str, Tuple[Any, Any]]:
        """Compare extracted fields and return mismatches.

        Args:
            original: Original expense record from CSV
            verified: Newly extracted expense from verification model

        Returns:
            Dictionary of mismatches: field_name -> (original_value, verified_value)
        """
        mismatches = {}

        # Compare provider (case-insensitive)
        if original.provider.lower() != verified.provider.lower():
            mismatches['provider'] = (original.provider, verified.provider)

        # Compare provider_address (normalized whitespace)
        original_addr = self._normalize_address(original.provider_address)
        verified_addr = self._normalize_address(verified.provider_address)
        if original_addr != verified_addr:
            mismatches['provider_address'] = (original.provider_address, verified.provider_address)

        # Compare date_of_service (exact date match)
        if original.date_of_service != verified.date_of_service:
            mismatches['date_of_service'] = (original.date_of_service, verified.date_of_service)

        # Compare amount_to_claim (rounded to 2 decimal places)
        original_amount = original.amount_to_claim.quantize(Decimal('0.01'))
        verified_amount = verified.amount_to_claim.quantize(Decimal('0.01'))
        if original_amount != verified_amount:
            mismatches['amount_to_claim'] = (original_amount, verified_amount)

        return mismatches

    async def validate_single_receipt(
        self,
        pdf_path: Path,
        original_record: ExpenseRecord
    ) -> ValidationResult:
        """Validate a single receipt against its CSV record.

        Args:
            pdf_path: Path to receipt PDF
            original_record: Original expense record from CSV

        Returns:
            ValidationResult with comparison details
        """
        try:
            # Re-extract using verification model
            logger.info(
                "Validating receipt",
                file_name=original_record.file_name,
                pdf_path=str(pdf_path),
            )

            verified_expense = await self.verification_extractor.extract_expense(
                pdf_path,
                original_record.file_name
            )

            # Compare fields
            mismatches = self._compare_expenses(original_record, verified_expense)

            passed = len(mismatches) == 0

            logger.info(
                "Validation complete",
                file_name=original_record.file_name,
                passed=passed,
                mismatch_count=len(mismatches),
            )

            return ValidationResult(
                file_name=original_record.file_name,
                passed=passed,
                original=original_record,
                verified=verified_expense,
                mismatches=mismatches,
                error=None,
            )

        except Exception as e:
            error_msg = f"Extraction failed: {str(e)}"
            logger.error(
                "Validation extraction failed",
                file_name=original_record.file_name,
                error=error_msg,
                exc_info=True,
            )

            return ValidationResult(
                file_name=original_record.file_name,
                passed=False,
                original=original_record,
                verified=None,
                mismatches={},
                error=error_msg,
            )

    async def validate_receipts(
        self,
        target_files: Optional[List[str]] = None
    ) -> ValidationSummary:
        """Validate multiple receipts.

        Args:
            target_files: List of file names to validate, or None to validate all

        Returns:
            ValidationSummary with all validation results
        """
        # Load all expenses from CSV
        all_expenses = self.csv_manager.load_expenses()

        # Filter by target_files if provided
        if target_files:
            expenses_to_validate = [e for e in all_expenses if e.file_name in target_files]
        else:
            expenses_to_validate = all_expenses

        total = len(expenses_to_validate)
        click.echo(f"Validating {total} expenses from CSV...\n")

        results = []
        validated_count = 0
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        for idx, expense in enumerate(expenses_to_validate, 1):
            # Check for graceful shutdown
            if GracefulShutdown.should_shutdown():
                logger.info("Graceful shutdown requested, stopping validation")
                click.echo("\n\nShutdown requested. Stopping validation...")
                break

            # Check if PDF exists
            pdf_path = self.receipts_folder / expense.file_name

            # Progress indicator
            click.echo(f"[{idx}/{total}] Validating {expense.file_name}...")

            if not pdf_path.exists():
                # PDF file missing
                logger.warning(
                    "PDF file not found, skipping validation",
                    file_name=expense.file_name,
                    pdf_path=str(pdf_path),
                )
                click.echo(f"⚠️  Skipped - PDF file not found\n")
                skipped_count += 1

                # Create a result for skipped file
                result = ValidationResult(
                    file_name=expense.file_name,
                    passed=False,
                    original=expense,
                    verified=None,
                    mismatches={},
                    error="PDF file not found",
                )
                results.append(result)
                continue

            # Validate the receipt
            result = await self.validate_single_receipt(pdf_path, expense)
            results.append(result)
            validated_count += 1

            if result.error:
                # Extraction failed
                click.echo(f"⚠️  Extraction failed - see logs\n")
                failed_count += 1
            elif result.passed:
                # Validation passed
                click.echo(f"✓ Passed\n")
                passed_count += 1
            else:
                # Validation failed (mismatches)
                mismatch_count = len(result.mismatches)
                click.echo(f"❌ Failed - {mismatch_count} mismatch(es)\n")
                failed_count += 1

        return ValidationSummary(
            total=total,
            validated=validated_count,
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            results=results,
        )

    def _format_summary(self, summary: ValidationSummary) -> str:
        """Format validation summary for display.

        Args:
            summary: ValidationSummary to format

        Returns:
            Formatted summary string
        """
        lines = []

        # Summary statistics
        lines.append("=" * 60)
        lines.append("Validation Summary")
        lines.append("=" * 60)
        lines.append(f"Total expenses: {summary.total}")
        lines.append(f"Validated: {summary.validated}")
        lines.append(f"Passed: {summary.passed}")
        lines.append(f"Failed: {summary.failed}")
        lines.append(f"Skipped (missing PDFs): {summary.skipped}")
        lines.append("")

        # If there are failures, show details
        failed_results = [r for r in summary.results if not r.passed]

        if failed_results:
            lines.append("=" * 60)
            lines.append(f"FAILED VALIDATIONS ({len(failed_results)})")
            lines.append("=" * 60)
            lines.append("")

            for idx, result in enumerate(failed_results, 1):
                lines.append(f"{idx}. File: {result.file_name}")

                if result.error:
                    # Extraction error
                    lines.append(f"   Error: {result.error}")
                else:
                    # Field mismatches
                    lines.append("   Mismatches:")
                    for field_name, (original_val, verified_val) in result.mismatches.items():
                        lines.append(f"   • {field_name}:")
                        lines.append(f"     Original: {original_val}")
                        lines.append(f"     Verified: {verified_val}")

                lines.append("")

            lines.append("=" * 60)
        else:
            lines.append("All validations passed!")
            lines.append("=" * 60)

        return "\n".join(lines)
