"""
Real API Contract Tests - TIER 2 INTEGRATION

Tests that validate real API contracts and behavior.
Run with: pytest -m integration
Budget: 8-10 API calls per test run to respect API limits.
"""

import pytest
from datetime import date, timedelta

from edinet_tools.api import (
    fetch_documents_list,
    fetch_document,
    get_documents_for_date_range
)


def _load_api_key_or_skip() -> str:
    """Load the real EDINET API key, or skip the test if unavailable.

    python-dotenv is optional dev-convenience tooling, not a runtime
    dependency of edinet-tools (0.8.0 dropped it -- see CHANGELOG). A
    `pip install -e .[dev]` environment (CI's install path) has no reason
    to carry it, so this must not hard-fail on import: fall through to
    reading the environment directly, exactly as a CI runner without a
    .env file already does.
    """
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # no dotenv installed -- rely on the environment as-is

    api_key = os.environ.get('EDINET_API_KEY')

    if not api_key:
        pytest.skip("EDINET_API_KEY not found - integration tests skipped (set it in .env)")
    if len(api_key.strip()) < 10:
        pytest.skip(f"EDINET_API_KEY too short ({len(api_key)} chars) - integration tests skipped")
    return api_key


@pytest.mark.integration
class TestRealAPIContracts:
    """Tests that validate real EDINET API behavior and contracts"""

    def setup_method(self):
        self.api_key = _load_api_key_or_skip()

    def test_fetch_documents_list_recent_date(self):
        """Test document list fetch for a recent date (any day)"""
        # Use yesterday's date - simple and reliable
        test_date = date.today() - timedelta(days=1)
        date_str = test_date.strftime('%Y-%m-%d')
        
        result = fetch_documents_list(date_str, api_key=self.api_key)
        
        # Should get valid response structure regardless of day type
        assert isinstance(result, dict)
        assert 'results' in result
        assert isinstance(result['results'], list)
        
        # Log what we got for debugging
        print(f"Tested date: {date_str} ({test_date.strftime('%A')})")
        print(f"Documents found: {len(result['results'])}")
        
        # Results may be empty on weekends/holidays, which is expected
    
    def test_fetch_documents_list_weekend_handling(self):
        """Test document list fetch for a weekend date"""
        # Find the most recent Saturday
        test_date = date.today()
        while test_date.weekday() != 5:  # Saturday=5
            test_date = test_date - timedelta(days=1)
        
        date_str = test_date.strftime('%Y-%m-%d')
        result = fetch_documents_list(date_str, api_key=self.api_key)
        
        # Should get valid response but likely no documents on weekend
        assert isinstance(result, dict)
        assert 'results' in result
        assert isinstance(result['results'], list)
        
        # Weekend typically has no filings - this is expected behavior
        print(f"Weekend test ({date_str}): {len(result['results'])} documents")
    
    def test_api_response_structure_compliance(self):
        """Verify API response structure matches expected format"""
        # Use 3 days ago to likely hit a business day
        test_date = date.today() - timedelta(days=3)
        date_str = test_date.strftime('%Y-%m-%d')
        
        result = fetch_documents_list(date_str, api_key=self.api_key)
        
        # Validate response structure
        assert isinstance(result, dict)
        assert 'results' in result
        
        # If documents exist, validate their structure
        if result['results']:
            doc = result['results'][0]
            expected_fields = ['docID', 'edinetCode', 'docTypeCode', 'filerName']
            for field in expected_fields:
                assert field in doc, f"Missing required field: {field}"
    
    def test_fetch_document_by_recent_doc_id(self):
        """Test document download with a recent document ID"""
        # Look back up to 7 days to find a document
        for days_back in range(1, 8):
            test_date = date.today() - timedelta(days=days_back)
            date_str = test_date.strftime('%Y-%m-%d')
            
            doc_list = fetch_documents_list(date_str, api_key=self.api_key)
            
            # Only documents EDINET marks csvFlag='1' have a type=5 form; a
            # PDF-only filing (e.g. a 訂正発行登録書) raises DocumentNotFoundError
            # by design, so the pick must honour the flag (found 2026-09-10).
            with_csv = [d for d in doc_list['results'] if d.get('csvFlag') == '1']
            if with_csv:
                doc_id = with_csv[0]['docID']
                zip_content = fetch_document(doc_id, api_key=self.api_key)
                
                # Should get binary ZIP content
                assert isinstance(zip_content, bytes)
                assert len(zip_content) > 0
                
                # Should start with ZIP file signature
                assert zip_content[:4] == b'PK\x03\x04' or zip_content[:4] == b'PK\x05\x06'
                
                print(f"Downloaded document {doc_id}: {len(zip_content)} bytes")
                return
        
        pytest.skip("No documents found in recent 7 days for download test")
    
    def test_date_range_api_usage_efficiency(self):
        """Test date range functionality with minimal API calls"""
        # Test small date range (2 recent days) to limit API usage
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=1)
        
        results = get_documents_for_date_range(start_date, end_date, api_key=self.api_key)
        
        # Should get list of documents
        assert isinstance(results, list)
        
        # Each document should have required metadata
        for doc in results:
            assert 'docID' in doc
            assert 'docTypeCode' in doc
            assert 'filerName' in doc
        
        print(f"Date range ({start_date} to {end_date}): {len(results)} total documents")
    
    def test_api_error_handling_with_invalid_key(self):
        """An invalid key raises AuthenticationError (fail-loud contract).

        EDINET answers HTTP 200 with {"StatusCode": 401, "message": "Access
        denied..."}. Returning that as data made a rejected key look exactly
        like a day with no filings; since the 0.8.1 documents-list fail-loud
        change it is raised, carrying EDINET's own message.
        """
        from edinet_tools.exceptions import AuthenticationError
        invalid_key = "invalid_test_key_12345"
        test_date = date.today() - timedelta(days=1)
        date_str = test_date.strftime('%Y-%m-%d')

        with pytest.raises(AuthenticationError) as exc_info:
            fetch_documents_list(date_str, api_key=invalid_key)

        msg = str(exc_info.value).lower()
        assert 'access denied' in msg or 'subscription key' in msg or 'unauthorized' in msg
    
    def test_api_document_not_found_handling(self):
        """A non-existent document ID raises a typed error (fail-loud contract).

        EDINET answers with an in-body error envelope under HTTP 200; since the
        fetch_document fail-loud change it is raised as DocumentNotFoundError
        (status 404) or APIError (any other status, e.g. 400 Bad Request for a
        malformed id) — never handed back as document bytes.
        """
        from edinet_tools.exceptions import APIError, DocumentNotFoundError
        fake_doc_id = "S999FAKE999"

        with pytest.raises((DocumentNotFoundError, APIError)) as exc_info:
            fetch_document(fake_doc_id, api_key=self.api_key)

        msg = str(exc_info.value).lower()
        assert fake_doc_id.lower() in msg
        assert ('404' in msg or 'not found' in msg or '400' in msg or 'bad request' in msg
                or 'status' in msg), f"Expected EDINET status text in error, got: {msg[:200]}"


@pytest.mark.integration
class TestCriticalDocumentTypeRetrieval:
    """Integration tests for periodic/event report retrieval (160, 180; 140 historical-only)"""

    def setup_method(self):
        self.api_key = _load_api_key_or_skip()

    def test_document_type_filtering_in_real_data(self):
        """Test that we can find and filter critical document types in real API data"""
        # Search recent days to find critical document types
        critical_types_found = set()
        
        # Look back up to 14 days to find examples of critical document types
        for days_back in range(1, 15):
            test_date = date.today() - timedelta(days=days_back)
            date_str = test_date.strftime('%Y-%m-%d')
            
            result = fetch_documents_list(date_str, api_key=self.api_key)
            
            for doc in result.get('results', []):
                doc_type = doc.get('docTypeCode')
                if doc_type in ['140', '160', '180']:
                    critical_types_found.add(doc_type)
                    print(f"Found {doc_type}: {doc.get('filerName', 'Unknown')} on {date_str}")
            
            # Stop early if we found examples of all critical types
            if len(critical_types_found) >= 2:
                break
        
        # Log what we found (may not find all types in date range)
        print(f"Critical document types found: {sorted(critical_types_found)}")
        
        # Doc 180 (extraordinary reports) is filed every business day by SOMEONE on
        # the TSE — even on quiet days there are typically multiple corporate-event
        # filings. Across a 14-day rolling window, finding at least one of
        # {140, 160, 180} is a real lower bound; finding zero would indicate an
        # API contract change (docTypeCode field renamed/missing) or fetch failure.
        # (140 is post-Apr 2024 sparse — historical only; 160 is bi-annual; 180 is daily.
        # So 180 is the load-bearing one.)
        assert len(critical_types_found) >= 1, (
            f"no critical document types (140/160/180) found across 14-day window — "
            f"API contract may have drifted or fetch returning empty results. "
            f"found: {critical_types_found}"
        )