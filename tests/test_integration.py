"""
Integration tests for EDINET Tools package.

Tests package-level exports, configuration, and end-to-end workflows.
Detailed unit tests for Entity, Fund, etc. are in their respective test files.
"""

import os
from unittest.mock import patch

import edinet_tools


class TestPackageExports:
    """Test that expected symbols are exported from the package."""

    def test_version(self):
        """Package version is available and correct."""
        assert edinet_tools.__version__  # version is set

    def test_metadata(self):
        """Package metadata is available."""
        assert edinet_tools.__author__ == "Matt Helmer"
        assert "Japanese" in edinet_tools.__description__

    def test_configuration_exports(self):
        """Configuration functions are exported."""
        assert callable(edinet_tools.configure)
        assert callable(edinet_tools.documents)
        assert isinstance(edinet_tools.DOCUMENT_TYPES, dict)

    def test_entity_exports(self):
        """Entity API is exported."""
        assert callable(edinet_tools.entity)
        assert callable(edinet_tools.entity_by_ticker)
        assert callable(edinet_tools.entity_by_edinet_code)
        assert callable(edinet_tools.search)
        assert callable(edinet_tools.search_entities)

    def test_fund_exports(self):
        """Fund API is exported."""
        assert callable(edinet_tools.fund)
        assert callable(edinet_tools.funds_by_issuer)

    def test_document_exports(self):
        """Document API is exported."""
        assert edinet_tools.Document is not None
        assert callable(edinet_tools.doc_type)
        assert callable(edinet_tools.doc_types)
        assert callable(edinet_tools.list_doc_types)

    def test_parser_exports(self):
        """Parser classes are exported."""
        assert callable(edinet_tools.parse)
        assert edinet_tools.ParsedReport is not None
        assert edinet_tools.LargeHoldingReport is not None
        assert edinet_tools.SecuritiesReport is not None

    def test_legacy_exports(self):
        """Legacy/deprecated exports still available for migration."""
        assert edinet_tools.EntityClassifier is not None

    def test_all_exports_complete(self):
        """__all__ contains all expected exports."""
        expected = [
            'configure', 'documents', 'DOCUMENT_TYPES', '__version__',
            'Entity', 'entity', 'entity_by_ticker', 'entity_by_edinet_code',
            'search_entities', 'search', 'Fund', 'fund', 'funds_by_issuer',
            'Document', 'DocType', 'doc_type', 'list_doc_types', 'doc_types',
            'parse', 'ParsedReport',
        ]
        for name in expected:
            assert name in edinet_tools.__all__, f"Missing: {name}"


class TestModuleConfiguration:
    """Test module-level client configuration."""

    def test_configure_exported(self):
        """configure() is available at package level."""
        assert callable(edinet_tools.configure)

    def test_get_client_returns_singleton(self):
        """_get_client() returns the same instance."""
        from edinet_tools._client import _get_client, _reset_client

        _reset_client()
        with patch.dict(os.environ, {'EDINET_API_KEY': 'test-key'}):
            client1 = _get_client()
            client2 = _get_client()
            assert client1 is client2

    def test_configure_resets_client(self):
        """configure() resets the cached client."""
        from edinet_tools._client import configure, _get_client, _reset_client

        _reset_client()
        with patch.dict(os.environ, {'EDINET_API_KEY': 'key1'}):
            client1 = _get_client()

        configure(api_key='key2')
        client2 = _get_client()
        assert client1 is not client2

    def test_documents_function_returns_list(self):
        """documents() returns a list of Document objects."""
        from edinet_tools._client import _reset_client, configure

        _reset_client()
        with patch('edinet_tools._client._ApiClient') as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_documents_by_date.return_value = [
                {'docID': 'S100TEST', 'docTypeCode': '350',
                 'submitDateTime': '2026-01-15 09:30',
                 'edinetCode': 'E12345', 'filerName': 'Test Corp'}
            ]
            configure(api_key='test-key')
            docs = edinet_tools.documents('2026-01-15')

            assert isinstance(docs, list)
            assert len(docs) == 1


class TestEndToEndWorkflows:
    """Test complete workflows using the public API."""

    def test_company_discovery_workflow(self):
        """Find a company and access its properties."""
        # Search -> get entity -> access properties
        results = edinet_tools.search('Toyota')
        assert len(results) > 0

        toyota = edinet_tools.entity('7203')
        assert toyota is not None
        assert toyota.edinet_code == 'E02144'
        assert toyota.entity_type == edinet_tools.EntityType.LISTED_COMPANY

    def test_document_type_workflow(self):
        """Look up document types."""
        # Get a specific type
        large_holding = edinet_tools.doc_type('350')
        assert large_holding is not None
        assert large_holding.code == '350'

        # List all types
        all_types = edinet_tools.doc_types()
        assert len(all_types) > 10

    def test_graceful_not_found(self):
        """Invalid lookups return None, not exceptions."""
        assert edinet_tools.entity('INVALID_12345') is None
        assert edinet_tools.entity_by_ticker('0000') is None
        assert edinet_tools.entity_by_edinet_code('E99999') is None
        assert edinet_tools.doc_type('999') is None


class TestEntityAutoClient:
    """Test that Entity/Document use module-level client automatically."""

    def test_entity_documents_uses_module_client(self):
        """Entity.documents() works without explicit client."""
        from edinet_tools._client import _reset_client, configure

        _reset_client()
        with patch('edinet_tools._client._ApiClient') as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_documents_by_date.return_value = []

            configure(api_key='test-key')
            toyota = edinet_tools.entity("7203")
            docs = toyota.documents(days=1)
            assert docs == []

    def test_document_fetch_uses_module_client(self):
        """Document.fetch() works without explicit client."""
        from edinet_tools._client import _reset_client, configure
        from edinet_tools.document import Document

        _reset_client()
        with patch('edinet_tools._client._ApiClient') as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.download_filing_raw.return_value = b'test content'

            configure(api_key='test-key')
            doc = Document({
                'docID': 'S100TEST', 'docTypeCode': '350',
                'submitDateTime': '2026-01-15 09:30',
                'edinetCode': 'E12345', 'filerName': 'Test Corp',
            })
            content = doc.fetch()
            assert content == b'test content'

    def test_document_parse_returns_report(self):
        """Document.parse() returns a ParsedReport."""
        from edinet_tools.document import Document
        from edinet_tools.parsers.base import ParsedReport

        doc = Document({
            'docID': 'S100TEST', 'docTypeCode': '999',
            'submitDateTime': '2026-01-15 09:30',
            'edinetCode': 'E12345', 'filerName': 'Test Corp',
        })

        with patch.object(doc, 'fetch', return_value=b''):
            result = doc.parse()
            assert isinstance(result, ParsedReport)

    def test_fetch_and_parse_is_exported(self):
        """Verify fetch_and_parse is importable from the public API."""
        from edinet_tools import fetch_and_parse
        assert callable(fetch_and_parse)
