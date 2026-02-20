# Claim Submission — Full Flow

## Overview

**Full mode**: Submit claims with provider information and receipt upload. More complete but slower.

Use this flow when the user wants to attach receipts and include provider details.

Required data per claim:
- Provider name
- Provider address
- Amount to claim
- Date of service
- Receipt file path

---

## Workflow (10 Steps)

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
6. Take a snapshot and verify the field displays the correct dollar amount

**IMPORTANT**: Do NOT use any form autofill — it bypasses currency masking and disables the Next button.

### Step 3: Click Next

1. Take a snapshot to find the "Next" or "Continue" button
2. Click it
3. Wait for the provider/date section to load

### Step 4: Add Provider

1. Take a snapshot and click "Add provider" button
2. Search for the provider name
3. If the provider exists in search results:
   - Select it from the list
4. If the provider is NOT found:
   - Click "Add new provider" or similar option
   - Enter the provider name
   - Enter the provider address
   - If a 2FA / verification prompt appears: **pause and ask the user** to complete it, then wait for them to confirm before continuing
5. Save/confirm the provider selection

### Step 5: Enter Date of Service

1. Take a snapshot to find the date input field
2. Enter the date in MM/DD/YYYY format
   - Convert from YYYY-MM-DD: `2026-01-15` → `01/15/2026`
3. Confirm the date entry

### Step 6: Upload Receipt

1. Take a snapshot to find the file upload input or "Add documents" button
2. Ask the user to confirm the receipt file is accessible at its path
3. Use `browser_file_upload` to upload the receipt file
4. Wait for the upload to complete (may take a few seconds)
5. Verify the file appears as attached

**Note**: If the file upload button is not visible, look for an "Add documents" link and click it first.

### Step 7: Review Details

Verify all information on the review page:
- **Amount**: Matches the claim amount — VERIFY
- **Provider**: Matches the provider name — VERIFY
- **Date**: Matches the date of service — VERIFY
- **Receipt**: File is attached — VERIFY

If anything is wrong, go back and correct it before submitting.

### Step 8: Submit Claim

1. Take a snapshot to find the "Submit" or "Submit reimbursement" button
2. Click it
3. Wait for the confirmation page to load

### Step 9: Capture Confirmation

1. Take a snapshot of the confirmation page
2. Extract the confirmation number — it typically looks like `CLAIM-XXXXXXXX` or a similar alphanumeric code
3. DO NOT make up or guess a confirmation number — extract it from the actual page
4. If you cannot find a confirmation number, take a screenshot and ask the user to read it

### Step 10: Complete

1. Update the CSV: set `claimed` to `true` and `claim_confirmation_id` to the confirmation number
2. Report success to the user: "Claim submitted successfully. Confirmation: [ID]"
3. If more unclaimed rows remain in the CSV, ask the user if they want to continue with the next claim

---

## Rules for Full Mode

1. Always verify you're on the correct page before taking actions
2. Take a snapshot after each navigation to understand page structure
3. Double-check amounts match EXACTLY before submitting
4. If 2FA appears during provider addition, pause and ask the user to complete it
5. Extract the confirmation number carefully — it's critical for tracking
6. If anything fails or looks wrong, explain clearly what you see
7. Do NOT make up confirmation numbers
8. For currency fields with masking, ALWAYS use `browser_type` with cents value

---

## Tips

- Currency masking: type digits only (e.g., `7500`), the mask adds `$` and decimal point
- Use `browser_wait_for` for slow-loading pages and file uploads
- Dismiss any popups before interacting with the form
- Be patient with file uploads — they may take several seconds
- If stuck, take a snapshot to understand what's on screen
- Verify each step succeeded before proceeding to the next
