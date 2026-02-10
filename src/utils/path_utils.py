"""Path utilities for CSV file deduction."""

from pathlib import Path
from typing import Optional


def deduce_csv_path(input_path: Path, explicit_csv: Optional[str] = None) -> Path:
    """Deduce CSV file path from input path.

    Args:
        input_path: Input path (folder, PDF file, or CSV file)
        explicit_csv: Explicit CSV path override (optional)

    Returns:
        Deduced CSV file path

    Logic:
        - If explicit_csv is provided, use it
        - If input_path is a directory, return {directory}/expenses.csv
        - If input_path is a PDF file, return {basename}.csv
        - Otherwise, assume input_path is already a CSV and return it

    Examples:
        >>> deduce_csv_path(Path("/path/to/receipts"))
        Path("/path/to/receipts/expenses.csv")

        >>> deduce_csv_path(Path("/path/to/receipt.pdf"))
        Path("/path/to/receipt.csv")

        >>> deduce_csv_path(Path("/path/to/custom.csv"))
        Path("/path/to/custom.csv")

        >>> deduce_csv_path(Path("/path/to/receipt.pdf"), "/custom/path.csv")
        Path("/custom/path.csv")
    """
    # Explicit override takes precedence
    if explicit_csv is not None:
        return Path(explicit_csv)

    # Directory: use expenses.csv
    if input_path.is_dir():
        return input_path / 'expenses.csv'

    # PDF file: replace extension with .csv
    if input_path.suffix.lower() == '.pdf':
        return input_path.with_suffix('.csv')

    # Default: assume it's already a CSV path
    return input_path
