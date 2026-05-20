"""Shared fixtures for all tests."""
from src.agents import utils as agent_utils


def pytest_runtest_setup(item):
    """Reset shared caches before each test."""
    agent_utils._OPENCODE_FREE_MODEL_CACHE = None
    agent_utils.clear_rate_limit_cache()
