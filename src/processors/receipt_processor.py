"""Receipt processor orchestration."""

import asyncio
from pathlib import Path
from typing import List
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
    ):
        """Initialize receipt processor.

        Args:
            receipts_folder: Path to folder containing receipt PDFs
            csv_manager: CSV manager instance
            llm_extractor: LLM extractor instance
        """
        self.receipts_folder = receipts_folder
        self.csv_manager = csv_manager
        self.llm_extractor = llm_extractor

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

    async def process_single_receipt(self, pdf_path: Path) -> bool:
        """Process a single receipt PDF.

        Args:
            pdf_path: Path to receipt PDF

        Returns:
            True if successful

        Raises:
            Exception: Any exception during processing will propagate
        """
        file_name = pdf_path.name

        logger.info("Processing receipt", file_name=file_name, path=str(pdf_path))

        # No exception handling - let errors propagate for debugging
        extracted = await self.llm_extractor.extract_expense(pdf_path, file_name)
        expense = ExpenseRecord.from_extracted(extracted, file_name)
        self.csv_manager.add_expense(expense)

        logger.info(
            "Successfully processed receipt",
            file_name=file_name,
            provider=expense.provider,
            amount=str(expense.amount_to_claim),
        )

        return True

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

        # Get already processed files
        processed_files = self.csv_manager.get_processed_files()
        logger.info("Already processed files", count=len(processed_files))

        # Filter to unprocessed files
        unprocessed = [f for f in pdf_files if f.name not in processed_files]
        logger.info("Unprocessed files found", count=len(unprocessed))

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
        failed_count = 0

        for i, pdf_path in enumerate(unprocessed, 1):
            # Check for graceful shutdown
            if GracefulShutdown.should_shutdown():
                logger.info("Graceful shutdown requested, stopping processing")
                print(f"\nShutdown requested. Processed {processed_count}/{len(unprocessed)} receipts.")
                break

            print(f"[{i}/{len(unprocessed)}] Processing {pdf_path.name}...")

            success = await self.process_single_receipt(pdf_path)

            if success:
                processed_count += 1
                print(f"✓ Successfully processed {pdf_path.name}")
            else:
                failed_count += 1

        # Print summary
        print(f"\n" + "=" * 50)
        print(f"Processing Summary")
        print(f"=" * 50)
        print(f"Total receipts found: {len(pdf_files)}")
        print(f"Already processed: {len(processed_files)}")
        print(f"Newly processed: {processed_count}")
        print(f"Failed: {failed_count}")
        print(f"=" * 50)

        logger.info(
            "Receipt processing completed",
            total=len(pdf_files),
            processed=processed_count,
            failed=failed_count,
            skipped=len(processed_files),
        )

        return {
            "total_found": len(pdf_files),
            "processed": processed_count,
            "skipped": len(processed_files),
            "failed": failed_count,
        }
