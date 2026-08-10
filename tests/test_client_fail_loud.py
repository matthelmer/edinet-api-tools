"""get_documents_by_date must fail loud on EDINET's in-body errors.

EDINET returns HTTP 200 with an error JSON body on auth failures
({"StatusCode": 401, "message": "Access denied..."}), so transport-level
error handling never fires and `.get('results', [])` silently reads the
failure as an empty filing day. Found by the maintainer's first hands-on
0.8.0 session (2026-08-10): a malformed key produced `[]`, not an error.

Rule: a body with an error StatusCode (or metadata.status != 200) raises;
a healthy body with zero results (weekend, holiday) stays a legitimate
empty list.
"""
import pytest
from unittest.mock import patch

from edinet_tools._client import _ApiClient
from edinet_tools.exceptions import APIError, AuthenticationError


def _client():
    return _ApiClient(api_key='test_key')


class TestInBodyErrorsRaise:
    def test_401_body_raises_authentication_error(self):
        body = {"StatusCode": 401,
                "message": "Access denied due to invalid subscription key."}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            with pytest.raises(AuthenticationError):
                _client().get_documents_by_date('2026-08-07')

    def test_non_auth_error_body_raises_api_error(self):
        body = {"StatusCode": 500, "message": "Internal server error."}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            with pytest.raises(APIError):
                _client().get_documents_by_date('2026-08-07')

    def test_metadata_error_status_raises_api_error(self):
        # EDINET v2 also reports failures inside metadata.status.
        body = {"metadata": {"status": "404", "message": "not found"}}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            with pytest.raises(APIError):
                _client().get_documents_by_date('2026-08-07')

    def test_error_message_carries_edinet_text(self):
        body = {"StatusCode": 401,
                "message": "Access denied due to invalid subscription key."}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            with pytest.raises(AuthenticationError) as exc_info:
                _client().get_documents_by_date('2026-08-07')
        assert 'invalid subscription key' in str(exc_info.value)


class TestHealthyBodiesStillWork:
    def test_results_returned(self):
        body = {"metadata": {"status": "200"},
                "results": [{"docID": "S100TEST", "docTypeCode": "120"}]}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            docs = _client().get_documents_by_date('2026-08-07')
        assert len(docs) == 1

    def test_empty_day_is_legitimate_not_an_error(self):
        # Saturdays/holidays: healthy status, zero filings — must NOT raise.
        body = {"metadata": {"status": "200"}, "results": []}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            assert _client().get_documents_by_date('2026-08-09') == []

    def test_doc_type_filter_still_applies(self):
        body = {"metadata": {"status": "200"},
                "results": [{"docID": "A", "docTypeCode": "120"},
                            {"docID": "B", "docTypeCode": "350"}]}
        with patch('edinet_tools._client.fetch_documents_list', return_value=body):
            docs = _client().get_documents_by_date('2026-08-07', doc_type='350')
        assert [d['docID'] for d in docs] == ['B']
