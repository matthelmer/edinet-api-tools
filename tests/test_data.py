"""
Tests for edinet_tools.data module (company lookup functionality).
"""

import pytest
from edinet_tools.data import (
    ticker_to_edinet, resolve_company, search_companies,
    get_company_info, get_supported_companies, CompanyLookup
)


class TestTickerLookup:
    """Test ticker symbol to EDINET code conversion."""
    
    def test_valid_tickers(self):
        """Test conversion of valid ticker symbols."""
        assert ticker_to_edinet('7203') == 'E02144'  # Toyota Motor Corporation
        assert ticker_to_edinet('6758') == 'E01777'  # Sony Group Corporation
        assert ticker_to_edinet('9984') == 'E02778'  # SoftBank Group Corp
    
    def test_ticker_with_suffix(self):
        """Test tickers with .T or .JP suffixes."""
        assert ticker_to_edinet('7203.T') == 'E02144'
        assert ticker_to_edinet('6758.JP') == 'E01777'
    
    def test_invalid_ticker(self):
        """Test invalid ticker symbols."""
        assert ticker_to_edinet('0000') is None
        assert ticker_to_edinet('INVALID') is None
        assert ticker_to_edinet('') is None


class TestCompanyResolution:
    """Test company identifier resolution."""
    
    def test_edinet_code_passthrough(self):
        """Test that valid EDINET codes pass through unchanged."""
        assert resolve_company('E02144') == 'E02144'
        assert resolve_company('E01777') == 'E01777'
    
    def test_ticker_resolution(self):
        """Test ticker to EDINET code resolution."""
        assert resolve_company('7203') == 'E02144'
        assert resolve_company('6758') == 'E01777'
    
    def test_invalid_identifier(self):
        """Test invalid identifiers return None."""
        assert resolve_company('INVALID') is None
        assert resolve_company('0000') is None
        assert resolve_company('') is None


class TestCompanySearch:
    """Test company search functionality."""
    
    def test_exact_name_search(self):
        """Test searching by exact company name."""
        results = search_companies('TOYOTA MOTOR CORPORATION')
        assert len(results) > 0
        assert results[0]['name_en'] == 'TOYOTA MOTOR CORPORATION'
    
    def test_partial_name_search(self):
        """Test searching by partial company name."""
        results = search_companies('Toyota')
        assert len(results) > 0
        toyota_found = any('TOYOTA' in r['name_en'] for r in results)
        assert toyota_found
    
    def test_ticker_search(self):
        """Test searching by ticker symbol."""
        results = search_companies('72030')  # EDINET uses 5-digit format
        assert len(results) > 0
        assert results[0]['ticker'] == '72030'
    
    def test_industry_search(self):
        """Test searching by industry.

        FSA's current download endpoint serves industries in Japanese, but
        the loader normalizes them to English (via the translation map in
        entity_classifier) before caching. Search matches against both the
        normalized English form and the raw Japanese form, so queries in
        either language return results.
        """
        results = search_companies('Banks')
        assert len(results) > 0
        assert any('Banks' in r.get('industry', '') for r in results)

    def test_industry_search_japanese(self):
        """Industry search should also match the raw Japanese value."""
        results = search_companies('銀行業')
        assert len(results) > 0
    
    def test_no_results(self):
        """Test search with no results."""
        results = search_companies('NonexistentCompany12345')
        assert len(results) == 0
    
    def test_search_limit(self):
        """Test search result limiting."""
        results = search_companies('Corporation', limit=2)
        assert len(results) <= 2


class TestCompanyInfo:
    """Test company information retrieval."""
    
    def test_valid_edinet_code(self):
        """Test getting info for valid EDINET codes."""
        info = get_company_info('E02144')  # Toyota
        assert info is not None
        assert info['ticker'] == '72030'  # EDINET uses 5-digit format
        assert 'TOYOTA' in info['name_en']
    
    def test_invalid_edinet_code(self):
        """Test getting info for invalid EDINET codes."""
        info = get_company_info('E00000')
        assert info is None
        
        info = get_company_info('INVALID')
        assert info is None


class TestSupportedCompanies:
    """Test supported companies list."""
    
    def test_get_supported_companies(self):
        """Test getting list of supported companies."""
        companies = get_supported_companies()
        assert len(companies) > 0
        
        # Check structure
        for company in companies:
            assert 'edinet_code' in company
            assert 'ticker' in company
            assert 'name_en' in company
            assert 'name_ja' in company
    
    def test_companies_sorted(self):
        """Test that companies are sorted by ticker."""
        companies = get_supported_companies()
        tickers = [c.get('ticker', '') for c in companies if c.get('ticker')]
        assert tickers == sorted(tickers)


class TestCompanyLookupClass:
    """Test CompanyLookup class directly."""
    
    def setup_method(self):
        """Set up test instance."""
        self.lookup = CompanyLookup()
    
    def test_initialization(self):
        """Test proper initialization."""
        assert len(self.lookup.ticker_to_edinet_map) > 0
        assert len(self.lookup.companies) > 0
        assert len(self.lookup.edinet_to_ticker_map) > 0
    
    def test_reverse_lookup(self):
        """Test EDINET to ticker reverse lookup."""
        ticker = self.lookup.edinet_to_ticker_code('E02144')
        assert ticker == '72030'  # EDINET uses 5-digit format
    
    def test_search_indexes(self):
        """Test that search indexes are built."""
        assert len(self.lookup.name_to_edinet) > 0
        
        # Test that some variations exist
        toyota_variations = [
            k for k in self.lookup.name_to_edinet.keys() 
            if 'toyota' in k.lower()
        ]
        assert len(toyota_variations) > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_strings(self):
        """Test handling of empty strings."""
        assert ticker_to_edinet('') is None
        assert resolve_company('') is None
        
        results = search_companies('')
        assert len(results) == 0
    
    def test_whitespace_handling(self):
        """Test handling of whitespace."""
        assert ticker_to_edinet('  7203  ') == 'E02144'
        assert resolve_company('  E02144  ') == 'E02144'
    
    def test_case_insensitive_search(self):
        """Test case insensitive search."""
        results_lower = search_companies('toyota')
        results_upper = search_companies('TOYOTA')
        results_mixed = search_companies('Toyota')
        
        # Should find results regardless of case
        assert len(results_lower) > 0
        assert len(results_upper) > 0
        assert len(results_mixed) > 0


class TestCSVDataIntegrity:
    """Test CSV data file integrity and structure."""
    
    @pytest.mark.slow
    def test_edinet_codes_csv_integrity(self):
        """Ensure EDINET codes CSV has expected structure and key companies."""
        from edinet_tools.data_loader import get_data_loader
        
        # Load the raw company data
        data_loader = get_data_loader()
        companies = data_loader.get_companies()
        
        # Structure validation
        assert len(companies) > 10000, f"Expected >10k companies, got {len(companies)}"
        
        # Check that we have essential data fields
        sample_company = companies[0] if companies else {}
        required_fields = ['edinet_code', 'name_en', 'name_ja', 'ticker']
        
        for field in required_fields:
            assert field in sample_company, f"Missing required field: {field}"
        
        # Spot check that Toyota Motor Corporation exists
        toyota_found = any(
            company.get('name_en', '').upper().find('TOYOTA MOTOR CORPORATION') >= 0 
            for company in companies
        )
        assert toyota_found, "Toyota Motor Corporation not found in company data"
        
        # Validate Toyota's specific data
        toyota_companies = [
            company for company in companies 
            if 'TOYOTA MOTOR CORPORATION' in company.get('name_en', '').upper()
        ]
        assert len(toyota_companies) > 0, "No Toyota Motor Corporation entries found"
        
        # Check Toyota's EDINET code matches expected
        toyota_main = next(
            (company for company in toyota_companies 
             if company.get('ticker') in ['7203', '72030']), 
            None
        )
        assert toyota_main is not None, "Toyota Motor Corporation with ticker 7203 not found"
        assert toyota_main['edinet_code'] == 'E02144', f"Expected Toyota EDINET code E02144, got {toyota_main['edinet_code']}"
    
    @pytest.mark.slow
    def test_company_translations_csv_loadable(self):
        """Test that corporate entity translations CSV loads without errors."""
        from edinet_tools.data_loader import get_data_loader
        
        data_loader = get_data_loader()
        # This should not raise an exception
        translations = data_loader.load_translations()
        
        assert isinstance(translations, dict), "Translations should be a dictionary"
        assert len(translations) > 0, "Translations dictionary should not be empty"


if __name__ == "__main__":
    # Run tests if pytest is available
    try:
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not available. Install with: pip install pytest")
        print("Running basic test validation...")
        
        # Basic validation
        assert ticker_to_edinet('7203') == 'E02144'
        assert resolve_company('7203') == 'E02144'
        assert len(search_companies('Toyota')) > 0
        assert get_company_info('E02144') is not None
        assert len(get_supported_companies()) > 0
        
        print("✅ Basic validation passed!")

class TestWidthFoldedSearch:
    """Full-width / half-width folding in the data.py search layer (0.8.0).

    Japanese IMEs naturally produce full-width Latin (ＱＰＳ, ＫＥＹＥＮＣＥ)
    and catalogs mix widths (三菱ＵＦＪ carries full-width ＵＦＪ in its own
    search_text). Queries and index keys must be normalized via
    normalize_for_matching (NFKC + (株) rewrites + lowercase) so visually
    identical strings match. The entity.py layer already does this; this
    pins the same behavior for the data.py layer.
    """

    def test_halfwidth_query_matches_fullwidth_search_text(self):
        # 三菱ＵＦＪフィナンシャル・グループ's search_text contains full-width ＵＦＪ.
        results = search_companies('ufj')
        assert results, "half-width 'ufj' must match full-width ＵＦＪ"
        assert any(r['edinet_code'] == 'E03606' for r in results)

    def test_fullwidth_query_matches_halfwidth_search_text(self):
        # Keyence's search_text carries ASCII 'keyence'.
        results = search_companies('ＫＥＹＥＮＣＥ')
        assert results, "full-width ＫＥＹＥＮＣＥ must match ascii 'keyence'"
        assert any(r['edinet_code'] == 'E01967' for r in results)

    def test_halfwidth_katakana_resolves_name(self):
        # Half-width katakana ｷｰｴﾝｽ NFKC-folds to キーエンス.
        lookup = CompanyLookup()
        assert lookup.resolve_company_identifier('ｷｰｴﾝｽ') == 'E01967'
