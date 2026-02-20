---
name: optum-hsa-claims
description: 'Process medical receipts and submit HSA reimbursement claims to Optum Bank. Use this skill when the user mentions: "submit HSA claims", "file medical expense reimbursements", "process medical receipts for HSA", "submit receipts to Optum Bank", "claim HSA reimbursement", "I have medical receipts", "HSA claim", or wants to file reimbursement claims for medical expenses.'
---

# Optum HSA Claims Skill

You help users process medical receipts and submit HSA reimbursement claims to Optum Bank. You extract expense data from receipt images/PDFs using your vision capability, save it to a CSV file, and use Playwright MCP tools to automate claim submission.

---

## Step 0: Verify Playwright MCP is Available

Before anything else, confirm the Playwright MCP tools are available by checking for `mcp__plugin_playwright_playwright__browser_navigate` in your tool list.

- If the tool is **available**: proceed with the workflow.
- If the tool is **not available**: tell the user:
  > "The Playwright MCP server is required for browser automation. Please install it and restart Claude Code, then try again. See: https://github.com/microsoft/playwright-mcp"
  >
  > "You can still process receipts and save them to CSV without Playwright — just let me know if you'd like to do that."

  Stop here if the user only wants browser automation.

---

## Step 1: Collect Receipts

Ask the user to provide their receipt files. Accept any format Claude can read natively:
- PDF (preferred — contains full text)
- PNG, JPG, JPEG, HEIC (images — Claude uses vision)
- Any other image format

Say:
> "Please share the receipt files you'd like to process. You can provide PDFs or images (PNG, JPG, HEIC, etc.)."

Wait for the user to provide the files before proceeding.

---

## Step 2: Extract Expense Data

Read `./references/extraction-prompt.md` for the detailed extraction rules.

For each provided receipt file:

1. Read/view the file using your native capabilities (no subprocess needed)
2. Apply the extraction rules from `extraction-prompt.md`
3. Extract: provider name, provider address, date of service, amount to claim

Apply these rules carefully:
- Only extract information VISIBLE on the document
- Never use external knowledge for addresses
- Distinguish receipts (payment made) from bills/invoices (payment requested)
- Extract patient-paid amount only (not insurance amounts)

---

## Step 3: User Review and Correction

Present all extracted data in a clear table:

```
| # | File Name | Provider | Date of Service | Amount |
|---|-----------|----------|-----------------|--------|
| 1 | receipt1.pdf | EnVision Eye Care | 2026-01-15 | $160.89 |
| 2 | receipt2.pdf | Costco Pharmacy | 2026-02-03 | $45.23 |
```

Ask the user:
> "Please review this extracted data. Is everything correct? If any field needs correction, let me know (e.g., 'The amount for receipt 2 should be $48.00')."

Allow corrections:
- Apply any corrections the user provides
- Re-display the corrected table
- Ask for final confirmation before writing to CSV

Do not proceed until the user explicitly confirms the data is correct.

---

## Step 4: Save to CSV

### CSV Location

Determine the current year from the date(s) of service (or today's date if ambiguous). Save to:
```
~/Documents/HSA-Claims/YYYY/expenses.csv
```

Where `YYYY` is the 4-digit year. All receipts for the same year accumulate in one file.

### CSV Format

```csv
file_name,provider,provider_address,date_of_service,amount_to_claim,claimed,claim_confirmation_id
```

Column definitions:
- `file_name`: Original filename of the receipt
- `provider`: Provider name as extracted
- `provider_address`: Single-line address or "Not Found"
- `date_of_service`: YYYY-MM-DD format
- `amount_to_claim`: Numeric only (e.g., `160.89`)
- `claimed`: `false` for new entries
- `claim_confirmation_id`: Empty for new entries

### Write/Append Logic

1. Create `~/Documents/HSA-Claims/YYYY/` if it does not exist (use Bash `mkdir -p`)
2. If `expenses.csv` does not exist: create it with the header row, then append new rows
3. If `expenses.csv` exists:
   - Read the existing file
   - Check for existing rows with matching `file_name` (deduplication)
   - Skip any file already in the CSV
   - **Never modify rows where `claimed=true`**
   - Append only new rows

### After Writing

Report to the user:
- CSV path: `~/Documents/HSA-Claims/YYYY/expenses.csv`
- Number of new entries added
- Total unclaimed amount (sum of `amount_to_claim` where `claimed=false`)

---

## Step 5: Claim Now or Save for Later

Ask the user:
> "Your receipts have been saved to CSV. Would you like to submit these claims to Optum Bank now, or save them for later?"

**If save for later**:
> "Your claims are saved at `~/Documents/HSA-Claims/YYYY/expenses.csv`. Whenever you're ready to submit, just say 'submit my HSA claims' and I'll pick up where we left off."

Stop here.

**If submit now**: continue to Step 6.

---

## Step 6: Choose Workflow Mode

Ask the user:
> "Which submission flow would you prefer?
>
> **Simplified** (recommended): Submits amount and date only. Faster and more reliable. No provider search or receipt upload needed.
>
> **Full**: Includes provider search, address, and receipt file upload. More complete but slower."

- If **Simplified**: read `./references/claim-submission-simplified.md` for the flow instructions
- If **Full**: read `./references/claim-submission-full.md` for the flow instructions

Also read `./references/claim-submission-base.md` for Playwright tool guidance that applies to both flows.

---

## Step 7: Request Login

Before starting automation, tell the user:
> "I'll open the Optum Bank website now. Please log in when prompted, then let me know when you're ready and I'll continue with the claim submission."

Navigate to:
```
https://account.optumbank.com/account/expenses/new?expense-type=reimbursement
```

Wait for the user to confirm they are logged in before proceeding with claim submission.

---

## Step 8: Submit Claims via Playwright MCP

### Load All Unclaimed Claims

Read `~/Documents/HSA-Claims/YYYY/expenses.csv` and collect ALL rows where `claimed=false`.

**Important**: This includes any previously saved unclaimed receipts, not just those just processed. A user may have accumulated unclaimed receipts from multiple sessions.

### Submit Each Claim

For each unclaimed expense, follow the workflow from the reference file (simplified or full).

After each successful submission:
1. Update the CSV row: set `claimed` to `true`, set `claim_confirmation_id` to the confirmation number
2. Report to the user: "✓ Claim submitted — [Provider] $[Amount] — Confirmation: [ID]"

If a claim fails:
1. Report the error clearly
2. Ask the user: "This claim failed. Would you like to retry, skip it, or stop?"
3. Do NOT mark the row as claimed on error

### Post-Submission Summary

After processing all claims, show a summary:
```
Submission Complete
-------------------
Submitted: N claims — Total: $XXX.XX
Skipped:   N claims
Failed:    N claims

Confirmed claim IDs:
  - [Provider] $[Amount] → [Confirmation ID]
  ...
```

---

## Key Rules

- **Never hallucinate** data — only extract what is visibly printed on receipts
- **Never mark as claimed on error** — atomicity guarantee
- **Never modify** rows where `claimed=true`
- **Never skip** deduplication check when appending to CSV
- **Always confirm** extracted data with the user before writing to CSV
- **Always wait** for user login confirmation before submitting claims
- **Currency masking**: type digits in cents (e.g., `7500` for `$75.00`) using `browser_type`
- **Date format**: convert YYYY-MM-DD to MM/DD/YYYY for form entry
