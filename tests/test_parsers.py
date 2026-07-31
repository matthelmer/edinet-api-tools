"""Tests for document parsers."""
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from edinet_tools.parsers.base import ParsedReport
from edinet_tools.parsers.generic import RawReport
from edinet_tools.parsers import parse
from edinet_tools.parsers.large_holding import LargeHoldingReport, parse_large_holding
from edinet_tools.parsers.securities import SecuritiesReport, parse_securities_report
from edinet_tools.parsers.quarterly import QuarterlyReport, parse_quarterly_report
from edinet_tools.parsers.semi_annual import SemiAnnualReport, parse_semi_annual_report
from edinet_tools.parsers.extraordinary import ExtraordinaryReport, parse_extraordinary_report
from edinet_tools.parsers.treasury_stock import TreasuryStockReport, parse_treasury_stock_report


class TestParsedReportBase:
    """Test ParsedReport base class."""

    def test_parsed_report_structure(self):
        """ParsedReport has required attributes."""
        report = ParsedReport(
            doc_id='S100ABC123',
            doc_type_code='350',
            source_files=['file1.csv'],
            raw_fields={'key': 'value'},
            unmapped_fields={'other': 'data'},
            text_blocks={'block1': 'some text'},
        )
        assert report.doc_id == 'S100ABC123'
        assert report.raw_fields == {'key': 'value'}

    def test_parsed_report_fields_method(self):
        """ParsedReport.fields() lists field names."""
        report = ParsedReport(
            doc_id='S100ABC123',
            doc_type_code='350',
        )
        fields = report.fields()
        assert 'doc_id' in fields
        assert 'doc_type_code' in fields

    def test_parsed_report_to_dict(self):
        """ParsedReport.to_dict() exports as dict."""
        report = ParsedReport(
            doc_id='S100ABC123',
            doc_type_code='350',
        )
        d = report.to_dict()
        assert d['doc_id'] == 'S100ABC123'


class TestRawReport:
    """Test RawReport fallback."""

    def test_raw_report_extends_parsed_report(self):
        """RawReport extends ParsedReport."""
        report = RawReport(
            doc_id='S100ABC123',
            doc_type_code='999',
            filer_name='Test Corp',
        )
        assert report.filer_name == 'Test Corp'
        assert 'doc_id' in report.fields()


class TestParseDispatcher:
    """Test parse() dispatcher function."""

    def test_parse_returns_parsed_report(self):
        """parse() returns a ParsedReport subclass."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100ABC123'
        doc.doc_type_code = '999'  # Unknown type -> RawReport
        doc.fetch.return_value = b''  # Empty content

        result = parse(doc)
        assert isinstance(result, ParsedReport)

    def test_parse_dispatches_to_correct_parser(self):
        """parse() dispatches to typed parser for known doc types."""
        from unittest.mock import Mock, patch

        doc = Mock()
        doc.doc_id = 'S100ABC123'
        doc.doc_type_code = '350'

        with patch('edinet_tools.parsers.parse_large_holding') as mock_parser:
            mock_parser.return_value = Mock(spec=ParsedReport)
            result = parse(doc)
            mock_parser.assert_called_once_with(doc)


class TestLargeHoldingReport:
    """Test LargeHoldingReport parser (Doc 350)."""

    def test_large_holding_report_structure(self):
        """LargeHoldingReport has expected fields."""
        report = LargeHoldingReport(
            doc_id='S100ABC123',
            doc_type_code='350',
            filer_name='エフィッシモ キャピタル マネージメント',
            target_company='東芝',
            target_ticker='6502',
            ownership_pct=Decimal('8.23'),
            shares_held=35000000,
        )
        assert report.filer_name == 'エフィッシモ キャピタル マネージメント'
        assert report.target_company == '東芝'
        assert report.ownership_pct == Decimal('8.23')

    def test_large_holding_report_repr(self):
        """LargeHoldingReport repr is informative."""
        report = LargeHoldingReport(
            doc_id='S100ABC123',
            doc_type_code='350',
            filer_name='エフィッシモ',
            target_company='東芝',
            ownership_pct=Decimal('8.23'),
        )
        repr_str = repr(report)
        assert 'エフィッシモ' in repr_str or 'filer' in repr_str.lower()
        assert '東芝' in repr_str or 'target' in repr_str.lower()

    def test_large_holding_filer_property(self):
        """LargeHoldingReport.filer returns Entity if resolvable."""
        report = LargeHoldingReport(
            doc_id='S100ABC123',
            doc_type_code='350',
            filer_edinet_code='E02144',  # Toyota
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:  # May be None if code not found
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_large_holding_target_property(self):
        """LargeHoldingReport.target returns Entity if resolvable."""
        report = LargeHoldingReport(
            doc_id='S100ABC123',
            doc_type_code='350',
            target_ticker='7203',
            target_company='トヨタ自動車',
        )
        target = report.target
        if target:
            from edinet_tools.entity import Entity
            assert isinstance(target, Entity)

    def test_parse_large_holding_returns_report(self):
        """parse_large_holding returns LargeHoldingReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '350'

        report = parse_large_holding(doc)
        assert isinstance(report, LargeHoldingReport)
        assert report.doc_id == 'S100TEST'

    def test_listed_or_otc_field(self):
        """LargeHoldingReport has listed_or_otc field."""
        from edinet_tools.parsers.large_holding import ELEMENT_MAP
        report = LargeHoldingReport(doc_id='S100TEST', doc_type_code='350')
        assert report.listed_or_otc is None
        assert 'listed_or_otc' in ELEMENT_MAP


class TestSecuritiesReport:
    """Test SecuritiesReport parser (Doc 120)."""

    def test_securities_report_structure(self):
        """SecuritiesReport has expected fields."""
        report = SecuritiesReport(
            doc_id='S100ABC123',
            doc_type_code='120',
            filer_name='トヨタ自動車株式会社',
            filer_edinet_code='E02144',
            fiscal_year_end=date(2025, 3, 31),
            net_sales=45000000000000,
            operating_income=3000000000000,
            net_income=2500000000000,
        )
        assert report.filer_name == 'トヨタ自動車株式会社'
        assert report.net_sales == 45000000000000

    def test_securities_report_repr(self):
        """SecuritiesReport repr is informative."""
        report = SecuritiesReport(
            doc_id='S100ABC123',
            doc_type_code='120',
            filer_name='トヨタ自動車',
            fiscal_year_end=date(2025, 3, 31),
        )
        repr_str = repr(report)
        assert 'トヨタ' in repr_str or '120' in repr_str

    def test_securities_report_filer_property(self):
        """SecuritiesReport.filer returns Entity if resolvable."""
        report = SecuritiesReport(
            doc_id='S100ABC123',
            doc_type_code='120',
            filer_edinet_code='E02144',
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_parse_securities_report_returns_report(self):
        """parse_securities_report returns SecuritiesReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '120'

        report = parse_securities_report(doc)
        assert isinstance(report, SecuritiesReport)
        assert report.doc_id == 'S100TEST'

    def test_dataclass_has_balance_sheet_detail_fields(self):
        """SecuritiesReport should have balance sheet and income detail fields."""
        from edinet_tools.parsers.securities import ELEMENT_MAP
        report = SecuritiesReport(doc_id='S100TEST', doc_type_code='120')
        # Balance sheet detail
        assert report.cash_and_deposits is None
        assert report.current_assets is None
        assert report.noncurrent_assets is None
        assert report.property_plant_equipment is None
        assert report.deferred_tax_assets is None
        assert report.current_liabilities is None
        assert report.retained_earnings is None
        # Income detail
        assert report.income_before_taxes is None
        assert report.income_taxes is None
        # Cash flow detail
        assert report.depreciation_amortization is None
        # Element map entries
        for key in ['cash_and_deposits', 'current_assets', 'noncurrent_assets',
                     'property_plant_equipment', 'income_before_taxes', 'income_taxes',
                     'depreciation_amortization_cfo']:
            assert key in ELEMENT_MAP, f"Missing ELEMENT_MAP key: {key}"

    def test_element_map_has_ifrs_summary_entries(self):
        """ELEMENT_MAP should include IFRS Summary elements."""
        from edinet_tools.parsers.securities import ELEMENT_MAP
        for key in ['net_sales_ifrs_summary', 'net_income_ifrs_summary',
                     'total_assets_ifrs_summary', 'net_assets_ifrs_summary',
                     'operating_income_ifrs_summary', 'earnings_per_share_ifrs',
                     'equity_ratio_ifrs', 'roe_ifrs']:
            assert key in ELEMENT_MAP, f"Missing ELEMENT_MAP key: {key}"


class TestQuarterlyReport:
    """Test QuarterlyReport parser (Doc 140)."""

    def test_quarterly_report_structure(self):
        """QuarterlyReport has expected fields."""
        report = QuarterlyReport(
            doc_id='S100ABC123',
            doc_type_code='140',
            filer_name='トヨタ自動車株式会社',
            quarter_number=2,
            fiscal_year_end=date(2026, 3, 31),
            revenue_ytd=11000000000000,
        )
        assert report.quarter_number == 2
        assert report.revenue_ytd == 11000000000000

    def test_quarterly_report_repr(self):
        """QuarterlyReport repr shows quarter."""
        report = QuarterlyReport(
            doc_id='S100ABC123',
            doc_type_code='140',
            filer_name='トヨタ',
            quarter_number=3,
        )
        repr_str = repr(report)
        assert 'Q3' in repr_str or '3' in repr_str

    def test_quarterly_report_filer_property(self):
        """QuarterlyReport.filer returns Entity if resolvable."""
        report = QuarterlyReport(
            doc_id='S100ABC123',
            doc_type_code='140',
            filer_edinet_code='E02144',
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_parse_quarterly_report_returns_report(self):
        """parse_quarterly_report returns QuarterlyReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '140'

        report = parse_quarterly_report(doc)
        assert isinstance(report, QuarterlyReport)
        assert report.doc_id == 'S100TEST'


class TestSemiAnnualReport:
    """Test SemiAnnualReport parser (Doc 160)."""

    def test_semi_annual_report_structure(self):
        """SemiAnnualReport has expected fields."""
        report = SemiAnnualReport(
            doc_id='S100ABC123',
            doc_type_code='160',
            filer_name='野村アセットマネジメント',
            fund_name='野村日本株ファンド',
            period_end=date(2025, 9, 30),
            net_assets=50000000000,
            total_assets=60000000000,
        )
        assert report.fund_name == '野村日本株ファンド'
        assert report.net_assets == 50000000000
        assert report.total_assets == 60000000000

    def test_semi_annual_report_repr(self):
        """SemiAnnualReport repr shows fund name and period."""
        report = SemiAnnualReport(
            doc_id='S100ABC123',
            doc_type_code='160',
            filer_name='野村アセット',
            fund_name='日本株ファンド',
            period_end=date(2025, 9, 30),
        )
        repr_str = repr(report)
        assert '日本株ファンド' in repr_str or '2025-09' in repr_str

    def test_semi_annual_report_filer_property(self):
        """SemiAnnualReport.filer returns Entity if resolvable."""
        report = SemiAnnualReport(
            doc_id='S100ABC123',
            doc_type_code='160',
            filer_edinet_code='E02144',
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_parse_semi_annual_report_returns_report(self):
        """parse_semi_annual_report returns SemiAnnualReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '160'

        report = parse_semi_annual_report(doc)
        assert isinstance(report, SemiAnnualReport)
        assert report.doc_id == 'S100TEST'


class TestExtraordinaryReport:
    """Test ExtraordinaryReport parser (Doc 180)."""

    def test_extraordinary_report_structure(self):
        """ExtraordinaryReport has expected fields."""
        report = ExtraordinaryReport(
            doc_id='S100ABC123',
            doc_type_code='180',
            filer_name='ソフトバンクグループ',
            event_type='merger',
            reason_for_filing='合併に関する報告',
            filing_date=date(2025, 6, 15),
        )
        assert report.filer_name == 'ソフトバンクグループ'
        assert report.event_type == 'merger'
        assert report.reason_for_filing == '合併に関する報告'

    def test_extraordinary_report_repr(self):
        """ExtraordinaryReport repr shows filer and event."""
        report = ExtraordinaryReport(
            doc_id='S100ABC123',
            doc_type_code='180',
            filer_name='ソフトバンク',
            event_type='合併',
        )
        repr_str = repr(report)
        assert 'ソフトバンク' in repr_str or '合併' in repr_str

    def test_extraordinary_report_filer_property(self):
        """ExtraordinaryReport.filer returns Entity if resolvable."""
        report = ExtraordinaryReport(
            doc_id='S100ABC123',
            doc_type_code='180',
            filer_edinet_code='E02144',
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_parse_extraordinary_report_returns_report(self):
        """parse_extraordinary_report returns ExtraordinaryReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '180'

        report = parse_extraordinary_report(doc)
        assert isinstance(report, ExtraordinaryReport)
        assert report.doc_id == 'S100TEST'

    def test_dataclass_has_amendment_and_contact_fields(self):
        """ExtraordinaryReport has amendment and contact fields."""
        from edinet_tools.parsers.extraordinary import ELEMENT_MAP
        report = ExtraordinaryReport(
            doc_id='S100TEST', doc_type_code='180',
        )
        assert report.amendment_flag is None
        assert report.report_amendment_flag is None
        assert report.place_of_filing is None
        assert report.contact_person is None
        for key in ['amendment_flag', 'report_amendment_flag',
                     'place_of_filing_fund', 'place_of_filing_corp',
                     'contact_person_fund', 'contact_person_corp']:
            assert key in ELEMENT_MAP, f"Missing ELEMENT_MAP key: {key}"


class TestTreasuryStockReport:
    """Test TreasuryStockReport parser (Doc 220/230)."""

    def test_treasury_stock_report_structure(self):
        """TreasuryStockReport has expected fields."""
        report = TreasuryStockReport(
            doc_id='S100ABC123',
            doc_type_code='220',
            filer_name='トヨタ自動車株式会社',
            filing_date=date(2025, 11, 15),
            by_board_meeting='取締役会決議に基づく取得',
            is_amendment=False,
        )
        assert report.filer_name == 'トヨタ自動車株式会社'
        assert report.filing_date == date(2025, 11, 15)
        assert report.by_board_meeting == '取締役会決議に基づく取得'
        assert report.is_amendment is False

    def test_treasury_stock_report_amendment(self):
        """TreasuryStockReport handles amendments (Doc 230)."""
        report = TreasuryStockReport(
            doc_id='S100ABC456',
            doc_type_code='230',
            filer_name='ソニーグループ',
            is_amendment=True,
        )
        assert report.is_amendment is True
        assert report.doc_type_code == '230'

    def test_treasury_stock_report_repr(self):
        """TreasuryStockReport repr shows filer and amendment status."""
        report = TreasuryStockReport(
            doc_id='S100ABC123',
            doc_type_code='220',
            filer_name='三菱UFJ',
        )
        assert '三菱UFJ' in repr(report)

        amended = TreasuryStockReport(
            doc_id='S100ABC456',
            doc_type_code='230',
            filer_name='三菱UFJ',
            is_amendment=True,
        )
        assert 'AMENDED' in repr(amended)

    def test_treasury_stock_authorization_text_blocks(self):
        """The authorization facts are the raw by_*_meeting text blocks."""
        report = TreasuryStockReport(
            doc_id='S100ABC123',
            doc_type_code='220',
            by_board_meeting='取締役会決議に基づく取得',
            by_shareholders_meeting=None,
        )
        assert report.by_board_meeting == '取締役会決議に基づく取得'
        assert report.by_shareholders_meeting is None

    def test_treasury_stock_filer_property(self):
        """TreasuryStockReport.filer returns Entity if resolvable."""
        report = TreasuryStockReport(
            doc_id='S100ABC123',
            doc_type_code='220',
            filer_edinet_code='E02144',
            filer_name='トヨタ自動車',
        )
        filer = report.filer
        if filer:
            from edinet_tools.entity import Entity
            assert isinstance(filer, Entity)

    def test_parse_treasury_stock_returns_report(self):
        """parse_treasury_stock_report returns TreasuryStockReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '220'

        report = parse_treasury_stock_report(doc)
        assert isinstance(report, TreasuryStockReport)
        assert report.doc_id == 'S100TEST'

    def test_parse_dispatches_doc_220(self):
        """parse() dispatches doc type 220 to TreasuryStockReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST220'
        doc.doc_type_code = '220'

        report = parse(doc)
        assert isinstance(report, TreasuryStockReport)

    def test_parse_dispatches_doc_230(self):
        """parse() dispatches doc type 230 (amendment) to TreasuryStockReport."""
        from unittest.mock import Mock
        doc = Mock()
        doc.doc_id = 'S100TEST230'
        doc.doc_type_code = '230'

        report = parse(doc)
        assert isinstance(report, TreasuryStockReport)

    def test_treasury_stock_to_dict(self):
        """TreasuryStockReport.to_dict exports clean dict."""
        report = TreasuryStockReport(
            doc_id='S100ABC123',
            doc_type_code='220',
            filer_name='Test Corp',
            filing_date=date(2025, 11, 15),
            is_amendment=False,
        )
        d = report.to_dict()
        assert d['doc_id'] == 'S100ABC123'
        assert d['filer_name'] == 'Test Corp'
        assert d['is_amendment'] is False
        assert 'raw_fields' not in d
        assert 'unmapped_fields' not in d


class TestExtractionUtilities:
    """Test extraction.py utility functions."""

    def test_parse_int_basic(self):
        """parse_int handles basic integers."""
        from edinet_tools.parsers.extraction import parse_int
        assert parse_int('12345') == 12345
        assert parse_int(12345) == 12345
        assert parse_int('1,234,567') == 1234567

    def test_parse_int_japanese_formatting(self):
        """parse_int handles Japanese formatting."""
        from edinet_tools.parsers.extraction import parse_int
        assert parse_int('1，234，567') == 1234567  # Fullwidth comma
        assert parse_int('－') is None  # Japanese dash
        assert parse_int('―') is None  # Em dash
        assert parse_int('—') is None  # Horizontal bar

    def test_parse_int_edge_cases(self):
        """parse_int handles edge cases."""
        from edinet_tools.parsers.extraction import parse_int
        assert parse_int(None) is None
        assert parse_int('') is None
        assert parse_int('  ') is None
        assert parse_int('123.45') == 123  # Truncates float

    def test_parse_percentage_basic(self):
        """parse_percentage handles basic percentages."""
        from edinet_tools.parsers.extraction import parse_percentage
        from decimal import Decimal
        assert parse_percentage('0.0567') == Decimal('0.0567')
        assert parse_percentage('5.67%') == Decimal('5.67')

    def test_parse_percentage_edge_cases(self):
        """parse_percentage handles edge cases."""
        from edinet_tools.parsers.extraction import parse_percentage
        assert parse_percentage(None) is None
        assert parse_percentage('') is None
        assert parse_percentage('－') is None
        assert parse_percentage('N/A') is None
        assert parse_percentage('n/a') is None

    def test_parse_date_formats(self):
        """parse_date handles various formats."""
        from edinet_tools.parsers.extraction import parse_date
        from datetime import date
        assert parse_date('2025-01-15') == date(2025, 1, 15)
        assert parse_date('2025/01/15') == date(2025, 1, 15)
        assert parse_date('2025年01月15日') == date(2025, 1, 15)

    def test_parse_date_edge_cases(self):
        """parse_date handles edge cases."""
        from edinet_tools.parsers.extraction import parse_date
        from datetime import date, datetime
        assert parse_date(None) is None
        assert parse_date('') is None
        assert parse_date('－') is None
        assert parse_date(date(2025, 1, 15)) == date(2025, 1, 15)
        assert parse_date(datetime(2025, 1, 15, 10, 30)) == date(2025, 1, 15)

    def test_extract_value_no_context(self):
        """extract_value finds value without context patterns."""
        from edinet_tools.parsers.extraction import extract_value
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'jpdei_cor:EDINETCodeDEI', 'コンテキストID': 'FilingDateInstant', '値': 'E02144'},
                {'要素ID': 'jppfs_cor:Assets', 'コンテキストID': 'CurrentYearInstant', '値': '1000000'},
            ]
        }]
        assert extract_value(csv_files, 'jpdei_cor:EDINETCodeDEI') == 'E02144'
        assert extract_value(csv_files, 'jppfs_cor:Assets') == '1000000'
        assert extract_value(csv_files, 'nonexistent') is None

    def test_extract_value_with_context_patterns(self):
        """extract_value respects context pattern priority."""
        from edinet_tools.parsers.extraction import extract_value
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'jppfs_cor:Assets', 'コンテキストID': 'CurrentYearInstant_NonConsolidatedMember', '値': '500000'},
                {'要素ID': 'jppfs_cor:Assets', 'コンテキストID': 'CurrentYearInstant_ConsolidatedMember', '値': '1000000'},
            ]
        }]
        # Consolidated first
        patterns = ['CurrentYearInstant_ConsolidatedMember', 'CurrentYearInstant_NonConsolidatedMember']
        assert extract_value(csv_files, 'jppfs_cor:Assets', context_patterns=patterns) == '1000000'
        # Non-consolidated first
        patterns = ['CurrentYearInstant_NonConsolidatedMember', 'CurrentYearInstant_ConsolidatedMember']
        assert extract_value(csv_files, 'jppfs_cor:Assets', context_patterns=patterns) == '500000'

    def test_extract_value_exact_context_matching(self):
        """extract_value uses exact context matching, not substring."""
        from edinet_tools.parsers.extraction import extract_value
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'jppfs_cor:NetSales', 'コンテキストID': 'CurrentYearDuration_NonConsolidatedMember', '値': '174000000000'},
            ]
        }]
        # Bare context should NOT match _NonConsolidatedMember (was a bug: substring matching)
        assert extract_value(csv_files, 'jppfs_cor:NetSales', context_patterns=['CurrentYearDuration']) is None
        # Explicit NonConsolidatedMember pattern should match
        assert extract_value(csv_files, 'jppfs_cor:NetSales', context_patterns=['CurrentYearDuration_NonConsolidatedMember']) == '174000000000'

    def test_extract_value_get_last(self):
        """extract_value get_last returns last occurrence."""
        from edinet_tools.parsers.extraction import extract_value
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'elem1', 'コンテキストID': 'ctx1', '値': 'first'},
                {'要素ID': 'elem1', 'コンテキストID': 'ctx2', '値': 'last'},
            ]
        }]
        assert extract_value(csv_files, 'elem1', get_last=False) == 'first'
        assert extract_value(csv_files, 'elem1', get_last=True) == 'last'

    def test_get_context_patterns_consolidated(self):
        """get_context_patterns: consolidated filers use ONLY the bare context.

        Strict invariant: a consolidated filer must never silently fall back to the
        non-consolidated (parent) context for a missing value — borrowing the parent
        is the root cause of IFRS/US-GAAP revenue reading the parent figure. A missing
        consolidated value falls through to the next element/tier (or honest None),
        never to the parent. (Previously this returned a `_NonConsolidatedMember`
        fallback as patterns[1]; that fallback was the bug.)
        """
        from edinet_tools.parsers.extraction import get_context_patterns
        patterns = get_context_patterns(is_consolidated=True, period='CurrentYearDuration')
        assert patterns == ['CurrentYearDuration']  # bare only — no parent fallback

    def test_get_context_patterns_non_consolidated(self):
        """get_context_patterns: _NonConsolidatedMember preferred for non-consolidated."""
        from edinet_tools.parsers.extraction import get_context_patterns
        patterns = get_context_patterns(is_consolidated=False, period='CurrentYearInstant')
        assert patterns[0] == 'CurrentYearInstant_NonConsolidatedMember'
        assert patterns[1] == 'CurrentYearInstant'  # Fallback to bare

    def test_extract_financial_with_ifrs_fallback(self):
        """extract_financial falls back to IFRS elements."""
        from edinet_tools.parsers.extraction import extract_financial
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'jpigp_cor:AssetsIFRS', 'コンテキストID': 'CurrentYearInstant', '値': '2000000'},
            ]
        }]
        ifrs_map = {'jppfs_cor:Assets': 'jpigp_cor:AssetsIFRS'}
        # Primary element not found, falls back to IFRS
        result = extract_financial(csv_files, 'jppfs_cor:Assets', 'CurrentYearInstant', True, ifrs_map)
        assert result == 2000000

    def test_categorize_elements_separates_textblocks(self):
        """categorize_elements properly separates TextBlock elements."""
        from edinet_tools.parsers.extraction import categorize_elements
        csv_files = [{
            'filename': 'test.csv',
            'data': [
                {'要素ID': 'jpcrp_cor:BusinessDescriptionTextBlock', 'コンテキストID': 'ctx1', '値': 'Business text'},
                {'要素ID': 'jppfs_cor:Assets', 'コンテキストID': 'ctx1', '値': '1000000'},
                {'要素ID': 'custom:SomeElement', 'コンテキストID': 'ctx1', '値': 'custom value'},
            ]
        }]
        element_map = {'assets': 'jppfs_cor:Assets'}
        raw, text_blocks, unmapped, raw_facts = categorize_elements(csv_files, element_map)

        # Raw contains everything
        assert 'jpcrp_cor:BusinessDescriptionTextBlock' in raw
        assert 'jppfs_cor:Assets' in raw
        assert 'custom:SomeElement' in raw

        # TextBlocks separated
        assert 'BusinessDescriptionTextBlock' in text_blocks
        assert text_blocks['BusinessDescriptionTextBlock'] == 'Business text'

        # Unmapped excludes mapped and TextBlocks
        assert 'SomeElement' in unmapped
        assert 'BusinessDescriptionTextBlock' not in unmapped
        assert 'Assets' not in unmapped

    def test_extract_csv_from_zip_empty(self):
        """extract_csv_from_zip handles empty/invalid input."""
        from edinet_tools.parsers.extraction import extract_csv_from_zip
        assert extract_csv_from_zip(b'') == []
        assert extract_csv_from_zip(b'not a zip') == []

    def test_extract_csv_from_zip_valid(self):
        """extract_csv_from_zip extracts CSV from valid ZIP."""
        from edinet_tools.parsers.extraction import extract_csv_from_zip
        import io
        import zipfile

        # Create a minimal ZIP with tab-separated CSV content
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            # Create minimal EDINET-style CSV (9 tab-separated columns)
            csv_content = 'elem1\tlabel\tctx1\t0\t連結\t期間\tunit1\t円\t12345'
            zf.writestr('XBRL_TO_CSV/test.csv', csv_content.encode('utf-16le'))
        zip_buffer.seek(0)

        result = extract_csv_from_zip(zip_buffer.read())
        assert len(result) == 1
        assert result[0]['filename'] == 'test.csv'
        assert len(result[0]['data']) == 1
        assert result[0]['data'][0]['要素ID'] == 'elem1'
        assert result[0]['data'][0]['値'] == '12345'
