# Claim Submission — Base Playwright Guidance

## Playwright MCP Tool Mapping

When submitting claims, use these Playwright MCP tools directly:

| Action | Playwright MCP Tool |
|--------|---------------------|
| Navigate to URL | `mcp__plugin_playwright_playwright__browser_navigate` |
| Click element | `mcp__plugin_playwright_playwright__browser_click` |
| Type text | `mcp__plugin_playwright_playwright__browser_type` |
| Read page / get element refs | `mcp__plugin_playwright_playwright__browser_snapshot` |
| Take screenshot | `mcp__plugin_playwright_playwright__browser_take_screenshot` |
| Wait for element | `mcp__plugin_playwright_playwright__browser_wait_for` |
| Handle dialog | `mcp__plugin_playwright_playwright__browser_handle_dialog` |
| Press key | `mcp__plugin_playwright_playwright__browser_press_key` |
| Select option | `mcp__plugin_playwright_playwright__browser_select_option` |
| Upload file | `mcp__plugin_playwright_playwright__browser_file_upload` |

## General Navigation Guidelines

1. **Always take a snapshot before interacting** — After navigating or clicking, always call `browser_snapshot` to get element references before interacting. Element references (ref values) are more reliable than coordinates.

2. **Verify page state** — After each navigation, take a snapshot to confirm you're on the expected page before proceeding.

3. **Prefer element references over coordinates** — Use `ref` values from snapshots for clicks and interactions when possible.

4. **Wait for slow-loading pages** — Use `browser_wait_for` if pages take time to load after navigation or form submission.

5. **Read text from snapshots** — Extract text content from `browser_snapshot` output rather than from screenshots.

## Popup and Dialog Handling

If you encounter any of the following, dismiss them before continuing:
- Feedback request dialog → Look for "No thanks", "Close", or "X" button
- "Do you need help?" dialog → Dismiss it
- Cookie notices → Accept or dismiss them
- Any blocking overlay → Remove or dismiss it before continuing

After dismissing a popup, take a new snapshot to confirm the popup is gone.

## Currency Field Masking

The Optum claim form uses currency masking on the amount field:
- The field **expects digits only** (no dollar sign, no decimal point)
- Type the amount in cents: `7500` formats to `$75.00`
- Use `browser_type` (NOT any form-fill shortcut) so the masking script runs
- After typing, wait briefly (0.5s) for the currency mask to format the value
- Verify the field displays the correct dollar amount before proceeding

**IMPORTANT**: Do NOT use any form autofill or direct value-setting approach — it bypasses the currency masking and will leave the "Next" button disabled.

## Date Field Entry

- Date format expected by the form: MM/DD/YYYY
- Convert your YYYY-MM-DD date to MM/DD/YYYY before entering
- Example: `2026-01-15` → type `01/15/2026`

## Error Recovery

If an action fails:
1. Take a screenshot to see current page state
2. Take a snapshot to get fresh element references
3. Try the action again with updated references
4. If DOM-based actions aren't working, try coordinate-based clicks as fallback
5. If still failing, report clearly what you see on screen

## Completion Tracking

When a claim is successfully submitted:
1. Capture the confirmation number from the confirmation page (typically looks like "CLAIM-XXXXXXXX" or similar)
2. Update the CSV row: set `claimed` to `true` and record the `claim_confirmation_id`
3. Report success to the user with the confirmation number

If a claim fails or must be skipped:
1. Report the error clearly
2. Ask the user whether to retry, skip this claim, or stop
3. Do NOT mark the row as claimed
