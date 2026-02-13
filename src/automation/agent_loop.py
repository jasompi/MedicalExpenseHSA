"""Agent loop for HSA claim submission.

Adapted from browser-use-demo sampling loop for the specific use case
of submitting medical expense claims to Optum Bank.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import httpx
from anthropic import Anthropic
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
)

from src.core.models import ExpenseRecord
from src.automation.browser_tool import BrowserTool
from src.automation.optum_tools import OptumToolCollection
from src.automation.message_handler import MessageBuilder, ResponseProcessor
from src.automation.prompts import get_claim_submission_system_prompt
from src.utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"


def _get_apple_auth_token() -> str:
    """Get auth token from Apple Connect for internal gateway.

    Returns:
        Auth token string for Apple's Anthropic gateway

    Raises:
        RuntimeError: If token acquisition fails
    """
    logger.info("Acquiring Apple Connect auth token...")

    try:
        cmd = (
            '/usr/local/bin/appleconnect getToken '
            '-C hvys3fcwcteqrvw3qzkvtk86viuoqv '
            '--token-type=oauth '
            '--interactivity-type=none '
            '-E prod '
            '-G pkce '
            '-o openid,dsid,accountname,profile,groups'
        )
        result = os.popen(cmd).read()
        token = result.split()[-1] if result.strip() else ""

        if not token:
            raise RuntimeError(
                "Failed to get Apple auth token. "
                "Ensure appleconnect CLI is installed and configured."
            )

        logger.info("Successfully acquired Apple Connect auth token")
        return token

    except Exception as e:
        logger.error("Failed to acquire Apple auth token", error=str(e))
        raise RuntimeError(
            f"Failed to authenticate with Apple Connect: {str(e)}. "
            "Ensure appleconnect CLI is installed and configured."
        )


def _create_anthropic_client(model: str, api_key: str) -> Anthropic:
    """Create Anthropic client with appropriate configuration.

    Determines whether to use Apple's internal Anthropic gateway or the
    standard Anthropic API based on the model name prefix.

    Args:
        model: Model name (e.g., "anthropic.claude-sonnet-4-20250514-v1:0"
               or "claude-sonnet-4-5-20250929")
        api_key: API key for standard Anthropic API (used if not using Apple gateway)

    Returns:
        Configured Anthropic client instance

    Raises:
        RuntimeError: If Apple auth token acquisition fails
    """
    if model.startswith("anthropic."):
        # Use Apple internal gateway
        logger.info(
            "Using Apple internal Anthropic gateway",
            model=model,
            base_url="https://floodgate.g.apple.com/api/anthropic"
        )
        auth_token = _get_apple_auth_token()

        # Create HTTP client with SSL verification disabled for internal Apple gateway
        # This is necessary for connecting to internal Apple infrastructure
        logger.warning(
            "SSL verification disabled for Apple internal gateway",
            reason="Required for internal infrastructure connectivity"
        )
        http_client = httpx.Client(verify=False)

        return Anthropic(
            auth_token=auth_token,
            base_url="https://floodgate.g.apple.com/api/anthropic",
            max_retries=4,
            http_client=http_client
        )
    else:
        # Use standard Anthropic API
        logger.info(
            "Using standard Anthropic API",
            model=model,
            base_url="https://api.anthropic.com"
        )
        return Anthropic(
            api_key=api_key,
            max_retries=4
        )


async def claim_submission_loop(
    *,
    expense: ExpenseRecord,
    receipt_path: Path,
    model: str,
    messages: list[BetaMessageParam],
    browser_tool: BrowserTool,
    output_callback: Callable[[BetaContentBlockParam], None],
    tool_output_callback: Callable[[str, str], None],
    api_response_callback: Callable[[httpx.Request | None, httpx.Response | object | None, Exception | None], None],
    api_key: str,
    max_tokens: int = 4096,
    turn_offset: int = 0,
) -> dict:
    """Agent loop for submitting a single claim.

    This is a specialized version of the browser-use-demo sampling_loop
    tailored for HSA claim submission with structured return values.

    Args:
        expense: ExpenseRecord containing claim details
        receipt_path: Path to the PDF receipt file
        model: Model name to use (e.g., "claude-sonnet-4-5-20250929")
        messages: Initial message history
        browser_tool: Persistent BrowserTool instance
        output_callback: Callback for agent text/tool outputs
        tool_output_callback: Callback for tool results
        api_response_callback: Callback for API responses
        api_key: Anthropic API key
        max_tokens: Maximum tokens for response
        turn_offset: Starting turn number (for resumed loops). Default 0.

    Returns:
        Dictionary with:
            - success: bool
            - confirmation_id: str | None
            - error: str | None
            - intervention_needed: str | None (e.g., "login", "2fa", "manual_step")
            - turns_used: int (total turns used in this call)
    """
    logger.info(
        "Starting claim submission loop",
        file_name=expense.file_name,
        provider=expense.provider,
        amount=float(expense.amount_to_claim)
    )

    # Create tool collection with browser and custom tools
    tool_collection = OptumToolCollection(browser_tool)

    # Build system prompt with expense context
    system_prompt = get_claim_submission_system_prompt(expense)
    system = BetaTextBlockParam(
        type="text",
        text=system_prompt,
    )

    # Initialize client
    client = _create_anthropic_client(model, api_key)
    enable_prompt_caching = True

    # Add cache control for prompt caching
    if enable_prompt_caching:
        system = BetaTextBlockParam(
            type="text",
            text=system["text"],
            cache_control=BetaCacheControlEphemeralParam(type="ephemeral"),
        )

    # Result tracking
    result = {
        "success": False,
        "confirmation_id": None,
        "error": None,
        "intervention_needed": None
    }

    try:
        # Agent loop
        turn_count = 0
        max_turns = 50  # Prevent infinite loops

        while turn_count < max_turns:
            turn_count += 1
            cumulative_turn = turn_offset + turn_count  # Track cumulative turns
            logger.info("=" * 60)
            logger.info(f"AGENT TURN {cumulative_turn}/{turn_offset + max_turns}")
            logger.info("=" * 60)

            # Make API call
            logger.info("⏳ Waiting for LLM response...")
            try:
                api_kwargs = {
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "model": model,
                    "system": [system],
                    "tools": tool_collection.to_params(),
                }

                # Apple gateway doesn't support prompt caching beta flag
                if enable_prompt_caching and not model.startswith("anthropic."):
                    api_kwargs["betas"] = [PROMPT_CACHING_BETA_FLAG]
                    response = client.beta.messages.create(**api_kwargs)
                else:
                    response = client.messages.create(**api_kwargs)

                logger.info(f"✓ Received LLM response (stop_reason: {response.stop_reason})")

            except Exception as e:
                logger.error(
                    "API call failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    model=model,
                    exc_info=True
                )
                api_response_callback(None, None, e)
                result["error"] = f"API error: {str(e)}"
                return result

            api_response_callback(None, response, None)

            # Process response
            logger.info("📋 Processing response...")
            processor = ResponseProcessor()
            processed = processor.process_response(response)

            # Log what we received
            if processed.has_text:
                logger.info(f"💬 Agent provided text response")
            if processed.has_tools:
                logger.info(f"🔧 Agent requested {len(processed.tool_uses)} tool call(s)")

            # Output all content blocks
            for content_block in processed.assistant_content:
                output_callback(content_block)

            # Build and append assistant message
            builder = MessageBuilder()
            builder.add_assistant_message(messages, processed.assistant_content)

            # Execute tools if present
            if processed.tool_uses:
                logger.info("🔨 Executing tools...")
                for i, tool_use in enumerate(processed.tool_uses, 1):
                    tool_name = tool_use["name"]
                    tool_input = tool_use["input"]
                    logger.info(f"  [{i}/{len(processed.tool_uses)}] Calling tool: {tool_name}")
                    logger.info(f"      Input: {tool_input}")

                tool_results = await processor.execute_tools(
                    processed.tool_uses,
                    tool_collection,
                    tool_output_callback
                )

                logger.info(f"✓ All tools executed, sending {len(tool_results)} result(s) back to LLM")

                # Check for completion or intervention signals
                for tool_use in processed.tool_uses:
                    tool_name = tool_use["name"]

                    # Check if claim was successfully submitted
                    if tool_name == "submit_claim":
                        confirmation_id = tool_use["input"].get("confirmation_id")
                        if confirmation_id:
                            logger.info(f"✅ CLAIM SUBMITTED - Confirmation: {confirmation_id}")
                            result["success"] = True
                            result["confirmation_id"] = confirmation_id
                            result["turns_used"] = turn_count
                            return result

                    # Check if user intervention is needed
                    elif tool_name == "wait_for_user":
                        reason = tool_use["input"].get("reason")
                        instruction = tool_use["input"].get("instruction")
                        logger.info(f"⏸️  USER INTERVENTION REQUESTED - Reason: {reason}")
                        result["intervention_needed"] = reason
                        result["error"] = f"User intervention required: {instruction}"
                        result["turns_used"] = turn_count
                        return result

                # Add tool results to messages
                builder.add_tool_results(messages, tool_results)

                # Continue loop for next turn
            else:
                # No tools used - agent finished without completion
                logger.warning("Agent finished without calling submit_claim")
                result["error"] = "Agent completed without submitting claim"
                result["turns_used"] = turn_count
                return result

        # Max turns reached
        logger.error("Max turns reached without completion",
                     max_turns=max_turns, cumulative_turn=turn_offset + max_turns)
        result["error"] = f"Agent reached maximum {turn_offset + max_turns} turns without completing submission"
        result["turns_used"] = turn_count
        return result

    except Exception as e:
        logger.error("Claim submission loop failed", error=str(e), exc_info=True)
        result["error"] = f"Unexpected error: {str(e)}"
        result["turns_used"] = turn_count if 'turn_count' in locals() else 0
        return result
