"""End-to-end extraction tests for all parsers using synthetic EDINET CSV data.

Each test creates a realistic ZIP with EDINET-format CSV rows, passes it through
the full parser pipeline, and verifies extracted field values. This catches
regressions in element IDs, context patterns, type conversions, and fallback logic.
"""
import io
import zipfile
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock


def make_csv_row(element_id, context_id, value, item_name=''):
    """Create a single EDINET CSV row dict.

    item_name corresponds to the Japanese `項目名` (label) column found in
    real EDINET extracts. Defaults to empty string for backward compatibility
    with existing tests that don't need label-based extraction.
    """
    return {
        '要素ID': element_id,
        'コンテキストID': context_id,
        '値': value,
        '項目名': item_name,
    }


def make_zip_with_rows(rows):
    """Create a ZIP containing a CSV with the given rows in EDINET format."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        lines = []
        for row in rows:
            item_name = row.get('項目名', '')
            line = f"{row['要素ID']}\t{item_name}\t{row['コンテキストID']}\t0\t連結\t期間\tunit1\t円\t{row['値']}"
            lines.append(line)
        content = '\n'.join(lines)
        zf.writestr('XBRL_TO_CSV/test.csv', content.encode('utf-16le'))
    return zip_buffer.getvalue()


def make_mock_doc(doc_id='S100TEST', doc_type='120', rows=None, filer_name='', filer_edinet_code=''):
    """Create a mock Document for parser tests."""
    doc = MagicMock()
    doc.doc_id = doc_id
    doc.doc_type_code = doc_type
    doc.filer_name = filer_name
    doc.filer_edinet_code = filer_edinet_code
    if rows is not None:
        doc.fetch.return_value = make_zip_with_rows(rows)
    else:
        doc.fetch.return_value = b''
    return doc

from edinet_tools.parsers.securities import parse_securities_report, SecuritiesReport
from edinet_tools.parsers.quarterly import parse_quarterly_report, QuarterlyReport
from edinet_tools.parsers.large_holding import parse_large_holding, LargeHoldingReport
from edinet_tools.parsers.treasury_stock import parse_treasury_stock_report, TreasuryStockReport
from edinet_tools.parsers.extraordinary import parse_extraordinary_report, ExtraordinaryReport
from edinet_tools.parsers.semi_annual import parse_semi_annual_report, SemiAnnualReport


# =====================================================================
# Securities Report (Doc 120)
# =====================================================================

class TestSecuritiesExtraction:
    """End-to-end extraction tests for parse_securities_report."""

    def _base_rows(self):
        """Minimal viable securities report CSV rows."""
        return [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '24770'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
            make_csv_row('jpdei_cor:FilerNameInEnglishDEI', 'FilingDateInstant', 'Test Corp'),
            make_csv_row('jpdei_cor:CurrentFiscalYearStartDateDEI', 'FilingDateInstant', '2024-04-01'),
            make_csv_row('jpdei_cor:CurrentFiscalYearEndDateDEI', 'FilingDateInstant', '2025-03-31'),
            make_csv_row('jpdei_cor:AccountingStandardsDEI', 'FilingDateInstant', 'Japan GAAP'),
            make_csv_row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
            # Summary financials
            make_csv_row('jpcrp_cor:NetSalesSummaryOfBusinessResults', 'CurrentYearDuration', '50000000000'),
            make_csv_row('jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults', 'CurrentYearDuration', '5000000000'),
            make_csv_row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults', 'CurrentYearDuration', '3000000000'),
            make_csv_row('jpcrp_cor:TotalAssetsSummaryOfBusinessResults', 'CurrentYearInstant', '100000000000'),
            make_csv_row('jpcrp_cor:NetAssetsSummaryOfBusinessResults', 'CurrentYearInstant', '40000000000'),
            # Operating income via FS
            make_csv_row('jppfs_cor:OperatingIncome', 'CurrentYearDuration', '4500000000'),
            # Cash flow
            make_csv_row('jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults', 'CurrentYearDuration', '6000000000'),
            make_csv_row('jpcrp_cor:NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults', 'CurrentYearDuration', '-2000000000'),
            make_csv_row('jpcrp_cor:NetCashProvidedByUsedInFinancingActivitiesSummaryOfBusinessResults', 'CurrentYearDuration', '-1000000000'),
            # Per-share
            make_csv_row('jpcrp_cor:NetAssetsPerShareSummaryOfBusinessResults', 'CurrentYearInstant', '2345.67'),
            make_csv_row('jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults', 'CurrentYearDuration', '123.45'),
            # Ratios (XBRL "pure"-typed element: decimal fraction, not a raw
            # percentage — 0.400 = 40.0%, matching real filings)
            make_csv_row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults', 'CurrentYearInstant', '0.400'),
            make_csv_row('jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults', 'CurrentYearDuration', '8.5'),
            # Employees
            make_csv_row('jpcrp_cor:NumberOfEmployees', 'CurrentYearInstant', '5000'),
        ]

    def test_full_extraction(self):
        doc = make_mock_doc('S100SEC', '120', self._base_rows())
        r = parse_securities_report(doc)

        assert isinstance(r, SecuritiesReport)
        assert r.filer_edinet_code == 'E05123'
        assert r.ticker == '2477.T'
        assert r.filer_name == 'テスト株式会社'
        assert r.filer_name_en == 'Test Corp'
        assert r.accounting_standard == 'Japan GAAP'
        assert r.is_consolidated is True
        assert r.fiscal_year_start == date(2024, 4, 1)
        assert r.fiscal_year_end == date(2025, 3, 31)

        # Financials
        assert r.net_sales == 50000000000
        assert r.operating_income == 4500000000
        assert r.ordinary_income == 5000000000
        assert r.net_income_owners == 3000000000
        assert r.total_assets == 100000000000
        assert r.net_assets_total == 40000000000

        # Cash flow
        assert r.operating_cash_flow == 6000000000
        assert r.investing_cash_flow == -2000000000
        assert r.financing_cash_flow == -1000000000

        # Per-share (Decimal)
        assert r.net_assets_per_share == Decimal('2345.67')
        assert r.earnings_per_share == Decimal('123.45')

        # Ratios (decimal fraction: "pure"-typed XBRL element, not a raw percentage)
        assert r.equity_ratio == Decimal('0.400')
        assert r.roe == Decimal('8.5')

        # Employees
        assert r.num_employees == 5000

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '120', rows=None)
        r = parse_securities_report(doc)
        assert isinstance(r, SecuritiesReport)
        assert r.filer_name is None
        assert r.net_sales is None

    def test_csv_files_param(self):
        """Verify csv_files= parameter path (used by downstream consumers)."""
        from edinet_tools.parsers.extraction import extract_csv_from_zip
        rows = self._base_rows()
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)

        r = parse_securities_report(csv_files=csv_files, doc_id='S100CSV', doc_type_code='120')
        assert r.filer_edinet_code == 'E05123'
        assert r.net_sales == 50000000000

    def test_ifrs_cash_flow_fallback(self):
        """When J-GAAP summary CF is missing, should fall back to IFRS summary."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E99999'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '12340'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'IFRS社'),
            make_csv_row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
            # No J-GAAP summary CF — use IFRS summary
            make_csv_row('jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '7000000000'),
            make_csv_row('jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '-3000000000'),
        ]
        doc = make_mock_doc('S100IFRS', '120', rows)
        r = parse_securities_report(doc)

        assert r.operating_cash_flow == 7000000000
        assert r.investing_cash_flow == -3000000000

    def test_is_consolidated_none_when_dei_missing(self):
        """When is_consolidated DEI element is absent, return None (unknown)."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E11111'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト'),
        ]
        doc = make_mock_doc('S100DEF', '120', rows)
        r = parse_securities_report(doc)
        assert r.is_consolidated is None

    def test_ifrs_full_extraction(self):
        """IFRS company should extract via IFRS Summary and FS elements."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E04425'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '80580'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', '三菱商事株式会社'),
            make_csv_row('jpdei_cor:FilerNameInEnglishDEI', 'FilingDateInstant', 'Mitsubishi Corporation'),
            make_csv_row('jpdei_cor:CurrentFiscalYearStartDateDEI', 'FilingDateInstant', '2024-04-01'),
            make_csv_row('jpdei_cor:CurrentFiscalYearEndDateDEI', 'FilingDateInstant', '2025-03-31'),
            make_csv_row('jpdei_cor:AccountingStandardsDEI', 'FilingDateInstant', 'IFRS'),
            make_csv_row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
            # IFRS Summary elements (no J-GAAP summary available for IFRS filers)
            make_csv_row('jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '19000000000000'),
            make_csv_row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '1200000000000'),
            make_csv_row('jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults', 'CurrentYearInstant', '22000000000000'),
            make_csv_row('jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults', 'CurrentYearInstant', '8000000000000'),
            # IFRS Summary CF
            make_csv_row('jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '1500000000000'),
            make_csv_row('jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '-800000000000'),
            make_csv_row('jpcrp_cor:CashFlowsFromUsedInFinancingActivitiesIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '-400000000000'),
            # IFRS Summary ratios/per-share
            make_csv_row('jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '289.45'),
            # Real equity-ratio element (親会社所有者帰属持分比率（IFRS）; pure decimal:
            # 0.364 = 36.4%, matching real filings)
            make_csv_row('jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults', 'CurrentYearInstant', '0.364'),
            # Misnomer element: label is 1株当たり親会社所有者帰属持分 (BPS, yen)
            make_csv_row('jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults', 'CurrentYearInstant', '5150.56'),
            make_csv_row('jpcrp_cor:RateOfReturnOnEquityIFRSSummaryOfBusinessResults', 'CurrentYearDuration', '15.8'),
            # IFRS FS elements (operating income not in summary)
            make_csv_row('jpigp_cor:OperatingProfitLossIFRS', 'CurrentYearDuration', '1800000000000'),
            # IFRS balance sheet detail
            make_csv_row('jpigp_cor:CashAndCashEquivalentsIFRS', 'CurrentYearInstant', '2500000000000'),
            make_csv_row('jpigp_cor:CurrentAssetsIFRS', 'CurrentYearInstant', '10000000000000'),
            make_csv_row('jpigp_cor:RetainedEarningsIFRS', 'CurrentYearInstant', '5000000000000'),
            # Prior year IFRS Summary
            make_csv_row('jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'Prior1YearDuration', '18000000000000'),
            make_csv_row('jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults', 'Prior1YearDuration', '1100000000000'),
            # Employees
            make_csv_row('jpcrp_cor:NumberOfEmployees', 'CurrentYearInstant', '80000'),
        ]
        doc = make_mock_doc('S100IFRS_FULL', '120', rows)
        r = parse_securities_report(doc)

        assert r.accounting_standard == 'IFRS'
        assert r.filer_name == '三菱商事株式会社'
        assert r.ticker == '8058.T'

        # Revenue from IFRS Summary
        assert r.net_sales == 19000000000000
        assert r.prior_net_sales == 18000000000000

        # Operating income from IFRS FS (via IFRS_FALLBACK_MAP)
        assert r.operating_income == 1800000000000

        # Net income from IFRS Summary (owners-of-parent basis)
        assert r.net_income_owners == 1200000000000
        assert r.prior_net_income_owners == 1100000000000

        # Balance sheet from IFRS Summary (owners-of-parent basis)
        assert r.total_assets == 22000000000000
        assert r.net_assets_owners == 8000000000000

        # Cash flow from IFRS Summary
        assert r.operating_cash_flow == 1500000000000
        assert r.investing_cash_flow == -800000000000
        assert r.financing_cash_flow == -400000000000

        # Per-share from IFRS Summary
        assert r.earnings_per_share == Decimal('289.45')

        # Ratios from IFRS Summary
        assert r.equity_ratio == Decimal('0.364')
        assert r.roe == Decimal('15.8')

        # Balance sheet detail from IFRS FS
        assert r.cash_and_deposits == 2500000000000
        assert r.current_assets == 10000000000000
        assert r.retained_earnings == 5000000000000

        # Employees
        assert r.num_employees == 80000

    def test_ifrs_fs_revenue_fallback_chain(self):
        """When IFRS Summary missing, should try IFRS FS elements for revenue."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E99999'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'IFRS社'),
            make_csv_row('jpdei_cor:AccountingStandardsDEI', 'FilingDateInstant', 'IFRS'),
            make_csv_row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
            # No summary at all — only IFRS FS element
            make_csv_row('jpigp_cor:RevenueIFRS', 'CurrentYearDuration', '5000000000000'),
            make_csv_row('jpigp_cor:ProfitLossIFRS', 'CurrentYearDuration', '300000000000'),
            make_csv_row('jpigp_cor:AssetsIFRS', 'CurrentYearInstant', '8000000000000'),
        ]
        doc = make_mock_doc('S100IFRS_FS', '120', rows)
        r = parse_securities_report(doc)

        assert r.net_sales == 5000000000000
        assert r.net_income_total == 300000000000
        assert r.total_assets == 8000000000000


# =====================================================================
# Quarterly Report (Doc 140)
# =====================================================================

class TestQuarterlyExtraction:
    """End-to-end extraction tests for parse_quarterly_report."""

    def _base_rows(self):
        return [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '24770'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
            make_csv_row('jpdei_cor:CurrentFiscalYearEndDateDEI', 'FilingDateInstant', '2025-03-31'),
            make_csv_row('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
            # Filing date (needed for quarter derivation)
            make_csv_row('jpcrp_cor:FilingDateCoverPage', 'FilingDateInstant', '2024-11-14'),
            # YTD income
            make_csv_row('jppfs_cor:NetSales', 'CurrentYTDDuration', '25000000000'),
            make_csv_row('jppfs_cor:OperatingIncome', 'CurrentYTDDuration', '2500000000'),
            make_csv_row('jppfs_cor:OrdinaryIncome', 'CurrentYTDDuration', '2600000000'),
            make_csv_row('jppfs_cor:ProfitLossAttributableToOwnersOfParent', 'CurrentYTDDuration', '1500000000'),
            # Balance sheet
            make_csv_row('jppfs_cor:Assets', 'CurrentQuarterInstant', '90000000000'),
            make_csv_row('jppfs_cor:NetAssets', 'CurrentQuarterInstant', '38000000000'),
            make_csv_row('jppfs_cor:Liabilities', 'CurrentQuarterInstant', '52000000000'),
            # Cash flow
            make_csv_row('jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults', 'CurrentYTDDuration', '4000000000'),
            # EPS
            make_csv_row('jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults', 'CurrentYTDDuration', '75.50'),
            # Equity ratio
            make_csv_row('jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults', 'CurrentQuarterInstant', '42.2'),
        ]

    def test_full_extraction(self):
        doc = make_mock_doc('S100QTR', '140', self._base_rows())
        r = parse_quarterly_report(doc)

        assert isinstance(r, QuarterlyReport)
        assert r.filer_edinet_code == 'E05123'
        assert r.ticker == '2477.T'
        assert r.fiscal_year_end == date(2025, 3, 31)
        assert r.filing_date == date(2024, 11, 14)
        assert r.is_consolidated is True

        # Q2 filing: Nov 2024, fiscal year starts Apr 2024 → 7 months from start
        assert r.quarter_number == 2

        assert r.revenue_ytd == 25000000000
        assert r.operating_profit_ytd == 2500000000
        assert r.ordinary_profit_ytd == 2600000000
        assert r.net_income_ytd == 1500000000
        assert r.total_assets == 90000000000
        assert r.operating_cash_flow_ytd == 4000000000
        assert r.eps_basic_ytd == Decimal('75.50')
        assert r.equity_ratio == Decimal('42.2')

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '140', rows=None)
        r = parse_quarterly_report(doc)
        assert isinstance(r, QuarterlyReport)
        assert r.revenue_ytd is None

    def test_quarter_number_q1(self):
        """Q1 filing: ~4 months from fiscal year start."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト'),
            make_csv_row('jpdei_cor:CurrentFiscalYearEndDateDEI', 'FilingDateInstant', '2025-03-31'),
            make_csv_row('jpcrp_cor:FilingDateCoverPage', 'FilingDateInstant', '2024-08-14'),
        ]
        doc = make_mock_doc('S100Q1', '140', rows)
        r = parse_quarterly_report(doc)
        assert r.quarter_number == 1


# =====================================================================
# Large Holding Report (Doc 350)
# =====================================================================

class TestLargeHoldingExtraction:
    """End-to-end extraction tests for parse_large_holding."""

    def _base_rows(self):
        return [
            make_csv_row('jplvh_cor:EDINETCodeDEI', 'FilingDateInstant', 'E99001'),
            make_csv_row('jplvh_cor:Name', 'FilingDateInstant', 'アクティビスト投資'),
            make_csv_row('jplvh_cor:FilerNameInEnglishDEI', 'FilingDateInstant', 'Activist Fund'),
            make_csv_row('jplvh_cor:IndividualOrCorporation', 'FilingDateInstant', '法人'),
            make_csv_row('jplvh_cor:ResidentialAddressOrAddressOfRegisteredHeadquarter', 'FilingDateInstant', '東京都千代田区'),
            make_csv_row('jplvh_cor:DescriptionOfBusiness', 'FilingDateInstant', '投資業'),
            make_csv_row('jplvh_cor:NameOfIssuer', 'FilingDateInstant', 'ターゲット株式会社'),
            make_csv_row('jplvh_cor:SecurityCodeOfIssuer', 'FilingDateInstant', '24770'),
            make_csv_row('jplvh_cor:ListedOrOTC', 'FilingDateInstant', '上場'),
            make_csv_row('jplvh_cor:TotalNumberOfStocksEtcHeld', 'FilingDateInstant', '5,000,000'),
            make_csv_row('jplvh_cor:HoldingRatioOfShareCertificatesEtc', 'FilingDateInstant', '9.67'),
            make_csv_row('jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport', 'FilingDateInstant', '5.12'),
            make_csv_row('jplvh_cor:TotalNumberOfOutstandingStocksEtc', 'FilingDateInstant', '51,700,000'),
            make_csv_row('jplvh_cor:PurposeOfHolding', 'FilingDateInstant', '純投資'),
            make_csv_row('jplvh_cor:FilingDateCoverPage', 'FilingDateInstant', '2025-06-15'),
            make_csv_row('jplvh_cor:AmountOfOwnFund', 'FilingDateInstant', '500,000,000'),
            make_csv_row('jplvh_cor:TotalAmountOfFundingForAcquisition', 'FilingDateInstant', '500,000,000'),
            make_csv_row('jplvh_cor:DocumentTitleCoverPage', 'FilingDateInstant', '大量保有報告書'),
        ]

    def test_full_extraction(self):
        doc = make_mock_doc('S100LH', '350', self._base_rows())
        r = parse_large_holding(doc)

        assert isinstance(r, LargeHoldingReport)
        assert r.filer_edinet_code == 'E99001'
        assert r.filer_name == 'アクティビスト投資'
        assert r.filer_name_en == 'Activist Fund'
        assert r.filer_type == '法人'
        assert r.target_company == 'ターゲット株式会社'
        assert r.target_ticker == '2477.T'
        assert r.listed_or_otc == '上場'
        assert r.shares_held == 5000000
        assert r.shares_outstanding == 51700000
        assert r.purpose == '純投資'
        assert r.filing_date == date(2025, 6, 15)
        assert r.report_indication == '大量保有報告書'

        # Ownership percentages (stored as raw percentage value)
        assert r.ownership_pct == Decimal('9.67')
        assert r.prior_ownership_pct == Decimal('5.12')

        # Calculated change
        assert r.ownership_change == Decimal('9.67') - Decimal('5.12')

        # Funding
        assert r.acquisition_fund_own == 500000000
        assert r.acquisition_fund_total == 500000000

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '350', rows=None)
        r = parse_large_holding(doc)
        assert isinstance(r, LargeHoldingReport)
        assert r.filer_name is None

    def test_filer_name_fallback(self):
        """When primary Name element missing, should fall back to DEI FilerName."""
        rows = [
            # No jplvh_cor:Name — fall back to FilerNameInJapaneseDEI
            make_csv_row('jplvh_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'Fallback Filer'),
            make_csv_row('jplvh_cor:NameOfIssuer', 'FilingDateInstant', 'Target'),
        ]
        doc = make_mock_doc('S100FB', '350', rows)
        r = parse_large_holding(doc)
        assert r.filer_name == 'Fallback Filer'

    def test_csv_files_param(self):
        """Verify csv_files= parameter path."""
        from edinet_tools.parsers.extraction import extract_csv_from_zip
        zip_bytes = make_zip_with_rows(self._base_rows())
        csv_files = extract_csv_from_zip(zip_bytes)

        r = parse_large_holding(csv_files=csv_files, doc_id='S100CSV', doc_type_code='350')
        assert r.filer_name == 'アクティビスト投資'
        assert r.target_ticker == '2477.T'

    def test_single_filer_holder1_only_is_not_joint(self):
        """Real-shape single-filer LHR carries only FilerLargeVolumeHolder1Member."""
        rows = self._base_rows() + [
            # Real-EDINET-shape: primary filer's contribution under Holder1Member
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                '5000000',
            ),
        ]
        doc = make_mock_doc('S100SOLO', '350', rows)
        r = parse_large_holding(doc)
        assert r.is_joint_filing is False

    def test_holder2_axis_marks_joint_filing(self):
        """Real-shape joint LHR carries FilerLargeVolumeHolder2Member (or higher).

        Joint Large Holding Reports (multiple co-reporters reporting the same
        holding) carry per-co-reporter axis members in context_ids:
        `..._FilerLargeVolumeHolder1Member`, `2Member`, `3Member`, etc.
        Detection: presence of any Holder<N>Member where N >= 2 = joint filing.
        Captured from real filings: Mizuho Bank (3 holders) and
        SMBC Nikko (3 holders).
        """
        rows = self._base_rows() + [
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                '3000000',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                '2000000',
            ),
        ]
        doc = make_mock_doc('S100JOINT', '350', rows)
        r = parse_large_holding(doc)
        assert r.is_joint_filing is True

    def test_three_co_reporters_marks_joint_filing(self):
        """3 co-reporters (Holder1+2+3 all present) is joint."""
        rows = self._base_rows() + [
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                f'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder{n}Member',
                '1000000',
            )
            for n in (1, 2, 3)
        ]
        doc = make_mock_doc('S100JOINT3', '350', rows)
        r = parse_large_holding(doc)
        assert r.is_joint_filing is True

    def test_double_digit_holder_number_marks_joint_filing(self):
        """Two-digit holder numbers (e.g. Holder12Member) are recognized as joint."""
        rows = self._base_rows() + [
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder12Member',
                '500000',
            ),
        ]
        doc = make_mock_doc('S100JOINT12', '350', rows)
        r = parse_large_holding(doc)
        assert r.is_joint_filing is True

    def test_empty_zip_is_not_joint(self):
        """Empty/missing csv_files returns is_joint_filing=False (default)."""
        doc = make_mock_doc('S100EMPTY2', '350', rows=None)
        r = parse_large_holding(doc)
        assert r.is_joint_filing is False

    def test_extract_joint_holders_returns_all_filers_for_4_holder_filing(self):
        """A 4-holder Doc 350 should produce a 4-element joint_holders list
        sorted by holder_number ascending, with identity fields populated."""
        rows = self._base_rows() + [
            # Holder 1 — primary, corporate
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                'プライマリ株式会社',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:EdinetCodeOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                'E11111',
                'EDINETコード、大量保有DEI',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                '1000000',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
            # Holder 2 — co-reporter, individual
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                '田中　太郎',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:EdinetCodeOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                'E22222',
                'EDINETコード、大量保有DEI',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                '500000',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
            # Holder 3 — co-reporter, corporate
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder3Member',
                'サードコ株式会社',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder3Member',
                '250000',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
            # Holder 4 — co-reporter, corporate, only name
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder4Member',
                'フォース株式会社',
                '氏名又は名称',
            ),
        ]
        doc = make_mock_doc('S100JOINT4FULL', '350', rows)
        r = parse_large_holding(doc)
        assert r.joint_holder_count == 4
        assert len(r.joint_holders) == 4
        assert [h.holder_number for h in r.joint_holders] == [1, 2, 3, 4]
        assert r.joint_holders[0].name_jp == 'プライマリ株式会社'
        assert r.joint_holders[0].edinet_code == 'E11111'
        assert r.joint_holders[0].shares_held == 1000000
        assert r.joint_holders[1].name_jp == '田中　太郎'
        assert r.joint_holders[1].edinet_code == 'E22222'
        assert r.joint_holders[1].shares_held == 500000
        assert r.joint_holders[2].name_jp == 'サードコ株式会社'
        assert r.joint_holders[2].shares_held == 250000
        assert r.joint_holders[3].name_jp == 'フォース株式会社'
        assert r.joint_holders[3].shares_held is None  # not provided
        assert r.is_joint_filing is True  # K=4 >= 2

    def test_extract_joint_holders_single_filer_returns_one_element_list(self):
        """A single-filer LHR (only FilerLargeVolumeHolder1Member) returns
        a 1-element list; is_joint_filing stays False."""
        rows = self._base_rows() + [
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                'ソロ株式会社',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                '3000000',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
        ]
        doc = make_mock_doc('S100SOLOFULL', '350', rows)
        r = parse_large_holding(doc)
        assert r.joint_holder_count == 1
        assert len(r.joint_holders) == 1
        assert r.joint_holders[0].holder_number == 1
        assert r.joint_holders[0].name_jp == 'ソロ株式会社'
        assert r.joint_holders[0].shares_held == 3000000
        assert r.is_joint_filing is False

    def test_extract_joint_holders_empty_csv_files_returns_empty_list(self):
        """Empty/missing csv_files returns joint_holders=[]; joint_holder_count=0."""
        doc = make_mock_doc('S100EMPTYJH', '350', rows=None)
        r = parse_large_holding(doc)
        assert r.joint_holders == []
        assert r.joint_holder_count == 0
        assert r.is_joint_filing is False

    def test_extract_joint_holders_normalizes_null_markers(self):
        """A holder with all '－' fields appears in the list with NULL
        identity/ownership but with holder_number populated."""
        rows = self._base_rows() + [
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                'プライマリ株式会社',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder1Member',
                '1000000',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
            # Holder 2 — all NULL markers
            make_csv_row(
                'jplvh_cor:NameOfReporter',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                '－',
                '氏名又は名称',
            ),
            make_csv_row(
                'jplvh_cor:NumberOfStocksOrEquityHeld',
                'FilingDateInstant_jplvh030000-lvh_E99001-000FilerLargeVolumeHolder2Member',
                '－',
                '株券又は投資証券等、法第27条の23第3項本文',
            ),
        ]
        doc = make_mock_doc('S100NULLJH', '350', rows)
        r = parse_large_holding(doc)
        assert r.joint_holder_count == 2
        assert r.joint_holders[0].name_jp == 'プライマリ株式会社'
        assert r.joint_holders[0].shares_held == 1000000
        assert r.joint_holders[1].holder_number == 2
        assert r.joint_holders[1].name_jp is None
        assert r.joint_holders[1].shares_held is None

    def test_holder_name_html_unescaped(self):
        """Holder names with HTML entities (&amp;) are unescaped — EDINET emits
        raw entity references in some filer names (~4,400 rows carry '&amp;')."""
        from edinet_tools.parsers.large_holding import _normalize_holder_value
        assert _normalize_holder_value(
            'HOKUBU Communication &amp; Industrial Co.,Ltd.', str
        ) == 'HOKUBU Communication & Industrial Co.,Ltd.'


# =====================================================================
# Treasury Stock Report (Doc 220)
# =====================================================================

class TestTreasuryStockExtraction:
    """End-to-end extraction tests for parse_treasury_stock_report."""

    def _base_rows(self):
        return [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
            make_csv_row('jpdei_cor:FilerNameInEnglishDEI', 'FilingDateInstant', 'Test Corp'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '24770'),
            make_csv_row('jpdei_cor:AmendmentFlagDEI', 'FilingDateInstant', 'false'),
            make_csv_row('jpcrp-sbr_cor:DocumentTitleCoverPage', 'FilingDateInstant', '自己株券買付状況報告書'),
            make_csv_row('jpcrp-sbr_cor:FilingDateCoverPage', 'FilingDateInstant', '2025-07-15'),
            make_csv_row('jpcrp-sbr_cor:TitleAndNameOfRepresentativeCoverPage', 'FilingDateInstant', '代表取締役 田中太郎'),
            make_csv_row('jpcrp-sbr_cor:AddressOfRegisteredHeadquarterCoverPage', 'FilingDateInstant', '東京都渋谷区'),
            make_csv_row('jpcrp-sbr_cor:ReportingPeriodCoverPage', 'FilingDateInstant', '2025年6月'),
            # TextBlock content
            make_csv_row('jpcrp-sbr_cor:AcquisitionsByResolutionOfShareholdersMeetingTextBlock', 'FilingDateInstant', '<p>株主総会決議による取得</p>'),
            make_csv_row('jpcrp-sbr_cor:AcquisitionsByResolutionOfBoardOfDirectorsMeetingTextBlock', 'FilingDateInstant', '<p>取締役会決議による取得</p>'),
            make_csv_row('jpcrp-sbr_cor:HoldingOfTreasurySharesTextBlock', 'FilingDateInstant', '保有自己株式数1,000,000株'),
        ]

    def test_full_extraction(self):
        doc = make_mock_doc('S100TS', '220', self._base_rows())
        r = parse_treasury_stock_report(doc)

        assert isinstance(r, TreasuryStockReport)
        assert r.filer_edinet_code == 'E05123'
        assert r.filer_name == 'テスト株式会社'
        assert r.ticker == '2477.T'
        assert r.filing_date == date(2025, 7, 15)
        assert r.representative == '代表取締役 田中太郎'
        assert r.reporting_period == '2025年6月'
        assert r.is_amendment is False

        # TextBlock content
        assert '株主総会決議' in r.by_shareholders_meeting
        assert '取締役会決議' in r.by_board_meeting
        assert '保有自己株式数' in r.disposal_holding_text

    def test_amendment_flag(self):
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト'),
            make_csv_row('jpdei_cor:AmendmentFlagDEI', 'FilingDateInstant', 'true'),
        ]
        doc = make_mock_doc('S100AMEND', '230', rows)
        r = parse_treasury_stock_report(doc)
        assert r.is_amendment is True

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '220', rows=None)
        r = parse_treasury_stock_report(doc)
        assert isinstance(r, TreasuryStockReport)
        assert r.filer_name is None


# =====================================================================
# Extraordinary Report (Doc 180)
# =====================================================================

class TestExtraordinaryExtraction:
    """End-to-end extraction tests for parse_extraordinary_report."""

    def test_corporate_report(self):
        """Corporate extraordinary report uses jpcrp-esr_cor namespace."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
            make_csv_row('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '24770'),
            make_csv_row('jpcrp-esr_cor:DocumentTitleCoverPage', 'FilingDateInstant', '臨時報告書'),
            make_csv_row('jpcrp-esr_cor:FilingDateCoverPage', 'FilingDateInstant', '2025-08-01'),
            make_csv_row('jpcrp-esr_cor:TitleAndNameOfRepresentativeCoverPage', 'FilingDateInstant', '代表取締役 山田花子'),
            make_csv_row('jpcrp-esr_cor:ReasonForFilingTextBlock', 'FilingDateInstant', '重要な変更が発生しました'),
        ]
        doc = make_mock_doc('S100EX', '180', rows)
        r = parse_extraordinary_report(doc)

        assert isinstance(r, ExtraordinaryReport)
        assert r.filer_edinet_code == 'E05123'
        assert r.filer_name == 'テスト株式会社'
        assert r.ticker == '2477.T'
        assert r.document_title == '臨時報告書'
        assert r.filing_date == date(2025, 8, 1)
        assert r.reason_for_filing == '重要な変更が発生しました'
        assert r.event_type == 'material_change'

    def test_fund_report(self):
        """Fund extraordinary report uses jpsps-esr_cor namespace."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E77777'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テストファンド'),
            make_csv_row('jpdei_cor:FundCodeDEI', 'FilingDateInstant', 'G12345'),
            make_csv_row('jpdei_cor:FundNameInJapaneseDEI', 'FilingDateInstant', 'テスト投資信託'),
            make_csv_row('jpsps-esr_cor:DocumentTitleCoverPage', 'FilingDateInstant', '臨時報告書'),
            make_csv_row('jpsps-esr_cor:FilingDateCoverPage', 'FilingDateInstant', '2025-09-01'),
            make_csv_row('jpsps-esr_cor:ReasonForFilingTextBlock', 'FilingDateInstant', '信託終了のお知らせ'),
        ]
        doc = make_mock_doc('S100FUND', '180', rows)
        r = parse_extraordinary_report(doc)

        assert r.fund_code == 'G12345'
        assert r.fund_name == 'テスト投資信託'
        assert r.event_type == 'trust_termination'
        assert r.filing_date == date(2025, 9, 1)

    def test_event_type_classification(self):
        """Various event type keywords should be classified correctly."""
        from edinet_tools.parsers.extraordinary import _classify_event_type

        assert _classify_event_type('信託終了のお知らせ') == 'trust_termination'
        assert _classify_event_type('吸収合併のお知らせ') == 'merger'
        assert _classify_event_type('約款変更のお知らせ') == 'trust_change'
        assert _classify_event_type('解散について') == 'dissolution'
        assert _classify_event_type('重要な変更') == 'material_change'
        assert _classify_event_type('通常のお知らせ') == 'other'
        assert _classify_event_type(None) == 'unknown'

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '180', rows=None)
        r = parse_extraordinary_report(doc)
        assert isinstance(r, ExtraordinaryReport)
        assert r.filer_name is None


# =====================================================================
# Semi-Annual Report (Doc 160)
# =====================================================================

class TestSemiAnnualExtraction:
    """End-to-end extraction tests for parse_semi_annual_report."""

    def _base_rows(self):
        return [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
            make_csv_row('jpdei_cor:CurrentFiscalYearStartDateDEI', 'FilingDateInstant', '2024-04-01'),
            make_csv_row('jpdei_cor:CurrentPeriodEndDateDEI', 'FilingDateInstant', '2024-09-30'),
            make_csv_row('jpdei_cor:DateOfSubmissionDEI', 'FilingDateInstant', '2024-12-25'),
            # Financials (no context filtering in semi_annual parser)
            make_csv_row('jppfs_cor:Assets', 'CurrentQuarterInstant', '80000000000'),
            make_csv_row('jppfs_cor:CurrentAssets', 'CurrentQuarterInstant', '30000000000'),
            make_csv_row('jppfs_cor:Liabilities', 'CurrentQuarterInstant', '45000000000'),
            make_csv_row('jppfs_cor:NetAssets', 'CurrentQuarterInstant', '35000000000'),
            make_csv_row('jppfs_cor:OperatingIncome', 'CurrentYTDDuration', '2000000000'),
            make_csv_row('jppfs_cor:OrdinaryIncome', 'CurrentYTDDuration', '2100000000'),
            make_csv_row('jppfs_cor:ProfitLoss', 'CurrentYTDDuration', '1200000000'),
        ]

    def test_full_extraction(self):
        doc = make_mock_doc('S100SA', '160', self._base_rows())
        r = parse_semi_annual_report(doc)

        assert isinstance(r, SemiAnnualReport)
        assert r.filer_edinet_code == 'E05123'
        assert r.filer_name == 'テスト株式会社'
        assert r.period_start == date(2024, 4, 1)
        assert r.period_end == date(2024, 9, 30)
        assert r.filing_date == date(2024, 12, 25)

        assert r.total_assets == 80000000000
        assert r.current_assets == 30000000000
        assert r.total_liabilities == 45000000000
        assert r.net_assets == 35000000000
        assert r.operating_income == 2000000000
        assert r.ordinary_income == 2100000000
        assert r.profit_loss == 1200000000

    def test_fund_report(self):
        """Fund semi-annual report extracts fund_code from DEI."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E77777'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト投信'),
            make_csv_row('jpdei_cor:FundCodeDEI', 'FilingDateInstant', 'G12345'),
            make_csv_row('jpdei_cor:FundNameInJapaneseDEI', 'FilingDateInstant', 'テストファンド'),
            make_csv_row('jpsps_cor:NetAssetsAtFiscalYearEnd', 'CurrentYearInstant', '1000000000'),
        ]
        doc = make_mock_doc('S100FUND', '160', rows)
        r = parse_semi_annual_report(doc)
        assert r.fund_code == 'G12345'

    def test_ifrs_fallback(self):
        """When J-GAAP element missing, should fall back to IFRS."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E88888'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'IFRS社'),
            # No J-GAAP Assets — should fall back to IFRS
            make_csv_row('jpigp_cor:AssetsIFRS', 'CurrentQuarterInstant', '99000000000'),
        ]
        doc = make_mock_doc('S100IFRS', '160', rows)
        r = parse_semi_annual_report(doc)
        assert r.total_assets == 99000000000

    def test_empty_zip(self):
        doc = make_mock_doc('S100EMPTY', '160', rows=None)
        r = parse_semi_annual_report(doc)
        assert isinstance(r, SemiAnnualReport)
        assert r.total_assets is None

    def test_filing_date_fallback_to_period_end(self):
        """When submission_date missing, filing_date should fall back to period_end."""
        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E05123'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト'),
            make_csv_row('jpdei_cor:CurrentPeriodEndDateDEI', 'FilingDateInstant', '2024-09-30'),
            # No submission_date
        ]
        doc = make_mock_doc('S100FB', '160', rows)
        r = parse_semi_annual_report(doc)
        assert r.filing_date == date(2024, 9, 30)


# =====================================================================
# IFRS Summary Metrics Extraction (v0.7.2+)
# =====================================================================


class TestIFRSSummaryMetricsExtraction:
    """Verify ifrs_summary_basic_eps / _roe / _bps extraction from
    jpcrp_cor:*IFRSSummaryOfBusinessResults XBRL elements at the
    CurrentYearDuration / CurrentYearInstant context."""

    def _base_rows(self):
        """Minimal csv_files-shape rows for a synthetic IFRS securities report."""
        return [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E99001'),
            make_csv_row('jpdei_cor:CurrentFiscalYearStartDateDEI',
                         'FilingDateInstant', '2024-04-01'),
            make_csv_row('jpdei_cor:CurrentFiscalYearEndDateDEI',
                         'FilingDateInstant', '2025-03-31'),
            make_csv_row('jpdei_cor:AccountingStandardsDEI',
                         'FilingDateInstant', 'IFRS'),
        ]

    def test_ifrs_reporter_populates_all_3_summary_fields(self):
        """An IFRS reporter with all 3 summary fields at CurrentYear context
        populates all 3 typed fields with correct Decimal values."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '350.92',
            ),
            make_csv_row(
                'jpcrp_cor:RateOfReturnOnEquityIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '0.069',
            ),
            make_csv_row(
                'jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults',
                'CurrentYearInstant', '5150.56',
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSALL',
                                    doc_type_code='120')

        assert r.ifrs_summary_basic_eps == Decimal('350.92')
        assert r.ifrs_summary_roe == Decimal('0.069')
        assert r.ifrs_summary_bps == Decimal('5150.56')

    def test_jgaap_reporter_leaves_ifrs_summary_fields_null(self):
        """A J-GAAP reporter (no IFRS summary fields in csv_files) returns
        all 3 typed fields as None."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = [r for r in self._base_rows()
                if r['要素ID'] != 'jpdei_cor:AccountingStandardsDEI']
        rows.append(make_csv_row('jpdei_cor:AccountingStandardsDEI',
                                 'FilingDateInstant', 'Japan GAAP'))
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SJGAAP',
                                    doc_type_code='120')

        assert r.ifrs_summary_basic_eps is None
        assert r.ifrs_summary_roe is None
        assert r.ifrs_summary_bps is None

    def test_ifrs_reporter_partial_coverage_returns_partial(self):
        """An IFRS reporter with only EPS summary present (missing ROE +
        BPS) populates only ifrs_summary_basic_eps; others stay None."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '780.82',
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSPARTIAL',
                                    doc_type_code='120')

        assert r.ifrs_summary_basic_eps == Decimal('780.82')
        assert r.ifrs_summary_roe is None
        assert r.ifrs_summary_bps is None

    def test_ifrs_reporter_ignores_prior_year_values(self):
        """When both Prior4YearDuration and CurrentYearDuration rows are
        present for the same element, only CurrentYearDuration is picked."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'Prior4YearDuration', '-35.22',  # should be ignored
            ),
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '350.92',  # should be picked
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSCTX',
                                    doc_type_code='120')

        assert r.ifrs_summary_basic_eps == Decimal('350.92')

    def test_ifrs_null_marker_normalizes_to_none(self):
        """EDINET emits '－' (U+FF0D full-width minus) as the null marker
        on numeric fields. A truthy check ('if x else None') lets the marker
        through to Decimal() and crashes with ConversionSyntax. The 3 new
        ifrs_summary_* extractions must normalize '－' / '-' / empty to None
        before Decimal().
        """
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '－',  # U+FF0D full-width minus
            ),
            make_csv_row(
                'jpcrp_cor:RateOfReturnOnEquityIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '-',  # bare ASCII hyphen
            ),
            make_csv_row(
                'jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults',
                'CurrentYearInstant', '',  # empty string
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSNULL',
                                    doc_type_code='120')

        assert r.ifrs_summary_basic_eps is None
        assert r.ifrs_summary_roe is None
        assert r.ifrs_summary_bps is None

    def test_jgaap_eps_waterfall_null_markers_normalize_to_none(self):
        """The pre-existing J-GAAP-then-IFRS EPS waterfall (line 432-436)
        had the same truthy-vs-None pattern. Both branches must normalize
        '－' to None — otherwise '－' in the J-GAAP element truthy-passes
        the `if not eps_str` gate (skipping the fallback) and crashes
        Decimal(); or '－' in the IFRS fallback after a missing J-GAAP
        element similarly crashes Decimal()."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        # Case 1: J-GAAP EPS is '－', no IFRS fallback element.
        # Without the fix: '－' truthy-passes, Decimal('－') crashes.
        # With the fix: '－' normalized to None, falls through, no IFRS
        # element → eps stays None.
        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults',
                'CurrentYearDuration', '－',
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SJGAPNULL',
                                    doc_type_code='120')
        assert r.earnings_per_share is None

        # Case 2: J-GAAP EPS missing entirely, IFRS-element fallback is '－'.
        # Without the fix: J-GAAP absent → falls through to IFRS → '－' →
        # Decimal('－') crashes.
        # With the fix: IFRS '－' normalized to None → eps stays None.
        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
                'CurrentYearDuration', '－',
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSFB',
                                    doc_type_code='120')
        assert r.earnings_per_share is None

    def test_jgaap_navps_null_marker_normalizes_to_none(self):
        """The pre-existing NAVPS extraction (line 430) had the same
        truthy-vs-None pattern. Must normalize '－' / '-' / empty to
        None before Decimal()."""
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            make_csv_row(
                'jpcrp_cor:NetAssetsPerShareSummaryOfBusinessResults',
                'CurrentYearInstant', '－',  # U+FF0D
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SNAVNULL',
                                    doc_type_code='120')
        assert r.net_assets_per_share is None

    def test_extract_financial_uses_ifrs_fallback_when_jgaap_is_null_marker(self):
        """Soft bug in extract_financial: if J-GAAP element is '－', the
        truthy check `if value_str` passed (since '－' is truthy), parse_int
        returned None, and the function returned None immediately — never
        firing the IFRS fallback at the same context level. Result: IFRS
        reporters that emit J-GAAP elements with '－' silently had None
        for net_sales / operating_income / total_assets / etc.

        Fix: normalize '－' to None BEFORE the truthy check so the IFRS
        fallback fires correctly.
        """
        from edinet_tools.parsers.securities import parse_securities_report
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = self._base_rows() + [
            # J-GAAP NetSales with null marker
            make_csv_row(
                'jppfs_cor:NetSales', 'CurrentYearDuration', '－',
            ),
            # IFRS Revenue with real value at the same context level
            make_csv_row(
                'jpigp_cor:RevenueIFRS', 'CurrentYearDuration', '5000000000',
            ),
            # J-GAAP OperatingIncome with null marker
            make_csv_row(
                'jppfs_cor:OperatingIncome', 'CurrentYearDuration', '－',
            ),
            # IFRS OperatingProfitLoss with real value
            make_csv_row(
                'jpigp_cor:OperatingProfitLossIFRS', 'CurrentYearDuration', '700000000',
            ),
        ]
        zip_bytes = make_zip_with_rows(rows)
        csv_files = extract_csv_from_zip(zip_bytes)
        r = parse_securities_report(csv_files=csv_files, doc_id='SIFRSFB',
                                    doc_type_code='120')

        # Without the fix: both would be None (J-GAAP '－' truthy-passes →
        # parse_int returns None → function returns None, IFRS fallback never
        # fires). With the fix: IFRS values are picked up.
        assert r.net_sales == 5000000000
        assert r.operating_income == 700000000

    def test_semi_annual_extract_financial_uses_ifrs_fallback_when_jgaap_is_null(self):
        """Same soft-bug shape as extract_financial above, but in
        semi_annual._extract_financial. Fix: normalize before truthy check
        so IFRS fallback fires when J-GAAP element is '－'.
        """
        from edinet_tools.parsers.semi_annual import parse_semi_annual_report

        rows = [
            make_csv_row('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E12345'),
            make_csv_row('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト'),
            make_csv_row('jpdei_cor:CurrentFiscalYearStartDateDEI',
                         'FilingDateInstant', '2024-04-01'),
            make_csv_row('jpdei_cor:CurrentPeriodEndDateDEI',
                         'FilingDateInstant', '2024-09-30'),
            make_csv_row('jpdei_cor:DateOfSubmissionDEI',
                         'FilingDateInstant', '2024-12-25'),
            # J-GAAP Assets is '－', IFRS AssetsIFRS has a real value
            make_csv_row('jppfs_cor:Assets', 'CurrentQuarterInstant', '－'),
            make_csv_row('jpigp_cor:AssetsIFRS', 'CurrentQuarterInstant', '90000000000'),
        ]
        doc = make_mock_doc('S100IFRSFB', '160', rows)
        r = parse_semi_annual_report(doc)

        # Without the fix: total_assets would be None despite IFRS having
        # a value. With the fix: total_assets is the IFRS value.
        assert r.total_assets == 90000000000


class TestExtractCsvFromZipEncodingOrder:
    """Regression pin (0.8.0 stage-5, found via the zero-dependency smoke
    test): extract_csv_from_zip's encoding-trial order must try 'utf-8'
    before the 'utf-16' family. utf-16/utf-16le barely validate anything -
    most even-length byte strings decode "successfully" into mojibake
    rather than raising - so a non-BOM UTF-8 file tried under utf-16le
    first can silently collapse into a single garbage row instead of the
    correct multi-row parse. Every other extraction test in this file
    builds its fixture via .encode('utf-16le'), matching the first-tried
    encoding, so this class is the only place a non-BOM UTF-8 input
    actually exercises the encoding order.
    """

    def test_non_bom_utf8_csv_parses_correctly_not_mojibake(self):
        from edinet_tools.parsers.extraction import extract_csv_from_zip

        rows = [
            ('要素ID', '項目名', 'コンテキストID', '相対年度',
             '連結・個別', '期間・時点', 'ユニットID', '単位', '値'),
            ('jpdei_cor:EDINETCodeDEI', 'EDINETコード', 'FilingDateInstant',
             '', '', '', '', '', 'E99999'),
            ('jpcrp_cor:NetSalesSummaryOfBusinessResults', '売上高',
             'CurrentYearDuration', '', '', '', '', '円', '50000000000'),
        ]
        csv_content = '\n'.join('\t'.join(r) for r in rows)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            # Plain UTF-8, no BOM - the class that previously mojibaked.
            zf.writestr('XBRL_TO_CSV/test.csv', csv_content.encode('utf-8'))

        csv_files = extract_csv_from_zip(zip_buffer.getvalue())

        assert len(csv_files) == 1
        data = csv_files[0]['data']
        # 3 rows: the header (kept as an ordinary data row by design) + 2
        # real rows - NOT 1 garbage row from a false-positive utf-16 decode.
        assert len(data) == 3
        element_ids = [row['要素ID'] for row in data]
        assert 'jpdei_cor:EDINETCodeDEI' in element_ids
        assert 'jpcrp_cor:NetSalesSummaryOfBusinessResults' in element_ids
        net_sales_row = next(
            row for row in data
            if row['要素ID'] == 'jpcrp_cor:NetSalesSummaryOfBusinessResults'
        )
        assert net_sales_row['値'] == '50000000000'
