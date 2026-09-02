"""
Unit tests for edinet_tools.api module.

Tests core API functionality including URL construction, parameter handling,
error scenarios, and response processing with realistic Japanese market conditions.
"""

import pytest
import urllib.error
import urllib.request
import json
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from io import BytesIO

from edinet_tools.api import (
    fetch_documents_list, 
    fetch_document, 
    save_document_content,
    download_documents,
    filter_documents,
    get_documents_for_date_range
)


class TestFetchDocumentsList:
    """Test fetch_documents_list function with realistic market scenarios."""
    
    def test_url_construction_with_business_day(self):
        """Test URL construction with typical business day."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b'{"results": []}'
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            # Wednesday 2025-01-08 - typical business day
            fetch_documents_list('2025-01-08', api_key='test_key')
            
            called_url = mock_urlopen.call_args[0][0]
            assert 'api.edinet-fsa.go.jp' in called_url
            assert 'date=2025-01-08' in called_url
            assert 'type=2' in called_url
            assert 'Subscription-Key=test_key' in called_url
    
    def test_url_construction_with_date_object(self):
        """Test URL construction with datetime.date object."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b'{"results": []}'
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            test_date = date(2025, 2, 14)  # Q4 earnings season
            fetch_documents_list(test_date, api_key='test_key')
            
            called_url = mock_urlopen.call_args[0][0]
            assert 'date=2025-02-14' in called_url
    
    def test_parameter_encoding_special_chars(self):
        """Test that URL parameters are properly encoded."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b'{"results": []}'
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            # Test with special characters in API key
            fetch_documents_list('2025-03-31', type=1, api_key='test+key&value=123')
            
            called_url = mock_urlopen.call_args[0][0]
            # Should be URL encoded properly
            assert 'test%2Bkey%26value%3D123' in called_url or 'Subscription-Key=test%2Bkey%26value%3D123' in called_url
    
    def test_invalid_date_formats(self):
        """Test error handling for various invalid date formats."""
        invalid_dates = [
            'invalid-date',
            '2025/01/15',  # Wrong separator
            '25-01-15',    # Wrong format
            '2025-13-01',  # Invalid month
            '2025-01-32',  # Invalid day
        ]
        
        for invalid_date in invalid_dates:
            with pytest.raises(ValueError) as exc_info:
                fetch_documents_list(invalid_date)
            assert "Invalid date string" in str(exc_info.value)
    
    def test_response_body_matches_real_edinet_api_shape(self):
        """Closes the audit's C/LOW gap: the URL-construction tests use a stub
        b'{"results": []}' body and never exercise our JSON-parsing path against
        the actual EDINET response shape. If the API renamed/dropped a field
        (docTypeCode → docType, secCode → securityCode, etc.) or the response
        nesting changed, the URL tests still pass green. This test fixes that
        by feeding a realistic response body and asserting on the fields
        downstream callers actually read."""
        # Shape derived from the EDINET API spec — fields the rest of the
        # codebase reads off `.get('results', [])[i]`.
        realistic_body = (
            b'{"metadata": {"title": "EDINET document list",'
            b' "parameter": {"date": "2025-01-08", "type": "2"},'
            b' "resultset": {"count": 2},'
            b' "processDateTime": "2025-01-08 14:00",'
            b' "status": "200", "message": "OK"},'
            b' "results": ['
            b'{"seqNumber": 1, "docID": "S100ABCD", "edinetCode": "E12345",'
            b' "secCode": "12345", "JCN": "1234567890123",'
            b' "filerName": "Test Corporation",'
            b' "fundCode": null, "ordinanceCode": "010", "formCode": "030000",'
            b' "docTypeCode": "120", "periodStart": "2024-04-01",'
            b' "periodEnd": "2025-03-31", "submitDateTime": "2025-01-08 13:30",'
            b' "docDescription": "Annual Securities Report",'
            b' "issuerEdinetCode": null, "subjectEdinetCode": null,'
            b' "subsidiaryEdinetCode": null, "currentReportReason": null,'
            b' "parentDocID": null, "opeDateTime": null,'
            b' "withdrawalStatus": "0", "docInfoEditStatus": "0",'
            b' "disclosureStatus": "0", "xbrlFlag": "1", "pdfFlag": "1",'
            b' "attachDocFlag": "0", "englishDocFlag": "0",'
            b' "csvFlag": "1", "legalStatus": "1"},'
            b'{"seqNumber": 2, "docID": "S100WXYZ", "edinetCode": "E67890",'
            b' "secCode": null, "JCN": "9999999999999",'
            b' "filerName": "Fund Trust", "fundCode": "F12345",'
            b' "ordinanceCode": "030", "formCode": "07A000",'
            b' "docTypeCode": "180", "periodStart": null, "periodEnd": null,'
            b' "submitDateTime": "2025-01-08 14:15",'
            b' "docDescription": "Extraordinary Report",'
            b' "issuerEdinetCode": null, "subjectEdinetCode": null,'
            b' "subsidiaryEdinetCode": null, "currentReportReason": null,'
            b' "parentDocID": null, "opeDateTime": null,'
            b' "withdrawalStatus": "0", "docInfoEditStatus": "0",'
            b' "disclosureStatus": "0", "xbrlFlag": "1", "pdfFlag": "1",'
            b' "attachDocFlag": "0", "englishDocFlag": "0",'
            b' "csvFlag": "1", "legalStatus": "1"}]}'
        )
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = realistic_body
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = fetch_documents_list('2025-01-08', api_key='test_key')

        # Top-level shape — metadata + results, both required by downstream.
        assert 'metadata' in result, "metadata block missing from parsed response"
        assert 'results' in result, "results block missing from parsed response"
        assert isinstance(result['results'], list)
        assert len(result['results']) == 2

        # Per-row contract — the field names downstream code (data_collection
        # processors, ingestion sync) reads. If EDINET renamed any of these,
        # downstream code would silently miss documents; this test surfaces it.
        doc = result['results'][0]
        for required_key in ('docID', 'edinetCode', 'docTypeCode',
                             'submitDateTime', 'filerName'):
            assert required_key in doc, f"contract drift: '{required_key}' missing from result row"

        # Fund-style row (null secCode, set fundCode) — the second-row shape we
        # depend on for filtering listed vs fund filings.
        fund = result['results'][1]
        assert fund['secCode'] is None
        assert fund['fundCode'] == 'F12345'
        assert fund['docTypeCode'] == '180'

    def test_http_error_codes(self):
        """Test handling of various HTTP error codes."""
        error_scenarios = [
            (401, "Unauthorized - Invalid API key"),
            (403, "Forbidden - API access denied"), 
            (404, "Not Found - Invalid endpoint"),
            (429, "Rate limit exceeded"),
            (500, "Internal server error"),
            (503, "Service unavailable")
        ]
        
        for status_code, error_msg in error_scenarios:
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = Mock()
                mock_response.getcode.return_value = status_code
                mock_response.read.return_value = error_msg.encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                with pytest.raises(urllib.error.HTTPError):
                    fetch_documents_list('2025-01-15', max_retries=1, api_key='test_key')
    
    def test_retry_logic_server_errors(self):
        """Test retry logic for transient server errors."""
        with patch('urllib.request.urlopen') as mock_urlopen, \
             patch('time.sleep') as mock_sleep:
            
            # First two calls return 503, third succeeds
            responses = [
                Mock(getcode=lambda: 503, read=lambda: b'Service Unavailable'),
                Mock(getcode=lambda: 503, read=lambda: b'Service Unavailable'),
                Mock(getcode=lambda: 200, read=lambda: b'{"results": [{"docID": "S100A001"}]}')
            ]
            
            mock_urlopen.return_value.__enter__.side_effect = responses
            
            result = fetch_documents_list('2025-01-15', max_retries=3, delay_seconds=1, api_key='test_key')
            
            assert mock_urlopen.call_count == 3
            assert mock_sleep.call_count == 2
            assert result == {"results": [{"docID": "S100A001"}]}
    
    def test_network_timeout_handling(self):
        """Test handling of network timeouts and connection issues."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Network timeout")
            
            with pytest.raises(urllib.error.URLError):
                fetch_documents_list('2025-01-15', max_retries=1, api_key='test_key')
    
    def test_malformed_json_response(self):
        """Test handling of malformed JSON responses."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b'{"results": [invalid json'
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            with pytest.raises(json.JSONDecodeError):
                fetch_documents_list('2025-01-15', api_key='test_key')
    
    def test_empty_response_handling(self):
        """Test handling of empty API responses."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = b''
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            with pytest.raises(json.JSONDecodeError):
                fetch_documents_list('2025-01-15', api_key='test_key')


class TestFetchDocument:
    """Test fetch_document function with realistic 2025 document scenarios."""
    
    def test_url_construction_realistic_doc_id(self):
        """Test URL construction with realistic 2025 document IDs."""
        realistic_doc_ids = ['S100A001', 'S100B999', 'S100ZZZZ', 'S100C123']
        
        for doc_id in realistic_doc_ids:
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = Mock()
                mock_response.getcode.return_value = 200
                mock_response.read.return_value = b'fake_zip_content'
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                fetch_document(doc_id, api_key='test_key')
                
                called_url = mock_urlopen.call_args[0][0]
                assert 'api.edinet-fsa.go.jp' in called_url  # Correct domain
                assert f'documents/{doc_id}' in called_url
                assert 'type=5' in called_url  # CSV format
                assert 'Subscription-Key=test_key' in called_url
    
    def test_document_not_found_scenarios(self):
        """Test various document not found scenarios."""
        not_found_scenarios = [
            ('S100XXXX', 404, "Document not found"),
            ('S099ZZZZ', 404, "Invalid document ID format"),
            ('S100OLD1', 410, "Document no longer available"),
        ]
        
        for doc_id, status_code, error_msg in not_found_scenarios:
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = Mock()
                mock_response.getcode.return_value = status_code
                mock_response.read.return_value = error_msg.encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                with pytest.raises(urllib.error.HTTPError):
                    fetch_document(doc_id, api_key='test_key')
    

class TestSaveDocumentContent:
    """Test save_document_content with realistic file scenarios."""
    
    def test_save_zip_content(self, tmp_path):
        """Test saving actual ZIP file content."""
        # Realistic ZIP file content with proper headers
        zip_content = (
            b'\x50\x4b\x03\x04\x14\x00\x00\x00\x08\x00'  # ZIP header
            b'test_document_content_here'
        )
        output_path = tmp_path / "S100A001-160-TestCompany.zip"
        
        save_document_content(zip_content, str(output_path))
        
        assert output_path.exists()
        assert output_path.read_bytes() == zip_content
        assert output_path.suffix == '.zip'
    
    def test_save_to_nested_directory(self, tmp_path):
        """Test saving to nested directory structure."""
        nested_dir = tmp_path / "downloads" / "2025" / "01"
        nested_dir.mkdir(parents=True)
        
        test_content = b'test_zip_content'
        output_path = nested_dir / "S100C123.zip"
        
        save_document_content(test_content, str(output_path))
        
        assert output_path.exists()
        assert output_path.read_bytes() == test_content
    
    def test_permission_errors(self, tmp_path):
        """Test handling of file permission errors."""
        import os
        test_content = b'test'
        
        # Create read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only
        
        output_path = readonly_dir / "test.zip"
        
        try:
            with pytest.raises(IOError):
                save_document_content(test_content, str(output_path))
        finally:
            # Cleanup - restore write permissions
            readonly_dir.chmod(0o755)


class TestFilterDocuments:
    """Test document filtering with realistic 2025 market data."""
    
    def test_filter_by_document_type_earnings(self):
        """Test filtering for earnings-related document types."""
        docs = [
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Toyota Motor Corp', 'edinetCode': 'E02144', 'secCode': '7203'},
            {'docID': 'S100A002', 'docTypeCode': '180', 'filerName': 'Sony Group Corp', 'edinetCode': 'E02134', 'secCode': '6758'},
            {'docID': 'S100A003', 'docTypeCode': '999', 'filerName': 'Other Filing', 'edinetCode': 'E99999'},
        ]
        
        # Filter for semi-annual reports (160) and extraordinary reports (180)
        earnings_docs = filter_documents(docs, doc_type_codes=['160', '180'])
        assert len(earnings_docs) == 2
        assert all(doc['docTypeCode'] in ['160', '180'] for doc in earnings_docs)
    
    def test_filter_by_major_companies(self):
        """Test filtering for major Japanese companies."""
        docs = [
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Toyota Motor Corp', 'edinetCode': 'E02144', 'secCode': '7203'},
            {'docID': 'S100A002', 'docTypeCode': '160', 'filerName': 'Sony Group Corp', 'edinetCode': 'E02134', 'secCode': '6758'},
            {'docID': 'S100A003', 'docTypeCode': '160', 'filerName': 'Small Company Ltd', 'edinetCode': 'E99999', 'secCode': None},
        ]
        
        # Filter for companies with securities codes (listed companies)
        listed_companies = filter_documents(docs, require_sec_code=True)
        assert len(listed_companies) == 2
        assert all(doc['secCode'] is not None for doc in listed_companies)
    
    def test_filter_quarterly_earnings_season(self):
        """Test filtering during quarterly earnings season."""
        docs = [
            # Q3 earnings filings - need edinetCode for filtering to work
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Company A', 'edinetCode': 'E12345', 'submitDateTime': '2025-02-14T15:00:00'},
            {'docID': 'S100A002', 'docTypeCode': '180', 'filerName': 'Company B', 'edinetCode': 'E12346', 'submitDateTime': '2025-02-14T16:30:00'},
            # Regular filings
            {'docID': 'S100A003', 'docTypeCode': '999', 'filerName': 'Company C', 'edinetCode': 'E12347', 'submitDateTime': '2025-02-14T10:00:00'},
        ]
        
        earnings_types = filter_documents(docs, doc_type_codes=['160', '180'], require_sec_code=False)
        assert len(earnings_types) == 2
    
    def test_filter_incomplete_filings(self):
        """Test filtering out incomplete or malformed filings."""
        docs = [
            # Complete filing - need edinetCode to pass all filters
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Complete Company', 'edinetCode': 'E12345'},
            # Missing required fields
            {'docID': 'S100A002', 'docTypeCode': '160'},  # Missing filerName
            {'docTypeCode': '160', 'filerName': 'Missing DocID'},  # Missing docID
            {'docID': 'S100A004', 'filerName': 'Missing Type'},  # Missing docTypeCode
            {},  # Empty document
            None,  # Null document
        ]
        
        # Filter should handle None values gracefully
        docs_clean = [doc for doc in docs if doc is not None]
        filtered = filter_documents(docs_clean, require_sec_code=False)
        assert len(filtered) == 1
        assert filtered[0]['docID'] == 'S100A001'
    
    def test_filter_by_edinet_code_string_and_list_inputs(self):
        """A bare-string edinet_codes filter behaves like a one-element list,
        and docs missing the edinetCode field are excluded when the filter
        is active."""
        docs = [
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Toyota Motor Corporation', 'edinetCode': 'E02144', 'secCode': '7203'},
            {'docID': 'S100A002', 'docTypeCode': '160', 'filerName': 'Sony Group Corporation', 'edinetCode': 'E02134', 'secCode': '6758'},
            {'docID': 'S100A003', 'docTypeCode': '160', 'filerName': 'No Code Ltd', 'secCode': '9999'},  # no edinetCode field
        ]

        string_input = filter_documents(docs, edinet_codes='E02144')
        assert [d['docID'] for d in string_input] == ['S100A001']

        list_input = filter_documents(docs, edinet_codes=['E02134'])
        assert [d['docID'] for d in list_input] == ['S100A002']

        both = filter_documents(docs, edinet_codes=['E02144', 'E02134'])
        assert [d['docID'] for d in both] == ['S100A001', 'S100A002']


class TestDownloadDocuments:
    """Test bulk document download functionality."""
    
    @patch('edinet_tools.api.fetch_document')
    @patch('edinet_tools.api.save_document_content')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_download_earnings_batch(self, mock_makedirs, mock_exists, mock_save, mock_fetch):
        """Test downloading a batch of earnings documents."""
        mock_exists.return_value = False
        mock_fetch.return_value = b'fake_zip_content'
        
        # Realistic earnings season documents
        docs = [
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Toyota Motor Corporation'},
            {'docID': 'S100A002', 'docTypeCode': '180', 'filerName': 'Sony Group Corporation'},
            {'docID': 'S100A003', 'docTypeCode': '160', 'filerName': 'SoftBank Group Corp'},
        ]
        
        download_documents(docs, download_dir='/downloads/2025/earnings')
        
        assert mock_fetch.call_count == 3
        assert mock_save.call_count == 3
        mock_makedirs.assert_called_once_with('/downloads/2025/earnings', exist_ok=True)
        
        # Check filename format
        save_calls = mock_save.call_args_list
        for i, call in enumerate(save_calls):
            filepath = call[0][1]  # Second argument is filepath
            assert f"S100A00{i+1}" in filepath
            assert docs[i]['docTypeCode'] in filepath
            assert filepath.endswith('.zip')
    
    @patch('os.path.exists')
    def test_skip_already_downloaded(self, mock_exists):
        """Test skipping documents that were already downloaded."""
        mock_exists.return_value = True  # All files already exist
        
        docs = [
            {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Toyota Motor Corporation'},
        ]
        
        with patch('edinet_tools.api.fetch_document') as mock_fetch:
            download_documents(docs)
            
            # Should not download if file already exists
            mock_fetch.assert_not_called()
    
    def test_handle_problematic_filer_names(self):
        """Test handling of filer names with special characters."""
        with patch('edinet_tools.api.fetch_document') as mock_fetch, \
             patch('os.path.exists') as mock_exists, \
             patch('edinet_tools.api.save_document_content') as mock_save:
            
            mock_exists.return_value = False
            mock_fetch.return_value = b'content'
            
            docs = [
                {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Company/With\\Slashes'},
                {'docID': 'S100A002', 'docTypeCode': '160', 'filerName': 'Company<With>Brackets'},
                {'docID': 'S100A003', 'docTypeCode': '160', 'filerName': 'Company:With:Colons'},
            ]
            
            download_documents(docs)
            
            # Should still attempt to save files (with filename sanitization)
            assert mock_save.call_count == 3
    


class TestGetDocumentsForDateRange:
    """Test date range document retrieval with Japanese market patterns."""
    
    @patch('edinet_tools.api.fetch_documents_list')
    def test_business_week_range(self, mock_fetch):
        """Test fetching documents for a typical business week."""
        mock_fetch.return_value = {'results': []}
        
        # Week of 2025-01-06 to 2025-01-10 (Monday to Friday)
        start_date = date(2025, 1, 6)
        end_date = date(2025, 1, 10)
        
        get_documents_for_date_range(start_date, end_date)
        
        # Should call for 5 business days
        assert mock_fetch.call_count == 5
        
        # Verify dates are sequential
        called_dates = [call[1]['date'] for call in mock_fetch.call_args_list]
        expected_dates = [
            date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8),
            date(2025, 1, 9), date(2025, 1, 10)
        ]
        assert called_dates == expected_dates
    
    @patch('edinet_tools.api.fetch_documents_list')
    def test_date_range_applies_filters_across_days(self, mock_fetch):
        """Filters passed to get_documents_for_date_range apply to every
        day's results: 3 docs/day mocked, the unlisted filer dropped by
        require_sec_code, 2 kept per day over 5 days."""
        mock_fetch.return_value = {
            'results': [
                {'docID': 'S100A001', 'docTypeCode': '160', 'filerName': 'Company A', 'edinetCode': 'E12345', 'secCode': '7203'},
                {'docID': 'S100A002', 'docTypeCode': '180', 'filerName': 'Company B', 'edinetCode': 'E12346', 'secCode': '6758'},
                {'docID': 'S100A003', 'docTypeCode': '160', 'filerName': 'Unlisted Fund', 'edinetCode': 'E12347', 'secCode': None},
            ]
        }

        result = get_documents_for_date_range(
            date(2025, 2, 10), date(2025, 2, 14),  # Mon-Fri
            doc_type_codes=['160', '180'],
            require_sec_code=True,
        )

        assert mock_fetch.call_count == 5
        assert len(result) == 10  # 2 kept docs x 5 days
        assert all(doc['docTypeCode'] in ('160', '180') for doc in result)
        assert all(doc['secCode'] is not None for doc in result)