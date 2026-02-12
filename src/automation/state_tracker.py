"""State tracking for claim submission progress.

Tracks the status of each expense claim through the submission process
with timestamps and error information.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional
from src.core.models import ExpenseRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ClaimState:
    """State of a single claim submission."""

    file_name: str
    status: Literal['pending', 'in_progress', 'completed', 'failed', 'skipped']
    confirmation_id: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0


class StateTracker:
    """Track claim submission progress across multiple expenses.

    Provides a centralized way to track the state of each claim as it
    progresses through the submission workflow.
    """

    def __init__(self):
        """Initialize state tracker."""
        self._states: Dict[str, ClaimState] = {}
        logger.info("StateTracker initialized")

    def initialize(self, expenses: List[ExpenseRecord]):
        """Initialize tracking for all unclaimed expenses.

        Args:
            expenses: List of ExpenseRecords to track
        """
        for expense in expenses:
            self._states[expense.file_name] = ClaimState(
                file_name=expense.file_name,
                status='pending'
            )
        logger.info("Initialized state tracking", count=len(expenses))

    def mark_in_progress(self, file_name: str):
        """Mark claim as currently being processed.

        Args:
            file_name: Unique file name of the expense
        """
        if file_name in self._states:
            state = self._states[file_name]
            state.status = 'in_progress'
            state.started_at = datetime.now()
            logger.info("Claim marked in progress", file_name=file_name)
        else:
            logger.warning("Attempted to mark unknown claim in progress", file_name=file_name)

    def mark_completed(self, file_name: str, confirmation_id: str):
        """Mark claim as successfully submitted.

        Args:
            file_name: Unique file name of the expense
            confirmation_id: Confirmation ID from Optum
        """
        if file_name in self._states:
            state = self._states[file_name]
            state.status = 'completed'
            state.confirmation_id = confirmation_id
            state.completed_at = datetime.now()
            state.error = None  # Clear any previous errors
            logger.info(
                "Claim marked completed",
                file_name=file_name,
                confirmation_id=confirmation_id
            )
        else:
            logger.warning("Attempted to mark unknown claim completed", file_name=file_name)

    def mark_failed(self, file_name: str, error: str):
        """Mark claim as failed.

        Args:
            file_name: Unique file name of the expense
            error: Error message describing the failure
        """
        if file_name in self._states:
            state = self._states[file_name]
            state.status = 'failed'
            state.error = error
            state.completed_at = datetime.now()
            state.retry_count += 1
            logger.error(
                "Claim marked failed",
                file_name=file_name,
                error=error,
                retry_count=state.retry_count
            )
        else:
            logger.warning("Attempted to mark unknown claim failed", file_name=file_name)

    def mark_skipped(self, file_name: str, reason: Optional[str] = None):
        """Mark claim as skipped by user.

        Args:
            file_name: Unique file name of the expense
            reason: Optional reason for skipping
        """
        if file_name in self._states:
            state = self._states[file_name]
            state.status = 'skipped'
            state.error = reason
            state.completed_at = datetime.now()
            logger.info("Claim marked skipped", file_name=file_name, reason=reason)
        else:
            logger.warning("Attempted to mark unknown claim skipped", file_name=file_name)

    def reset_for_retry(self, file_name: str):
        """Reset claim to pending for retry.

        Args:
            file_name: Unique file name of the expense
        """
        if file_name in self._states:
            state = self._states[file_name]
            state.status = 'pending'
            state.started_at = None
            state.completed_at = None
            # Keep error history and retry count
            logger.info("Claim reset for retry", file_name=file_name, retry_count=state.retry_count)
        else:
            logger.warning("Attempted to reset unknown claim", file_name=file_name)

    def get_state(self, file_name: str) -> Optional[ClaimState]:
        """Get current state of a claim.

        Args:
            file_name: Unique file name of the expense

        Returns:
            ClaimState if found, None otherwise
        """
        return self._states.get(file_name)

    def get_pending(self) -> List[ClaimState]:
        """Get all pending claims.

        Returns:
            List of ClaimStates with status='pending'
        """
        return [state for state in self._states.values() if state.status == 'pending']

    def get_statistics(self) -> dict:
        """Get summary statistics.

        Returns:
            Dictionary with counts by status and error details
        """
        stats = {
            'total': len(self._states),
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'submitted': 0,  # Alias for completed (matches CSV manager convention)
            'errors': []
        }

        for state in self._states.values():
            stats[state.status] += 1
            if state.status == 'completed':
                stats['submitted'] += 1
            if state.status == 'failed' and state.error:
                stats['errors'].append({
                    'file_name': state.file_name,
                    'error': state.error,
                    'retry_count': state.retry_count
                })

        logger.info("Generated statistics", **stats)
        return stats

    def get_all_states(self) -> List[ClaimState]:
        """Get all claim states.

        Returns:
            List of all ClaimStates
        """
        return list(self._states.values())
