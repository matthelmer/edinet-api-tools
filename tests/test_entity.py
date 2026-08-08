"""Tests for Entity and Fund classes."""
import pytest
from unittest.mock import Mock, patch
from edinet_tools.entity import (
    Entity, entity, entity_by_ticker, entity_by_edinet_code, search_entities,
    Fund, fund, funds_by_issuer
)
from edinet_tools.entity_classifier import EntityType


class TestEntityBasics:
    """Test Entity dataclass structure."""

    def test_entity_has_required_attributes(self):
        """Entity should have all expected attributes."""
        data = {
            'edinet_code': 'E02144',
            'name_jp': 'トヨタ自動車株式会社',
            'name_en': 'TOYOTA MOTOR CORPORATION',
            'ticker': '7203',
            'is_listed': True,
            'submitter_type': 'Listed company',
            'industry': 'Automobiles',
        }
        entity = Entity(data)

        assert entity.edinet_code == 'E02144'
        assert entity.name_jp == 'トヨタ自動車株式会社'
        assert entity.name_en == 'TOYOTA MOTOR CORPORATION'
        assert entity.ticker == '7203'
        assert entity.entity_type == EntityType.LISTED_COMPANY

    def test_entity_name_property_prefers_english(self):
        """Entity.name should return English name if available."""
        data = {
            'edinet_code': 'E02144',
            'name_jp': 'トヨタ自動車株式会社',
            'name_en': 'TOYOTA MOTOR CORPORATION',
        }
        entity = Entity(data)
        assert entity.name == 'TOYOTA MOTOR CORPORATION'

    def test_entity_name_falls_back_to_japanese(self):
        """Entity.name should fall back to Japanese if no English."""
        data = {
            'edinet_code': 'E12345',
            'name_jp': 'テスト株式会社',
            'name_en': None,
        }
        entity = Entity(data)
        assert entity.name == 'テスト株式会社'

    def test_entity_repr(self):
        """Entity repr should be informative."""
        data = {
            'edinet_code': 'E02144',
            'name_jp': 'トヨタ自動車株式会社',
            'name_en': 'TOYOTA MOTOR CORPORATION',
            'ticker': '7203',
        }
        entity = Entity(data)
        repr_str = repr(entity)
        assert 'E02144' in repr_str


class TestEntityLookup:
    """Test entity lookup functions using real CSV data."""

    def test_entity_by_ticker_toyota(self):
        """Look up Toyota by ticker."""
        result = entity_by_ticker("7203")
        assert result is not None
        assert result.edinet_code == 'E02144'

    def test_entity_by_ticker_with_suffix(self):
        """Ticker lookup handles .T suffix."""
        result = entity_by_ticker("7203.T")
        assert result is not None
        assert result.edinet_code == 'E02144'

    def test_entity_by_edinet_code(self):
        """Look up by EDINET code."""
        result = entity_by_edinet_code("E02144")
        assert result is not None
        assert 'TOYOTA' in result.name.upper()

    def test_entity_smart_lookup_ticker(self):
        """Smart lookup resolves ticker."""
        result = entity("7203")
        assert result is not None
        assert result.edinet_code == 'E02144'

    def test_entity_smart_lookup_edinet_code(self):
        """Smart lookup resolves EDINET code."""
        result = entity("E02144")
        assert result is not None

    def test_entity_smart_lookup_name(self):
        """Smart lookup resolves name."""
        result = entity("Toyota")
        assert result is not None
        assert result.edinet_code == 'E02144'

    def test_entity_not_found_returns_none(self):
        """Lookup returns None for unknown identifiers."""
        assert entity("XXXXXX") is None
        assert entity_by_ticker("0000") is None
        assert entity_by_edinet_code("E99999") is None


class TestEntitySearch:
    """Test entity search using real CSV data."""

    def test_search_entities_by_name(self):
        """Search finds entities by name."""
        results = search_entities("Toyota", limit=5)
        assert len(results) > 0
        assert any(e.edinet_code == 'E02144' for e in results)

    def test_search_entities_returns_entity_objects(self):
        """Search returns Entity objects."""
        results = search_entities("自動車", limit=3)
        assert all(isinstance(e, Entity) for e in results)

    def test_search_entities_respects_limit(self):
        """Search respects limit parameter."""
        results = search_entities("株式会社", limit=5)
        assert len(results) <= 5


class TestFundBasics:
    """Test Fund class structure."""

    def test_fund_has_required_attributes(self):
        """Fund has expected attributes."""
        data = {
            'fund_code': 'G01003',
            'name': 'しんきんインデックスファンド225',
            'issuer_edinet_code': 'E12422',
            'issuer_name': 'しんきんアセットマネジメント投信株式会社',
        }
        f = Fund(data)
        assert f.fund_code == 'G01003'
        assert f.issuer_edinet_code == 'E12422'

    def test_fund_repr(self):
        """Fund repr is informative."""
        data = {
            'fund_code': 'G01003',
            'name': 'しんきんインデックスファンド225',
            'issuer_edinet_code': 'E12422',
            'issuer_name': 'しんきんアセットマネジメント投信',
        }
        f = Fund(data)
        assert 'G01003' in repr(f)


class TestFundLookup:
    """Test fund lookup using real CSV data."""

    def test_fund_by_code(self):
        """Look up fund by fund code."""
        result = fund("G01003")
        assert result is not None
        assert result.fund_code == 'G01003'

    def test_funds_by_issuer_returns_list(self):
        """funds_by_issuer returns a list."""
        # Use a known fund issuer from the data
        results = funds_by_issuer("E12422")
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(f, Fund) for f in results)


class TestEntityFundIssuer:
    """Test entity fund issuer functionality."""

    def test_entity_type_is_fund_for_issuer(self):
        """Fund issuers classify as EntityType.FUND_ISSUER; regular companies do not."""
        toyota = entity("7203")
        assert toyota is not None
        assert toyota.entity_type != EntityType.FUND_ISSUER
        # E12422 is しんきんアセットマネジメント投信 - a known fund issuer
        issuer = entity_by_edinet_code("E12422")
        assert issuer is not None
        assert issuer.entity_type == EntityType.FUND_ISSUER

    def test_entity_type_unknown_for_nonexistent_code(self):
        """A code absent from the registry classifies as UNKNOWN, not a coerced False."""
        assert Entity({'edinet_code': 'E_NONEXISTENT'}).entity_type == EntityType.UNKNOWN

    def test_entity_funds_property_returns_list(self):
        """Entity.funds returns a list."""
        toyota = entity("7203")
        assert isinstance(toyota.funds, list)

    def test_entity_funds_empty_for_non_issuer(self):
        """Non-fund-issuers have empty funds list."""
        toyota = entity("7203")
        assert toyota.funds == []

    def test_entity_funds_populated_for_issuer(self):
        """Fund issuers have populated funds list."""
        issuer = entity_by_edinet_code("E12422")
        assert issuer is not None
        funds_list = issuer.funds
        assert len(funds_list) > 0
        assert all(isinstance(f, Fund) for f in funds_list)


class TestEntityDocuments:
    """Test Entity.documents() with mocked client."""

    def test_entity_documents_uses_module_client_when_no_explicit_client(self):
        """Entity.documents() uses module-level client when _client is None."""
        from unittest.mock import patch, MagicMock
        from edinet_tools._client import _reset_client, configure

        toyota = entity("7203")
        assert toyota._client is None

        _reset_client()
        with patch('edinet_tools._client._ApiClient') as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_documents_by_date.return_value = []

            configure(api_key='test-key')
            # Should NOT raise RuntimeError - uses module-level client
            docs = toyota.documents(days=1)
            assert docs == []

    def test_entity_documents_returns_list(self):
        """Entity.documents() returns list of Documents."""
        from edinet_tools.document import Document

        # Mock client response
        mock_filings = [
            {
                'docID': 'S100TEST1',
                'docTypeCode': '350',
                'submitDateTime': '2026-01-15 09:30',
                'edinetCode': 'E02144',
                'filerName': 'トヨタ',
            }
        ]

        mock_client = Mock()
        mock_client.get_documents_by_date.return_value = mock_filings

        toyota = entity("7203")
        toyota._client = mock_client
        docs = toyota.documents(days_back=1)

        assert isinstance(docs, list)

    def test_entity_documents_filters_by_doc_type(self):
        """Entity.documents() filters by doc type."""
        from edinet_tools.document import Document

        mock_filings = [
            {'docID': 'S1', 'docTypeCode': '350', 'submitDateTime': '2026-01-15 09:30', 'edinetCode': 'E02144', 'filerName': 'トヨタ'},
            {'docID': 'S2', 'docTypeCode': '120', 'submitDateTime': '2026-01-15 09:30', 'edinetCode': 'E02144', 'filerName': 'トヨタ'},
        ]

        mock_client = Mock()
        mock_client.get_documents_by_date.return_value = mock_filings

        toyota = entity("7203")
        toyota._client = mock_client
        docs = toyota.documents(doc_type="350", days_back=1)

        for doc in docs:
            assert doc.doc_type_code == "350"

    def test_entity_documents_returns_document_objects(self):
        """Entity.documents() returns Document objects."""
        from edinet_tools.document import Document

        mock_filings = [
            {
                'docID': 'S100TEST1',
                'docTypeCode': '350',
                'submitDateTime': '2026-01-15 09:30',
                'edinetCode': 'E02144',
                'filerName': 'トヨタ',
            }
        ]

        mock_client = Mock()
        mock_client.get_documents_by_date.return_value = mock_filings

        toyota = entity("7203")
        toyota._client = mock_client
        docs = toyota.documents(days_back=1)

        assert len(docs) > 0
        assert all(isinstance(d, Document) for d in docs)

def test_entity_has_industry_attribute():
    """Verify Entity objects expose the industry field."""
    from edinet_tools import entity_by_edinet_code
    # Toyota — should have industry data in the bundled CSV
    entity = entity_by_edinet_code('E02144')
    assert hasattr(entity, 'industry')
    # industry may be None for some entities, but the attribute must exist


def test_entity_has_phonetic_attribute():
    """Regression: Entity.name_phonetic should be populated for known entities."""
    import edinet_tools
    # E03533 = 株式会社三菱ＵＦＪ銀行; CSV col 8 = カブシキガイシャミツビシユーエフジェイギンコウ
    e = edinet_tools.entity_by_edinet_code("E03533")
    assert e is not None
    assert e.name_phonetic is not None
    assert len(e.name_phonetic) > 0
    # Phonetic field is katakana
    assert any('゠' <= c <= 'ヿ' for c in e.name_phonetic), \
        f"Expected katakana in phonetic name, got: {e.name_phonetic!r}"


def test_entity_has_corporate_number_attribute():
    """Regression: Entity.corporate_number should be populated for known entities."""
    import edinet_tools
    # E03533 = 株式会社三菱ＵＦＪ銀行; CSV col 12 = 5010001008846
    e = edinet_tools.entity_by_edinet_code("E03533")
    assert e is not None
    assert e.corporate_number == "5010001008846"
    assert len(e.corporate_number) == 13
    assert e.corporate_number.isdigit()


def test_entity_by_corporate_number_known():
    """Known 法人番号 returns the corresponding entity."""
    import edinet_tools
    # E03533 = 株式会社三菱ＵＦＪ銀行, 法人番号 5010001008846
    e = edinet_tools.entity_by_corporate_number("5010001008846")
    assert e is not None
    assert e.edinet_code == "E03533"


def test_entity_by_corporate_number_unknown():
    """Unknown 法人番号 returns None."""
    import edinet_tools
    assert edinet_tools.entity_by_corporate_number("9999999999999") is None


def test_entity_by_corporate_number_empty():
    """Empty / None / malformed inputs return None."""
    import edinet_tools
    assert edinet_tools.entity_by_corporate_number("") is None
    assert edinet_tools.entity_by_corporate_number(None) is None
    assert edinet_tools.entity_by_corporate_number("abc") is None


def test_search_smbc_half_width_finds_full_width_catalog():
    """Real-registry regression: half-width SMBC query finds full-width catalog entry.

    Catalog stores ＳＭＢＣ日興証券株式会社 (full-width SMBC); downstream
    extraction often yields SMBC日興証券株式会社 (half-width). Pre-v0.6.0
    these don't match; after NFKC normalization they collapse to the
    same key and resolve to E23615.
    """
    import edinet_tools
    results = edinet_tools.search_entities("SMBC日興証券株式会社")
    codes = [e.edinet_code for e in results]
    assert "E23615" in codes, f"Expected E23615 in results, got: {codes}"


def test_search_full_width_ufj_matches():
    """株式会社三菱UFJ銀行 (half-width) finds E03533 (catalog has full-width ＵＦＪ)."""
    import edinet_tools
    results = edinet_tools.search_entities("株式会社三菱UFJ銀行")
    codes = [e.edinet_code for e in results]
    assert "E03533" in codes


def test_search_individual_name_space_variance_query_no_space():
    """Query without internal space finds catalog entry with full-width space.

    Real case: shareholder lists may render '伊藤翔太' (no space) but the
    catalog has '伊藤　翔太' (with U+3000). NFKC folds the catalog space
    to ASCII; bidirectional whitespace handling must still bridge them.
    """
    import edinet_tools
    results = edinet_tools.search_entities("伊藤翔太")
    codes = [e.edinet_code for e in results]
    assert "E36920" in codes, f"Expected E36920 in results, got: {codes}"


def test_search_individual_name_space_variance_query_with_space():
    """Query with full-width space finds catalog entry with no space.

    Real case: query '代永　衛' (U+3000) vs catalog '代永衛' (no space).
    """
    import edinet_tools
    results = edinet_tools.search_entities("代永　衛")
    codes = [e.edinet_code for e in results]
    assert "E10888" in codes, f"Expected E10888 in results, got: {codes}"


def test_search_kabushiki_gaiji_matches():
    """㈱ in query matches 株式会社 in catalog."""
    import edinet_tools
    # JPモルガン証券㈱ should find E20021 (catalog: ＪＰモルガン証券株式会社)
    results = edinet_tools.search_entities("JPモルガン証券㈱")
    codes = [e.edinet_code for e in results]
    assert "E20021" in codes


def test_search_empty_returns_empty_list():
    """Empty / whitespace-only query returns empty list."""
    import edinet_tools
    assert edinet_tools.search_entities("") == []
    assert edinet_tools.search_entities("   ") == []
    assert edinet_tools.search_entities("　　") == []  # full-width spaces


def test_search_no_match_returns_empty_list():
    """Query that matches no entity returns empty list."""
    import edinet_tools
    assert edinet_tools.search_entities("zzz-not-a-real-entity-xyz") == []


def test_search_respects_limit():
    """limit parameter caps the returned list."""
    import edinet_tools
    results = edinet_tools.search_entities("株式会社", limit=5)
    assert len(results) <= 5


def test_search_toyota_still_works():
    """Regression: existing 'Toyota' test still passes after rewrite."""
    import edinet_tools
    results = edinet_tools.search_entities("Toyota", limit=10)
    codes = [e.edinet_code for e in results]
    assert "E02144" in codes


def test_search_exact_match_is_fast():
    """Performance canary: exact-match path completes in under 0.1s for 100 calls."""
    import edinet_tools
    import time
    # Warm-up to ensure classifier is loaded (load time isn't what we're measuring)
    edinet_tools.search_entities("Toyota Motor Corporation", limit=1)
    start = time.perf_counter()
    for _ in range(100):
        edinet_tools.search_entities("Toyota Motor Corporation", limit=1)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"100 calls took {elapsed:.3f}s, expected <0.1s"


import csv as _csv_module
from pathlib import Path as _Path


def _load_name_variants_fixture():
    """Load tests/data/name_variants.csv as a list of pytest.param tuples."""
    fixture_path = _Path(__file__).parent / 'data' / 'name_variants.csv'
    rows = []
    with open(fixture_path, 'r', encoding='utf-8') as f:
        reader = _csv_module.DictReader(f)
        for row in reader:
            xfail_marker = row.get('xfail', '').strip().lower() == 'xfail'
            marks = (pytest.mark.xfail(reason=row['scenario']),) if xfail_marker else ()
            rows.append(pytest.param(
                row['query'],
                row['expected_edinet_code'],
                id=row['scenario'],
                marks=marks,
            ))
    return rows


@pytest.mark.parametrize("query,expected_code", _load_name_variants_fixture())
def test_search_variants(query, expected_code):
    """Variant regression: each row in name_variants.csv asserts that
    search_entities(query) returns expected_code among the top results.

    Passing rows assert v0.6.0 normalization resolves the variance.
    xfail rows document scope boundaries (structural variance, punctuation,
    symbols, abbreviations) deliberately left for future work.
    """
    import edinet_tools
    results = edinet_tools.search_entities(query, limit=10)
    codes = [e.edinet_code for e in results]
    assert expected_code in codes, \
        f"Expected {expected_code} in results for {query!r}, got: {codes}"


def test_entity_by_ticker_alphanumeric_192A():
    """Alphanumeric ticker (192A class) resolves to its entity."""
    import edinet_tools
    e = edinet_tools.entity_by_ticker("192A")
    assert e is not None
    assert e.edinet_code == "E37627"


def test_entity_by_ticker_alphanumeric_262A():
    import edinet_tools
    e = edinet_tools.entity_by_ticker("262A")
    assert e is not None
    assert e.edinet_code == "E03492"


def test_entity_by_ticker_numeric_still_works():
    """Regression: existing 4-digit numeric lookup (Toyota 7203) still works."""
    import edinet_tools
    e = edinet_tools.entity_by_ticker("7203")
    assert e is not None
    assert e.edinet_code == "E02144"


def test_entity_by_ticker_with_T_suffix():
    """Regression: .T suffix is stripped."""
    import edinet_tools
    e = edinet_tools.entity_by_ticker("7203.T")
    assert e is not None
    assert e.edinet_code == "E02144"


def test_entity_by_ticker_unknown_returns_none():
    """Unknown ticker returns None."""
    import edinet_tools
    assert edinet_tools.entity_by_ticker("9999") is None


def test_entity_by_ticker_is_fast():
    """Performance canary: 100 lookups under 0.1s (was O(N) scan over 11k rows)."""
    import edinet_tools
    import time
    # Warm-up
    edinet_tools.entity_by_ticker("7203")
    start = time.perf_counter()
    for _ in range(100):
        edinet_tools.entity_by_ticker("7203")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"100 ticker lookups took {elapsed:.3f}s"


def test_search_homonym_returns_multiple():
    """When multiple EDINET codes share a normalized name, search_entities
    returns all of them. Common for Japanese individual filers and for
    parent/subsidiary entities sharing an English name."""
    import edinet_tools
    from edinet_tools.entity_classifier import EntityClassifier
    from edinet_tools.normalize import normalize_for_matching
    c = EntityClassifier()
    homonyms = [(k, v) for k, v in c._by_normalized_name.items() if len(v) > 1]
    if not homonyms:
        pytest.skip("No homonym pairs in catalog")
    normalized_name, codes = homonyms[0]
    # Reconstruct a query that produces this normalized key. The collision
    # may be on the JP side, the EN side, or both — find which.
    query = None
    for code in codes:
        raw = c._edinet_entities[code]
        if normalize_for_matching(raw.get('name_jp')) == normalized_name:
            query = raw['name_jp']
            break
        if normalize_for_matching(raw.get('name_en')) == normalized_name:
            query = raw['name_en']
            break
    assert query is not None, "Could not reconstruct a query for the homonym set"
    results = edinet_tools.search_entities(query, limit=20)
    result_codes = {e.edinet_code for e in results}
    intersection = set(codes) & result_codes
    assert len(intersection) >= 2, \
        f"Homonym query {query!r} (norm: {normalized_name!r}) returned {result_codes}, " \
        f"expected at least 2 of {codes}"
