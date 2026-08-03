"""Unit tests for debt field extraction from Securities Reports."""
import pytest
from unittest.mock import Mock, patch
from edinet_tools.parsers.securities import SecuritiesReport, parse_securities_report


class TestDebtFieldExtraction:
    """Test extraction of debt-related fields from securities reports."""

    def test_debt_fields_exist_on_securities_report(self):
        """SecuritiesReport has all debt-related fields."""
        report = SecuritiesReport(
            doc_id='S100TEST',
            doc_type_code='120',
        )

        # Verify all debt fields exist
        assert hasattr(report, 'short_term_loans_payable')
        assert hasattr(report, 'long_term_loans_payable')
        assert hasattr(report, 'bonds_payable')
        assert hasattr(report, 'current_portion_long_term_loans_payable')
        assert hasattr(report, 'lease_obligations_current')
        assert hasattr(report, 'lease_obligations_noncurrent')
        assert hasattr(report, 'commercial_paper')

    def test_debt_fields_in_to_dict(self):
        """Debt fields are included in to_dict() export."""
        report = SecuritiesReport(
            doc_id='S100TEST',
            doc_type_code='120',
            short_term_loans_payable=1_000_000_000,
            long_term_loans_payable=5_000_000_000,
            bonds_payable=2_000_000_000,
        )

        data = report.to_dict()
        assert data['short_term_loans_payable'] == 1_000_000_000
        assert data['long_term_loans_payable'] == 5_000_000_000
        assert data['bonds_payable'] == 2_000_000_000

    def test_debt_fields_default_to_none(self):
        """Debt fields default to None when not provided."""
        report = SecuritiesReport(
            doc_id='S100TEST',
            doc_type_code='120',
        )

        assert report.short_term_loans_payable is None
        assert report.long_term_loans_payable is None
        assert report.bonds_payable is None
        assert report.current_portion_long_term_loans_payable is None
        assert report.lease_obligations_current is None
        assert report.lease_obligations_noncurrent is None
        assert report.commercial_paper is None

    def test_parse_securities_report_extracts_debt_fields_end_to_end(self):
        """Sister of the mocked test below — runs through the REAL UTF-16 ZIP
        decode path so a divergence in extract_csv_from_zip's output shape
        (column keys, encoding handling) would surface here. Closes the gap
        called out in the 2026-05-22 false-confidence audit (Category C, LOW)."""
        import io, zipfile
        cols = ['要素ID', '項目名', 'コンテキストID', '相対年度',
                '連結・個別', '期間・時点', 'ユニットID', '単位', '値']
        rows = [
            ('jppfs_cor:ShortTermLoansPayable', '短期借入金', 'CurrentYearInstant',
             '', '', '', '', 'JPY', '1000000000'),
            ('jppfs_cor:LongTermLoansPayable', '長期借入金', 'CurrentYearInstant',
             '', '', '', '', 'JPY', '5000000000'),
            ('jppfs_cor:BondsPayable', '社債', 'CurrentYearInstant',
             '', '', '', '', 'JPY', '2000000000'),
            ('jpdei_cor:EDINETCodeDEI', 'EDINETコード', 'FilingDateInstant',
             '', '', '', '', '', 'E12345'),
        ]
        csv_body = '\t'.join(cols) + '\n' + '\n'.join('\t'.join(r) for r in rows) + '\n'
        # EDINET ships CSVs as UTF-16-LE with BOM — exercise the real decode path.
        encoded = b'\xff\xfe' + csv_body.encode('utf-16-le')
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr('XBRL_TO_CSV/jpcrp030000-asr_debt_test.csv', encoded)

        mock_doc = Mock()
        mock_doc.doc_id = 'S100REAL'
        mock_doc.doc_type_code = '120'
        mock_doc.fetch.return_value = zip_buf.getvalue()

        # NO patch — runs through extract_csv_from_zip + decode + parser end-to-end.
        report = parse_securities_report(mock_doc)
        assert report.short_term_loans_payable == 1_000_000_000
        assert report.long_term_loans_payable == 5_000_000_000
        assert report.bonds_payable == 2_000_000_000
        assert report.raw_fields.get('jpdei_cor:EDINETCodeDEI') == 'E12345'

    def test_parse_securities_report_extracts_debt_fields(self):
        """parse_securities_report() extracts debt fields from CSV data."""
        # Mock CSV data with debt elements
        mock_csv_files = [
            {
                'filename': 'test.csv',
                'data': [
                    {
                        '要素ID': 'jppfs_cor:ShortTermLoansPayable',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '1000000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:LongTermLoansPayable',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '5000000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:BondsPayable',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '2000000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:CurrentPortionOfLongTermLoansPayable',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '500000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:CommercialPaper',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '300000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:LeaseObligationsCL',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '100000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jppfs_cor:LeaseObligationsNCL',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '200000000',
                        '単位': 'JPY',
                    },
                    # Add some basic identification fields
                    {
                        '要素ID': 'jpdei_cor:EDINETCodeDEI',
                        'コンテキストID': 'FilingDateInstant',
                        '値': 'E12345',
                        '単位': None,
                    },
                    {
                        '要素ID': 'jpdei_cor:SecurityCodeDEI',
                        'コンテキストID': 'FilingDateInstant',
                        '値': '1234',
                        '単位': None,
                    },
                ]
            }
        ]

        # Mock document object
        mock_doc = Mock()
        mock_doc.doc_id = 'S100TEST'
        mock_doc.doc_type_code = '120'
        mock_doc.fetch.return_value = b'fake_zip_data'

        with patch('edinet_tools.parsers.securities.extract_csv_from_zip', return_value=mock_csv_files):
            report = parse_securities_report(mock_doc)

        # Verify debt fields were extracted
        assert report.short_term_loans_payable == 1_000_000_000
        assert report.long_term_loans_payable == 5_000_000_000
        assert report.bonds_payable == 2_000_000_000
        assert report.current_portion_long_term_loans_payable == 500_000_000
        assert report.commercial_paper == 300_000_000
        assert report.lease_obligations_current == 100_000_000
        assert report.lease_obligations_noncurrent == 200_000_000

    def test_parse_securities_report_handles_missing_debt_fields(self):
        """parse_securities_report() handles missing debt fields gracefully."""
        # Mock CSV data without debt elements
        mock_csv_files = [
            {
                'filename': 'test.csv',
                'data': [
                    {
                        '要素ID': 'jpdei_cor:EDINETCodeDEI',
                        'コンテキストID': 'FilingDateInstant',
                        '値': 'E12345',
                        '単位': None,
                    },
                ]
            }
        ]

        # Mock document object
        mock_doc = Mock()
        mock_doc.doc_id = 'S100TEST'
        mock_doc.doc_type_code = '120'
        mock_doc.fetch.return_value = b'fake_zip_data'

        with patch('edinet_tools.parsers.securities.extract_csv_from_zip', return_value=mock_csv_files):
            report = parse_securities_report(mock_doc)

        # Verify debt fields are None when not present
        assert report.short_term_loans_payable is None
        assert report.long_term_loans_payable is None
        assert report.bonds_payable is None

    def test_total_debt_calculation(self):
        """Test calculating total debt from individual components."""
        report = SecuritiesReport(
            doc_id='S100TEST',
            doc_type_code='120',
            short_term_loans_payable=1_000_000_000,
            long_term_loans_payable=5_000_000_000,
            bonds_payable=2_000_000_000,
            current_portion_long_term_loans_payable=500_000_000,
            commercial_paper=300_000_000,
        )

        # Calculate total financial debt (excluding lease obligations)
        total_debt = sum(filter(None, [
            report.short_term_loans_payable,
            report.long_term_loans_payable,
            report.bonds_payable,
            report.current_portion_long_term_loans_payable,
            report.commercial_paper,
        ]))

        assert total_debt == 8_800_000_000

    def test_debt_to_equity_ratio_calculation(self):
        """Test D/E ratio calculation with extracted debt fields."""
        report = SecuritiesReport(
            doc_id='S100TEST',
            doc_type_code='120',
            short_term_loans_payable=1_000_000_000,
            long_term_loans_payable=5_000_000_000,
            bonds_payable=2_000_000_000,
            net_assets_total=10_000_000_000,
        )

        total_debt = sum(filter(None, [
            report.short_term_loans_payable,
            report.long_term_loans_payable,
            report.bonds_payable,
        ]))

        de_ratio = (total_debt / report.net_assets_total) * 100 if report.net_assets_total else None

        assert de_ratio is not None
        assert de_ratio == 80.0  # 8B debt / 10B equity = 80%

    def test_ifrs_debt_fields_extraction(self):
        """Test extraction of debt fields from IFRS reports."""
        # Mock CSV data with IFRS debt elements
        mock_csv_files = [
            {
                'filename': 'test.csv',
                'data': [
                    {
                        '要素ID': 'jpigp_cor:ShortTermBorrowingsIFRS',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '1500000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jpigp_cor:LongTermBorrowingsIFRS',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '6000000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jpigp_cor:BondsPayableIFRS',
                        'コンテキストID': 'CurrentYearInstant',
                        '値': '2500000000',
                        '単位': 'JPY',
                    },
                    {
                        '要素ID': 'jpdei_cor:EDINETCodeDEI',
                        'コンテキストID': 'FilingDateInstant',
                        '値': 'E12345',
                        '単位': None,
                    },
                ]
            }
        ]

        # Mock document object
        mock_doc = Mock()
        mock_doc.doc_id = 'S100TEST'
        mock_doc.doc_type_code = '120'
        mock_doc.fetch.return_value = b'fake_zip_data'

        with patch('edinet_tools.parsers.securities.extract_csv_from_zip', return_value=mock_csv_files):
            report = parse_securities_report(mock_doc)

        # Verify IFRS debt fields were extracted using fallback mapping
        assert report.short_term_loans_payable == 1_500_000_000
        assert report.long_term_loans_payable == 6_000_000_000
        assert report.bonds_payable == 2_500_000_000
