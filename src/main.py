"""CLI for HSA medical expense claim automation."""

import asyncio
import sys
from pathlib import Path
import click
from dotenv import load_dotenv

from src.core.csv_manager import CSVManager
from src.core.signal_handler import GracefulShutdown
from src.processors.llm_extractor import ReceiptExtractor
from src.processors.receipt_processor import ReceiptProcessor
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
@click.pass_context
def process(ctx, receipts_path, csv_file):
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
        processor = ReceiptProcessor(receipts_folder, csv_manager, llm_extractor)

        # Process based on mode
        if is_single_file:
            success = asyncio.run(processor.process_single_receipt(receipts_path))
            if success:
                click.echo(f"\n✓ Processing complete!")
                click.echo(f"Data saved to: {csv_path}")
            else:
                click.echo(f"\n⏭️  Receipt already processed, skipped")
        else:
            asyncio.run(processor.process_receipts())
            click.echo("\n✓ Processing complete!")

    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.")
        sys.exit(0)


@cli.command()
@click.pass_context
def submit(ctx):
    """Submit unclaimed expenses to Optum Bank.

    Opens browser and automates claim submission for all unclaimed expenses in CSV.
    """
    click.echo("\n⚠️  Claim submission feature coming in Phase 2!")
    click.echo("This will automate filing claims on the Optum Bank website.\n")
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

    # Then submit claims
    ctx.invoke(submit)


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
