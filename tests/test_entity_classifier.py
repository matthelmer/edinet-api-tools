"""
Tests for EntityClassifier.

Uses real FSA data files to validate classification logic.
"""
import warnings

import pytest
from edinet_tools.entity_classifier import (
    EntityClassifier,
    EntityType,
    _EDINET_COLUMN_ALIASES,
    _resolve_columns,
    translate_industry_to_english,
)


@pytest.fixture
def classifier():
    """Load EntityClassifier with real data."""
    return EntityClassifier()


class TestIndustryTranslation:
    """Test the JP→EN industry translation helper."""

    def test_translates_japanese_to_english(self):
        assert translate_industry_to_english("銀行業") == "Banks"
        assert translate_industry_to_english("輸送用機器") == "Transportation Equipments"
        assert translate_industry_to_english("電気機器") == "Electric Appliances"

    def test_passes_through_english(self):
        # Values already in English stay unchanged (same CSV-variant tolerance
        # the loader needs when given an English-format file).
        assert translate_industry_to_english("Banks") == "Banks"
        assert translate_industry_to_english("Transportation Equipments") == "Transportation Equipments"

    def test_passes_through_none(self):
        assert translate_industry_to_english(None) is None

    def test_passes_through_unknown(self):
        # Don't guess: unknown values come back verbatim so the underlying
        # data is never silently rewritten.
        assert translate_industry_to_english("Some Brand New FSA Category") == "Some Brand New FSA Category"

    def test_multiple_jp_values_collapse_to_others(self):
        # Several non-industrial entity categories all translate to "Others"
        # in the official English CSV; the helper mirrors that.
        assert translate_industry_to_english("外国法人・組合") == "Others"
        assert translate_industry_to_english("個人（組合発行者を除く）") == "Others"


class TestColumnResolution:
    """Test the header-based column resolver."""

    def test_resolves_english_header(self):
        header = [
            "EDINET Code", "Type of Submitter", "Listed company / Unlisted company",
            "Consolidated / NonConsolidated", "Capital stock", "account closing date",
            "Submitter Name", "Submitter Name（alphabetic）", "Submitter Name（phonetic）",
            "Province", "Submitter's industry", "Securities Identification Code",
            "Submitter's Japan Corporate Number",
        ]
        cols = _resolve_columns(header, _EDINET_COLUMN_ALIASES)
        assert cols["edinet_code"] == 0
        assert cols["listed"] == 2
        assert cols["industry"] == 10
        assert cols["securities_code"] == 11

    def test_resolves_japanese_header(self):
        header = [
            "ＥＤＩＮＥＴコード", "提出者種別", "上場区分", "連結の有無", "資本金", "決算日",
            "提出者名", "提出者名（英字）", "提出者名（ヨミ）", "所在地", "提出者業種",
            "証券コード", "提出者法人番号",
        ]
        cols = _resolve_columns(header, _EDINET_COLUMN_ALIASES)
        assert cols["edinet_code"] == 0
        assert cols["listed"] == 2
        assert cols["industry"] == 10
        assert cols["securities_code"] == 11

    def test_missing_column_raises_clear_error(self):
        # If FSA ever renames a column entirely (no match in any known
        # language), the loader should fail loudly rather than silently
        # returning wrong data indexed from the wrong column.
        header = ["EDINET Code", "WeirdRename", "Listed company / Unlisted company"]
        with pytest.raises(ValueError) as exc_info:
            _resolve_columns(header, _EDINET_COLUMN_ALIASES)
        msg = str(exc_info.value)
        # Error message identifies which logical field is missing so the
        # maintainer knows exactly what to update.
        assert "submitter_type" in msg
        assert "Type of Submitter" in msg  # shows the tried aliases


class TestEntityClassifierLoading:
    """Test data loading and initialization."""

    def test_loads_successfully(self, classifier):
        """Classifier should load without errors."""
        assert classifier is not None
        assert len(classifier._edinet_entities) > 10000
        assert len(classifier._fund_edinet_codes) > 300

    def test_stats_returns_expected_structure(self, classifier):
        """Stats should return count information."""
        stats = classifier.stats
        assert 'total_entities' in stats
        assert 'listed_companies' in stats
        assert 'unlisted_entities' in stats
        assert 'fund_issuers' in stats
        assert stats['total_entities'] > 10000
        assert stats['listed_companies'] > 3000

    def test_data_version_extracted(self, classifier):
        """Data version should be extracted from filenames."""
        version = classifier.data_version
        assert 'edinet_codes' in version
        assert 'fund_codes' in version
        # Should be YYYY-MM-DD format or 'unknown'
        assert version['edinet_codes'] == 'unknown' or len(version['edinet_codes']) == 10


class TestListedCompanyClassification:
    """Test classification of listed companies."""

    def test_toyota_is_listed_company(self, classifier):
        """Toyota (E02144) should be a listed company."""
        assert classifier.get_entity_type('E02144') == EntityType.LISTED_COMPANY
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert classifier.is_listed('E02144')
        assert not classifier.is_fund('E02144')
        assert classifier.is_known('E02144')

    def test_toyota_securities_code(self, classifier):
        """Toyota should have correct securities code."""
        code = classifier.get_securities_code('E02144')
        assert code == '7203'

    def test_toyota_name(self, classifier):
        """Toyota should have correct name."""
        name = classifier.get_entity_name('E02144')
        assert 'TOYOTA' in name.upper()

    def test_sony_is_listed_company(self, classifier):
        """Sony (E01777) should be a listed company."""
        assert classifier.get_entity_type('E01777') == EntityType.LISTED_COMPANY
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert classifier.is_listed('E01777')

    def test_softbank_group_is_listed(self, classifier):
        """SoftBank Group (E02778) should be listed."""
        assert classifier.get_entity_type('E02778') == EntityType.LISTED_COMPANY


class TestFundClassification:
    """Test classification of investment funds."""

    def test_pure_fund_issuer_detected(self, classifier):
        """A fund issuer that is not also listed should classify as FUND."""
        # Find a fund issuer that is NOT also listed in the EDINET registry.
        for code in classifier._fund_edinet_codes:
            entity = classifier._edinet_entities.get(code)
            if not entity or not entity['is_listed']:
                assert classifier.is_fund(code)
                assert classifier.get_entity_type(code) == EntityType.FUND
                return
        pytest.fail("No pure (non-listed) fund issuer found in registry")

    def test_listed_company_takes_precedence_over_fund_registry(self, classifier):
        """
        Some listed companies (e.g. Credit Saison, JAFCO) also appear in the
        fund registry because they have issued fund products. They should
        classify as LISTED_COMPANY, not FUND — that is what investors care
        about.

        Regression test for the fund-precedence bug fixed in 0.5.1.
        """
        # Credit Saison (E03041, ticker 8253) — credit card / consumer finance,
        # listed on TSE Prime, also issued fund products historically.
        assert classifier.is_fund('E03041'), \
            "Credit Saison should still be in the fund registry"
        assert classifier.get_entity_type('E03041') == EntityType.LISTED_COMPANY, \
            "Credit Saison should classify as LISTED_COMPANY despite fund-registry membership"

        # JAFCO Group (E04806, ticker 8595) — venture capital firm, listed
        # on TSE Prime, issues PE/VC funds.
        assert classifier.is_fund('E04806'), \
            "JAFCO should still be in the fund registry"
        assert classifier.get_entity_type('E04806') == EntityType.LISTED_COMPANY, \
            "JAFCO should classify as LISTED_COMPANY despite fund-registry membership"


class TestUnknownEntities:
    """Test handling of unknown EDINET codes."""

    def test_unknown_code_returns_unknown(self, classifier):
        """Unknown EDINET codes should return UNKNOWN."""
        assert classifier.get_entity_type('E99999') == EntityType.UNKNOWN
        assert not classifier.is_known('E99999')
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert not classifier.is_listed('E99999')
        assert not classifier.is_fund('E99999')

    def test_empty_code_returns_unknown(self, classifier):
        """Empty or None EDINET codes should return UNKNOWN."""
        assert classifier.get_entity_type('') == EntityType.UNKNOWN
        assert classifier.get_entity_type(None) == EntityType.UNKNOWN

    def test_invalid_format_returns_unknown(self, classifier):
        """Invalid EDINET code formats should return UNKNOWN."""
        assert classifier.get_entity_type('12345') == EntityType.UNKNOWN
        assert classifier.get_entity_type('ABCDE') == EntityType.UNKNOWN


class TestSecuritiesCodeFormatting:
    """Test securities code extraction and formatting."""

    def test_no_securities_code_for_unknown(self, classifier):
        """Unknown entities should return None for securities code."""
        assert classifier.get_securities_code('E99999') is None


class TestEntityNames:
    """Test entity name retrieval."""

    def test_english_name_preferred(self, classifier):
        """English name should be returned when available and preferred."""
        name = classifier.get_entity_name('E02144', prefer_english=True)
        assert name is not None
        # Toyota's English name should contain 'TOYOTA'
        assert 'TOYOTA' in name.upper()

    def test_japanese_name_fallback(self, classifier):
        """Japanese name should be returned when English not available."""
        # Find an entity without English name
        for edinet_code, entity in classifier._edinet_entities.items():
            if entity['name_jp'] and not entity.get('name_en'):
                name = classifier.get_entity_name(edinet_code, prefer_english=True)
                assert name == entity['name_jp']
                break

    def test_unknown_entity_name_is_none(self, classifier):
        """Unknown entities should return None for name."""
        assert classifier.get_entity_name('E99999') is None


class TestRepr:
    """Test string representation."""

    def test_repr_contains_counts(self, classifier):
        """Repr should contain entity and fund counts."""
        repr_str = repr(classifier)
        assert 'EntityClassifier' in repr_str
        assert 'entities=' in repr_str
        assert 'funds=' in repr_str


class TestReverseIndexes:
    """v0.6.0 — reverse indexes for O(1) lookup."""

    def test_reverse_index_by_normalized_name_built(self, classifier):
        """The _by_normalized_name reverse index is populated after load."""
        assert hasattr(classifier, '_by_normalized_name')
        assert isinstance(classifier._by_normalized_name, dict)
        assert len(classifier._by_normalized_name) > 1000
        # Each value is a list of EDINET codes (lists, not strings — homonyms possible)
        for key, value in list(classifier._by_normalized_name.items())[:5]:
            assert isinstance(value, list)
            assert all(v.startswith('E') for v in value)

    def test_reverse_index_by_securities_code_built(self, classifier):
        """The _by_securities_code reverse index is populated and maps to EDINET codes."""
        assert hasattr(classifier, '_by_securities_code')
        assert isinstance(classifier._by_securities_code, dict)
        assert len(classifier._by_securities_code) > 1000

    def test_reverse_index_by_corporate_number_built(self, classifier):
        """The _by_corporate_number reverse index is populated."""
        assert hasattr(classifier, '_by_corporate_number')
        assert isinstance(classifier._by_corporate_number, dict)
        # E03533 → 5010001008846
        assert classifier._by_corporate_number.get("5010001008846") == "E03533"

    def test_normalized_form_stored_per_entity(self, classifier):
        """Each entity in _edinet_entities has a _normalized field used by the substring scan."""
        raw = classifier._edinet_entities.get("E02144")  # Toyota
        assert raw is not None
        assert '_normalized' in raw
        assert isinstance(raw['_normalized'], str)
        assert len(raw['_normalized']) > 0

    def test_is_listed_handles_both_csv_languages(self, classifier):
        """FSA has used both 'Listed company' (English) and '上場' (Japanese)
        in the catalog's 上場区分 column at different points. The classifier
        must accept either form."""
        # Toyota is canonically a listed company. Whichever language the
        # bundled CSV currently uses, this assertion must hold.
        # is_listed() is deprecated (v0.6.1); the canonical check is get_entity_type() == LISTED_COMPANY.
        # This test verifies the deprecated path still returns the correct value.
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert classifier.is_listed("E02144"), \
                "Toyota (E02144) must be classified as listed regardless of " \
                "whether the catalog uses 'Listed company' or '上場'"
        stats = classifier.stats
        assert stats['listed_companies'] > 1000, \
            f"Expected >1000 listed companies, got {stats['listed_companies']}"
