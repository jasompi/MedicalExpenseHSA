"""System prompts for HSA claim submission agent.

These prompts guide the LLM agent through the claim submission process
on Optum Bank's website. Prompts are loaded from external text files
in src/prompts/ for easy editing and version control.
"""

from pathlib import Path
from datetime import datetime
from src.core.models import ExpenseRecord

# Prompt file paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
CLAIM_SUBMISSION_SIMPLIFIED_PROMPT = PROMPTS_DIR / "claim_submission_simplified.txt"
CLAIM_SUBMISSION_FULL_PROMPT = PROMPTS_DIR / "claim_submission_full.txt"
CLAIM_SUBMISSION_BASE_PROMPT = PROMPTS_DIR / "claim_submission_base.txt"


def load_prompt(prompt_path: Path) -> str:
    """Load a prompt template from file.

    Args:
        prompt_path: Path to the prompt text file

    Returns:
        Prompt template string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding='utf-8')


def format_amount_for_entry(amount: float) -> str:
    """Convert dollar amount to cents string for keyboard entry.

    Currency input fields with masking expect cents to be typed character-by-character.
    For example, $75.00 should be entered as "7500" which the mask formats to "$75.00".

    This function converts a dollar amount to the cents representation needed for
    typing into currency-masked fields.

    Args:
        amount: Dollar amount (e.g., 75.00)

    Returns:
        Cents as string without dollar sign (e.g., "7500")

    Examples:
        >>> format_amount_for_entry(75.00)
        '7500'
        >>> format_amount_for_entry(123.45)
        '12345'
        >>> format_amount_for_entry(0.99)
        '99'
    """
    cents = int(round(amount * 100))
    return str(cents)


def get_claim_submission_system_prompt(expense: ExpenseRecord, full_flow: bool = False) -> str:
    """Generate system prompt for claim submission with expense context.

    Loads the appropriate prompt template based on workflow mode and fills in
    expense details accordingly.

    Args:
        expense: ExpenseRecord containing claim details
        full_flow: If True, use full workflow with provider search and file upload.
                   If False (default), use simplified workflow without provider/file.

    Returns:
        Complete system prompt with expense details and appropriate workflow

    Raises:
        FileNotFoundError: If the prompt template file is missing
    """
    # Format shared variables
    date_str = expense.date_of_service.strftime('%m/%d/%Y')
    current_date_str = datetime.today().strftime('%A, %B %-d, %Y')
    amount_str = f"{expense.amount_to_claim:.2f}"
    amount_cents_str = format_amount_for_entry(float(expense.amount_to_claim))

    if full_flow:
        # Load full workflow template
        template = load_prompt(CLAIM_SUBMISSION_FULL_PROMPT)
        # Fill in ALL variables including provider and receipt
        return template.format(
            provider=expense.provider,
            provider_address=expense.provider_address,
            amount=amount_str,
            amount_cents=amount_cents_str,
            date_of_service=date_str,
            file_name=expense.file_name,
            current_date=current_date_str
        )
    else:
        # Load simplified workflow template
        template = load_prompt(CLAIM_SUBMISSION_SIMPLIFIED_PROMPT)
        # Fill in ONLY amount and date (no provider, no file)
        return template.format(
            amount=amount_str,
            amount_cents=amount_cents_str,
            date_of_service=date_str,
            current_date=current_date_str
        )


def get_base_system_prompt() -> str:
    """Get base system prompt without specific expense context.

    Loads the base claim submission template and fills in the current date.

    Returns:
        Base system prompt with current date filled in

    Raises:
        FileNotFoundError: If the prompt template file is missing
    """
    template = load_prompt(CLAIM_SUBMISSION_BASE_PROMPT)
    current_date_str = datetime.today().strftime('%A, %B %-d, %Y')
    return template.format(current_date=current_date_str)
