"""User intervention management for claim submission.

Handles user interactions during claim submission, with support for both
CLI (click-based) and Streamlit interfaces.
"""

import asyncio
from typing import Literal
import click
from src.core.models import ExpenseRecord
from src.automation.browser_tool import BrowserTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class UserInterventionManager:
    """Handle user interactions during claim submission.

    Provides an abstraction layer that supports both CLI (click) and
    Streamlit interfaces with the same API.
    """

    def __init__(self, streamlit_mode: bool = False):
        """Initialize user intervention manager.

        Args:
            streamlit_mode: If True, use Streamlit UI components.
                          If False, use CLI (click) components.
        """
        self.streamlit_mode = streamlit_mode
        logger.info("UserInterventionManager initialized", mode="streamlit" if streamlit_mode else "cli")

    async def wait_for_login(
        self,
        browser_tool: BrowserTool,
        timeout: int = 300
    ) -> bool:
        """Wait for user to complete login.

        Args:
            browser_tool: BrowserTool instance (for checking login state)
            timeout: Maximum seconds to wait (not enforced in CLI mode)

        Returns:
            True if user confirms login complete, False if user wants to exit
        """
        if self.streamlit_mode:
            # Streamlit implementation (future)
            import streamlit as st
            st.info("⏸️  Please log in to Optum Bank in the browser window.")
            st.info("Click 'Login Complete' when you've finished.")
            # Wait for button click (implementation depends on Streamlit app structure)
            # This is a placeholder - actual implementation will integrate with streamlit_app
            logger.warning("Streamlit mode not fully implemented for wait_for_login")
            return True
        else:
            # CLI implementation
            click.echo()
            click.secho("=" * 60, fg="yellow")
            click.secho("⏸️  USER ACTION REQUIRED", fg="yellow", bold=True)
            click.secho("=" * 60, fg="yellow")
            click.echo()
            click.echo("Please log in to Optum Bank in the browser window that just opened.")
            click.echo()
            click.secho("→ Complete the login process in the browser", fg="cyan")
            click.secho("→ When you're logged in, press Enter to continue", fg="cyan")
            click.secho("→ Or type 'cancel', 'quit', or 'exit' to abort", fg="red")
            click.echo()

            # Wait for Enter key or text input
            user_input = click.prompt("Press Enter to continue or type command", default="", show_default=False)

            # Check if user wants to exit
            if user_input.strip().lower() in ["cancel", "quit", "exit"]:
                click.echo()
                click.secho("🛑 User requested exit - closing browser and exiting...", fg="red", bold=True)
                logger.info("User requested exit from login prompt")
                return False

            logger.info("User confirmed login complete")
            return True

    async def wait_for_manual_action(
        self,
        instruction: str,
    ) -> bool:
        """Wait for user to complete a manual action during claim submission.

        This is used when the agent needs the user to perform an action
        (like uploading a file) that cannot be automated, then wants to
        resume the claim submission from where it left off.

        Args:
            instruction: What the user needs to do

        Returns:
            True if user confirms action is complete, False if user wants to quit
        """
        if self.streamlit_mode:
            # Streamlit implementation (future)
            import streamlit as st
            st.info(f"⏸️  {instruction}")
            st.info("Click 'Continue' when you've finished.")
            logger.warning("Streamlit mode not fully implemented for wait_for_manual_action")
            return True
        else:
            # CLI implementation
            click.echo()
            click.secho("=" * 60, fg="yellow")
            click.secho("⏸️  MANUAL ACTION REQUIRED", fg="yellow", bold=True)
            click.secho("=" * 60, fg="yellow")
            click.echo()
            click.echo(instruction)
            click.echo()
            click.secho("→ Complete the action described above", fg="cyan")
            click.secho("→ When done, press Enter to continue", fg="cyan")
            click.secho("→ Or type 'quit' to abort this claim", fg="red")
            click.echo()

            user_input = click.prompt("Press Enter to continue or type 'quit'",
                                       default="", show_default=False)

            if user_input.strip().lower() in ["quit", "exit", "cancel"]:
                click.echo()
                click.secho("🛑 User aborted - will prompt for retry/skip/quit...", fg="red")
                logger.info("User aborted manual action")
                return False

            logger.info("User confirmed manual action complete")
            return True

    async def prompt_on_error(
        self,
        expense: ExpenseRecord,
        error: str,
    ) -> Literal["retry", "skip", "quit"]:
        """Prompt user for decision when an error occurs.

        Args:
            expense: ExpenseRecord that failed
            error: Error message

        Returns:
            User's choice: 'retry', 'skip', or 'quit'
        """
        if self.streamlit_mode:
            # Streamlit implementation (future)
            import streamlit as st
            st.error(f"Error processing {expense.file_name}")
            st.error(f"Details: {error}")

            col1, col2, col3 = st.columns(3)
            # This is a placeholder - actual implementation will integrate with streamlit_app
            logger.warning("Streamlit mode not fully implemented for prompt_on_error")
            return "skip"  # Default action
        else:
            # CLI implementation
            click.echo()
            click.secho("=" * 60, fg="red")
            click.secho("❌ ERROR SUBMITTING CLAIM", fg="red", bold=True)
            click.secho("=" * 60, fg="red")
            click.echo()
            click.echo(f"File: {expense.file_name}")
            click.echo(f"Provider: {expense.provider}")
            click.echo(f"Amount: ${expense.amount_to_claim}")
            click.echo()
            click.secho(f"Error: {error}", fg="red")
            click.echo()
            click.echo("What would you like to do?")
            click.echo()
            click.echo("  r - Retry this claim")
            click.echo("  s - Skip this claim and continue to next")
            click.echo("  q - Quit the submission process")
            click.echo()

            choice = click.prompt(
                "Choose action",
                type=click.Choice(['r', 's', 'q'], case_sensitive=False),
                show_choices=False
            )

            choice_map = {
                'r': 'retry',
                's': 'skip',
                'q': 'quit'
            }

            action = choice_map[choice.lower()]
            logger.info("User selected action for error", action=action, file_name=expense.file_name)
            return action

    def show_progress(
        self,
        current: int,
        total: int,
        expense: ExpenseRecord
    ):
        """Display progress for current claim.

        Args:
            current: Current claim number (1-indexed)
            total: Total number of claims
            expense: Current ExpenseRecord being processed
        """
        if self.streamlit_mode:
            # Streamlit implementation (future)
            import streamlit as st
            st.info(f"Processing claim {current} of {total}: {expense.file_name}")
            st.progress(current / total)
        else:
            # CLI implementation
            click.echo()
            click.secho(f"{'='*60}", fg="cyan")
            click.secho(f"Processing Claim {current} of {total}", fg="cyan", bold=True)
            click.secho(f"{'='*60}", fg="cyan")
            click.echo()
            click.echo(f"File: {expense.file_name}")
            click.echo(f"Provider: {expense.provider}")
            click.echo(f"Amount: ${expense.amount_to_claim}")
            click.echo(f"Date of Service: {expense.date_of_service}")
            click.echo()

    def show_success(
        self,
        expense: ExpenseRecord,
        confirmation_id: str
    ):
        """Display success message for completed claim.

        Args:
            expense: ExpenseRecord that was successfully submitted
            confirmation_id: Confirmation ID from Optum
        """
        if self.streamlit_mode:
            # Streamlit implementation (future)
            import streamlit as st
            st.success(f"✓ Claim submitted: {confirmation_id}")
        else:
            # CLI implementation
            click.echo()
            click.secho("✓ Claim submitted successfully!", fg="green", bold=True)
            click.echo(f"Confirmation ID: {confirmation_id}")
            click.echo()
