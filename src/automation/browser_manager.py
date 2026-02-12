"""Browser lifecycle management for claim submission.

Manages a persistent browser instance that maintains login state across multiple claim submissions.
"""

import asyncio
from typing import Optional
from src.automation.browser_tool import BrowserTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """Manage browser lifecycle and login state detection."""

    def __init__(self, headless: bool = False):
        """Initialize browser manager.

        Args:
            headless: Whether to run browser in headless mode
        """
        self._browser_tool: Optional[BrowserTool] = None
        self._headless = headless
        logger.info("BrowserManager initialized", headless=headless)

    async def get_browser_tool(self) -> BrowserTool:
        """Get or create persistent browser tool.

        The browser is created once and reused across all operations.
        This maintains login sessions and navigation history.

        Returns:
            BrowserTool instance
        """
        if self._browser_tool is None:
            logger.info("Creating new BrowserTool instance")
            self._browser_tool = BrowserTool()
            # Browser will start on first action call
        else:
            logger.debug("Reusing existing BrowserTool instance")

        return self._browser_tool

    async def is_logged_in(self) -> bool:
        """Check if user is logged into Optum Bank.

        Uses multiple heuristics to detect login state:
        1. URL contains 'account.optumbank.com' and NOT a login path
        2. Page contains account-specific elements (via DOM inspection)

        Returns:
            True if logged in, False otherwise
        """
        if self._browser_tool is None or self._browser_tool._page is None:
            logger.debug("No browser or page - not logged in")
            return False

        try:
            current_url = self._browser_tool._page.url
            logger.debug("Checking login status", url=current_url)

            # Check 1: URL-based detection
            if 'account.optumbank.com' in current_url:
                # Check if NOT on login page
                login_indicators = ['login', 'signin', 'sso', 'auth']
                if not any(indicator in current_url.lower() for indicator in login_indicators):
                    logger.info("Login detected via URL", url=current_url)
                    return True

            # Check 2: DOM-based detection (look for account elements)
            # Use read_page to get DOM structure and check for logged-in indicators
            result = await self._browser_tool(action="read_page", text="interactive")

            if result.output:
                # Look for common account indicators in DOM
                logged_in_indicators = [
                    'logout',
                    'sign out',
                    'account menu',
                    'profile',
                    'expenses',
                    'reimbursement'
                ]

                output_lower = result.output.lower()
                if any(indicator in output_lower for indicator in logged_in_indicators):
                    logger.info("Login detected via DOM elements")
                    return True

            logger.debug("No login indicators found")
            return False

        except Exception as e:
            logger.warning("Error checking login status", error=str(e))
            return False

    async def wait_for_login(
        self,
        timeout: int = 300,
        poll_interval: int = 2
    ) -> bool:
        """Wait for user to manually log in.

        Polls the page every poll_interval seconds to check if login completed.

        Args:
            timeout: Maximum seconds to wait for login
            poll_interval: Seconds between login checks

        Returns:
            True if login detected within timeout, False otherwise

        Raises:
            TimeoutError: If login not detected within timeout
        """
        logger.info("Waiting for user to log in", timeout=timeout)

        elapsed = 0
        while elapsed < timeout:
            if await self.is_logged_in():
                logger.info("Login detected successfully", elapsed_time=elapsed)
                return True

            # Wait for poll interval
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            if elapsed % 30 == 0:  # Log every 30 seconds
                logger.debug("Still waiting for login", elapsed=elapsed, remaining=timeout - elapsed)

        logger.error("Login timeout reached", timeout=timeout)
        raise TimeoutError(f"Login not detected within {timeout} seconds")

    async def cleanup(self):
        """Close browser and cleanup resources."""
        if self._browser_tool:
            logger.info("Cleaning up browser")
            try:
                await self._browser_tool.cleanup()
                self._browser_tool = None
                logger.info("Browser cleanup complete")
            except Exception as e:
                logger.error("Error during browser cleanup", error=str(e))
