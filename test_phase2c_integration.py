#!/usr/bin/env python3
"""Integration test for Phase 2C claim submission system.

Tests that all components are properly integrated without actually submitting claims:
- Imports and dependencies
- ClaimSubmitter initialization
- BrowserManager and browser tool creation
- Tool collection setup
- Agent loop preparation
- CSV integration
- User intervention manager
"""

import os
import sys
import asyncio
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        from src.automation.claim_submitter import ClaimSubmitter
        from src.automation.browser_manager import BrowserManager
        from src.automation.agent_loop import claim_submission_loop
        from src.automation.optum_tools import OptumToolCollection, WaitForUserTool, SubmitClaimTool
        from src.automation.browser_tool import BrowserTool
        from src.automation.user_intervention import UserInterventionManager
        from src.automation.state_tracker import StateTracker
        from src.automation.prompts import get_claim_submission_system_prompt
        from src.core.models import ExpenseRecord
        from src.core.csv_manager import CSVManager
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_environment_config():
    """Test that required environment variables are set."""
    print("\nTesting environment configuration...")

    required_vars = ['ANTHROPIC_API_KEY']
    optional_vars = ['OPTUM_URL', 'CLAIM_MODEL', 'MAX_CLAIM_RETRIES', 'BROWSER_HEADLESS']

    missing_required = []
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)

    if missing_required:
        print(f"  ⚠ Missing required environment variables: {', '.join(missing_required)}")
        print(f"  ℹ Set these in .env file for end-to-end testing")
        # Don't fail - this is informational for the user
    else:
        print(f"  ✓ ANTHROPIC_API_KEY: {'*' * 10}{os.getenv('ANTHROPIC_API_KEY')[-4:]}")

    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✓ {var}: {value}")
        else:
            print(f"  ⚠ {var}: not set (will use default)")

    return True  # Always pass, just inform user


def test_browser_manager():
    """Test BrowserManager initialization and configuration."""
    print("\nTesting BrowserManager...")

    try:
        from src.automation.browser_manager import BrowserManager

        # Test headless=False
        manager = BrowserManager(headless=False)
        print(f"  ✓ BrowserManager created (headless=False)")

        # Test headless=True
        manager_headless = BrowserManager(headless=True)
        print(f"  ✓ BrowserManager created (headless=True)")

        return True
    except Exception as e:
        print(f"  ✗ BrowserManager test failed: {e}")
        return False


def test_user_intervention_manager():
    """Test UserInterventionManager initialization."""
    print("\nTesting UserInterventionManager...")

    try:
        from src.automation.user_intervention import UserInterventionManager

        # Test CLI mode
        ui_cli = UserInterventionManager(streamlit_mode=False)
        print(f"  ✓ UserInterventionManager created (CLI mode)")

        # Test Streamlit mode
        ui_streamlit = UserInterventionManager(streamlit_mode=True)
        print(f"  ✓ UserInterventionManager created (Streamlit mode)")

        return True
    except Exception as e:
        print(f"  ✗ UserInterventionManager test failed: {e}")
        return False


def test_state_tracker():
    """Test StateTracker initialization and operations."""
    print("\nTesting StateTracker...")

    try:
        from src.automation.state_tracker import StateTracker
        from src.core.models import ExpenseRecord

        tracker = StateTracker()
        print(f"  ✓ StateTracker created")

        # Create mock expenses
        mock_expenses = [
            ExpenseRecord(
                file_name="test1.pdf",
                provider="Test Provider",
                provider_address="123 Test St",
                date_of_service=datetime(2026, 1, 15).date(),
                amount_to_claim=Decimal("100.00"),
                processing_timestamp=datetime.now(),
                claimed=False
            ),
            ExpenseRecord(
                file_name="test2.pdf",
                provider="Another Provider",
                provider_address="456 Test Ave",
                date_of_service=datetime(2026, 1, 20).date(),
                amount_to_claim=Decimal("50.00"),
                processing_timestamp=datetime.now(),
                claimed=False
            )
        ]

        tracker.initialize(mock_expenses)
        print(f"  ✓ Initialized with {len(mock_expenses)} mock expenses")

        # Test state transitions
        tracker.mark_in_progress("test1.pdf")
        print(f"  ✓ Marked test1.pdf as in_progress")

        tracker.mark_completed("test1.pdf", "CLAIM-12345678")
        print(f"  ✓ Marked test1.pdf as completed")

        tracker.mark_failed("test2.pdf", "Test error")
        print(f"  ✓ Marked test2.pdf as failed")

        # Test statistics
        stats = tracker.get_statistics()
        print(f"  ✓ Generated statistics: {stats}")

        return True
    except Exception as e:
        print(f"  ✗ StateTracker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_optum_tools():
    """Test OptumToolCollection and custom tools."""
    print("\nTesting Optum tools...")

    try:
        from src.automation.optum_tools import OptumToolCollection, WaitForUserTool, SubmitClaimTool
        from src.automation.browser_tool import BrowserTool

        # Create browser tool
        browser_tool = BrowserTool()
        print(f"  ✓ BrowserTool created")

        # Create tool collection
        tools = OptumToolCollection(browser_tool)
        print(f"  ✓ OptumToolCollection created")
        print(f"    Tools available: {list(tools.tool_map.keys())}")

        # Test tool parameters
        params = tools.to_params()
        print(f"  ✓ Generated {len(params)} tool parameter definitions")

        # Verify expected tools
        expected_tools = ["browser", "wait_for_user", "submit_claim"]
        for tool_name in expected_tools:
            if tool_name in tools.tool_map:
                print(f"    ✓ {tool_name} present")
            else:
                print(f"    ✗ {tool_name} missing")
                return False

        return True
    except Exception as e:
        print(f"  ✗ Optum tools test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prompt_generation():
    """Test system prompt generation."""
    print("\nTesting prompt generation...")

    try:
        from src.automation.prompts import get_claim_submission_system_prompt
        from src.core.models import ExpenseRecord

        mock_expense = ExpenseRecord(
            file_name="test.pdf",
            provider="Test Provider",
            provider_address="123 Test St, City, ST 12345",
            date_of_service=datetime(2026, 1, 15).date(),
            amount_to_claim=Decimal("100.00"),
            processing_timestamp=datetime.now(),
            claimed=False
        )

        prompt = get_claim_submission_system_prompt(mock_expense)
        print(f"  ✓ Generated system prompt ({len(prompt)} characters)")

        # Check that expense details are in prompt
        if "Test Provider" in prompt and "$100.00" in prompt:
            print(f"  ✓ Expense details correctly embedded in prompt")
        else:
            print(f"  ✗ Expense details not found in prompt")
            return False

        return True
    except Exception as e:
        print(f"  ✗ Prompt generation test failed: {e}")
        return False


def test_claim_submitter_init():
    """Test ClaimSubmitter initialization with mock data."""
    print("\nTesting ClaimSubmitter initialization...")

    try:
        from src.automation.claim_submitter import ClaimSubmitter
        from src.core.csv_manager import CSVManager
        import tempfile

        # Check for API key first
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("  ⚠ Skipping ClaimSubmitter init (ANTHROPIC_API_KEY not set)")
            print("  ℹ Set ANTHROPIC_API_KEY in .env to test ClaimSubmitter initialization")
            return True  # Don't fail the test, just skip

        # Create temp directory for test
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "test_expenses.csv"
            receipts_path = temp_path / "receipts"
            receipts_path.mkdir()

            # Create CSV manager
            csv_manager = CSVManager(csv_path)
            print(f"  ✓ Created CSVManager with temp CSV: {csv_path}")

            # Create ClaimSubmitter
            submitter = ClaimSubmitter(
                csv_manager=csv_manager,
                receipts_folder=receipts_path,
                headless=False,
                streamlit_mode=False
            )
            print(f"  ✓ ClaimSubmitter initialized")

            # Check components
            if submitter.csv_manager:
                print(f"  ✓ CSVManager attached")
            if submitter.browser_manager:
                print(f"  ✓ BrowserManager attached")
            if submitter.user_intervention:
                print(f"  ✓ UserInterventionManager attached")
            if submitter.state_tracker:
                print(f"  ✓ StateTracker attached")
            if submitter.api_key:
                print(f"  ✓ API key loaded from environment")
            else:
                print(f"  ✗ API key not found")
                return False

        return True
    except Exception as e:
        print(f"  ✗ ClaimSubmitter initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_browser_tool_creation():
    """Test that browser tool can be created and configured."""
    print("\nTesting browser tool creation...")

    try:
        from src.automation.browser_manager import BrowserManager

        manager = BrowserManager(headless=False)

        # Get browser tool (this doesn't actually launch browser until first action)
        browser_tool = await manager.get_browser_tool()
        print(f"  ✓ Browser tool obtained from manager")
        print(f"    Note: Browser will launch on first action call")

        # Cleanup
        await manager.cleanup()
        print(f"  ✓ Browser manager cleanup successful")

        return True
    except Exception as e:
        print(f"  ✗ Browser tool creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all integration tests."""
    print("=" * 70)
    print("Phase 2C Integration Test Suite")
    print("=" * 70)

    results = {}

    # Synchronous tests
    results['imports'] = test_imports()
    results['environment'] = test_environment_config()
    results['browser_manager'] = test_browser_manager()
    results['user_intervention'] = test_user_intervention_manager()
    results['state_tracker'] = test_state_tracker()
    results['optum_tools'] = test_optum_tools()
    results['prompt_generation'] = test_prompt_generation()
    results['claim_submitter'] = test_claim_submitter_init()

    # Async tests
    results['browser_tool'] = asyncio.run(test_browser_tool_creation())

    # Summary
    print("\n" + "=" * 70)
    print("Test Results Summary")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_flag in results.items():
        status = "✓ PASS" if passed_flag else "✗ FAIL"
        print(f"{status}  {test_name}")

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✓ All integration tests passed! Ready for end-to-end testing.")
        print("\nNext step: Run with real claims using:")
        print("  python -m src.main submit /path/to/receipts")
    else:
        print("✗ Some tests failed. Please fix issues before proceeding.")
        sys.exit(1)

    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
