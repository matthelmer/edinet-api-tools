"""Pytest configuration for EDINET API Tools tests.

The autouse `set_test_env_vars` fixture below scrubs API credentials for
every non-integration test so accidental real-network calls fail loud.
Integration tests (marked with @pytest.mark.integration) keep the real
EDINET_API_KEY so they can talk to the live API.

Note: prior versions of this file shipped ~9 stand-alone sample/mock
fixtures (sample_csv_data, mock_llm_response, etc.). Verified 2026-05-23
that none were consumed by any test in the suite — dead code, removed.
Add new fixtures here only when at least one test will use them; otherwise
inline the test data with the test that needs it (easier to reason about,
no spooky-action-at-a-distance shape coupling).
"""
import os

import pytest


@pytest.fixture(autouse=True)
def set_test_env_vars(request):
    """Scrub credentials for the duration of every non-integration test.

    Integration tests (@pytest.mark.integration) keep the real
    EDINET_API_KEY so they can hit the live API; everything else gets a
    placeholder so any accidental real-network code path fails on auth
    rather than silently hitting prod.
    """
    is_integration_test = request.node.get_closest_marker('integration') is not None

    original_env = {}
    test_env_vars = {}
    if not is_integration_test:
        test_env_vars['EDINET_API_KEY'] = 'test-api-key'

    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


@pytest.fixture(autouse=True)
def reset_module_client():
    """Reset the module-level client singleton after every test.

    Without this, a test that calls configure() while EdinetClient is
    patched leaves the stale Mock in edinet_tools._client._client, and
    every later test that touches the module-level API silently talks to
    that Mock (found 2026-07-30: two tests had been skip-passing on the
    leaked Mock's empty results since the singleton pattern landed).
    """
    yield
    from edinet_tools import _client
    _client._reset_client()
