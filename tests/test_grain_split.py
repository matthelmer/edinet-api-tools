"""Ownership-basis field split (v0.8.0): net_assets / net_income /
prior_net_income each split into an *_owners field (equity/profit
attributable to owners of parent) and an *_total field (includes
non-controlling interests).

Routing is per accounting standard and never cross-basis: an owners-basis
XBRL element fills ONLY an *_owners field, a total-basis element fills ONLY
an *_total field. J-GAAP has no owners-only net-assets concept, so
net_assets_owners is ALWAYS None for J-GAAP filers (never derived by summing
the component fields). US-GAAP has no total-basis net-income concept in this
taxonomy tier, so net_income_total is structurally None for US-GAAP filers.

The three removed field names (net_assets, net_income, prior_net_income) are
tombstoned: reading them raises AttributeError with a message naming the
replacement field(s); constructing with them as kwargs raises TypeError
(a dataclass gives this for free).
"""
import pytest

from edinet_tools.parsers.securities import SecuritiesReport, parse_securities_report


def _row(element_id, context_id, value):
    return {'要素ID': element_id, 'コンテキストID': context_id, '値': value}


def _csv(rows):
    return [{'filename': 'jpcrp030000-asr-001_test.csv', 'data': rows}]


def _parse(rows, doc_id='TEST'):
    return parse_securities_report(csv_files=_csv(rows), doc_id=doc_id,
                                    doc_type_code='120')


def _dei(standard):
    return [
        _row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E99999'),
        _row('jpdei_cor:AccountingStandardsDEI', 'FilingDateInstant', standard),
        _row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',
             'FilingDateInstant', 'true'),
    ]


# =====================================================================
# J-GAAP routing
# =====================================================================

class TestJGAAPRouting:
    def _rows(self):
        return _dei('Japan GAAP') + [
            _row('jpcrp_cor:NetAssetsSummaryOfBusinessResults',
                 'CurrentYearInstant', '900'),
            _row('jppfs_cor:ShareholdersEquity', 'CurrentYearInstant', '700'),
            _row('jppfs_cor:ValuationAndTranslationAdjustments',
                 'CurrentYearInstant', '50'),
            _row('jppfs_cor:NonControllingInterests', 'CurrentYearInstant', '150'),
            # Summary owners-basis tier absent on purpose -- forces the NEW
            # FS-level owners mapping to fire.
            _row('jppfs_cor:ProfitLossAttributableToOwnersOfParent',
                 'CurrentYearDuration', '80'),
            _row('jppfs_cor:ProfitLoss', 'CurrentYearDuration', '95'),
            _row('jppfs_cor:ProfitLossAttributableToOwnersOfParent',
                 'Prior1YearDuration', '70'),
            _row('jppfs_cor:ProfitLoss', 'Prior1YearDuration', '85'),
        ]

    def test_net_assets_total_from_summary(self):
        r = _parse(self._rows())
        assert r.net_assets_total == 900

    def test_net_assets_owners_always_none_for_jgaap(self):
        # Never derived from shareholders_equity + valuation_translation_adjustments,
        # even though both components are present and non-None.
        r = _parse(self._rows())
        assert r.net_assets_owners is None

    def test_balance_sheet_components_filled(self):
        r = _parse(self._rows())
        assert r.shareholders_equity == 700
        assert r.valuation_translation_adjustments == 50
        assert r.non_controlling_interests == 150

    def test_net_income_owners_recovers_from_new_fs_level_mapping(self):
        # Summary tier (net_income_summary) is absent from these rows --
        # net_income_owners must fall back to the NEW FS-level
        # jppfs_cor:ProfitLossAttributableToOwnersOfParent mapping.
        r = _parse(self._rows())
        assert r.net_income_owners == 80

    def test_net_income_total_from_fs_profit_loss(self):
        r = _parse(self._rows())
        assert r.net_income_total == 95

    def test_prior_net_income_split_reads_prior_context(self):
        r = _parse(self._rows())
        assert r.prior_net_income_owners == 70
        assert r.prior_net_income_total == 85

    def test_summary_tier_wins_over_fs_level_when_both_present(self):
        # Waterfall order pin: net_income_summary (owners-basis summary
        # element) still wins over the new FS-level mapping when both exist.
        rows = self._rows() + [
            _row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
                 'CurrentYearDuration', '82'),
        ]
        r = _parse(rows)
        assert r.net_income_owners == 82


# =====================================================================
# IFRS routing
# =====================================================================

class TestIFRSRouting:
    def _rows(self):
        return _dei('IFRS') + [
            _row('jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '500'),
            # No jppfs_cor:NetAssets on an IFRS filer -- net_assets_total
            # reaches jpigp_cor:EquityIFRS via the pre-existing
            # IFRS_FALLBACK_MAP entry for net_assets_fs.
            _row('jpigp_cor:EquityIFRS', 'CurrentYearInstant', '560'),
            _row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
                 'CurrentYearDuration', '60'),
            _row('jpigp_cor:ProfitLossIFRS', 'CurrentYearDuration', '66'),
            _row('jpigp_cor:NonControllingInterestsIFRS', 'CurrentYearInstant', '60'),
        ]

    def test_net_assets_owners_from_ifrs_summary(self):
        r = _parse(self._rows())
        assert r.accounting_standard == 'IFRS'
        assert r.net_assets_owners == 500

    def test_net_assets_total_from_equity_ifrs_via_fallback_map(self):
        r = _parse(self._rows())
        assert r.net_assets_total == 560

    def test_net_income_owners_from_ifrs_summary(self):
        r = _parse(self._rows())
        assert r.net_income_owners == 60

    def test_net_income_total_from_profitloss_ifrs_via_fallback_map(self):
        r = _parse(self._rows())
        assert r.net_income_total == 66

    def test_non_controlling_interests_from_ifrs_element(self):
        r = _parse(self._rows())
        assert r.non_controlling_interests == 60

    def test_jgaap_only_components_stay_none_for_ifrs(self):
        # shareholders_equity / valuation_translation_adjustments have no
        # IFRS mapping -- honest None, not borrowed from anywhere.
        r = _parse(self._rows())
        assert r.shareholders_equity is None
        assert r.valuation_translation_adjustments is None

    def test_net_assets_owners_recovers_from_new_fs_level_mapping(self):
        # Summary tier absent -- net_assets_owners must fall back to the NEW
        # FS-level jpigp_cor:EquityAttributableToOwnersOfParentIFRS mapping.
        rows = _dei('IFRS') + [
            _row('jpigp_cor:EquityAttributableToOwnersOfParentIFRS',
                 'CurrentYearInstant', '333'),
        ]
        r = _parse(rows)
        assert r.net_assets_owners == 333

    def test_net_income_owners_recovers_from_new_ifrs_fs_level_mapping(self):
        # HOYA-shape filing: the *_ifrs_summary profit element is absent but
        # the FS-level jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS
        # is tagged (census: 89.1% of IFRS rows carry it; HOYA's own filing
        # is exactly this shape -- summary equity tagged, summary profit not
        # -- and is Task 3's counterexample fixture). net_income_owners must
        # recover it; net_income_total must NOT leak from this owners-only
        # element (no total-basis element present at all here).
        rows = _dei('IFRS') + [
            _row('jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
                 'CurrentYearDuration', '253085'),
        ]
        r = _parse(rows)
        assert r.net_income_owners == 253085
        assert r.net_income_total is None

    def test_prior_net_income_owners_recovers_from_new_ifrs_fs_level_mapping(self):
        # Same recovery tier, Prior1YearDuration context.
        rows = _dei('IFRS') + [
            _row('jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
                 'Prior1YearDuration', '200000'),
        ]
        r = _parse(rows)
        assert r.prior_net_income_owners == 200000
        assert r.prior_net_income_total is None

    def test_ifrs_summary_tier_wins_over_new_fs_level_when_both_present(self):
        # Waterfall order pin, mirroring the J-GAAP one above: the existing
        # *_ifrs_summary tier still wins over the new FS-level mapping.
        rows = self._rows()  # already carries the summary element (60)
        rows = rows + [
            _row('jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
                 'CurrentYearDuration', '999'),
        ]
        r = _parse(rows)
        assert r.net_income_owners == 60


# =====================================================================
# Parent-value (_NonConsolidatedMember) exclusion -- component fields +
# net_income_total (census headline trap: ShareholdersEquity appears in
# 100% of IFRS/US-GAAP filings but ONLY at NonConsolidatedMember contexts)
# =====================================================================

class TestParentContextExclusion:
    def test_ifrs_filer_excludes_nonconsolidated_only_components_and_total_income(self):
        # A consolidated IFRS filer (is_consolidated=True) only accepts the
        # bare (consolidated) context for these fields -- values tagged
        # exclusively at _NonConsolidatedMember must NOT leak through.
        rows = _dei('IFRS') + [
            _row('jppfs_cor:ShareholdersEquity',
                 'CurrentYearInstant_NonConsolidatedMember', '111'),
            _row('jppfs_cor:ValuationAndTranslationAdjustments',
                 'CurrentYearInstant_NonConsolidatedMember', '22'),
            _row('jppfs_cor:NonControllingInterests',
                 'CurrentYearInstant_NonConsolidatedMember', '33'),
            _row('jppfs_cor:ProfitLoss',
                 'CurrentYearDuration_NonConsolidatedMember', '444'),
        ]
        r = _parse(rows)
        assert r.accounting_standard == 'IFRS'
        assert r.shareholders_equity is None
        assert r.valuation_translation_adjustments is None
        assert r.non_controlling_interests is None
        assert r.net_income_total is None


# =====================================================================
# US-GAAP routing
# =====================================================================

class TestUSGAAPRouting:
    def _rows(self):
        return _dei('US GAAP') + [
            _row('jpcrp_cor:EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults',
                 'CurrentYearInstant', '400'),
            _row('jpcrp_cor:EquityIncludingPortionAttributableToNonControllingInterestUSGAAPSummaryOfBusinessResults',
                 'CurrentYearInstant', '450'),
            _row('jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults',
                 'CurrentYearDuration', '40'),
            # Deliberately NO total-basis net-income element anywhere.
        ]

    def test_net_assets_owners_from_usgaap_summary(self):
        r = _parse(self._rows())
        assert r.accounting_standard == 'US GAAP'
        assert r.net_assets_owners == 400

    def test_net_assets_total_from_suffix_matched_including_nci_element(self):
        r = _parse(self._rows())
        assert r.net_assets_total == 450

    def test_net_income_owners_from_usgaap_summary(self):
        r = _parse(self._rows())
        assert r.net_income_owners == 40

    def test_net_income_total_structurally_absent_is_honest_none(self):
        # No US-GAAP taxonomy tier carries a total-basis (incl. NCI) net
        # income concept -- honest None, not a silent zero or a borrowed
        # owners-basis value.
        r = _parse(self._rows())
        assert r.net_income_total is None


# =====================================================================
# No cross-basis coalescing, all six directions (net_assets owners/total,
# net_income owners/total, prior_net_income owners/total). Each test's
# row-set carries ONLY a wrong-basis element for the field under test --
# if any waterfall ever coalesced across basis, these would flip from None
# to the wrong-basis value. See the fix report for the mutation re-run that
# confirms each of these actually fails when the corresponding leak is
# introduced.
# =====================================================================

class TestNoCrossBasisLeaks:
    def test_net_income_owners_does_not_leak_from_total_only_element(self):
        # Only the total-basis jppfs_cor:ProfitLoss is present -- no
        # owners-basis element (summary, FS-level, IFRS, or US-GAAP) at all.
        rows = _dei('Japan GAAP') + [
            _row('jppfs_cor:ProfitLoss', 'CurrentYearDuration', '95'),
        ]
        r = _parse(rows)
        assert r.net_income_owners is None
        assert r.net_income_total == 95

    def test_net_income_total_does_not_leak_from_owners_only_element(self):
        # Only an owners-basis element is present -- no total-basis
        # jppfs_cor:ProfitLoss (or its IFRS fallback) anywhere.
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
                 'CurrentYearDuration', '80'),
        ]
        r = _parse(rows)
        assert r.net_income_owners == 80
        assert r.net_income_total is None

    def test_prior_net_income_owners_does_not_leak_from_total_only_element(self):
        # Prior-year mirror: only jppfs_cor:ProfitLoss @ Prior1YearDuration.
        rows = _dei('Japan GAAP') + [
            _row('jppfs_cor:ProfitLoss', 'Prior1YearDuration', '85'),
        ]
        r = _parse(rows)
        assert r.prior_net_income_owners is None
        assert r.prior_net_income_total == 85

    def test_prior_net_income_total_does_not_leak_from_owners_only_element(self):
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
                 'Prior1YearDuration', '70'),
        ]
        r = _parse(rows)
        assert r.prior_net_income_owners == 70
        assert r.prior_net_income_total is None

    def test_net_assets_total_does_not_leak_from_owners_only_ifrs_fs_element(self):
        # Only the NEW FS-level owners element (net_assets_owners_ifrs_fs) is
        # present -- no total-basis element (summary, FS jppfs:NetAssets/
        # jpigp_cor:EquityIFRS, or either suffix-matched total-equity
        # fallback) anywhere.
        rows = _dei('IFRS') + [
            _row('jpigp_cor:EquityAttributableToOwnersOfParentIFRS',
                 'CurrentYearInstant', '333'),
        ]
        r = _parse(rows)
        assert r.net_assets_owners == 333
        assert r.net_assets_total is None

    def test_net_assets_owners_does_not_leak_from_total_only_usgaap_suffix_element(self):
        # Only the suffix-matched total-equity-including-NCI element is
        # present -- no owners-basis US-GAAP summary element anywhere.
        rows = _dei('US GAAP') + [
            _row('jpcrp_cor:EquityIncludingPortionAttributableToNonControllingInterestUSGAAPSummaryOfBusinessResults',
                 'CurrentYearInstant', '450'),
        ]
        r = _parse(rows)
        assert r.net_assets_owners is None
        assert r.net_assets_total == 450


# =====================================================================
# Ownership-basis identity rewire (Task 3, Decision 4): the equity-ratio
# identity used to compare a single equity_ratio element against
# net_assets_total regardless of accounting standard. It is now split per
# standard: IFRS/US-GAAP's equity_ratio element is owners-only-attributable,
# so it is checked against net_assets_owners; J-GAAP has no owners-only
# net-assets element, so its equity_ratio is checked against an
# in-check-only sum of shareholders_equity + valuation_translation_adjustments
# (never written back to any field or shipped as data). No owners<=total
# containment rule exists for any field pair -- non-controlling interests
# can themselves post a loss, so an owners-attributable figure can
# legitimately EXCEED the corresponding total-including-NCI figure (the
# HOYA counterexample below).
# =====================================================================

class TestOwnershipBasisEquityRatioIdentity:
    def test_ifrs_equity_ratio_identity_compares_against_net_assets_owners(self):
        # equity_ratio (owners-only, RatioOfOwnersEquityToGrossAssetsIFRS...)
        # vs net_assets_owners: 500/1000 = 0.50 computed, 0.30 stated -> 0.20
        # gap, past IDENTITY_TOLERANCE (0.02) -> annotate. The rule NAME is
        # the load-bearing assertion here: it must read 'net_assets_owners',
        # proving the operand actually switched off net_assets_total.
        rows = _dei('IFRS') + [
            _row('jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.30'),
            _row('jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '500'),
            _row('jpigp_cor:EquityIFRS', 'CurrentYearInstant', '600'),
            _row('jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        assert r.net_assets_owners == 500
        assert r.net_assets_total == 600
        flags = [f for f in r.extraction_flags
                 if f.rule == 'identity:equity_ratio~net_assets_owners/total_assets']
        assert len(flags) == 1
        assert 'net_assets_owners=500' in flags[0].value

    def test_ifrs_equity_ratio_identity_within_tolerance_no_flag(self):
        # 500/1000 = 0.50 computed, 0.50 stated -> exact match, no flag.
        rows = _dei('IFRS') + [
            _row('jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.50'),
            _row('jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '500'),
            _row('jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        flags = [f for f in r.extraction_flags
                 if f.rule == 'identity:equity_ratio~net_assets_owners/total_assets']
        assert flags == []

    def test_jgaap_equity_ratio_identity_compares_against_component_sum(self):
        # J-GAAP has no owners-only net-assets element -- the identity
        # instead sums shareholders_equity (700) + valuation_translation_
        # adjustments (50) = 750 in-check-only, never written to any field.
        # 750/1000 = 0.75 computed vs 0.30 stated -> annotate.
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.30'),
            _row('jppfs_cor:ShareholdersEquity', 'CurrentYearInstant', '700'),
            _row('jppfs_cor:ValuationAndTranslationAdjustments',
                 'CurrentYearInstant', '50'),
            _row('jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        assert r.shareholders_equity == 700
        assert r.valuation_translation_adjustments == 50
        # The in-check-only sum (750) must never be written back anywhere.
        assert not hasattr(r, 'net_assets_owners_derived')
        assert r.net_assets_owners is None  # J-GAAP: always None, never derived
        flags = [
            f for f in r.extraction_flags
            if f.rule.startswith('identity:equity_ratio~shareholders_equity')
        ]
        assert len(flags) == 1
        assert 'shareholders_equity=700' in flags[0].value
        assert 'valuation_translation_adjustments=50' in flags[0].value

    def test_jgaap_equity_ratio_identity_within_tolerance_no_flag(self):
        # 700 + 50 = 750; 750/1000 = 0.75 computed, 0.75 stated -> no flag.
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.75'),
            _row('jppfs_cor:ShareholdersEquity', 'CurrentYearInstant', '700'),
            _row('jppfs_cor:ValuationAndTranslationAdjustments',
                 'CurrentYearInstant', '50'),
            _row('jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        flags = [
            f for f in r.extraction_flags
            if f.rule.startswith('identity:equity_ratio~shareholders_equity')
        ]
        assert flags == []

    def test_jgaap_equity_ratio_identity_skips_when_either_component_missing(self):
        # valuation_translation_adjustments absent -> skip, never fail (the
        # any-None-skips contract falls out of apply_identities for free --
        # no special-casing needed in the check function).
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.30'),
            _row('jppfs_cor:ShareholdersEquity', 'CurrentYearInstant', '700'),
            _row('jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        assert r.valuation_translation_adjustments is None
        flags = [
            f for f in r.extraction_flags
            if f.rule.startswith('identity:equity_ratio~shareholders_equity')
        ]
        assert flags == []

    def test_ifrs_identity_out_of_scope_for_jgaap_report(self):
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.30'),
            _row('jppfs_cor:NetAssets', 'CurrentYearInstant', '999999'),
            _row('jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        flags = [
            f for f in r.extraction_flags
            if f.rule == 'identity:equity_ratio~net_assets_owners/total_assets'
        ]
        assert flags == []

    def test_jgaap_identity_out_of_scope_for_ifrs_report(self):
        rows = _dei('IFRS') + [
            _row('jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.30'),
            _row('jppfs_cor:ShareholdersEquity', 'CurrentYearInstant', '700'),
            _row('jppfs_cor:ValuationAndTranslationAdjustments',
                 'CurrentYearInstant', '50'),
            _row('jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '1000'),
        ]
        r = _parse(rows)
        # jppfs_cor:ShareholdersEquity/ValuationAndTranslationAdjustments are
        # extraction-gated by XBRL context (bare context = consolidated), not
        # by accounting_standard -- at the bare CurrentYearInstant context
        # used here, both components DO populate even on an IFRS report (see
        # TestParentContextExclusion above for the realistic
        # _NonConsolidatedMember-only case, which stays honest-None). Both
        # operands are therefore non-None here -- this is a genuine
        # belt-and-suspenders check that the J-GAAP identity's `standards`
        # scope, not operand availability, is what excludes it from firing
        # on an IFRS report.
        assert r.shareholders_equity == 700
        assert r.valuation_translation_adjustments == 50
        flags = [
            f for f in r.extraction_flags
            if f.rule.startswith('identity:equity_ratio~shareholders_equity')
        ]
        assert flags == []


class TestHoyaOwnersExceedsTotalNoFalseFlag:
    """HOYA counterexample (Decision 4's explicit trap): HOYA's IFRS filing
    has net_income_owners (253,085) > net_income_total (251,451) because
    minorities lost money that period (NCI's own profit share is negative,
    -1,633). An owners<=total containment rule on ANY field pair would
    incorrectly flag this as a violation. No such rule exists in
    SECURITIES_IDENTITIES -- this test proves it by construction: parse a
    HOYA-shaped report with the inversion present on both net_income and
    net_assets, and assert there are ZERO flags from any rule touching
    these fields, not just that one specific named rule is absent."""

    def _hoya_shaped_rows(self):
        return _dei('IFRS') + [
            # Income: owners (253,085) > total (251,451) -- the real HOYA
            # FYE2026-03 inversion (see the golden-fixture panel for the
            # IR-pinned figures backing these numbers).
            _row('jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
                 'CurrentYearDuration', '253085'),
            _row('jpigp_cor:ProfitLossIFRS', 'CurrentYearDuration', '251451'),
            # Equity: owners/total inversion is structurally possible the
            # same way (NCI can carry a cumulative deficit) -- exercised
            # synthetically here since HOYA's own equity does not invert.
            _row('jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '1035004'),
            _row('jpigp_cor:EquityIFRS', 'CurrentYearInstant', '1020460'),
            _row('jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '0.70'),
            _row('jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults',
                 'CurrentYearInstant', '1478577'),
        ]

    def test_inversion_present_on_both_fields(self):
        r = self._hoya_shaped_rows()
        r = _parse(r)
        assert r.net_income_owners == 253085
        assert r.net_income_total == 251451
        assert r.net_income_owners > r.net_income_total
        assert r.net_assets_owners == 1035004
        assert r.net_assets_total == 1020460
        assert r.net_assets_owners > r.net_assets_total

    def test_zero_flags_from_any_containment_or_identity_on_the_inversion(self):
        r = _parse(self._hoya_shaped_rows())
        # No rule name anywhere may mention both an owners field and a total
        # field of the SAME concept in a <=/>= containment shape. Assert
        # this both by construction (no such flags fired) and by scanning
        # every flag that touched net_income_owners, net_income_total,
        # net_assets_owners, or net_assets_total for anything but the two
        # rules known to be safe (containment against total_assets, and the
        # per-standard equity_ratio identities -- neither compares owners
        # to total directly).
        touched_fields = {'net_income_owners', 'net_income_total',
                          'net_assets_owners', 'net_assets_total'}
        offending = [
            f for f in r.extraction_flags
            if f.field in touched_fields or
            any(tf in f.value for tf in ('net_income_owners=', 'net_income_total=',
                                          'net_assets_owners=', 'net_assets_total='))
        ]
        assert offending == [], offending


# =====================================================================
# Tombstones: removed-field reads raise a guided AttributeError
# =====================================================================

class TestRemovedFieldTombstones:
    def test_net_assets_read_raises_with_replacement_field_names(self):
        report = SecuritiesReport(doc_id='X', doc_type_code='120')
        with pytest.raises(AttributeError) as exc_info:
            report.net_assets
        message = str(exc_info.value)
        assert 'net_assets_total' in message
        assert 'net_assets_owners' in message

    def test_net_income_read_raises_with_replacement_field_names(self):
        report = SecuritiesReport(doc_id='X', doc_type_code='120')
        with pytest.raises(AttributeError) as exc_info:
            report.net_income
        message = str(exc_info.value)
        assert 'net_income_total' in message
        assert 'net_income_owners' in message

    def test_prior_net_income_read_raises_with_replacement_field_names(self):
        report = SecuritiesReport(doc_id='X', doc_type_code='120')
        with pytest.raises(AttributeError) as exc_info:
            report.prior_net_income
        message = str(exc_info.value)
        assert 'prior_net_income_total' in message
        assert 'prior_net_income_owners' in message

    def test_unrelated_missing_attribute_still_raises_plain_attribute_error(self):
        # The tombstone hook must not swallow genuinely unknown attributes.
        report = SecuritiesReport(doc_id='X', doc_type_code='120')
        with pytest.raises(AttributeError):
            report.this_field_never_existed


# =====================================================================
# Constructing with a removed field name is a TypeError (dataclass-free)
# =====================================================================

class TestRemovedFieldConstructionRejected:
    def test_net_assets_kwarg_raises_type_error(self):
        with pytest.raises(TypeError):
            SecuritiesReport(doc_id='X', doc_type_code='120', net_assets=100)

    def test_net_income_kwarg_raises_type_error(self):
        with pytest.raises(TypeError):
            SecuritiesReport(doc_id='X', doc_type_code='120', net_income=100)

    def test_prior_net_income_kwarg_raises_type_error(self):
        with pytest.raises(TypeError):
            SecuritiesReport(doc_id='X', doc_type_code='120', prior_net_income=100)


# =====================================================================
# to_dict: carries the new fields, none of the removed ones
# =====================================================================

class TestToDictCarriesSplitFields:
    NEW_FIELDS = {
        'net_assets_owners', 'net_assets_total',
        'net_income_owners', 'net_income_total',
        'prior_net_income_owners', 'prior_net_income_total',
        'shareholders_equity', 'valuation_translation_adjustments',
        'non_controlling_interests',
    }
    REMOVED_FIELDS = {'net_assets', 'net_income', 'prior_net_income'}

    def test_default_report_dict_has_new_fields_not_removed_ones(self):
        report = SecuritiesReport(doc_id='X', doc_type_code='120')
        d = report.to_dict()
        assert self.NEW_FIELDS <= d.keys()
        assert not (self.REMOVED_FIELDS & d.keys())

    def test_parsed_report_dict_carries_routed_values(self):
        rows = TestJGAAPRouting()._rows()
        r = _parse(rows)
        d = r.to_dict()
        assert d['net_assets_total'] == 900
        assert d['net_assets_owners'] is None
        assert d['net_income_owners'] == 80
        assert d['net_income_total'] == 95
        assert d['shareholders_equity'] == 700
        assert d['valuation_translation_adjustments'] == 50
        assert d['non_controlling_interests'] == 150
