# Claim Submission — Simplified Flow

## Overview

**Simplified mode**: Submit claims with amount and date only. Provider and document upload are NOT required.

This flow is faster and more reliable. Use it when the user does not need to attach receipts or specify a provider.

---

## Workflow (8 Steps)

### Step 1: Verify Page

Check if you're on the claim submission form.
- Expected URL: `https://account.optumbank.com/account/expenses/new?expense-type=reimbursement`
- If not on this URL, navigate there now
- Take a snapshot to confirm the form is visible

### Step 2: Enter Amount

Find the amount input field and enter the claim amount.

1. Take a snapshot to get element references
2. Click the amount input field using its `ref` to focus it
3. The field has currency masking — type digits in cents, NOT dollars:
   - Example: For `$75.00` → type `7500`
   - Example: For `$160.89` → type `16089`
   - To compute cents: multiply dollar amount by 100 and round to integer
4. Use `browser_type` with the cents value
5. Wait ~0.5 seconds for the currency mask to format
6. Take a snapshot and verify the field displays the correct dollar amount (e.g., `$75.00`)

**IMPORTANT**: Do NOT use any form autofill — it bypasses currency masking and disables the Next button.

### Step 3: Click Next

1. Take a snapshot to find the "Next" or "Continue" button reference
2. Click it
3. Wait for the next page/section to load

### Step 4: Enter Date of Service

1. Take a snapshot to find the date input field
2. Enter the date in MM/DD/YYYY format
   - Convert from YYYY-MM-DD: `2026-01-15` → `01/15/2026`
3. Click "Save" or equivalent button to confirm the date

### Step 5: Review Details

The form shows a review page. Verify:
- **Amount**: Matches the claim amount — VERIFY this is correct
- **Date**: Matches the date of service — VERIFY this is correct
- **Provider**: Empty/blank — This is **CORRECT** — DO NOT fill it
- **Documents**: Empty/blank — This is **CORRECT** — DO NOT add documents

**CRITICAL**: Even though Provider and Documents fields may show "Add provider" / "Add documents" links, do NOT click them. Empty provider and documents are expected and correct in simplified mode.

If amount or date is wrong, go back and fix it before submitting.

### Step 6: Submit Claim

1. Take a snapshot to find the "Submit" or "Submit reimbursement" button
2. Click it
3. Wait for the confirmation page to load

### Step 7: Capture Confirmation

1. Take a snapshot of the confirmation page
2. Extract the confirmation number — it typically looks like `CLAIM-XXXXXXXX` or a similar alphanumeric code
3. DO NOT make up or guess a confirmation number — extract it from the actual page
4. If you cannot find a confirmation number, take a screenshot and ask the user to read it

### Step 8: Complete

1. Update the CSV: set `claimed` to `true` and `claim_confirmation_id` to the confirmation number
2. Report success to the user: "Claim submitted successfully. Confirmation: [ID]"
3. If more unclaimed rows remain in the CSV, ask the user if they want to continue with the next claim

---

## Rules for Simplified Mode

1. Always verify you're on the correct page before taking actions
2. Take a snapshot after each navigation to understand page structure
3. Double-check amounts match EXACTLY before submitting
4. Extract the confirmation number carefully — it's critical for tracking
5. If anything fails or looks wrong, explain clearly what you see
6. Do NOT make up confirmation numbers
7. For currency fields with masking, ALWAYS use `browser_type` with cents value
8. **NEVER add provider information** — this is simplified mode
9. **NEVER upload documents** — this is simplified mode
10. Empty Provider and Documents fields are EXPECTED and CORRECT

---

## Tips

- Currency masking: type digits only (e.g., `7500`), the mask adds `$` and decimal point
- Use `browser_wait_for` for slow-loading pages
- Dismiss any popups before interacting with the form
- If stuck, take a snapshot to understand what's on screen
- Verify each step succeeded before proceeding to the next
