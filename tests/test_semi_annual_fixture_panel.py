"""Golden-fixture panel for the semi-annual context fix (0.8.0 stage-5 Task
9): three real semi-annual filings -- one fund (non-consolidated, Interim
regime), one corporate q2r-transitional filer (consolidated, FY2024
CurrentQuarter*/CurrentYTD* taxonomy), one consolidated bank in the
Interim-regime taxonomy with full parallel _NonConsolidatedMember rows and
three genuinely untagged fields. Every pinned NEW value below is the
filing's own STATED current-period figure (verified directly in the raw
CSV, full file preserved -- never a KEEP-filtered subset); the `old` values
noted in comments are what the pre-fix, context-blind parser returned
(the prior-period figure, because EDINET CSVs list prior-period rows first
in file order) -- kept only as commentary, never asserted.
"""
from edinet_tools.parsers.semi_annual import parse_semi_annual_report
from tests.conftest import load_semi_annual_fixture


def _parse(name, doc_type_code='160'):
    cf = load_semi_annual_fixture(name)
    return parse_semi_annual_report(csv_files=cf, doc_id=name,
                                    doc_type_code=doc_type_code)


def _assert_no_flags(report, fixture_name):
    assert report.extraction_flags == [], (
        f'{fixture_name}: expected zero flags on a well-formed real filing, '
        f'got {report.extraction_flags}'
    )


# =====================================================================
# Fund semi-annual (non-consolidated, Interim regime). Filing carries three
# repeated fund-share-class tables in file order; the strict current-period
# read (like the pre-fix blind read) resolves the FIRST one -- this fixture
# pins that first-table figure only.
# =====================================================================

class TestFundSemiAnnual:
    def test_dei(self):
        r = _parse('smbc_trust_am_fund')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.is_consolidated is False

    def test_balance_sheet(self):
        r = _parse('smbc_trust_am_fund')
        assert r.total_assets == 15_426_275_984      # old (prior-period defect): 13,576,924,957
        assert r.current_assets == 15_426_275_984
        assert r.total_liabilities == 32_801_803      # old: 26,189,965
        assert r.current_liabilities == 32_801_803
        assert r.net_assets == 15_393_474_181         # old: 13,550,734,992

    def test_income_statement(self):
        r = _parse('smbc_trust_am_fund')
        assert r.operating_income == 1_385_749_821    # old: 792,482,373
        assert r.ordinary_income == 1_385_749_821
        assert r.profit_loss == 1_385_749_821

    def test_zero_flags(self):
        _assert_no_flags(_parse('smbc_trust_am_fund'), 'smbc_trust_am_fund')


# =====================================================================
# Corporate semi-annual, consolidated, FY2024 transitional q2r taxonomy
# (CurrentQuarterInstant / CurrentYTDDuration).
# =====================================================================

class TestCorporateQ2rSemiAnnual:
    def test_dei(self):
        r = _parse('murakami_kaimeido_q2r')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.is_consolidated is True

    def test_balance_sheet(self):
        r = _parse('murakami_kaimeido_q2r')
        assert r.total_assets == 110_977_000_000       # old: 106,814,000,000
        assert r.current_assets == 75_036_000_000       # old: 70,677,000,000
        assert r.total_liabilities == 20_644_000_000    # old: 20,748,000,000
        assert r.current_liabilities == 18_133_000_000  # old: 17,733,000,000
        assert r.net_assets == 90_332_000_000           # old: 86,065,000,000

    def test_income_statement(self):
        r = _parse('murakami_kaimeido_q2r')
        assert r.operating_income == 4_023_000_000      # old: 4,060,000,000
        assert r.ordinary_income == 4_663_000_000        # old: 4,601,000,000
        assert r.profit_loss == 3_266_000_000            # old: 3,337,000,000

    def test_zero_flags(self):
        _assert_no_flags(_parse('murakami_kaimeido_q2r'), 'murakami_kaimeido_q2r')


# =====================================================================
# Bank semi-annual, consolidated, Interim regime with full parallel
# _NonConsolidatedMember rows -- pins the strict-consolidated bare-context
# pick (never the parent/individual figure) AND three honestly-absent
# fields (untagged for this bank).
# =====================================================================

class TestBankInterimSemiAnnual:
    def test_dei(self):
        r = _parse('oita_bank_interim')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.is_consolidated is True

    def test_balance_sheet_bare_context_wins_over_parallel_nonconsolidated(self):
        r = _parse('oita_bank_interim')
        assert r.total_assets == 4_501_767_000_000       # old: 4,554,183,000,000
        assert r.total_liabilities == 4_287_959_000_000  # old: 4,336,302,000,000
        assert r.net_assets == 213_807_000_000           # old: 217,880,000,000

    def test_income_statement(self):
        r = _parse('oita_bank_interim')
        assert r.ordinary_income == 5_345_000_000  # old: 4,411,000,000
        assert r.profit_loss == 3_713_000_000       # old: 3,211,000,000

    def test_untagged_fields_honest_none(self):
        """current_assets / current_liabilities / operating_income carry no
        element for this bank at any context -- honest absence, not a
        parsing miss."""
        r = _parse('oita_bank_interim')
        assert r.current_assets is None
        assert r.current_liabilities is None
        assert r.operating_income is None

    def test_zero_flags(self):
        _assert_no_flags(_parse('oita_bank_interim'), 'oita_bank_interim')
