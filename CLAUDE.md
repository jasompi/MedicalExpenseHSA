# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedicalExpenseHSA is a Python 3.12 automation tool that:
1. Processes medical receipt PDFs using LLM vision to extract expense data
2. Stores extracted data in CSV with atomic operations for state management
3. Automates HSA claim filing through Optum Bank using Playwright browser automation

The project uses `uv` for dependency management and pydantic-ai as the LLM wrapper.

## Development Setup

Install dependencies:

```bash
uv sync
```

If network/proxy issues occur, see `NEXT_STEPS.md` for alternative installation methods.

Install Playwright browsers:

```bash
playwright install
```

Configure environment (copy `.env.example` to `.env` and edit):

```bash
cp .env.example .env
# Edit .env with your LLM API key and paths
```

## Running the Application

```bash
# Process receipts from a folder (receipts folder is required)
# CSV file is created in the receipts folder by default
python -m src.main process /path/to/receipts

# Check expense status
python -m src.main status

# Submit claims (Phase 2)
python -m src.main submit

# Run full workflow
python -m src.main run /path/to/receipts

# With optional flags
python -m src.main --log-level DEBUG --log-file debug.log process /path/to/receipts --csv custom_expenses.csv
```

Or with uv:

```bash
uv run python -m src.main process /path/to/receipts
```

**Note**: By default, `expenses.csv` is created in the same folder as the receipts. You can override this with the `--csv` option.

## Project Structure

```
medicalexpensehsa/
├── src/                 # All source code
│   ├── core/            # Core data models and state management
│   │   ├── models.py            # ExtractedExpense and ExpenseRecord models
│   │   ├── csv_manager.py       # Thread-safe atomic CSV operations
│   │   └── signal_handler.py    # Graceful Ctrl-C handling
│   ├── processors/      # Receipt processing pipeline
│   │   ├── llm_extractor.py     # Vision-based extraction with pydantic-ai
│   │   └── receipt_processor.py # Main orchestration
│   ├── automation/      # Browser automation (Phase 2)
│   ├── utils/           # Utilities
│   │   ├── logger.py            # Structured logging with structlog
│   │   └── exceptions.py        # Custom exception hierarchy
│   ├── prompts/         # LLM prompts
│   └── main.py          # CLI entry point with Click
├── .env                 # Environment variables (API keys)
├── .env.example         # Environment template
└── expenses.csv         # Generated state store
```

## Architecture

### Receipt Processing Pipeline (Phase 1 - Complete)

1. **PDF Discovery**: Glob receipts folder for *.pdf files (flat directory only)
2. **Deduplication**: Skip files already in expenses.csv
3. **LLM Extraction**: Send PDFs directly to vision-capable LLM (GPT-4o, Claude Sonnet)
   - Extract: provider, address, date of service, patient-paid amount
   - Important: Only extract amount paid by patient (NOT insurance payment)
4. **CSV Storage**: Atomically write to CSV with temp file + rename pattern
5. **Error Handling**: Log errors, skip bad files, continue processing

### State Management

- **CSV as source of truth**: expenses.csv tracks all processed receipts
- **Atomic operations**: All CSV writes use temp file + rename for atomicity
- **Thread-safe**: File locks prevent concurrent access issues
- **Resume capability**: Rerunning skips already-processed files
- **Error history**: JSON-encoded error log per expense

### Graceful Shutdown

- Ctrl-C sets shutdown flag (doesn't force exit)
- Processors check flag between operations
- Current operation completes before exit
- Press Ctrl-C twice to force exit

## Key Implementation Details

### CSV Operations Must Be Atomic

The `CSVManager` class uses this pattern for all writes:

```python
# Write to temp file
temp_path = self.csv_path.with_suffix('.tmp')
# ... write data ...
# Atomic rename (POSIX guarantee)
temp_path.replace(self.csv_path)
```

This ensures that:
- No partial writes if process is killed
- Safe for concurrent access (with file locks)
- CSV is always in valid state

### LLM Vision Processing

The `ReceiptExtractor` uses pydantic-ai with structured output and sends PDFs as binary content:

```python
# Initialize agent
agent = Agent(
    MODEL_NAME,  # e.g., "gpt-4o" or "claude-3-7-sonnet-20250219"
    output_type=ExtractedExpense,  # Pydantic model
    system_prompt=EXTRACTION_PROMPT,
)

# Send PDF as binary content (not base64 text)
result = await agent.run([
    user_prompt,
    BinaryContent(data=pdf_bytes, media_type='application/pdf'),
])
```

This ensures:
- PDFs are sent as actual documents, not text
- Type-safe extraction with validation
- Consistent output format
- Automatic retries on failure

### Error Handling Philosophy

- **Receipt processing**: Log error, skip file, continue
- **Claim submission**: Log error, prompt user for decision
- **CSV operations**: Critical failure, halt execution
- **Never mark as claimed on error**: Atomicity guarantee

## Common Development Tasks

### Adding a New Expense Field

1. Update `core/models.py`:
   - Add field to `ExtractedExpense` (LLM output)
   - Add field to `ExpenseRecord` (CSV storage)
   - Update `to_csv_dict()` method
2. Update `core/csv_manager.py`:
   - Add column name to `CSV_HEADERS`
3. Update LLM prompt in `processors/llm_extractor.py`:
   - Add extraction instruction
4. Migration: Existing CSV files need manual column addition

### Changing LLM Model

The model is configured via the `MODEL_NAME` constant in `src/processors/llm_extractor.py`:

```python
# Model constants - change these to use different models
# MODEL_NAME = "claude-3-7-sonnet-20250219"
MODEL_NAME = "gpt-4o"
```

To change models:
1. Edit the `MODEL_NAME` constant in `llm_extractor.py`
2. Set the appropriate API key in `.env`:
   - For OpenAI models: `OPENAI_API_KEY=sk-proj-...`
   - For Anthropic models: `ANTHROPIC_API_KEY=sk-ant-...`

Supported models (must have PDF/vision capability):
- OpenAI: `gpt-4o`, `gpt-4o-mini`
- Anthropic: `claude-3-7-sonnet-20250219`, `claude-3-5-sonnet-20241022`

### Testing with Sample Receipts

Sample receipts are in `/Users/jasompi/Documents/Receipts/2026`:
- 21 PDF files with various formats
- Naming convention: `YYYYMMDD Provider Name.pdf`
- Mix of single and multi-page documents

## Implementation Status

- ✅ Phase 1A: Foundation (config, models, logging, exceptions)
- ✅ Phase 1B: Core processing (PDF extraction, CSV manager, LLM extractor)
- ✅ Phase 1C: Orchestration (receipt processor, CLI)
- ⏳ Phase 2A: Browser infrastructure (browser manager)
- ⏳ Phase 2B: Optum navigation (page interactions, form filling)
- ⏳ Phase 2C: Claim orchestration (submission workflow)

## Documentation

- `README.md` - User-facing documentation
- `.env.example` - Configuration template