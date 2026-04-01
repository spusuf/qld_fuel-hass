"""Test fixtures for qld_fuel component tests."""

import asyncio
import sys

import pytest


@pytest.fixture
def event_loop_policy(socket_enabled):
    """Use a Windows-safe loop policy without overriding event_loop."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def wait_for_stop_scripts_after_shutdown():
    """Avoid plugin patching into Home Assistant script helpers in stubbed tests."""
    return True
