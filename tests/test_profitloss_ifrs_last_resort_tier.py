"""ProfitLossIFRS last-resort tier (0.8.0 stage 5): `net_income_total` /
`prior_net_income_total` gain one additional, IFRS-only tier —
`jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults` — tried strictly after
every existing tier and consulted only when every earlier tier resolved to
None. This closes a real coverage gap: some IFRS filers tag this
SummaryOfBusinessResults total-basis profit element but tag neither the
owners-basis summary element nor the owners-basis FS element anywhere in
the filing, so `net_income_total` (and its prior-year mirror) were
structurally None even though the filing states a real total-basis figure.

The element is TOTAL-basis (includes non-controlling interests, matching
its jppfs_cor:ProfitLoss sibling in the existing tier table) -- it must
never fill `net_income_owners` / `prior_net_income_owners`.

Real-filing fixture: an IFRS securities report (public EDINET filing
S100FHXZ) that tags `jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults` at
both CurrentYearDuration and Prior1YearDuration with real values, and tags
no owners-basis element (summary or FS-level) anywhere -- confirmed by
direct inspection of the filing's full raw CSV (715 rows, no element
filtering).
"""
from edinet_tools.parsers.securities import parse_securities_report
from tests.conftest import load_securities_fixture


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
# Real filing: S100FHXZ tags the SummaryOfBusinessResults total-basis IFRS
# profit element at both duration contexts and tags no owners-basis element
# anywhere in the filing.
# =====================================================================

def _parse_fixture():
    cf = load_securities_fixture('profitloss_ifrs_rakuten_s100fhxz')
    return parse_securities_report(csv_files=cf, doc_id='S100FHXZ',
                                    doc_type_code='120')


class TestRealFilingFillsFromLastResortTier:
    def test_net_income_total_filled_from_last_resort_element(self):
        r = _parse_fixture()
        assert r.accounting_standard == 'IFRS'
        # jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults @ CurrentYearDuration
        assert r.net_income_total == 141_889_000_000

    def test_prior_net_income_total_filled_from_last_resort_element(self):
        r = _parse_fixture()
        # jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults @ Prior1YearDuration
        assert r.prior_net_income_total == 110_488_000_000

    def test_owners_basis_stays_honest_none(self):
        # No owners-basis element (summary or FS-level) is tagged anywhere
        # in this filing -- the new tier fills ONLY *_total, so *_owners
        # must stay None, not be derived or borrowed from the total figure.
        r = _parse_fixture()
        assert r.net_income_owners is None
        assert r.prior_net_income_owners is None

    def test_zero_flags(self):
        r = _parse_fixture()
        assert r.extraction_flags == []


# =====================================================================
# Synthetic (a): a J-GAAP filing that tags the IFRS-only element must NOT
# read it -- the tier is standards=('IFRS',)-gated.
# =====================================================================

class TestJGAAPFilingDoesNotReadTheIFRSElement:
    def test_jgaap_filer_tagging_element_gets_none(self):
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults',
                 'CurrentYearDuration', '999'),
        ]
        r = _parse(rows)
        assert r.accounting_standard == 'Japan GAAP'
        assert r.net_income_total is None

    def test_jgaap_filer_tagging_element_gets_none_prior_year(self):
        rows = _dei('Japan GAAP') + [
            _row('jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults',
                 'Prior1YearDuration', '888'),
        ]
        r = _parse(rows)
        assert r.prior_net_income_total is None


# =====================================================================
# Synthetic (b): last_resort means LAST -- when an earlier tier already
# resolves net_income_total, the new tier must never override it, even
# though standards=('IFRS',) lets it apply to this same filing.
# =====================================================================

class TestLastResortDoesNotOverrideAnEarlierTier:
    def test_ifrs_filing_with_both_elements_keeps_the_earlier_tiers_value(self):
        rows = _dei('IFRS') + [
            # jppfs_cor:ProfitLoss (the existing, non-last-resort
            # net_income_total tier) resolves first and wins.
            _row('jppfs_cor:ProfitLoss', 'CurrentYearDuration', '100'),
            _row('jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults',
                 'CurrentYearDuration', '200'),
        ]
        r = _parse(rows)
        assert r.net_income_total == 100

    def test_ifrs_filing_with_both_elements_keeps_the_earlier_tiers_value_prior_year(self):
        rows = _dei('IFRS') + [
            _row('jppfs_cor:ProfitLoss', 'Prior1YearDuration', '110'),
            _row('jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults',
                 'Prior1YearDuration', '210'),
        ]
        r = _parse(rows)
        assert r.prior_net_income_total == 110
