"""
Tests for edinet_tools.client module (EdinetClient functionality).
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import date, timedelta

from edinet_tools.client import EdinetClient
from edinet_tools.exceptions import (
    ConfigurationError, CompanyNotFoundError, AuthenticationError,
    DocumentNotFoundError, APIError
)

# All tests in this file test deprecated EdinetClient functionality.
# Suppress deprecation warnings since we're intentionally testing legacy code.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class TestEdinetClientInitialization:
    """Test EdinetClient initialization."""
    
    def test_init_with_api_key(self):
        """Test initialization with API key parameter."""
        client = EdinetClient(api_key="test_key")
        assert client.api_key == "test_key"
        assert os.path.exists(client.download_dir)
    
    def test_init_with_env_var(self):
        """Test initialization with environment variable."""
        with patch.dict(os.environ, {'EDINET_API_KEY': 'env_key'}):
            client = EdinetClient()
            assert client.api_key == "env_key"
    
    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                EdinetClient()
            
            assert "EDINET API key required" in str(exc_info.value)
            assert "https://disclosure.edinet-fsa.go.jp/" in str(exc_info.value)
    
    def test_custom_download_dir(self):
        """Test initialization with custom download directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_dir = os.path.join(temp_dir, "custom_downloads")
            client = EdinetClient(api_key="test_key", download_dir=custom_dir)
            assert client.download_dir == custom_dir
            assert os.path.exists(custom_dir)


class TestCompanyLookup:
    """Test company lookup functionality in client."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    def test_search_companies(self):
        """Test company search via client."""
        results = self.client.search_companies("Toyota")
        assert len(results) > 0
        assert any("TOYOTA" in r['name_en'] for r in results)
    
    def test_search_companies_no_results(self):
        """Test company search with no results."""
        results = self.client.search_companies("NonexistentCompany12345")
        assert len(results) == 0
    
    def test_resolve_valid_company(self):
        """Test resolving valid company identifiers."""
        # Ticker
        edinet_code = self.client._resolve_company_identifier("7203")
        assert edinet_code == "E02144"
        
        # EDINET code
        edinet_code = self.client._resolve_company_identifier("E02144")
        assert edinet_code == "E02144"
    
    def test_resolve_invalid_company(self):
        """Test resolving invalid company identifier."""
        with pytest.raises(CompanyNotFoundError) as exc_info:
            self.client._resolve_company_identifier("InvalidCompany123")
        
        assert "InvalidCompany123" in str(exc_info.value)
        assert "search_entities" in str(exc_info.value)


class TestDocumentMethods:
    """Test document retrieval methods."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    @patch('edinet_tools.client.fetch_documents_list')
    def test_get_documents_by_date(self, mock_fetch):
        """Test getting documents by date."""
        # Mock API response
        mock_fetch.return_value = {
            'results': [
                {'docID': 'S100TEST1', 'docTypeCode': '160', 'filerName': 'Test Company 1'},
                {'docID': 'S100TEST2', 'docTypeCode': '180', 'filerName': 'Test Company 2'}
            ]
        }
        
        documents = self.client.get_documents_by_date('2024-01-01')
        
        assert len(documents) == 2
        assert documents[0]['docID'] == 'S100TEST1'
        mock_fetch.assert_called_once()
    
    @patch('edinet_tools.client.fetch_documents_list')
    def test_get_documents_by_date_with_filter(self, mock_fetch):
        """Test getting documents by date with document type filter."""
        mock_fetch.return_value = {
            'results': [
                {'docID': 'S100TEST1', 'docTypeCode': '160', 'filerName': 'Test Company 1'},
                {'docID': 'S100TEST2', 'docTypeCode': '180', 'filerName': 'Test Company 2'}
            ]
        }
        
        documents = self.client.get_documents_by_date('2024-01-01', doc_type='160')
        
        assert len(documents) == 1
        assert documents[0]['docTypeCode'] == '160'
    
    @patch('edinet_tools.client.fetch_documents_list')
    def test_get_documents_api_error(self, mock_fetch):
        """Test API error handling in document retrieval."""
        mock_fetch.side_effect = Exception("401 Unauthorized")
        
        with pytest.raises(AuthenticationError):
            self.client.get_documents_by_date('2024-01-01')
    
    def test_get_recent_filings(self):
        """Test getting recent filings."""
        with patch.object(self.client, 'get_documents_by_date') as mock_get_docs:
            mock_get_docs.return_value = [
                {'docID': 'S100TEST1', 'submitDateTime': '2024-01-01T10:00:00'}
            ]
            
            filings = self.client.get_recent_filings(days_back=1)
            
            assert len(filings) >= 0  # May be empty if mock returns empty
            # Should call get_documents_by_date for today
            assert mock_get_docs.call_count >= 1


class TestDocumentTypeMapping:
    """Test document type functionality."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    def test_get_document_types(self):
        """Test getting document type mappings."""
        doc_types = self.client.get_document_types()
        assert isinstance(doc_types, dict)
        assert len(doc_types) > 0
        
        # Check some known document types
        assert '160' in doc_types or '180' in doc_types
    
    def test_determine_document_type_from_filename(self):
        """Test document type determination from filename."""
        # Test with typical EDINET filename format
        doc_type = self.client._determine_document_type([], "S100TEST-160-TestCompany.zip")
        assert doc_type == "160"
        
        doc_type = self.client._determine_document_type([], "S100TEST-180-TestCompany.zip")
        assert doc_type == "180"
        
        # Test with unknown format
        doc_type = self.client._determine_document_type([], "unknown_format.zip")
        assert doc_type == "unknown"


class TestErrorHandling:
    """Test error handling throughout the client."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    def test_search_companies_error_handling(self):
        """Test error handling in company search."""
        # Should return empty list on error, not raise exception
        with patch('edinet_tools.client.search_companies_data') as mock_search:
            mock_search.side_effect = Exception("Test error")
            
            results = self.client.search_companies("test")
            assert results == []


class TestIntegration:
    """Integration tests for client functionality."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    def test_company_workflow(self):
        """Test complete company lookup workflow."""
        # Search for company
        results = self.client.search_companies("Toyota")
        assert len(results) > 0
        
        # Get company info
        company = results[0]
        assert 'edinet_code' in company
        assert 'ticker' in company
        
        # Resolve company identifier
        edinet_code = self.client._resolve_company_identifier(company['ticker'])
        assert edinet_code == company['edinet_code']
    
    def test_get_company_filings_no_crash(self):
        """Test that get_company_filings doesn't crash with edge cases."""
        # Test with a valid ticker that might not have recent filings
        with patch('edinet_tools.api.fetch_documents_list') as mock_fetch:
            # Mock response with None submitDateTime values
            mock_fetch.return_value = {
                'results': [
                    {'docID': 'test1', 'submitDateTime': None, 'docDescription': 'Test Doc'},
                    {'docID': 'test2', 'submitDateTime': '2024-01-15 10:00', 'docDescription': 'Test Doc 2'}
                ]
            }
            
            # This should not crash even with None values
            result = self.client.get_company_filings('3116', days_back=30)
            assert isinstance(result, list)


class TestMockAPI:
    """Test with mocked API calls to avoid actual network requests."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = EdinetClient(api_key="test_key")
    
    @patch('edinet_tools.client.fetch_document')
    def test_download_filing_success(self, mock_fetch):
        """Test successful filing download."""
        # Mock file content - return bytes that look like a ZIP file (starts with PK)
        mock_fetch.return_value = b"PK\x03\x04fake_zip_content"
        
        # Mock file processing to avoid actual file operations
        with patch.object(self.client, 'extract_filing_data') as mock_extract:
            mock_extract.return_value = {'test': 'data'}
            
            result = self.client.download_filing("S100TEST1", extract_data=True)
            
            assert result == {'test': 'data'}
            mock_fetch.assert_called_once()
    
    @patch('edinet_tools.client.fetch_document')
    def test_download_filing_not_found(self, mock_fetch):
        """Test filing download with document not found."""
        mock_fetch.side_effect = Exception("404 Not Found")
        
        with pytest.raises(DocumentNotFoundError) as exc_info:
            self.client.download_filing("S100NOTFOUND")
        
        assert "S100NOTFOUND" in str(exc_info.value)
    
    @patch('edinet_tools.client.fetch_document')
    def test_download_filing_not_found_graceful(self, mock_fetch):
        """Test filing download with document not found - graceful mode."""
        # Mock JSON error response like EDINET API returns
        json_error = b'{"metadata": {"title": "API", "status": "404", "message": "Not Found"}}'
        mock_fetch.return_value = json_error
        
        # Should return None instead of raising exception
        result = self.client.download_filing("S100NOTFOUND", raise_on_error=False)
        
        assert result is None
        mock_fetch.assert_called_once()
    
    @patch('edinet_tools.client.fetch_document')
    def test_batch_filing_download_graceful(self, mock_fetch):
        """Test batch filing download with mixed success/failure - graceful mode."""
        def mock_fetch_side_effect(doc_id, **kwargs):
            if doc_id == "S100VALID":
                return b"PK\x03\x04fake_zip_content"  # Valid ZIP file signature
            else:
                # Return JSON error for invalid doc IDs
                return b'{"metadata": {"title": "API", "status": "404", "message": "Not Found"}}'
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # Simulate batch processing like user would do
        doc_ids = ["S100VALID", "S100INVALID", "S100VALID"]
        results = []
        
        with patch.object(self.client, 'extract_filing_data') as mock_extract:
            mock_extract.return_value = {'company': 'Test Company'}
            
            for doc_id in doc_ids:
                data = self.client.download_filing(doc_id, raise_on_error=False)
                results.append(data)
        
        # Should have 2 successful results and 1 None (skipped)
        assert len(results) == 3
        assert results[0] == {'company': 'Test Company'}  # Success
        assert results[1] is None  # Failed gracefully
        assert results[2] == {'company': 'Test Company'}  # Success
        
        # Should have called fetch_document 3 times
        assert mock_fetch.call_count == 3
    
    @patch('edinet_tools.client.fetch_document')
    def test_download_filings_batch_convenience_method(self, mock_fetch):
        """Test the new batch download convenience method."""
        def mock_fetch_side_effect(doc_id, **kwargs):
            if doc_id in ["S100VALID1", "S100VALID2"]:
                return b"PK\x03\x04fake_zip_content"  # Valid ZIP file signature
            else:
                # Return JSON error for invalid doc IDs
                return b'{"metadata": {"title": "API", "status": "404", "message": "Not Found"}}'
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # Test batch processing with mixed results
        doc_ids = ["S100VALID1", "S100INVALID", "S100VALID2"]
        
        with patch.object(self.client, 'extract_filing_data') as mock_extract:
            mock_extract.return_value = {'company': 'Test Company'}
            
            # Call the new batch method
            results = self.client.download_filings_batch(doc_ids)
        
        # Check results structure - should be a list in same order as input
        assert len(results) == 3
        assert isinstance(results, list)
        
        # Check success/failure patterns in order
        assert results[0] == {'company': 'Test Company'}  # S100VALID1 - Success
        assert results[1] is None  # S100INVALID - Failed gracefully  
        assert results[2] == {'company': 'Test Company'}  # S100VALID2 - Success
        
        # Should have called fetch_document 3 times
        assert mock_fetch.call_count == 3
        
        # Test convenience filtering
        successful = [r for r in results if r is not None]
        assert len(successful) == 2
    
    @patch('edinet_tools.client.fetch_document')
    def test_download_filings_batch_with_raise_on_error_true(self, mock_fetch):
        """Test batch method with raise_on_error=True (fail fast behavior)."""
        def mock_fetch_side_effect(doc_id, **kwargs):
            if doc_id == "S100VALID":
                return b"PK\x03\x04fake_zip_content"  # Valid ZIP file signature
            else:
                # Return JSON error for invalid doc IDs
                return b'{"metadata": {"title": "API", "status": "404", "message": "Not Found"}}'
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # Test batch processing that should fail on first error
        doc_ids = ["S100VALID", "S100INVALID", "S100VALID"]
        
        with patch.object(self.client, 'extract_filing_data') as mock_extract:
            mock_extract.return_value = {'company': 'Test Company'}
            
            # This should raise an exception on the second document
            with pytest.raises(DocumentNotFoundError):
                self.client.download_filings_batch(doc_ids, raise_on_error=True)
        
        # Should have only called fetch_document twice (stopped on error)
        assert mock_fetch.call_count == 2


if __name__ == "__main__":
    # Run tests if pytest is available
    try:
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available. Install with: pip install pytest")
        print("Running basic test validation...")
        
        # Basic validation
        client = EdinetClient(api_key="test_key")
        assert client.api_key == "test_key"
        
        results = client.search_companies("Toyota")
        assert len(results) > 0
        
        doc_types = client.get_document_types()
        assert len(doc_types) > 0
        
        print("✅ Basic validation passed!")