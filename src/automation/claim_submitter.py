"""Main orchestrator for HSA claim submission.

ClaimSubmitter coordinates the entire claim submission process, managing
browser state, user intervention, and CSV updates across multiple expenses.
"""

import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from src.core.models import ExpenseRecord
from src.core.csv_manager import CSVManager
from src.core.signal_handler import GracefulShutdown
from src.automation.browser_manager import BrowserManager
from src.automation.agent_loop import claim_submission_loop
from src.automation.user_intervention import UserInterventionManager
from src.automation.state_tracker import StateTracker
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Configuration from environment
OPTUM_URL = os.getenv(
    "OPTUM_URL",
    "https://account.optumbank.com/account/expenses/new?expense-type=reimbursement"
)
CLAIM_MODEL = os.getenv("CLAIM_MODEL", "anthropic.claude-sonnet-4-20250514-v1:0")
MAX_CLAIM_RETRIES = int(os.getenv("MAX_CLAIM_RETRIES", "3"))


class ClaimSubmitter:
    """Main orchestrator for HSA claim submission.

    Manages the full lifecycle of submitting multiple claims:
    - Browser initialization and login
    - Agent-driven claim submission
    - User intervention for login/2FA/errors
    - CSV state updates
    - Progress tracking
    """

    def __init__(
        self,
        csv_manager: CSVManager,
        receipts_folder: Path,
        headless: bool = False,
        streamlit_mode: bool = False,
    ):
        """Initialize claim submitter.

        Args:
            csv_manager: CSVManager for updating claim state
            receipts_folder: Path to folder containing receipt PDFs
            headless: Whether to run browser in headless mode
            streamlit_mode: Whether to use Streamlit UI (vs CLI)
        """
        self.csv_manager = csv_manager
        self.receipts_folder = receipts_folder
        self.browser_manager = BrowserManager(headless)
        self.user_intervention = UserInterventionManager(streamlit_mode)
        self.state_tracker = StateTracker()

        # Get API key from environment
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable must be set")

        logger.info(
            "ClaimSubmitter initialized",
            receipts_folder=str(receipts_folder),
            headless=headless,
            mode="streamlit" if streamlit_mode else "cli"
        )

    async def submit_all_claims(self) -> dict:
        """Submit all unclaimed expenses.

        This is the main entry point called by the CLI.

        Returns:
            Dictionary with statistics:
                - total: int
                - submitted: int
                - failed: int
                - skipped: int
                - errors: List[dict]
        """
        logger.info("Starting claim submission process")

        try:
            # 1. Load unclaimed expenses from CSV
            unclaimed = self.csv_manager.get_unclaimed_expenses()
            self.state_tracker.initialize(unclaimed)

            total = len(unclaimed)
            logger.info(f"Found {total} unclaimed expense(s)")

            if total == 0:
                return {
                    'total': 0,
                    'submitted': 0,
                    'failed': 0,
                    'skipped': 0,
                    'errors': []
                }

            # 2. Create/get browser tool
            browser_tool = await self.browser_manager.get_browser_tool()

            # 3. Navigate to Optum and wait for login
            logger.info("Navigating to Optum Bank")
            await browser_tool(action="navigate", text=OPTUM_URL)

            # Check if already logged in
            if not await self.browser_manager.is_logged_in():
                login_success = await self.user_intervention.wait_for_login(browser_tool)

                # Check if user requested exit
                if not login_success:
                    logger.info("User requested exit during login - cleaning up")
                    await self.browser_manager.cleanup()
                    return {
                        'total': total,
                        'submitted': 0,
                        'failed': 0,
                        'skipped': total,
                        'errors': [{'reason': 'User cancelled during login'}]
                    }

                # Verify login succeeded
                if not await self.browser_manager.is_logged_in():
                    raise RuntimeError("Login verification failed after user confirmation")

            logger.info("User logged in successfully")

            # 4. Process each expense
            current = 0
            for expense in unclaimed:
                current += 1

                # Check for graceful shutdown
                if GracefulShutdown.should_shutdown():
                    logger.info("Graceful shutdown requested - stopping after current claim")
                    break

                # Show progress
                self.user_intervention.show_progress(current, total, expense)

                # Process single claim with error handling
                success = await self._process_single_claim_with_retry(
                    expense,
                    browser_tool,
                    current,
                    total
                )

                if not success and GracefulShutdown.should_shutdown():
                    # User chose quit on error
                    break

            # 5. Cleanup and return stats
            await self.browser_manager.cleanup()
            stats = self.state_tracker.get_statistics()

            logger.info("Claim submission complete", **stats)
            return stats

        except Exception as e:
            logger.error("Fatal error in submit_all_claims", error=str(e), exc_info=True)
            # Attempt cleanup
            try:
                await self.browser_manager.cleanup()
            except Exception:
                pass
            raise

    async def _process_single_claim_with_retry(
        self,
        expense: ExpenseRecord,
        browser_tool,
        current: int,
        total: int
    ) -> bool:
        """Process a single claim with retry logic.

        Args:
            expense: ExpenseRecord to process
            browser_tool: BrowserTool instance
            current: Current claim number (1-indexed)
            total: Total number of claims

        Returns:
            True if successful or skipped, False if should quit
        """
        max_retries = MAX_CLAIM_RETRIES
        attempt = 0

        while attempt < max_retries:
            attempt += 1

            try:
                self.state_tracker.mark_in_progress(expense.file_name)

                # Submit the claim
                success, claim_id, error = await self._submit_single_claim(
                    expense,
                    browser_tool
                )

                if success and claim_id:
                    # Update CSV and state tracker
                    self.csv_manager.mark_as_claimed(
                        expense.file_name,
                        claim_id,
                        datetime.now()
                    )
                    self.state_tracker.mark_completed(expense.file_name, claim_id)
                    self.user_intervention.show_success(expense, claim_id)
                    return True

                elif error:
                    # Handle error - prompt user
                    self.state_tracker.mark_failed(expense.file_name, error)

                    # If max retries not reached, ask user what to do
                    if attempt < max_retries:
                        decision = await self.user_intervention.prompt_on_error(
                            expense,
                            f"Attempt {attempt}/{max_retries}: {error}"
                        )

                        if decision == "retry":
                            logger.info("User chose to retry", file_name=expense.file_name, attempt=attempt + 1)
                            self.state_tracker.reset_for_retry(expense.file_name)
                            continue  # Retry loop
                        elif decision == "skip":
                            logger.info("User chose to skip", file_name=expense.file_name)
                            self.state_tracker.mark_skipped(expense.file_name, error)
                            return True
                        elif decision == "quit":
                            logger.info("User chose to quit")
                            GracefulShutdown.request_shutdown()
                            return False
                    else:
                        # Max retries reached - skip this claim
                        logger.warning("Max retries reached", file_name=expense.file_name, max_retries=max_retries)
                        self.state_tracker.mark_skipped(expense.file_name, f"Max retries reached: {error}")
                        return True

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error("Error processing claim", file_name=expense.file_name, error=error_msg, exc_info=True)
                self.state_tracker.mark_failed(expense.file_name, error_msg)

                # Ask user what to do
                decision = await self.user_intervention.prompt_on_error(expense, error_msg)
                if decision == "retry" and attempt < max_retries:
                    self.state_tracker.reset_for_retry(expense.file_name)
                    continue
                elif decision == "skip":
                    self.state_tracker.mark_skipped(expense.file_name, error_msg)
                    return True
                elif decision == "quit":
                    GracefulShutdown.request_shutdown()
                    return False

        # Should not reach here, but handle gracefully
        logger.warning("Exited retry loop without resolution", file_name=expense.file_name)
        self.state_tracker.mark_skipped(expense.file_name, "Max retries exhausted")
        return True

    async def _submit_single_claim(
        self,
        expense: ExpenseRecord,
        browser_tool,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Submit one claim using LLM agent.

        Args:
            expense: ExpenseRecord to submit
            browser_tool: BrowserTool instance

        Returns:
            Tuple of (success: bool, confirmation_id: str | None, error: str | None)
        """
        logger.info("=" * 80)
        logger.info(f"🏥 STARTING CLAIM SUBMISSION")
        logger.info(f"   File: {expense.file_name}")
        logger.info(f"   Provider: {expense.provider}")
        logger.info(f"   Amount: ${expense.amount_to_claim}")
        logger.info("=" * 80)

        print(f"\n{'=' * 80}")
        print(f"🏥 SUBMITTING CLAIM: {expense.file_name}")
        print(f"   Provider: {expense.provider}")
        print(f"   Amount: ${expense.amount_to_claim}")
        print(f"{'=' * 80}\n")

        # Get receipt path
        receipt_path = self.receipts_folder / expense.file_name

        if not receipt_path.exists():
            error = f"Receipt file not found: {receipt_path}"
            logger.error(error)
            return (False, None, error)

        # Prepare initial messages with task instruction
        messages = [
            {
                "role": "user",
                "content": f"""Please submit this HSA claim to Optum Bank:

Provider: {expense.provider}
Amount: ${expense.amount_to_claim}
Date of Service: {expense.date_of_service.strftime('%m/%d/%Y')}
Receipt: {expense.file_name}

Follow the workflow in your system prompt to complete the submission and capture the confirmation number."""
            }
        ]

        # Callbacks for agent output (enhanced with detailed logging)
        def output_callback(content_block):
            if content_block.get("type") == "text":
                text = content_block.get("text", "")
                if text.strip():
                    # Print agent's thinking to console
                    logger.info("💭 Agent says:", text=text)
                    # Also print to stdout for immediate visibility
                    print(f"\n💭 Agent: {text}\n")
            elif content_block.get("type") == "tool_use":
                tool_name = content_block.get("name", "unknown")
                logger.debug(f"Agent wants to use tool: {tool_name}")

        def tool_output_callback(result, tool_id):
            # Log tool results
            if result.output:
                output_preview = result.output[:200] if len(result.output) > 200 else result.output
                logger.info(f"📤 Tool result preview: {output_preview}...")
            if result.error:
                logger.error(f"Tool error: {result.error}")

        def api_response_callback(request, response, error):
            if error:
                logger.error("API error", error=str(error))
            elif response:
                logger.debug("API response received")

        try:
            # Run agent loop
            logger.info("🚀 Starting agent loop...")
            result = await claim_submission_loop(
                expense=expense,
                receipt_path=receipt_path,
                model=CLAIM_MODEL,
                messages=messages,
                browser_tool=browser_tool,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=self.api_key,
                turn_offset=0,  # Starting fresh
            )

            logger.info("🏁 Agent loop completed")
            logger.info(f"   Success: {result.get('success', False)}")
            logger.info(f"   Confirmation ID: {result.get('confirmation_id', 'N/A')}")
            logger.info(f"   Error: {result.get('error', 'N/A')}")

            success = result.get("success", False)
            confirmation_id = result.get("confirmation_id")
            error = result.get("error")
            intervention_needed = result.get("intervention_needed")

            # Check for resumable interventions (manual_step, 2fa)
            if intervention_needed:
                if intervention_needed in ["manual_step", "2fa"]:
                    # This is a resumable intervention - pause and wait for user
                    logger.info("Resumable intervention detected", reason=intervention_needed)

                    # Extract the instruction from the error message
                    instruction = error.replace("User intervention required: ", "") if error else "Please complete the required action"

                    # Wait for user to complete the manual action
                    user_confirmed = await self.user_intervention.wait_for_manual_action(instruction)

                    if not user_confirmed:
                        # User chose to quit during manual action
                        logger.warning("User aborted manual action", reason=intervention_needed)
                        return (False, None, f"User aborted during {intervention_needed}: {instruction}")

                    # User confirmed - resume the agent loop with updated messages
                    logger.info("Resuming agent loop after manual action", reason=intervention_needed)

                    # Calculate turn offset for cumulative tracking
                    turns_used = result.get("turns_used", 0)

                    # Append user confirmation message to existing conversation
                    messages.append({
                        "role": "user",
                        "content": "I have completed the requested action. Please verify and continue with the claim submission."
                    })

                    # Resume the agent loop with preserved message history
                    result = await claim_submission_loop(
                        expense=expense,
                        receipt_path=receipt_path,
                        model=CLAIM_MODEL,
                        messages=messages,  # SAME messages list with conversation history
                        browser_tool=browser_tool,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        api_response_callback=api_response_callback,
                        api_key=self.api_key,
                        turn_offset=turns_used,  # Continue turn count
                    )

                    # Process the resumed result
                    success = result.get("success", False)
                    confirmation_id = result.get("confirmation_id")
                    error = result.get("error")
                    intervention_needed = result.get("intervention_needed")

                    # Safety check: if we get another intervention after resume, fail
                    if intervention_needed:
                        logger.error("Multiple interventions detected - failing claim", reason=intervention_needed)
                        return (False, None, f"Multiple interventions required: {error}")
                else:
                    # Other intervention types (login, unexpected_error)
                    # Login is already handled at start, so this is unexpected
                    logger.warning("Unexpected intervention during claim", reason=intervention_needed)
                    return (False, None, f"Intervention needed: {error}")

            if success and confirmation_id:
                logger.info("Claim submitted successfully", confirmation_id=confirmation_id)
                return (True, confirmation_id, None)
            else:
                logger.warning("Claim submission failed", error=error)
                return (False, None, error or "Unknown error")

        except Exception as e:
            error = f"Agent error: {str(e)}"
            logger.error("Exception in claim submission", error=error, exc_info=True)
            return (False, None, error)
