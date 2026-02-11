"""Receipt processor orchestration."""

import asyncio
import re
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime
from src.core.models import ExpenseRecord
from src.core.csv_manager import CSVManager
from src.core.signal_handler import GracefulShutdown
from src.processors.llm_extractor import ReceiptExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReceiptProcessor:
    """Orchestrate receipt processing from PDFs to CSV."""

    def __init__(
        self,
        receipts_folder: Path,
        csv_manager: CSVManager,
        llm_extractor: ReceiptExtractor,
        force: bool = False,
    ):
        """Initialize receipt processor.

        Args:
            receipts_folder: Path to folder containing receipt PDFs
            csv_manager: CSV manager instance
            llm_extractor: LLM extractor instance
            force: If True, reprocess files already in CSV (but skip claimed expenses)
        """
        self.receipts_folder = receipts_folder
        self.csv_manager = csv_manager
        self.llm_extractor = llm_extractor
        self.force = force

    def _validate_address(self, address: str) -> Tuple[bool, Optional[str]]:
        """Validate extracted address for completeness and hallucination patterns.

        Args:
            address: The extracted provider_address field

        Returns:
            Tuple of (is_valid, warning_message)
            - is_valid: False if address needs review, True otherwise
            - warning_message: Description of the issue, or None if valid
        """
        # If address is "Not Found", that's expected and valid
        if address == "Not Found":
            return (True, None)

        # Check for obvious placeholder patterns that indicate hallucination
        placeholder_patterns = [
            r'123\s+Main\s+St',
            r'Vision\s+Blvd',
            r'Optics\s+City',
            r'Sight\s+City',
            r'Example\s+Street',
            r'Sample\s+Ave',
        ]

        for pattern in placeholder_patterns:
            if re.search(pattern, address, re.IGNORECASE):
                return (False, f"Address contains placeholder pattern: '{address}'")

        # Check if address looks like an email
        if '@' in address:
            return (False, f"Address appears to be an email, not physical address: '{address}'")

        # Check if address looks like a phone number
        if re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', address):
            return (False, f"Address appears to be a phone number, not physical address: '{address}'")

        # Check for address completeness (Street, City, State ZIP)
        # A complete address should have: street number, city name, state, and ZIP code
        has_number = bool(re.search(r'\d+', address))
        has_state = bool(re.search(r'\b[A-Z]{2}\b', address))  # Two-letter state code
        has_zip = bool(re.search(r'\b\d{5}\b', address))  # 5-digit ZIP code

        if not has_number:
            return (False, f"Address missing street number (may be incomplete): '{address}'")

        if not has_state:
            return (False, f"Address missing state code (may be incomplete): '{address}'")

        if not has_zip:
            return (False, f"Address missing ZIP code (may be incomplete): '{address}'")

        # Address appears complete and valid
        return (True, None)

    def find_receipt_pdfs(self) -> List[Path]:
        """Find all PDF files in the receipts folder.

        Returns:
            List of PDF file paths

        Note:
            Only processes flat directory (no subdirectories)
        """
        pdf_files = []

        # Find .pdf files (case insensitive)
        for pattern in ["*.pdf", "*.PDF"]:
            pdf_files.extend(self.receipts_folder.glob(pattern))

        # Sort by filename for consistent processing order
        pdf_files = sorted(pdf_files)

        logger.info(
            "Found PDF files in receipts folder",
            folder=str(self.receipts_folder),
            count=len(pdf_files),
        )

        return pdf_files

    async def process_single_receipt(self, pdf_path: Path) -> tuple[bool, bool]:
        """Process a single receipt PDF.

        Args:
            pdf_path: Path to receipt PDF

        Returns:
            Tuple of (success: bool, is_update: bool)
            - success: True if processed successfully, False if skipped
            - is_update: True if this was an update to existing record, False if new or skipped

        Raises:
            Exception: Any exception during processing will propagate
        """
        file_name = pdf_path.name

        # Check if already processed (unless force mode)
        all_expenses = self.csv_manager.load_expenses()
        existing_expense = next((e for e in all_expenses if e.file_name == file_name), None)

        if existing_expense and not self.force:
            # Normal mode: skip all processed files
            logger.info("receipt_already_processed", file_name=file_name)
            print(f"⏭️  Receipt already processed: {file_name}")
            return (False, False)

        if existing_expense and existing_expense.claimed:
            # Force mode: skip claimed files
            logger.info("receipt_claimed_skipping", file_name=file_name)
            print(f"⊘ Receipt claimed (cannot reprocess): {file_name}")
            return (False, False)

        # Determine if this is an update or new record
        is_update = existing_expense is not None and self.force
        if is_update:
            logger.info("reprocessing_receipt", file_name=file_name)

        logger.info("processing_receipt", file_name=file_name, path=str(pdf_path), is_update=is_update)

        # No exception handling - let errors propagate for debugging
        extracted = await self.llm_extractor.extract_expense(pdf_path, file_name)
        expense = ExpenseRecord.from_extracted(extracted, file_name)

        # Validate the extracted address
        address_valid, address_warning = self._validate_address(extracted.provider_address)
        if not address_valid and address_warning:
            # Add warning to error history
            expense.add_error(f"Address validation warning: {address_warning}")
            logger.warning(
                "address_validation_failed",
                file_name=file_name,
                address=extracted.provider_address,
                warning=address_warning,
            )
            print(f"⚠️  Address validation warning: {address_warning}")


        # Add or update CSV
        if is_update:
            # Update existing record (preserve claimed status but update error history if warnings were added)
            updates = {
                'provider': expense.provider,
                'provider_address': expense.provider_address,
                'date_of_service': expense.date_of_service,
                'amount_to_claim': expense.amount_to_claim,
                'processing_timestamp': expense.processing_timestamp,
                'error_history': expense.error_history,  # Include error_history to capture validation warnings
            }
            self.csv_manager.update_expense(file_name, updates)
            logger.info(
                "successfully_updated_receipt",
                file_name=file_name,
                provider=expense.provider,
                amount=str(expense.amount_to_claim),
            )
        else:
            # Add new record
            self.csv_manager.add_expense(expense)
            logger.info(
                "successfully_processed_receipt",
                file_name=file_name,
                provider=expense.provider,
                amount=str(expense.amount_to_claim),
            )

        return (True, is_update)

    async def process_receipts(self) -> dict:
        """Process all unprocessed receipts in the folder.

        Returns:
            Dictionary with processing statistics
        """
        logger.info("Starting receipt processing")

        # Find all PDF files
        pdf_files = self.find_receipt_pdfs()

        if not pdf_files:
            logger.warning("No PDF files found in receipts folder")
            print(f"No PDF files found in {self.receipts_folder}")
            return {
                "total_found": 0,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
            }

        # Determine which files to skip based on force flag
        if self.force:
            # Force mode: skip only claimed files
            all_expenses = self.csv_manager.load_expenses()
            claimed_files = {e.file_name for e in all_expenses if e.claimed}
            processed_files = claimed_files  # For logging
            unprocessed = [f for f in pdf_files if f.name not in claimed_files]
            logger.info(
                "force_mode_enabled",
                total_files=len(pdf_files),
                skipping_claimed=len(claimed_files),
            )
        else:
            # Normal mode: skip all processed files
            processed_files = self.csv_manager.get_processed_files()
            unprocessed = [f for f in pdf_files if f.name not in processed_files]

        logger.info("Filtered files", to_process=len(unprocessed), skipped=len(processed_files))

        if not unprocessed:
            print(f"\nAll {len(pdf_files)} receipts already processed.")
            return {
                "total_found": len(pdf_files),
                "processed": 0,
                "skipped": len(pdf_files),
                "failed": 0,
            }

        print(f"\nFound {len(pdf_files)} total receipts")
        print(f"Already processed: {len(processed_files)}")
        print(f"To process: {len(unprocessed)}\n")

        # Process each file
        processed_count = 0
        updated_count = 0
        failed_count = 0

        for i, pdf_path in enumerate(unprocessed, 1):
            # Check for graceful shutdown
            if GracefulShutdown.should_shutdown():
                logger.info("Graceful shutdown requested, stopping processing")
                print(f"\nShutdown requested. Processed {processed_count}/{len(unprocessed)} receipts.")
                break

            print(f"[{i}/{len(unprocessed)}] Processing {pdf_path.name}...")

            success, is_update = await self.process_single_receipt(pdf_path)

            if success:
                processed_count += 1
                if is_update:
                    updated_count += 1
                    print(f"✓ Successfully updated {pdf_path.name}")
                else:
                    print(f"✓ Successfully processed {pdf_path.name}")
            else:
                failed_count += 1

        # Print summary
        print(f"\n" + "=" * 50)
        print(f"Processing Summary")
        print(f"=" * 50)
        print(f"Total receipts found: {len(pdf_files)}")
        if self.force:
            print(f"Skipped (claimed): {len(processed_files)}")
            print(f"Updated: {updated_count}")
            print(f"Newly processed: {processed_count - updated_count}")
        else:
            print(f"Already processed: {len(processed_files)}")
            print(f"Newly processed: {processed_count}")
        print(f"Failed: {failed_count}")
        print(f"=" * 50)

        logger.info(
            "receipt_processing_completed",
            total=len(pdf_files),
            processed=processed_count,
            updated=updated_count if self.force else 0,
            failed=failed_count,
            skipped=len(processed_files),
            force_mode=self.force,
        )

        return {
            "total_found": len(pdf_files),
            "processed": processed_count,
            "updated": updated_count if self.force else 0,
            "skipped_claimed": len(processed_files) if self.force else 0,
            "skipped": len(processed_files) if not self.force else 0,
            "failed": failed_count,
        }
