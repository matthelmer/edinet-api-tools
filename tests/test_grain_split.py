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
from decimal import Decimal

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
