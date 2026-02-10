"""CSV state manager with atomic operations."""

import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any
from decimal import Decimal
from src.core.models import ExpenseRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CSVManager:
    """Manage expenses CSV with thread-safe atomic operations."""

    CSV_HEADERS = [
        "provider",
        "provider_address",
        "date_of_service",
        "file_name",
        "amount_to_claim",
        "claimed",
        "processing_timestamp",
        "claim_timestamp",
        "claim_confirmation_id",
        "error_history",
    ]

    def __init__(self, csv_path: Path):
        """Initialize CSV manager.

        Args:
            csv_path: Path to the expenses CSV file
        """
        self.csv_path = csv_path
        self._lock = threading.Lock()
        self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """Ensure CSV file exists with headers."""
        if not self.csv_path.exists():
            logger.info("Creating new CSV file", csv_path=str(self.csv_path))
            with self._lock:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                    writer.writeheader()

    def load_expenses(self) -> List[ExpenseRecord]:
        """Load all expenses from CSV.

        Returns:
            List of ExpenseRecord objects

        Raises:
            Exception: If CSV cannot be read
        """
        with self._lock:
            if not self.csv_path.exists():
                return []

            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                expenses = []
                for row in reader:
                    try:
                        expense = ExpenseRecord(
                            provider=row['provider'],
                            provider_address=row['provider_address'],
                            date_of_service=datetime.fromisoformat(row['date_of_service']).date(),
                            file_name=row['file_name'],
                            amount_to_claim=Decimal(row['amount_to_claim']),
                            claimed=row['claimed'].lower() == 'true',
                            processing_timestamp=datetime.fromisoformat(row['processing_timestamp']),
                            claim_timestamp=datetime.fromisoformat(row['claim_timestamp']) if row['claim_timestamp'] else None,
                            claim_confirmation_id=row['claim_confirmation_id'] if row['claim_confirmation_id'] else None,
                            error_history=row['error_history'] or "[]",
                        )
                        expenses.append(expense)
                    except Exception as e:
                        logger.warning(f"Skipping invalid CSV row", row=row, error=str(e))
                        continue

                logger.info("Loaded expenses from CSV", count=len(expenses))
                return expenses

    def get_processed_files(self) -> Set[str]:
        """Get set of file names that have been processed.

        Returns:
            Set of file names already in CSV
        """
        expenses = self.load_expenses()
        return {expense.file_name for expense in expenses}

    def add_expense(self, expense: ExpenseRecord) -> None:
        """Add a new expense to CSV atomically.

        Args:
            expense: ExpenseRecord to add

        Raises:
            Exception: If operation fails
        """
        with self._lock:
            # Append to CSV
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writerow(expense.to_csv_dict())

            logger.info("Added expense to CSV", file_name=expense.file_name)

    def update_expense(self, file_name: str, updates: Dict[str, Any]) -> None:
        """Update an expense atomically using temp file pattern.

        Args:
            file_name: File name to update (unique key)
            updates: Dictionary of fields to update

        Raises:
            Exception: If operation fails
        """
        with self._lock:
            # Read all expenses
            expenses = self.load_expenses()

            # Find and update the expense
            found = False
            for expense in expenses:
                if expense.file_name == file_name:
                    for key, value in updates.items():
                        if hasattr(expense, key):
                            setattr(expense, key, value)
                    found = True
                    break

            if not found:
                raise ValueError(f"Expense not found: {file_name}")

            # Write to temp file
            temp_path = self.csv_path.with_suffix('.tmp')
            with open(temp_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writeheader()
                for expense in expenses:
                    writer.writerow(expense.to_csv_dict())

            # Atomic rename
            temp_path.replace(self.csv_path)

            logger.info("Updated expense in CSV", file_name=file_name, updates=updates)

    def mark_as_claimed(self, file_name: str, claim_id: str, timestamp: datetime) -> None:
        """Mark an expense as claimed atomically.

        Args:
            file_name: File name to mark as claimed
            claim_id: Confirmation ID from claim submission
            timestamp: Timestamp when claim was submitted

        Raises:
            Exception: If operation fails
        """
        self.update_expense(
            file_name=file_name,
            updates={
                "claimed": True,
                "claim_timestamp": timestamp,
                "claim_confirmation_id": claim_id,
            }
        )

    def get_unclaimed_expenses(self) -> List[ExpenseRecord]:
        """Get all unclaimed expenses.

        Returns:
            List of unclaimed ExpenseRecord objects
        """
        expenses = self.load_expenses()
        unclaimed = [e for e in expenses if not e.claimed]
        logger.info("Found unclaimed expenses", count=len(unclaimed))
        return unclaimed

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about expenses.

        Returns:
            Dictionary with statistics
        """
        expenses = self.load_expenses()
        claimed = sum(1 for e in expenses if e.claimed)
        unclaimed = len(expenses) - claimed
        total_amount = sum(e.amount_to_claim for e in expenses)
        claimed_amount = sum(e.amount_to_claim for e in expenses if e.claimed)

        return {
            "total_expenses": len(expenses),
            "claimed": claimed,
            "unclaimed": unclaimed,
            "total_amount": total_amount,
            "claimed_amount": claimed_amount,
            "unclaimed_amount": total_amount - claimed_amount,
        }
