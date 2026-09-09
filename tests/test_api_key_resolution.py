"""The API key is resolved when a request is built, not when the package is
imported. Before 0.8.4 `config.EDINET_API_KEY` was read once at import and the
low-level fetchers used it as their fallback, so a key set afterwards — the
notebook / `load_dotenv()`-after-import path — went out as the literal string
`None`, and `configure()` had no effect on `api.fetch_document`. Importing the
package also wrote a warning to the ROOT logger, hijacking the host's logging
even on offline paths (found 2026-09-09)."""
import importlib
import logging
import os
import urllib.error
from unittest.mock import patch

import pytest

from edinet_tools import _client, api, config
from edinet_tools.exceptions import AuthenticationError


@pytest.fixture(autouse=True)
def _clean_key(monkeypatch):
    monkeypatch.delenv('EDINET_API_KEY', raising=False)
    _client._reset_client()
    yield
    _client._reset_client()


def _captured_query(fn, *args, **kwargs):
    seen = {}
    def fake_urlopen(req, timeout=None):
        seen['url'] = req if isinstance(req, str) else req.full_url
        raise urllib.error.URLError('stop')
    with patch.object(api.urllib.request, 'urlopen', fake_urlopen):
        try:
            fn(*args, max_retries=1, **kwargs)
        except Exception:
            pass
    return seen['url']


def test_key_set_after_import_is_used(monkeypatch):
    monkeypatch.setenv('EDINET_API_KEY', 'late-key')
    assert 'Subscription-Key=late-key' in _captured_query(api.fetch_document, 'S100ABC')
    assert 'Subscription-Key=late-key' in _captured_query(api.fetch_documents_list, '2026-09-01')


def test_configure_reaches_the_low_level_fetchers():
    _client.configure(api_key='configured-key')
    assert 'Subscription-Key=configured-key' in _captured_query(api.fetch_document, 'S100ABC')


def test_configure_none_falls_back_to_the_environment(monkeypatch):
    _client.configure(api_key='configured-key')
    _client.configure(api_key=None)
    monkeypatch.setenv('EDINET_API_KEY', 'env-key')
    assert 'Subscription-Key=env-key' in _captured_query(api.fetch_document, 'S100ABC')


def test_empty_string_override_is_not_a_key(monkeypatch):
    monkeypatch.setenv('EDINET_API_KEY', 'env-key')
    assert 'Subscription-Key=env-key' in _captured_query(api.fetch_document, 'S100ABC', api_key='')


def test_http_error_raised_by_fetch_document_carries_no_key(monkeypatch):
    """End to end: a non-200 response must not leave the key in the raised
    HTTPError's url or message."""
    monkeypatch.setenv('EDINET_API_KEY', 'secret-key-123')
    class Resp:
        headers = {}
        def getcode(self): return 500
        def read(self): return b''
        def __enter__(self): return self
        def __exit__(self, *a): return False
    with patch.object(api.urllib.request, 'urlopen', return_value=Resp()), patch.object(api.time, 'sleep'):
        with pytest.raises(urllib.error.HTTPError) as ei:
            api.fetch_document('S100ABC', max_retries=1)
    assert 'secret-key-123' not in (ei.value.url or '')
    assert 'secret-key-123' not in str(ei.value)


def test_explicit_override_wins():
    _client.configure(api_key='configured-key')
    assert 'Subscription-Key=explicit' in _captured_query(api.fetch_document, 'S100ABC', api_key='explicit')


def test_missing_key_raises_before_any_request_is_made():
    calls = []
    with patch.object(api.urllib.request, 'urlopen', side_effect=lambda *a, **k: calls.append(a)):
        with pytest.raises(AuthenticationError):
            api.fetch_document('S100ABC')
        with pytest.raises(AuthenticationError):
            api.fetch_documents_list('2026-09-01')
    assert calls == []


def test_import_does_not_write_to_the_root_logger(caplog):
    with caplog.at_level(logging.WARNING, logger=''):
        importlib.reload(config)
    assert not [r for r in caplog.records if 'EDINET_API_KEY' in r.getMessage()]


def test_error_messages_do_not_carry_the_key():
    assert api._redact_key('https://h/x?type=5&Subscription-Key=secret123') == 'https://h/x?type=5&Subscription-Key=***'
    assert api._redact_key('https://h/x?type=5') == 'https://h/x?type=5'
