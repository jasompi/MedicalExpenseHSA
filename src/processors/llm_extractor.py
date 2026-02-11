"""LLM-based receipt data extraction using pydantic_ai."""

import asyncio
import traceback
from datetime import datetime
from pathlib import Path

from pydantic_ai import Agent, BinaryContent
from src.core.models import ExtractedExpense
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Model constants - change these to use different models

ANTHROPIC_MODEL_NAME = "claude-3-7-sonnet-20250219"
OPENAI_MODEL_NAME = "gpt-4o"
GEMINI_MODEL_NAME = "gemini-2.5-flash"

MODEL_NAME = OPENAI_MODEL_NAME
VERIFICATION_MODEL_NAME = GEMINI_MODEL_NAME

def load_extraction_prompt() -> str:
    """Load the extraction prompt from file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "receipt_extraction.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


class ReceiptExtractor:
    """Extract expense data from receipt PDFs using LLM vision capabilities."""

    def __init__(self, model_name: str = MODEL_NAME):
        """Initialize the receipt extractor.

        Args:
            model_name: LLM model to use (defaults to MODEL_NAME)
        """
        self.model_name = model_name
        self.extraction_prompt = load_extraction_prompt()
        self.agent = Agent(
            model_name,
            output_type=ExtractedExpense,
            system_prompt=self.extraction_prompt,
        )
        logger.info(f"Initialized LLM extractor with model: {model_name}")

    def _write_debug_log(
        self,
        file_name: str,
        user_prompt: str,
        raw_response: str,
        exception: Exception,
        attempt: int,
    ) -> Path:
        """Write detailed debug log when extraction fails.

        Args:
            file_name: Name of the receipt file
            user_prompt: User prompt sent to LLM (without PDF data)
            raw_response: Raw response from LLM
            exception: Exception that occurred
            attempt: Attempt number

        Returns:
            Path to the debug log file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize filename to remove problematic characters
        safe_filename = file_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        debug_filename = f"llm_debug_{safe_filename}_{timestamp}_attempt{attempt}.txt"
        debug_path = Path("llm_debug_logs") / debug_filename
        debug_path.parent.mkdir(exist_ok=True)

        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("LLM EXTRACTION DEBUG LOG\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"File: {file_name}\n")
            f.write(f"Attempt: {attempt}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Exception Type: {type(exception).__name__}\n")
            f.write(f"Exception Message: {str(exception)}\n")
            f.write(f"Exception Repr: {repr(exception)}\n\n")

            f.write("=" * 80 + "\n")
            f.write("SYSTEM PROMPT\n")
            f.write("=" * 80 + "\n")
            f.write(self.extraction_prompt + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("USER PROMPT (without PDF base64)\n")
            f.write("=" * 80 + "\n")
            f.write(user_prompt + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("RAW LLM RESPONSE\n")
            f.write("=" * 80 + "\n")
            f.write(raw_response + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("FULL EXCEPTION TRACEBACK\n")
            f.write("=" * 80 + "\n")
            f.write(traceback.format_exc())

        return debug_path

    async def extract_expense(self, pdf_path: Path, file_name: str, max_retries: int = 3) -> ExtractedExpense:
        """Extract expense data from a receipt PDF.

        Args:
            pdf_path: Path to the receipt PDF
            file_name: Original filename
            max_retries: Maximum number of retry attempts

        Returns:
            ExtractedExpense with parsed data

        Raises:
            Exception: If extraction fails after retries
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Extracting expense data from receipt",
                    pdf_path=str(pdf_path),
                    file_name=file_name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )

                # Read PDF file as bytes
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()

                # Run agent with PDF using BinaryContent
                user_prompt = "Extract the medical expense information from this receipt PDF."

                # Log the request (without full PDF data to avoid flooding logs)
                logger.info(
                    "Sending PDF to LLM for extraction",
                    file_name=file_name,
                    pdf_size_bytes=len(pdf_bytes),
                    user_prompt=user_prompt,
                )

                result = await self.agent.run(
                    [
                        user_prompt,
                        BinaryContent(data=pdf_bytes, media_type='application/pdf'),
                    ],
                    message_history=[]
                )

                # Capture raw response for debugging
                raw_response = str(result)

                # Log that we got a response
                logger.info(
                    "Received LLM response",
                    file_name=file_name,
                    response_preview=raw_response[:200],
                )

                # pydantic-ai returns structured output in the 'output' attribute
                expense = result.output

                logger.info(
                    "Successfully extracted expense data",
                    file_name=file_name,
                    provider=expense.provider,
                    date=str(expense.date_of_service),
                    amount=str(expense.amount_to_claim),
                )

                return expense

            except Exception as e:
                logger.error(
                    "Extraction attempt failed",
                    file_name=file_name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    debug_log=str(self._write_debug_log(
                        file_name=file_name,
                        user_prompt=user_prompt if 'user_prompt' in locals() else "N/A",
                        raw_response=raw_response if 'raw_response' in locals() else "N/A",
                        exception=e,
                        attempt=attempt + 1,
                    )),
                    exc_info=True,
                )

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    # Last attempt failed
                    logger.error("All retry attempts exhausted", file_name=file_name, max_retries=max_retries)
                    raise
