# Medical Expense HSA Claim Automation

Automated tool for processing medical receipt PDFs and filing HSA claims to Optum Bank.

## Features

- **Receipt Processing**: Extract medical expense data from PDF receipts using LLM vision
- **CSV State Management**: Track all expenses with atomic operations
- **Automated Claim Filing**: Browser automation for Optum Bank (Phase 2)
- **Graceful Shutdown**: Ctrl-C handling with resume capability
- **Vision-Capable LLMs**: Support for OpenAI GPT-4o and Anthropic Claude models

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your API key:

```env
# For OpenAI (default model: gpt-4o)
OPENAI_API_KEY=sk-proj-your_key_here

# Or for Anthropic (change MODEL_NAME in src/processors/llm_extractor.py)
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

**Note**: To change the LLM model, edit the `MODEL_NAME` constant in `src/processors/llm_extractor.py`.

### 3. Process Receipts

```bash
# Process receipts from a folder
uv run python -m src.main process /path/to/receipts

# Or use the shorthand
uv run python main.py process /path/to/receipts
```

### 4. Check Status

```bash
# Check expense status
uv run python -m src.main status

# Or with custom CSV location
uv run python -m src.main status --csv /path/to/expenses.csv
```

## Usage

### Commands

```bash
# Process receipts and extract data to CSV
# Creates expenses.csv in the receipts folder by default
uv run python -m src.main process [RECEIPTS_FOLDER]

# Specify a custom CSV location if needed
uv run python -m src.main process [RECEIPTS_FOLDER] --csv /path/to/expenses.csv

# Submit unclaimed expenses (Phase 2)
uv run python -m src.main submit

# Run full workflow (process + submit)
uv run python -m src.main run [RECEIPTS_FOLDER]

# Show expense status
uv run python -m src.main status

# Or specify CSV location
uv run python -m src.main status --csv /path/to/expenses.csv
```

### Receipt Processing

The agent:
1. Scans the receipts folder for PDF files
2. Skips files already in `expenses.csv`
3. Sends each PDF to the LLM for vision-based extraction
4. Extracts: provider, address, date, amount paid by patient
5. Saves to `expenses.csv` in the same folder as the receipts

**Important**: The agent only extracts amounts paid by the patient (out-of-pocket), not insurance payments.

### Graceful Shutdown

Press Ctrl-C during processing to gracefully stop after the current receipt. Running the command again will resume from where it left off.

## Project Structure

```
medicalexpensehsa/
├── src/
│   ├── core/            # Core data models and CSV management
│   ├── processors/      # Receipt processing and LLM extraction
│   ├── automation/      # Browser automation (Phase 2)
│   ├── utils/           # Logging and utilities
│   └── main.py          # CLI entry point
└── Receipts/            # Your receipts folder
    ├── *.pdf            # Receipt PDFs
    └── expenses.csv     # Generated expense tracking database
```

## CSV Format

The `expenses.csv` file tracks all expenses:

| Field | Description |
|-------|-------------|
| provider | Provider name |
| provider_address | Provider address |
| date_of_service | Service date (YYYY-MM-DD) |
| file_name | Original PDF filename (unique key) |
| amount_to_claim | Amount paid by patient |
| claimed | True/False |
| processing_timestamp | When added to CSV |
| claim_timestamp | When claimed (if claimed) |
| claim_confirmation_id | Optum confirmation ID |
| error_history | JSON-encoded error log |

## Development

### Phase 1: Receipt Processing ✓

- Foundation (config, models, logging) ✓
- LLM vision-based extraction with BinaryContent ✓
- CSV state management with atomic operations ✓
- CLI interface ✓

### Phase 2: Claim Automation (Coming Next)

- Playwright browser automation
- Optum Bank navigation
- Claim form filling
- Atomic claim submission

## Requirements

- Python 3.12+
- LLM API key (OpenAI or Anthropic)
- Vision-capable model (GPT-4o, Claude 3.7 Sonnet, etc.)
- PDF receipts

## License

MIT
