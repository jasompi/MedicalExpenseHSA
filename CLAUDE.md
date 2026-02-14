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

## Environment Configuration

The `.env` file configures API access and automation behavior. See `.env.example` for template.

### API Keys (Required - at least one)

**OpenAI** (for receipt processing):
```env
OPENAI_API_KEY=sk-proj-your_key_here
```
- Obtain from: https://platform.openai.com/api-keys
- Used for: GPT-4o models for receipt extraction

**Anthropic** (for receipt processing and claim submission):
```env
ANTHROPIC_API_KEY=sk-ant-your_key_here
```
- Obtain from: https://console.anthropic.com/
- Used for: Claude models for receipt extraction AND claim submission agent
- Required for: Phase 2 claim submission (no alternative)

**Google Gemini** (for receipt processing):
```env
GEMINI_API_KEY=your_gemini_key_here
```
- Obtain from: https://aistudio.google.com/app/apikey
- Used for: Gemini models for receipt extraction
- Current default: `gemini-2.5-flash` is set as MODEL_NAME in `llm_extractor.py`

### Claim Submission Configuration (Optional)

**OPTUM_URL**:
```env
OPTUM_URL=https://account.optumbank.com/account/expenses/new?expense-type=reimbursement
```
- Default provided in .env.example
- Change only if Optum changes their URL structure

**CLAIM_MODEL**:
```env
CLAIM_MODEL=claude-sonnet-4-5-20250929
```
- LLM model for browser agent
- Requires ANTHROPIC_API_KEY
- Alternatives: Any Claude Sonnet 4+ model
- Apple internal gateway: `anthropic.claude-sonnet-4-20250514-v1:0`

**MAX_CLAIM_RETRIES**:
```env
MAX_CLAIM_RETRIES=3
```
- Number of retry attempts per claim on error
- Range: 1-10 (recommended: 2-5)
- Higher values = more resilient to transient errors
- Lower values = faster failure on persistent issues

**BROWSER_HEADLESS**:
```env
BROWSER_HEADLESS=false
```
- Values: `true` or `false` (case-insensitive)
- `false` (default): Visible browser window
  - Recommended for: debugging, manual intervention, initial setup
  - Allows user to see agent actions in real-time
- `true`: Invisible browser (headless mode)
  - Recommended for: automated runs, server environments
  - Note: Manual intervention (2FA, file upload) still works via CLI prompts

**INTERVENTION_TIMEOUT**:
```env
INTERVENTION_TIMEOUT=300
```
- Seconds to wait for manual actions (login, 2FA, file upload)
- Default: 300 seconds (5 minutes)
- Adjust based on user responsiveness needs

### Model Selection Guide

**Receipt Extraction Models**:
- Currently set in code: `src/processors/llm_extractor.py`
- `MODEL_NAME = GEMINI_MODEL_NAME` (current default: `"gemini-2.5-flash"`)
- Alternatives: `OPENAI_MODEL_NAME` (`"gpt-4o-2024-11-20"`), `ANTHROPIC_MODEL_NAME` (`"claude-3-7-sonnet-20250219"`)
- Requirements: Must support PDF/vision input via `BinaryContent`
- Set the corresponding API key: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`

**Claim Submission Model**:
- Set via `CLAIM_MODEL` in .env
- Requirements: Strong reasoning, tool use, vision capability
- Recommended: Claude Sonnet 4+ models
- Not recommended: Haiku (insufficient reasoning), GPT models (different tool format)

### Apple Internal Gateway

For Apple employees using internal Anthropic gateway:

```env
CLAIM_MODEL=anthropic.claude-sonnet-4-20250514-v1:0
```

**How it works**:
- Model name starting with `anthropic.` triggers gateway mode
- Automatically calls `/usr/local/bin/appleconnect getToken` for auth
- Uses `https://floodgate.g.apple.com/api/anthropic` endpoint
- Bypasses SSL verification (required for internal infrastructure)
- No external API key required (uses Apple SSO)

**Requirements**:
- Must be on Apple network
- Must have `appleconnect` CLI installed
- Must be authenticated via Apple SSO

See `.env.example` for complete configuration template with comments.

## Running the Application

```bash
# Process receipts from a folder
# CSV file is created in the receipts folder by default
python -m src.main process /path/to/receipts

# Process a SINGLE PDF file (debug mode)
# CSV file is created with the same basename as the PDF
python -m src.main process /path/to/receipts/receipt.pdf
# This creates receipt.csv in the same directory

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
uv run python -m src.main process /path/to/receipts/receipt.pdf
```

**CSV Output Defaults**:
- **Folder mode**: `expenses.csv` is created in the receipts folder
- **Single file mode**: `{basename}.csv` is created in the same directory as the PDF (e.g., `receipt.pdf` → `receipt.csv`)
- Both modes: Override with the `--csv` option

## Project Structure

```
medicalexpensehsa/
├── src/                 # All source code
│   ├── core/            # Core data models and state management
│   │   ├── models.py            # ExtractedExpense and ExpenseRecord models
│   │   ├── csv_manager.py       # Atomic CSV operations
│   │   └── signal_handler.py    # Graceful Ctrl-C handling
│   ├── processors/      # Receipt processing pipeline
│   │   ├── llm_extractor.py     # Vision-based extraction with pydantic-ai
│   │   └── receipt_processor.py # Main orchestration
│   ├── automation/      # Browser automation (Phase 2)
│   │   ├── claim_submitter.py   # Main orchestration for multi-claim workflow
│   │   ├── browser_manager.py   # Browser lifecycle & login detection
│   │   ├── agent_loop.py        # LLM-driven agent loop with Anthropic API
│   │   ├── browser_tool.py      # Playwright automation (20+ actions)
│   │   ├── optum_tools.py       # Custom tools (wait_for_user, submit_claim)
│   │   ├── state_tracker.py     # Progress tracking & retry logic
│   │   ├── user_intervention.py # CLI prompts for manual actions
│   │   ├── message_handler.py   # API response processing
│   │   ├── coordinate_scaling.py # Vision coordinate translation
│   │   ├── prompts.py           # System prompt templates
│   │   ├── base_tool.py         # Base tool abstractions
│   │   └── browser_tool_utils/  # JavaScript utilities for DOM interaction
│   ├── utils/           # Utilities
│   │   ├── logger.py            # Structured logging with structlog
│   │   └── exceptions.py        # Custom exception hierarchy
│   ├── prompts/         # LLM prompts
│   │   ├── claim_submission_simplified.txt  # Simplified mode prompt
│   │   ├── claim_submission_full.txt        # Full mode prompt
│   │   ├── receipt_extraction.txt           # Receipt processing prompt
│   │   └── element_finding.txt              # Element search prompt
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
- **Sequential processing**: Single-threaded asyncio model
- **Resume capability**: Rerunning skips already-processed files
- **Error history**: JSON-encoded error log per expense

### Graceful Shutdown

- Ctrl-C sets shutdown flag (doesn't force exit)
- Processors check flag between operations
- Current operation completes before exit
- Press Ctrl-C twice to force exit

## Browser Automation Architecture (Phase 2 - Complete)

The claim submission automation is derived from [Anthropic's browser-use-demo quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/browser-use-demo), which demonstrates using Claude with computer use tools.

### Attribution

The `src/automation/` code adapts the browser-use pattern from Anthropic's quickstart. Key adaptations for HSA claims:
- Domain-specific tools for Optum operations
- User intervention hooks for manual actions
- CSV state management integration
- Retry logic with user decision prompts
- Two-mode workflow (simplified vs full)
- Apple internal gateway support

### Key Components

**ClaimSubmitter** (`claim_submitter.py`) - Main orchestrator for multi-claim workflow. Loads unclaimed expenses, coordinates BrowserManager/StateTracker/UserInterventionManager, executes retry logic, handles user intervention, updates CSV atomically.

**BrowserManager** (`browser_manager.py`) - Manages persistent Playwright browser lifecycle. Lazy initialization, maintains session across claims, detects login via URL/DOM, polls until login complete.

**Agent Loop** (`agent_loop.py`) - LLM-driven automation via structured tools. Builds messages, calls Anthropic API with tools, processes responses, executes tools, preserves conversation history, returns structured results with turn offset tracking.

**BrowserTool** (`browser_tool.py`) - Playwright automation with 20+ actions (navigate, click, type, read_page, scroll, etc.). Element references via DOM tree, coordinate scaling for vision accuracy, persistent browser session.

**OptumToolCollection** (`optum_tools.py`) - Complete tool set: BrowserTool + WaitForUserTool (manual actions) + SubmitClaimTool (completion signal).

**StateTracker** (`state_tracker.py`) - Tracks claim status (pending → in_progress → completed/failed/skipped), records timestamps/confirmation IDs/errors/retry counts, provides statistics.

**UserInterventionManager** (`user_intervention.py`) - CLI prompts for manual actions (login, 2FA, file upload), error decision prompts (retry/skip/quit), progress display.

**MessageHandler** (`message_handler.py`) - Processes API responses (text + tool_use blocks), executes tools, maintains conversation history.

**CoordinateScaler** (`coordinate_scaling.py`) - Translates vision coordinates (1456x819) to viewport (1920x1080). Auto-detects when scaling needed based on coordinate magnitude.

### Tool-Based Architecture

The automation follows the Anthropic computer use pattern:

1. **System Prompt**: Agent receives claim context and workflow instructions
2. **Tool Definitions**: Agent has access to browser, wait_for_user, submit_claim tools
3. **Agentic Loop**: Agent analyzes page → decides tool → executes → sees result → repeats until completion
4. **Completion Signals**: `submit_claim(confirmation_id)` for success, `wait_for_user(reason, instruction)` for manual intervention

**Tool Interface** (via `BaseAnthropicTool`):
- `to_params()` - Returns tool definition for Anthropic API
- `async __call__(**kwargs)` - Executes action and returns `ToolResult`
- `ToolResult`: `output` (text), `error`, `base64_image`, `system` (message)

### Workflow Modes

**Simplified Mode** (default - `src/prompts/claim_submission_simplified.txt`):
- Context: amount + date
- Workflow: Navigate → enter amount → enter date → submit → extract confirmation → call submit_claim
- Advantages: Faster, more reliable, no provider search, no file upload
- Best for: Simple reimbursements

**Full Mode** (`--full-flow` flag - `src/prompts/claim_submission_full.txt`):
- Context: provider + address + amount + date + file_name
- Workflow: Navigate → search provider → verify address → enter amount/date → wait for file upload → submit → extract confirmation
- Advantages: Complete workflow, provider details, receipt attached
- Best for: Claims requiring documentation

### Error Recovery

**Retry Logic**: Up to MAX_CLAIM_RETRIES attempts per claim. On error, prompt user: retry/skip/quit. Reset to pending on retry, mark skipped if exhausted.

**User Intervention**: Agent calls `wait_for_user(reason, instruction)` → pause → display prompt → user completes action → resume with preserved context + turn offset.

**Resumable**: `manual_step`, `2fa` (agent continues after user action)
**Non-Resumable**: `login`, `unexpected_error` (report as failure)

### Apple Internal Gateway

When `CLAIM_MODEL` starts with `anthropic.`:
- Acquire token via `/usr/local/bin/appleconnect getToken`
- Use `https://floodgate.g.apple.com/api/anthropic` endpoint
- Pass `auth_token` instead of `api_key`
- Disable SSL verification
- Skip prompt caching beta flag

### Development Patterns

**Adding Browser Action**:
1. Add to `Actions` enum in `browser_tool.py`
2. Update `BROWSER_TOOL_INPUT_SCHEMA` with parameters
3. Implement handler method `async def _my_action()`
4. Add to `__call__` dispatcher
5. Update tool description

**Modifying System Prompts**:
- Edit `src/prompts/claim_submission_simplified.txt` or `claim_submission_full.txt`
- Use `{variable}` placeholders (replaced by ClaimSubmitter)
- Structure: SYSTEM_CAPABILITY → CURRENT_CLAIM → WORKFLOW → ERROR_HANDLING → COMPLETION
- Test with `--log-level DEBUG` to see agent thinking

**Debugging Agent**:
```bash
uv run python -m src.main submit --log-level DEBUG --log-file debug.log
```
- Logs agent text, tool calls, tool results, screenshots, API metadata
- Look for `[Auto-Scale]` logs for coordinate scaling
- Verify viewport 1920x1080, base dimensions 1456x819

**Coordinate Scaling**: Auto-detects based on coordinate magnitude. Only scales when coords < viewport. Logs actions for debugging.

### Performance

**Per-Claim**: Simplified 30-60s, Full 60-120s. Depends on page load, LLM latency, form complexity.

**Resources**: Browser 200-500MB RAM, Python 100-200MB RAM, 5-15K API tokens per claim.

**Batch**: Sequential (not parallel), login session persists, state saved after each claim.

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
ANTHROPIC_MODEL_NAME = "claude-3-7-sonnet-20250219"
OPENAI_MODEL_NAME = "gpt-4o-2024-11-20"
GEMINI_MODEL_NAME = "gemini-2.5-flash"

MODEL_NAME = GEMINI_MODEL_NAME  # Current default
```

To change models:
1. Edit the `MODEL_NAME` constant in `llm_extractor.py` to use one of the predefined model names
2. Set the appropriate API key in `.env`:
   - For OpenAI models: `OPENAI_API_KEY=sk-proj-...`
   - For Anthropic models: `ANTHROPIC_API_KEY=sk-ant-...`
   - For Google Gemini models: `GEMINI_API_KEY=...`

Supported models (must have PDF/vision capability):
- Google Gemini: `gemini-2.5-flash`, `gemini-1.5-pro`
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
- ✅ Phase 2A: Browser infrastructure (browser manager, browser tool)
- ✅ Phase 2B: Agent system (agent loop, tool collection, message handler)
- ✅ Phase 2C: Claim orchestration (claim submitter, state tracker, user intervention)
- ✅ Phase 2D: Advanced features (coordinate scaling, two-mode workflow, Apple gateway)

## Documentation

- `README.md` - User-facing documentation
- `.env.example` - Configuration template