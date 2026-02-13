"""CLI for HSA medical expense claim automation."""

import asyncio
import os
import sys
from pathlib import Path
import click
from dotenv import load_dotenv

from src.core.csv_manager import CSVManager
from src.core.signal_handler import GracefulShutdown
from src.processors.llm_extractor import ReceiptExtractor, VERIFICATION_MODEL_NAME
from src.processors.receipt_processor import ReceiptProcessor
from src.processors.receipt_verifier import ReceiptVerifier
from src.utils.logger import setup_logger, get_logger
from src.utils.path_utils import deduce_csv_path

# Load environment variables from .env file
load_dotenv()

logger = None  # Will be initialized after setup


@click.group()
@click.option('--log-level', default='INFO', help='Log level (DEBUG, INFO, WARNING, ERROR)')
@click.option('--log-file', default='hsa_agent.log', help='Log file path')
@click.pass_context
def cli(ctx, log_level, log_file):
    """HSA Claim Automation Agent - Process medical receipts and file claims automatically."""
    try:
        # Setup logging
        setup_logger(log_level, log_file)
        global logger
        logger = get_logger(__name__)

        # Store options in context
        ctx.obj = {'log_level': log_level, 'log_file': log_file}

        logger.info("HSA Agent started", log_level=log_level, log_file=log_file)

    except Exception as e:
        click.echo(f"Failed to initialize: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('receipts_path', type=click.Path(exists=True, path_type=Path))
@click.option('--csv', 'csv_file', default=None, help='CSV output file path (default: expenses.csv in folder or {basename}.csv for single file)')
@click.option('-f', '--force', is_flag=True, help='Reprocess all files, overriding existing results. Skips claimed expenses.')
@click.pass_context
def process(ctx, receipts_path, csv_file, force):
    """Process receipts and extract data to CSV.

    RECEIPTS_PATH: Path to folder containing receipt PDFs OR path to a single PDF file
    """
    GracefulShutdown.setup()

    try:
        # Determine mode (single file vs folder)
        is_single_file = receipts_path.is_file() and receipts_path.suffix.lower() == '.pdf'

        # Deduce CSV path
        csv_path = deduce_csv_path(receipts_path, csv_file)

        # Determine receipts folder
        receipts_folder = receipts_path.parent if is_single_file else receipts_path

        # Print banner
        mode = "Single Receipt Processing (Debug Mode)" if is_single_file else "Receipt Processing"
        click.echo(f"\n{'=' * 60}")
        click.echo(f"HSA Agent - {mode}")
        click.echo(f"{'=' * 60}")
        if is_single_file:
            click.echo(f"PDF file: {receipts_path}")
        else:
            click.echo(f"Receipts folder: {receipts_folder}")
        click.echo(f"CSV output: {csv_path}")
        click.echo(f"{'=' * 60}\n")

        # Initialize components (same for both modes)
        csv_manager = CSVManager(csv_path)
        llm_extractor = ReceiptExtractor()
        processor = ReceiptProcessor(receipts_folder, csv_manager, llm_extractor, force=force)

        # Process based on mode
        if is_single_file:
            success, is_update = asyncio.run(processor.process_single_receipt(receipts_path))
            if success:
                action = "updated" if is_update else "processed"
                click.echo(f"\n✓ Processing complete! Receipt {action}.")
                click.echo(f"Data saved to: {csv_path}")
            else:
                click.echo(f"\n⏭️  Receipt skipped (already processed or claimed)")
        else:
            asyncio.run(processor.process_receipts())
            click.echo("\n✓ Processing complete!")

    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.")
        sys.exit(0)


@cli.command()
@click.argument('receipts_path', type=click.Path(exists=True, path_type=Path))
@click.option('--csv', 'csv_file', default=None, help='CSV file to verify (default: expenses.csv in folder or {basename}.csv for single file)')
@click.pass_context
def verify(ctx, receipts_path, csv_file):
    """Verify existing CSV expense records using LLM semantic judgment.

    RECEIPTS_PATH: Path to folder containing receipt PDFs OR path to a single PDF file

    Only verifies expenses already recorded in the CSV (does not process new files).
    Reports verification issues but does NOT update the CSV.
    """
    GracefulShutdown.setup()

    try:
        # Determine mode (single file vs folder)
        is_single_file = receipts_path.is_file() and receipts_path.suffix.lower() == '.pdf'

        # Deduce CSV path
        csv_path = deduce_csv_path(receipts_path, csv_file)

        # Check CSV exists
        if not csv_path.exists():
            click.echo(f"\n❌ Error: CSV file not found: {csv_path}", err=True)
            click.echo("Nothing to verify. Run 'process' first to extract expenses.\n")
            sys.exit(1)

        # Determine receipts folder
        receipts_folder = receipts_path.parent if is_single_file else receipts_path

        # Print banner
        click.echo(f"\n{'=' * 60}")
        click.echo(f"HSA Agent - Receipt Verification")
        click.echo(f"{'=' * 60}")
        if is_single_file:
            click.echo(f"PDF file: {receipts_path}")
        else:
            click.echo(f"Receipts folder: {receipts_folder}")
        click.echo(f"CSV file: {csv_path}")
        click.echo(f"Verification model: {VERIFICATION_MODEL_NAME}")
        click.echo(f"{'=' * 60}\n")

        # Initialize components
        csv_manager = CSVManager(csv_path)
        verifier = ReceiptVerifier(receipts_folder, csv_manager)

        # Determine target files based on mode
        if is_single_file:
            # Single file mode: verify only this file
            target_file = receipts_path.name
            expenses = csv_manager.load_expenses()
            if not any(e.file_name == target_file for e in expenses):
                click.echo(f"❌ Error: {target_file} not found in CSV. Nothing to verify.\n", err=True)
                sys.exit(1)
            target_files = [target_file]
        else:
            # Folder mode: verify all files in CSV
            target_files = None  # None means verify all

        # Run verification
        summary = asyncio.run(verifier.verify_receipts(target_files=target_files))

        # Print formatted summary
        click.echo(verifier._format_summary(summary))

        # Exit with appropriate code
        if summary.failed > 0:
            sys.exit(1)  # Verification failures
        else:
            sys.exit(0)  # All passed or only skipped

    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.")
        sys.exit(0)


@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--full-flow', is_flag=True, default=False,
              help='Use full workflow with provider search and receipt upload. Default is simplified flow.')
@click.pass_context
def submit(ctx, path, full_flow):
    """Submit unclaimed expenses to Optum Bank.

    PATH: Path to folder (uses expenses.csv), a CSV file, or a PDF file (uses corresponding .csv)

    By default, uses simplified workflow (skip provider search and file upload).
    Use --full-flow to include provider search and receipt upload steps.

    Opens Chrome browser in visible mode. You'll need to sign in manually if not already signed in.
    """
    GracefulShutdown.setup()

    try:
        # Deduce CSV path
        csv_path = deduce_csv_path(path)

        # Deduce receipts folder
        if path.is_dir():
            receipts_folder = path
        elif path.suffix.lower() == '.pdf':
            receipts_folder = path.parent
        elif path.suffix.lower() == '.csv':
            receipts_folder = path.parent
        else:
            receipts_folder = path.parent

        # Print banner
        click.echo(f"\n{'=' * 60}")
        click.echo("HSA Agent - Claim Submission")
        click.echo(f"{'=' * 60}")
        click.echo(f"CSV file: {csv_path}")
        click.echo(f"Receipts folder: {receipts_folder}")

        # Show workflow mode
        if full_flow:
            click.echo("Workflow: FULL (with provider search and file upload)")
        else:
            click.echo("Workflow: SIMPLIFIED (skip provider search and file upload)")

        click.echo(f"{'=' * 60}\n")

        # Initialize components
        csv_manager = CSVManager(csv_path)

        # Check for unclaimed expenses
        unclaimed_count = csv_manager.get_statistics()['unclaimed']
        if unclaimed_count == 0:
            click.echo("✓ No unclaimed expenses found. Nothing to submit.\n")
            return

        click.echo(f"Found {unclaimed_count} unclaimed expense(s) to submit.\n")

        # Import here to avoid loading playwright if not needed
        from src.automation.claim_submitter import ClaimSubmitter

        # Read browser configuration from environment
        headless = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"

        click.echo(f"Browser mode: {'headless' if headless else 'visible UI'}\n")

        # Create submitter
        submitter = ClaimSubmitter(
            csv_manager=csv_manager,
            receipts_folder=receipts_folder,
            headless=headless,
            full_flow=full_flow,
        )

        # Run submission
        stats = asyncio.run(submitter.submit_all_claims())

        # Final message
        if stats['submitted'] > 0:
            click.echo(f"\n✓ Submission complete! {stats['submitted']} claim(s) filed.")
        else:
            click.echo(f"\n⚠️  No claims were submitted.")

    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        if logger:
            logger.error("Submit command failed", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('receipts_path', type=click.Path(exists=True, path_type=Path))
@click.option('--csv', 'csv_file', default=None, help='CSV output file path (default: expenses.csv in folder or {basename}.csv for single file)')
@click.pass_context
def run(ctx, receipts_path, csv_file):
    """Run full workflow: process receipts AND submit claims.

    RECEIPTS_PATH: Path to folder containing receipt PDFs OR path to a single PDF file
    """
    # First process receipts
    ctx.invoke(process, receipts_path=receipts_path, csv_file=csv_file)

    # Then submit claims (pass receipts_path as 'path')
    ctx.invoke(submit, path=receipts_path)


@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.pass_context
def status(ctx, path):
    """Show status of expenses (processed, claimed, errors).

    PATH: Path to folder (uses expenses.csv), a CSV file, or a PDF file (uses corresponding .csv)
    """
    try:
        # Deduce CSV path
        csv_path = deduce_csv_path(path)

        csv_manager = CSVManager(csv_path)

        # Get statistics
        stats = csv_manager.get_statistics()

        click.echo(f"\n{'=' * 60}")
        click.echo(f"HSA Agent - Expense Status")
        click.echo(f"{'=' * 60}")
        click.echo(f"CSV file: {csv_path}")
        click.echo(f"")
        click.echo(f"Total expenses: {stats['total_expenses']}")
        click.echo(f"  ✓ Claimed: {stats['claimed']}")
        click.echo(f"  ⏳ Unclaimed: {stats['unclaimed']}")
        click.echo(f"")
        click.echo(f"Amounts:")
        click.echo(f"  Total: ${stats['total_amount']:.2f}")
        click.echo(f"  Claimed: ${stats['claimed_amount']:.2f}")
        click.echo(f"  Unclaimed: ${stats['unclaimed_amount']:.2f}")
        click.echo(f"{'=' * 60}\n")

        # Show unclaimed expenses if any
        if stats['unclaimed'] > 0:
            unclaimed = csv_manager.get_unclaimed_expenses()
            click.echo("Unclaimed expenses:")
            for expense in unclaimed:
                click.echo(f"  - {expense.file_name}: ${expense.amount_to_claim} ({expense.provider})")
            click.echo("")

        # Show summary (only for multiple expenses)
        if stats['total_expenses'] > 1:
            click.echo(f"Summary:")
            click.echo(f"  Total expense: ${stats['total_amount']:.2f}")
            click.echo(f"  Already claimed: ${stats['claimed_amount']:.2f}")
            click.echo(f"  To be claimed: ${stats['unclaimed_amount']:.2f}")
            click.echo("")

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
