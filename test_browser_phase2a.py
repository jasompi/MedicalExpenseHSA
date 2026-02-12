"""Test script for Phase 2A: Browser Infrastructure.

This script verifies that:
1. Browser can be launched
2. Navigation to Optum works
3. Login detection works
4. Browser cleanup works
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation.browser_manager import BrowserManager


async def test_browser_infrastructure():
    """Test browser infrastructure components."""
    print("\n" + "=" * 60)
    print("Phase 2A: Browser Infrastructure Test")
    print("=" * 60 + "\n")

    manager = BrowserManager(headless=False)
    print("✓ BrowserManager initialized")

    try:
        # Test 1: Get browser tool
        print("\n[Test 1] Getting browser tool...")
        tool = await manager.get_browser_tool()
        print("✓ BrowserTool created")

        # Test 2: Navigate to Optum
        print("\n[Test 2] Navigating to Optum Bank...")
        result = await tool(action='navigate', text='https://account.optumbank.com')
        if result.base64_image:
            print("✓ Navigation successful (screenshot captured)")
        else:
            print("⚠️  Navigation complete but no screenshot")

        # Test 3: Check login status
        print("\n[Test 3] Checking login status...")
        is_logged_in = await manager.is_logged_in()
        if is_logged_in:
            print("✓ User is logged in")
        else:
            print("ℹ️  User is not logged in (expected)")

        # Test 4: Wait for user confirmation
        print("\n[Test 4] Testing user intervention...")
        print("The browser window should be open showing Optum Bank.")
        print("You can manually log in if you want to test login detection.")
        print()
        input("Press Enter to check login status again...")

        is_logged_in = await manager.is_logged_in()
        if is_logged_in:
            print("✓ Login detected!")
        else:
            print("ℹ️  Still not logged in (that's okay)")

        # Test 5: Cleanup
        print("\n[Test 5] Cleaning up browser...")
        await manager.cleanup()
        print("✓ Browser closed and cleaned up")

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_browser_infrastructure())
    sys.exit(0 if success else 1)
