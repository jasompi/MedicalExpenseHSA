"""Custom tools for Optum Bank claim submission.

Provides specialized tools that extend the browser tool with Optum-specific
operations like waiting for user intervention and marking claims complete.
"""

from typing import Any, Literal, Optional, cast
from anthropic.types.beta import BetaToolUnionParam
from src.automation.base_tool import BaseAnthropicTool, ToolResult, ToolError
from src.automation.browser_tool import BrowserTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WaitForUserTool(BaseAnthropicTool):
    """Tool for agent to request user intervention.

    Use this when you need the user to perform a manual action like
    logging in, completing 2FA, or handling an unexpected situation.
    """

    name: Literal["wait_for_user"] = "wait_for_user"

    def to_params(self) -> BetaToolUnionParam:
        """Return tool parameters for API."""
        return cast(
            BetaToolUnionParam,
            {
                "name": self.name,
                "description": "Request user intervention for manual actions that cannot be automated (login, 2FA, unexpected dialogs). Call this when you need the user to complete a step manually.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why user intervention is needed",
                            "enum": ["login", "2fa", "manual_step", "unexpected_error"]
                        },
                        "instruction": {
                            "type": "string",
                            "description": "Clear instruction telling the user what to do"
                        }
                    },
                    "required": ["reason", "instruction"]
                }
            }
        )

    async def __call__(
        self,
        reason: str,
        instruction: str,
        **kwargs
    ) -> ToolResult:
        """Request user intervention.

        Args:
            reason: Why intervention is needed (login, 2fa, manual_step, unexpected_error)
            instruction: What the user should do

        Returns:
            ToolResult indicating user should perform action
        """
        logger.info(
            "User intervention requested",
            reason=reason,
            instruction=instruction
        )

        # Return a result that signals intervention is needed
        # The ClaimSubmitter will handle the actual user prompting
        return ToolResult(
            output=f"User intervention requested: {reason}",
            system=f"WAIT_FOR_USER|{reason}|{instruction}"
        )


class SubmitClaimTool(BaseAnthropicTool):
    """Tool to signal successful claim submission.

    Call this ONLY after you have successfully submitted the claim
    and extracted the confirmation number from the success page.
    """

    name: Literal["submit_claim"] = "submit_claim"

    def to_params(self) -> BetaToolUnionParam:
        """Return tool parameters for API."""
        return cast(
            BetaToolUnionParam,
            {
                "name": self.name,
                "description": "Signal that claim was successfully submitted and confirmation number extracted. ONLY call this after verifying the claim was submitted and you have the confirmation number.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confirmation_id": {
                            "type": "string",
                            "description": "The confirmation number from Optum (e.g., 'CLAIM-12345678')"
                        },
                        "verified": {
                            "type": "boolean",
                            "description": "True if you verified the confirmation number is displayed on screen"
                        }
                    },
                    "required": ["confirmation_id", "verified"]
                }
            }
        )

    async def __call__(
        self,
        confirmation_id: str,
        verified: bool,
        **kwargs
    ) -> ToolResult:
        """Mark claim as successfully submitted.

        Args:
            confirmation_id: Confirmation number from Optum
            verified: Whether agent verified the confirmation on screen

        Returns:
            ToolResult with confirmation details
        """
        if not confirmation_id or not confirmation_id.strip():
            raise ToolError("Confirmation ID cannot be empty")

        if not verified:
            logger.warning(
                "Claim submitted but not verified",
                confirmation_id=confirmation_id
            )

        logger.info(
            "Claim submission complete",
            confirmation_id=confirmation_id,
            verified=verified
        )

        return ToolResult(
            output=f"Claim submitted successfully! Confirmation ID: {confirmation_id}",
            system=f"CLAIM_COMPLETE|{confirmation_id}|{verified}"
        )


class OptumToolCollection:
    """Collection of tools for Optum claim submission.

    Combines the browser tool with custom Optum-specific tools.
    """

    def __init__(self, browser_tool: BrowserTool):
        """Initialize tool collection.

        Args:
            browser_tool: BrowserTool instance for web automation
        """
        self.browser_tool = browser_tool
        self.wait_for_user = WaitForUserTool()
        self.submit_claim = SubmitClaimTool()

        # Create tool map for easy lookup
        self.tools = [
            self.browser_tool,
            self.wait_for_user,
            self.submit_claim,
        ]
        self.tool_map = {tool.name: tool for tool in self.tools}

        logger.info(
            "OptumToolCollection initialized",
            tools=[tool.name for tool in self.tools]
        )

    def to_params(self) -> list[BetaToolUnionParam]:
        """Convert all tools to API parameters.

        Returns:
            List of tool parameter dicts for Anthropic API
        """
        return [tool.to_params() for tool in self.tools]
