"""Receipt verification using LLM semantic judgment."""

from pathlib import Path
from typing import Optional, List

import click
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent
from src.core.csv_manager import CSVManager
from src.core.models import ExpenseRecord, VerificationResult, VerificationSummary, VerificationResponse
from src.core.signal_handler import GracefulShutdown
from src.processors.llm_extractor import VERIFICATION_MODEL_NAME
from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_verification_prompt() -> str:
    """Load the verification prompt from file.

    Returns:
        Verification prompt template string
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / "receipt_verification.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


class ReceiptVerifier:
    """Verify existing expense records using LLM semantic judgment."""

    def __init__(
        self,
        receipts_folder: Path,
        csv_manager: CSVManager,
        model_name: str = VERIFICATION_MODEL_NAME,
    ):
        """Initialize the receipt verifier.

        Args:
            receipts_folder: Path to folder containing receipt PDFs
            csv_manager: CSV manager instance
            model_name: LLM model to use for verification (defaults to VERIFICATION_MODEL_NAME)
        """
        self.receipts_folder = receipts_folder
        self.csv_manager = csv_manager
        self.model_name = model_name
        self.verification_prompt_template = load_verification_prompt()

        # Create verification agent with VerificationResponse output type
        self.verification_agent = Agent(
            model_name,
            output_type=VerificationResponse,
            system_prompt="You are a medical receipt verification expert. Follow the instructions carefully.",
        )
        logger.info(f"Initialized receipt verifier with model: {model_name}")

    async def verify_single_receipt(
        self,
        pdf_path: Path,
        original_record: ExpenseRecord
    ) -> VerificationResult:
        """Verify a single receipt against its CSV record using LLM judgment.

        Sends both the PDF and the existing extraction to the LLM
        for semantic correctness judgment.

        Args:
            pdf_path: Path to receipt PDF
            original_record: Original expense record from CSV

        Returns:
            VerificationResult with LLM judgment
        """
        try:
            logger.info(
                "Verifying receipt",
                file_name=original_record.file_name,
                pdf_path=str(pdf_path),
            )

            # Read PDF bytes
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()

            # Format extracted data for prompt
            extracted_data_text = f"""Provider: {original_record.provider}
Provider Address: {original_record.provider_address}
Date of Service: {original_record.date_of_service.isoformat()}
Amount to Claim: ${original_record.amount_to_claim}"""

            # Format verification prompt with extracted data
            verification_prompt = self.verification_prompt_template.format(
                extracted_data=extracted_data_text
            )

            # Send to LLM: verification prompt + PDF
            result = await self.verification_agent.run(
                [
                    verification_prompt,
                    BinaryContent(data=pdf_bytes, media_type='application/pdf'),
                ],
                message_history=[]
            )

            verification_response = result.output  # VerificationResponse model

            passed = verification_response.overall_correct

            logger.info(
                "Verification complete",
                file_name=original_record.file_name,
                passed=passed,
                issue_count=len(verification_response.incorrect_fields),
            )

            return VerificationResult(
                file_name=original_record.file_name,
                passed=passed,
                original=original_record,
                verification_response=verification_response,
                error=None,
            )

        except Exception as e:
            error_msg = f"Verification failed: {str(e)}"
            logger.error(
                "Verification failed",
                file_name=original_record.file_name,
                error=error_msg,
                exc_info=True,
            )

            return VerificationResult(
                file_name=original_record.file_name,
                passed=False,
                original=original_record,
                verification_response=None,
                error=error_msg,
            )

    async def verify_receipts(
        self,
        target_files: Optional[List[str]] = None
    ) -> VerificationSummary:
        """Verify multiple receipts.

        Args:
            target_files: List of file names to verify, or None to verify all

        Returns:
            VerificationSummary with all verification results
        """
        # Load all expenses from CSV
        all_expenses = self.csv_manager.load_expenses()

        # Filter by target_files if provided
        if target_files:
            expenses_to_verify = [e for e in all_expenses if e.file_name in target_files]
        else:
            expenses_to_verify = all_expenses

        total = len(expenses_to_verify)
        click.echo(f"Verifying {total} expenses from CSV...\n")

        results = []
        verified_count = 0
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        for idx, expense in enumerate(expenses_to_verify, 1):
            # Check for graceful shutdown
            if GracefulShutdown.should_shutdown():
                logger.info("Graceful shutdown requested, stopping verification")
                click.echo("\n\nShutdown requested. Stopping verification...")
                break

            # Check if PDF exists
            pdf_path = self.receipts_folder / expense.file_name

            # Progress indicator
            click.echo(f"[{idx}/{total}] Verifying {expense.file_name}...")

            if not pdf_path.exists():
                # PDF file missing
                logger.warning(
                    "PDF file not found, skipping verification",
                    file_name=expense.file_name,
                    pdf_path=str(pdf_path),
                )
                click.echo(f"⚠️  Skipped - PDF file not found\n")
                skipped_count += 1

                # Create a result for skipped file
                result = VerificationResult(
                    file_name=expense.file_name,
                    passed=False,
                    original=expense,
                    verification_response=None,
                    error="PDF file not found",
                )
                results.append(result)
                continue

            # Verify the receipt
            result = await self.verify_single_receipt(pdf_path, expense)
            results.append(result)
            verified_count += 1

            if result.error:
                # Verification system error
                click.echo(f"⚠️  Verification error - see logs\n")
                failed_count += 1
            elif result.passed:
                # Verification passed
                click.echo(f"✓ Passed\n")
                passed_count += 1
            else:
                # Verification failed (incorrect fields)
                issue_count = len(result.verification_response.incorrect_fields)
                click.echo(f"❌ Failed - {issue_count} incorrect field(s)\n")
                failed_count += 1

        return VerificationSummary(
            total=total,
            verified=verified_count,
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            results=results,
        )

    def _format_summary(self, summary: VerificationSummary) -> str:
        """Format verification summary for display.

        Args:
            summary: VerificationSummary to format

        Returns:
            Formatted summary string
        """
        lines = []

        # Summary statistics
        lines.append("=" * 60)
        lines.append("Verification Summary")
        lines.append("=" * 60)
        lines.append(f"Total expenses: {summary.total}")
        lines.append(f"Verified: {summary.verified}")
        lines.append(f"Passed: {summary.passed}")
        lines.append(f"Failed: {summary.failed}")
        lines.append(f"Skipped (missing PDFs): {summary.skipped}")
        lines.append("")

        # Show failed verifications
        failed_results = [r for r in summary.results if not r.passed]

        if failed_results:
            lines.append("=" * 60)
            lines.append(f"FAILED VERIFICATIONS ({len(failed_results)})")
            lines.append("=" * 60)
            lines.append("")

            for idx, result in enumerate(failed_results, 1):
                lines.append(f"{idx}. File: {result.file_name}")

                if result.error:
                    # System error
                    lines.append(f"   Error: {result.error}")
                elif result.verification_response:
                    # LLM found issues
                    if result.verification_response.incorrect_fields:
                        lines.append("   Incorrect fields:")
                        for issue in result.verification_response.incorrect_fields:
                            lines.append(f"   • {issue.field_name}:")
                            lines.append(f"     Extracted: {issue.extracted_value}")
                            lines.append(f"     Correct: {issue.correct_value}")
                            lines.append(f"     Reason: {issue.reason}")

                    if result.verification_response.notes:
                        lines.append(f"   Notes: {result.verification_response.notes}")

                lines.append("")

            lines.append("=" * 60)
        else:
            lines.append("All verifications passed!")
            lines.append("=" * 60)

        return "\n".join(lines)
