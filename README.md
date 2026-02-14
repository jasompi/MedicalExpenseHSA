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
# For Google Gemini (current default: gemini-2.5-flash)
GEMINI_API_KEY=your_gemini_key_here

# Or for OpenAI (gpt-4o)
OPENAI_API_KEY=sk-proj-your_key_here

# Or for Anthropic (change MODEL_NAME in src/processors/llm_extractor.py)
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

**Note**: To change the LLM model, edit the `MODEL_NAME` constant in `src/processors/llm_extractor.py`.

## Environment Configuration

The project uses `.env` for configuration. Copy `.env.example` to `.env` and configure:

### Required: API Keys

Provide at least one API key:

**For OpenAI models** (gpt-4o, gpt-4o-mini):
```env
OPENAI_API_KEY=sk-proj-your_key_here
```

**For Anthropic models** (claude-3-7-sonnet, claude-sonnet-4-5):
```env
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

**For Google Gemini models** (gemini-2.5-flash):
```env
GEMINI_API_KEY=your_gemini_key_here
```

Note: The default model in `llm_extractor.py` is currently `gemini-2.5-flash`. You need the corresponding API key set.

### Optional: Phase 2 Claim Submission

Configure browser automation for claim filing:

- **`OPTUM_URL`** - Optum Bank claim form URL (default provided)
- **`CLAIM_MODEL`** - Claude model for browser agent (default: `claude-sonnet-4-5-20250929`)
  - Requires `ANTHROPIC_API_KEY`
  - Apple employees can use internal gateway: `anthropic.claude-sonnet-4-20250514-v1:0`
- **`MAX_CLAIM_RETRIES`** - Retry attempts per claim on error (default: 3)
- **`BROWSER_HEADLESS`** - Run browser invisibly: `true`/`false` (default: false)
- **`INTERVENTION_TIMEOUT`** - Wait time for manual actions in seconds (default: 300)

See `.env.example` for complete documentation and default values.

### 3. Process Receipts

```bash
# Process receipts from a folder
uv run python -m src.main process /path/to/receipts

# Process a single PDF file (useful for debugging)
uv run python -m src.main process /path/to/receipts/receipt.pdf
# This creates receipt.csv in the same directory

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
# Process receipts from a folder - extracts data to CSV
# Creates expenses.csv in the receipts folder by default
uv run python -m src.main process [RECEIPTS_FOLDER]

# Process a SINGLE PDF file (debug mode)
# Creates a CSV with the same basename as the PDF (e.g., receipt.pdf -> receipt.csv)
uv run python -m src.main process [PATH_TO_PDF_FILE]

# Specify a custom CSV location if needed (works for both folder and file modes)
uv run python -m src.main process [RECEIPTS_FOLDER] --csv /path/to/expenses.csv
uv run python -m src.main process [PATH_TO_PDF_FILE] --csv /path/to/custom.csv

# Submit unclaimed expenses (Phase 2)
uv run python -m src.main submit

# Run full workflow (process + submit)
uv run python -m src.main run [RECEIPTS_FOLDER or PATH_TO_PDF_FILE]

# Show expense status
uv run python -m src.main status

# Or specify CSV location
uv run python -m src.main status --csv /path/to/expenses.csv
```

### Receipt Processing

**Folder Mode:**
The agent:
1. Scans the receipts folder for PDF files
2. Skips files already in `expenses.csv`
3. Sends each PDF to the LLM for vision-based extraction
4. Extracts: provider, address, date, amount paid by patient
5. Saves to `expenses.csv` in the same folder as the receipts

**Single File Mode (Debug):**
When you specify a single PDF file instead of a folder:
1. Processes only that one PDF file
2. Creates a CSV file with the same basename (e.g., `receipt.pdf` → `receipt.csv`)
3. Useful for debugging extraction issues with specific receipts

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

## Automation Architecture (Phase 2)

The claim submission automation uses a **tool-based agent architecture** derived from [Anthropic's browser-use-demo quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/browser-use-demo).

### Attribution

This implementation adapts the browser-use pattern from Anthropic's browser-use-demo, which demonstrates Claude with computer use tools. Our implementation specializes it for HSA claim submission with:
- Custom Optum-specific tools (`wait_for_user`, `submit_claim`)
- User intervention handling for manual actions (login, 2FA, file upload)
- CSV state management and atomic updates
- Retry logic with user decision prompts
- Two-mode workflow (simplified and full)

### Architecture Overview

```
┌────────────────────────────────────────────────┐
│         ClaimSubmitter (Orchestrator)          │
│  - Multi-claim workflow coordination           │
│  - Browser lifecycle management                │
│  - CSV state updates on completion             │
└──────────┬───────────────────────┬─────────────┘
           │                       │
           ▼                       ▼
  ┌──────────────────┐    ┌────────────────────┐
  │ BrowserManager   │    │  StateTracker      │
  │ - Login detection│    │  - Progress track  │
  │ - Session persist│    │  - Retry logic     │
  └──────────┬───────┘    └────────────────────┘
             │
             ▼
  ┌──────────────────────────────────────────────┐
  │       Agent Loop (LLM-driven automation)     │
  │  - Anthropic API with tool-based control     │
  └──────────┬───────────────────────┬───────────┘
             │                       │
             ▼                       ▼
  ┌──────────────────┐    ┌──────────────────────┐
  │ OptumToolKit     │    │ MessageHandler       │
  │ - browser        │    │ - API formatting     │
  │ - wait_for_user  │    │ - Tool execution     │
  │ - submit_claim   │    │ - History tracking   │
  └──────────┬───────┘    └──────────────────────┘
             │
             ▼
  ┌──────────────────────────────────────────────┐
  │  BrowserTool (Playwright wrapper)            │
  │  - 20+ actions: navigate, click, type, etc.  │
  │  - Coordinate scaling for vision accuracy    │
  │  - DOM reading with element references       │
  └──────────────────────────────────────────────┘
```

### Key Components

**Tool-Based Control**
- LLM agent controls browser through structured tools (Anthropic tool use API)
- 20+ browser actions: `navigate`, `read_page`, `click`, `type`, `scroll`, `screenshot`, etc.
- Custom Optum tools: `wait_for_user` (manual actions), `submit_claim` (completion signal)

**Browser Management**
- Persistent Playwright browser maintains login session across all claims
- Automatic login detection via URL patterns and DOM inspection
- Single browser instance processes all expenses sequentially

**State Tracking**
- CSV-backed state management: pending → in_progress → completed/failed/skipped
- Tracks confirmation IDs, timestamps, errors, retry counts
- Atomic updates only on confirmed success

**Error Recovery**
- Configurable retry logic (default: 3 attempts per claim)
- User intervention for manual steps: login, 2FA, file upload, unexpected errors
- Resume capability preserves conversation history after intervention
- User decides: retry / skip / quit on failures

**Coordinate Scaling**
- Automatic translation from Claude's vision coordinates (1456x819) to viewport (1920x1080)
- Ensures accurate click positioning based on screenshot analysis
- Transparent to agent - coordinates "just work"

### Workflow Modes

**Simplified Mode** (default):
```bash
uv run python -m src.main submit
```
- Submits amount + date only
- No provider search, no file upload
- Faster and more reliable
- Best for simple reimbursements

**Full Mode**:
```bash
uv run python -m src.main submit --full-flow
```
- Includes provider search and address verification
- Agent requests user to upload receipt file manually
- Complete Optum form workflow
- Use when provider details are required

### How It Works

1. **Load Claims**: ClaimSubmitter reads unclaimed expenses from CSV
2. **Browser Setup**: Launch Playwright browser, navigate to Optum
3. **Login**: User logs in manually (detected automatically via URL/DOM)
4. **Agent Loop**: For each expense:
   - Agent analyzes page with `read_page` (DOM tree with element refs)
   - Agent navigates form using `click`, `type`, `scroll` actions
   - Agent calls `wait_for_user` when manual action needed (2FA, file upload)
   - User completes action, agent resumes with preserved context
   - Agent extracts confirmation number from success page
   - Agent calls `submit_claim(confirmation_id)` to mark complete
5. **CSV Update**: Mark as claimed with confirmation ID and timestamp
6. **Error Handling**: On failure, prompt user: retry / skip / quit

### Tool Reference

| Tool | Purpose | Parameters |
|------|---------|------------|
| `browser` | Web automation | `action` (navigate, click, type, etc.), element `ref`, coordinates, text |
| `wait_for_user` | Request manual action | `reason` (login, 2fa, manual_step), `instruction` (what to do) |
| `submit_claim` | Mark claim complete | `confirmation_id` (extracted from page), `verified` (boolean) |

### Technical Details

**Agent Loop**:
- Uses Anthropic Messages API with tool use
- Max 50 turns per claim (configurable)
- Preserves full conversation history for context
- Turn offset tracking for resume after intervention

**Coordinate Scaling**:
- Claude's vision processes images at 1456x819 (16:9 aspect ratio)
- Browser viewport: 1920x1080
- Scaler automatically detects and translates coordinates
- Based on documented Anthropic image processing dimensions

**Apple Internal Gateway**:
- Set `CLAIM_MODEL=anthropic.claude-sonnet-4-20250514-v1:0` in .env
- Acquires auth token via `appleconnect getToken`
- Uses `https://floodgate.g.apple.com/api/anthropic` endpoint
- Automatic SSL verification bypass for internal infrastructure

See `src/automation/` for implementation details.

## Development

### Phase 1: Receipt Processing ✓

- Foundation (config, models, logging) ✓
- LLM vision-based extraction with BinaryContent ✓
- CSV state management with atomic operations ✓
- CLI interface ✓

### Phase 2: Claim Automation ✓

- Tool-based agent architecture ✓
- Playwright browser automation ✓
- Optum Bank navigation ✓
- User intervention handling ✓
- State tracking and retry logic ✓
- Two-mode workflow support ✓
- Coordinate scaling for vision accuracy ✓
- Apple internal gateway support ✓

## Requirements

- Python 3.12+
- LLM API key (Google Gemini, OpenAI, or Anthropic)
- Vision-capable model (Gemini 2.5 Flash, GPT-4o, Claude 3.7 Sonnet, etc.)
- PDF receipts

## License

MIT
