"""Tier-core tests (0.8.0 stage-5 Task 7).

`Tier` + `resolve_tiers` are the declarative replacement for the per-parser
waterfall idioms. Every semantic pinned here is a behavior the three
migrated parsers ALREADY have — the tier core must reproduce them exactly,
because the migration is proven by full-corpus old-vs-new equivalence:

- 'financial' mode == the get_fin/_coalesce idiom (extract_financial
  semantics per tier: pattern-major over the tier's element chain, null
  markers skip WITHIN the tier, a coerce-truthy string that fails parse_int
  advances the WATERFALL).
- 'string' mode == the per-share/ratio idioms (one extract_value call over
  the full pattern list per tier; coerce=True reproduces the eps/nav
  null-marker skipping, coerce=False reproduces the equity-ratio/roe
  first-non-empty-raw-string-stops legacy).
- suffix tiers == the five securities.py hatches (bare-period context only,
  marker rows skipped mid-scan).
"""
from decimal import Decimal

import pytest

from edinet_tools.parsers.extraction import (
    Tier,
    resolve_tiers,
    get_dei,
    coerce_numeric_value,
)


def _cf(*rows, filename='test.csv'):
    """Build a csv_files structure from (element_id, context_id, value)."""
    return [{
        'filename': filename,
        'data': [
            {'要素ID': e, '項目名': '', 'コンテキストID': c, '相対年度': '',
             '連結・個別': '', '期間・時点': '', 'ユニットID': 'JPY',
             '単位': '', '値': v}
            for e, c, v in rows
        ],
    }]


CYI = 'CurrentYearInstant'
CYI_NC = 'CurrentYearInstant_NonConsolidatedMember'


class TestTierDataclass:
    def test_frozen_and_defaults(self):
        t = Tier('jppfs_cor:Assets')
        assert t.element_id == 'jppfs_cor:Assets'
        assert t.standards is None
        assert t.exclude_standards is None
        assert t.suffix_match is False
        assert t.last_resort is False
        with pytest.raises(Exception):
            t.element_id = 'other'

    def test_elements_normalizes_single_and_tuple(self):
        assert Tier('a').elements == ('a',)
        assert Tier(('a', 'b')).elements == ('a', 'b')


class TestTierOrder:
    def test_first_matching_tier_wins(self):
        cf = _cf(('elemA', CYI, '100'), ('elemB', CYI, '200'))
        hit = resolve_tiers(cf, (Tier('elemA'), Tier('elemB')),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 100
        assert hit.element_id == 'elemA'

    def test_falls_through_absent_tier(self):
        cf = _cf(('elemB', CYI, '200'))
        hit = resolve_tiers(cf, (Tier('elemA'), Tier('elemB')),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 200
        assert hit.element_id == 'elemB'

    def test_honest_none_when_nothing_matches(self):
        cf = _cf(('other', CYI, '1'))
        hit = resolve_tiers(cf, (Tier('elemA'), Tier('elemB')),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit is None

    def test_wrong_context_does_not_match(self):
        cf = _cf(('elemA', 'Prior1YearInstant', '100'))
        hit = resolve_tiers(cf, (Tier('elemA'),),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit is None


class TestStandardsScoping:
    TIERS = (Tier('ifrs_elem', standards=('IFRS',)), Tier('neutral_elem'))

    def test_scoped_tier_used_when_standard_matches(self):
        cf = _cf(('ifrs_elem', CYI, '1'), ('neutral_elem', CYI, '2'))
        hit = resolve_tiers(cf, self.TIERS, standard='IFRS', period=CYI,
                            is_consolidated=True)
        assert hit.value == 1

    def test_scoped_tier_skipped_when_standard_excluded(self):
        cf = _cf(('ifrs_elem', CYI, '1'), ('neutral_elem', CYI, '2'))
        hit = resolve_tiers(cf, self.TIERS, standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 2

    def test_scoped_tier_skipped_when_standard_is_none(self):
        """A missing DEI standard only matches standards=None tiers."""
        cf = _cf(('ifrs_elem', CYI, '1'), ('neutral_elem', CYI, '2'))
        hit = resolve_tiers(cf, self.TIERS, standard=None, period=CYI,
                            is_consolidated=True)
        assert hit.value == 2

    def test_exclude_standards_blacklist(self):
        """The 0.7.1 operating-income gate shape: skip the parent J-GAAP
        tier for IFRS/US-GAAP filers, but keep it for J-GAAP AND for
        DEI-missing (standard=None) filers — a whitelist cannot express
        'every standard except these two including unknown ones'."""
        tiers = (Tier('jgaap_elem', exclude_standards=('IFRS', 'US GAAP')),)
        cf = _cf(('jgaap_elem', CYI, '5'))
        for standard, expect in (('Japan GAAP', 5), (None, 5)):
            hit = resolve_tiers(cf, tiers, standard=standard, period=CYI,
                                is_consolidated=True)
            assert hit.value == expect, standard
        for standard in ('IFRS', 'US GAAP'):
            assert resolve_tiers(cf, tiers, standard=standard, period=CYI,
                                 is_consolidated=True) is None, standard


class TestLastResort:
    def test_last_resort_consulted_only_when_all_else_none(self):
        cf = _cf(('lastA', CYI, '1'), ('normalB', CYI, '2'))
        # Positional order puts the last_resort tier FIRST — it must still
        # lose to any normal tier that resolves.
        tiers = (Tier('lastA', last_resort=True), Tier('normalB'))
        hit = resolve_tiers(cf, tiers, standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 2

    def test_last_resort_fills_when_normals_miss(self):
        cf = _cf(('lastA', CYI, '1'))
        tiers = (Tier('normalB'), Tier('lastA', last_resort=True))
        hit = resolve_tiers(cf, tiers, standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 1
        assert hit.element_id == 'lastA'

    def test_last_resort_respects_standards_scope(self):
        cf = _cf(('lastA', CYI, '1'))
        tiers = (Tier('lastA', standards=('IFRS',), last_resort=True),)
        assert resolve_tiers(cf, tiers, standard='Japan GAAP', period=CYI,
                             is_consolidated=True) is None


class TestFinancialModeSemantics:
    """'financial' mode must reproduce extract_financial + _coalesce exactly."""

    def test_pattern_major_within_tier(self):
        """Non-consolidated: the fallback element at the preferred
        (_NonConsolidatedMember) context beats the primary element at the
        bare context — extract_financial's pattern-outer loop."""
        cf = _cf(('primary', CYI, '100'), ('fallback', CYI_NC, '200'))
        hit = resolve_tiers(cf, (Tier(('primary', 'fallback')),),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=False)
        assert hit.value == 200
        assert hit.element_id == 'fallback'

    def test_consolidated_never_borrows_nonconsolidated(self):
        cf = _cf(('primary', CYI_NC, '100'))
        hit = resolve_tiers(cf, (Tier('primary'),),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit is None

    def test_null_marker_skips_within_tier_then_next_tier(self):
        cf = _cf(('elemA', CYI, '－'), ('elemB', CYI, '300'))
        hit = resolve_tiers(cf, (Tier('elemA'), Tier('elemB')),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 300

    def test_marker_on_primary_falls_to_fallback_same_tier(self):
        cf = _cf(('primary', CYI, '－'), ('fallback', CYI, '400'))
        hit = resolve_tiers(cf, (Tier(('primary', 'fallback')),),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 400

    def test_unparseable_string_advances_waterfall_skipping_rest_of_tier(self):
        """A coerce-truthy string that fails parse_int commits the tier
        (its remaining elements are NOT consulted) but advances the
        waterfall — matching get_fin returning None into _coalesce."""
        cf = _cf(('junk', CYI, 'true'), ('sibling', CYI, '7'),
                 ('nextTier', CYI, '8'))
        hit = resolve_tiers(cf, (Tier(('junk', 'sibling')), Tier('nextTier')),
                            standard='Japan GAAP', period=CYI,
                            is_consolidated=True)
        assert hit.value == 8
        assert hit.element_id == 'nextTier'

    def test_negative_and_fullwidth_values_parse(self):
        cf = _cf(('elemA', CYI, '-1000'), ('elemB', CYI, '１，０００'))
        hit = resolve_tiers(cf, (Tier('elemA'),), standard=None, period=CYI,
                            is_consolidated=True)
        assert hit.value == -1000
        hit = resolve_tiers(cf, (Tier('elemB'),), standard=None, period=CYI,
                            is_consolidated=True)
        assert hit.value == 1000

    def test_period_none_is_context_blind(self):
        """period=None reproduces the semi-annual first-row-in-file-order
        legacy (Task 9 replaces this with real periods)."""
        cf = _cf(('elemA', 'SomeOddContext', '11'), ('elemA', CYI, '22'))
        hit = resolve_tiers(cf, (Tier('elemA'),), standard=None, period=None,
                            is_consolidated=None)
        assert hit.value == 11


class TestSuffixTiers:
    def test_suffix_matches_custom_namespace_at_bare_period_only(self):
        cf = _cf(
            ('jpcrp030000-asr_E99999-000:SalesRevenuesIFRS', CYI_NC, '111'),
            ('jpcrp030000-asr_E99999-000:SalesRevenuesIFRS', CYI, '222'),
        )
        # Even for a non-consolidated filer the suffix hatch reads ONLY the
        # bare context — the securities.py hatches' documented contract.
        hit = resolve_tiers(cf, (Tier('SalesRevenuesIFRS', suffix_match=True),),
                            standard='IFRS', period=CYI, is_consolidated=False)
        assert hit.value == 222

    def test_suffix_marker_row_skipped_scan_continues(self):
        cf = _cf(
            ('nsA:TotalEquityIFRSSummaryOfBusinessResults', CYI, '－'),
            ('nsB:TotalEquityIFRSSummaryOfBusinessResults', CYI, '333'),
        )
        hit = resolve_tiers(
            cf, (Tier('TotalEquityIFRSSummaryOfBusinessResults', suffix_match=True),),
            standard='IFRS', period=CYI, is_consolidated=True)
        assert hit.value == 333

    def test_suffix_canonicals_tried_in_order(self):
        cf = _cf(
            ('ns:SecondCanonical', CYI, '2'),
            ('ns:FirstCanonical', CYI, '1'),
        )
        hit = resolve_tiers(
            cf, (Tier(('FirstCanonical', 'SecondCanonical'), suffix_match=True),),
            standard=None, period=CYI, is_consolidated=True)
        assert hit.value == 1

    def test_suffix_requires_period(self):
        with pytest.raises(ValueError):
            resolve_tiers(_cf(), (Tier('X', suffix_match=True),),
                          standard=None, period=None, is_consolidated=True)


class TestStringMode:
    def test_returns_string_value_and_element(self):
        cf = _cf(('ratioA', CYI, '0.55'))
        hit = resolve_tiers(cf, (Tier('ratioA'),), standard=None, period=CYI,
                            is_consolidated=True, mode='string')
        assert hit.value == '0.55'
        assert hit.element_id == 'ratioA'

    def test_coerce_true_marker_advances_to_next_tier(self):
        """The eps/nav idiom: coerce_numeric_value between tiers."""
        cf = _cf(('epsA', CYI, '－'), ('epsB', CYI, '12.34'))
        hit = resolve_tiers(cf, (Tier('epsA'), Tier('epsB')),
                            standard=None, period=CYI, is_consolidated=True,
                            mode='string', coerce=True)
        assert hit.value == '12.34'

    def test_coerce_false_first_nonempty_raw_string_stops(self):
        """The legacy equity-ratio/roe idiom: a null-marker string WINS the
        scan (later tiers are not consulted); the caller's parse_percentage
        turns it into None. Pinned so the migration cannot silently 'fix'
        this behavior outside the ratified C1 change."""
        cf = _cf(('ratioA', CYI, '－'), ('ratioB', CYI, '0.4'))
        hit = resolve_tiers(cf, (Tier('ratioA'), Tier('ratioB')),
                            standard=None, period=CYI, is_consolidated=True,
                            mode='string', coerce=False)
        assert hit.value == '－'
        assert hit.element_id == 'ratioA'

    def test_string_mode_is_element_major_across_patterns(self):
        """One extract_value call per tier over the FULL pattern list: for a
        non-consolidated filer, a marker at the preferred context is
        returned by extract_value (coerced to None -> next TIER) — the bare
        context of the SAME element is never reached. This is the
        eps-idiom's exact shape (extract_value short-circuits on the first
        pattern that has any row)."""
        cf = _cf(('epsA', CYI_NC, '－'), ('epsA', CYI, '99'),
                 ('epsB', CYI_NC, '55'))
        hit = resolve_tiers(cf, (Tier('epsA'), Tier('epsB')),
                            standard=None, period=CYI, is_consolidated=False,
                            mode='string', coerce=True)
        assert hit.value == '55'
        assert hit.element_id == 'epsB'

    def test_string_mode_suffix_tier(self):
        """The nav idiom's 4th tier is a suffix hatch returning a string."""
        cf = _cf(('ns:BpsVariantUSGAAP', CYI, '123.45'),)
        hit = resolve_tiers(cf, (Tier('missing'),
                                 Tier('BpsVariantUSGAAP', suffix_match=True)),
                            standard='US GAAP', period=CYI,
                            is_consolidated=True, mode='string', coerce=True)
        assert hit.value == '123.45'


class TestGetDei:
    def test_reads_filing_date_instant_only(self):
        cf = _cf(('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E12345'),
                 ('jpdei_cor:AccountingStandardsDEI', CYI, 'WRONG'))
        emap = {'edinet_code': 'jpdei_cor:EDINETCodeDEI',
                'accounting_standard': 'jpdei_cor:AccountingStandardsDEI'}
        assert get_dei(cf, emap, 'edinet_code') == 'E12345'
        assert get_dei(cf, emap, 'accounting_standard') is None
        assert get_dei(cf, emap, 'not_a_key') is None


class TestNullMarkerExtension:
    """B5: '―' (U+2015 horizontal bar) and '—' (U+2014 em dash) join the
    null-marker family BEFORE any coercion swap — they appear in real
    filings (the quarterly eps tuple has always nulled them) and NFKC does
    not fold them to '-'."""

    @pytest.mark.parametrize('marker', ['―', '—', '－', '−', '-', '', ' '])
    def test_markers_coerce_to_none(self, marker):
        assert coerce_numeric_value(marker) is None

    def test_negative_numbers_still_pass(self):
        assert coerce_numeric_value('-1000') == '-1000'

    def test_fullwidth_digits_still_normalize(self):
        assert coerce_numeric_value('１，０００') == '1,000'
