"""Tests for TenderOfferReport parser (Doc 240/250)."""
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from edinet_tools.parsers import parse
from edinet_tools.parsers.tender_offer import (
    TenderOfferReport,
    parse_tender_offer,
    ELEMENT_MAP,
)
from edinet_tools.parsers.extraction import extract_csv_from_zip


class TestTenderOfferReportStructure:
    """Test TenderOfferReport dataclass."""

    def test_basic_fields(self):
        report = TenderOfferReport(
            doc_id='S100V55A',
            doc_type_code='240',
            acquirer_name='KDDI株式会社',
            acquirer_name_en='KDDI CORPORATION',
            acquirer_edinet_code='E04425',
            target_name='株式会社ローソン',
            filing_date=date(2024, 3, 28),
            voting_rights_to_purchase=479238,
            purchase_ratio=Decimal('0.4784'),
            holding_ratio_after=Decimal('1.0000'),
            is_amendment=False,
        )
        assert report.acquirer_name == 'KDDI株式会社'
        assert report.target_name == '株式会社ローソン'
        assert report.voting_rights_to_purchase == 479238
        assert report.purchase_ratio == Decimal('0.4784')
        assert report.holding_ratio_after == Decimal('1.0000')
        assert report.is_amendment is False

    def test_optional_fields_default_none(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
        )
        assert report.acquirer_name is None
        assert report.target_name is None
        assert report.voting_rights_to_purchase is None
        assert report.purchase_ratio is None
        assert report.purpose_text is None
        assert report.is_amendment is False

    def test_amendment_flag(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='250',
            acquirer_name='Test Corp',
            is_amendment=True,
        )
        assert report.is_amendment is True
        assert report.doc_type_code == '250'

    def test_repr_normal(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
            acquirer_name='KDDI株式会社',
            target_name='株式会社ローソン',
        )
        r = repr(report)
        assert 'KDDI' in r
        assert 'ローソン' in r
        assert 'AMENDED' not in r

    def test_repr_amendment(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='250',
            acquirer_name='Test',
            is_amendment=True,
        )
        assert 'AMENDED' in repr(report)

    def test_repr_truncates_long_names(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
            acquirer_name='A' * 50,
            target_name='B' * 50,
        )
        r = repr(report)
        assert '...' in r
        assert len(r) < 200

    def test_to_dict_excludes_raw_fields(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
            acquirer_name='Test Corp',
            raw_fields={'key': 'val'},
            unmapped_fields={'other': 'val'},
        )
        d = report.to_dict()
        assert d['acquirer_name'] == 'Test Corp'
        assert 'raw_fields' not in d
        assert 'unmapped_fields' not in d

    def test_acquirer_property_resolves_entity(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
            acquirer_edinet_code='E02144',  # Toyota
        )
        acquirer = report.acquirer
        if acquirer:
            from edinet_tools.entity import Entity
            assert isinstance(acquirer, Entity)

    def test_acquirer_property_none_without_code(self):
        report = TenderOfferReport(
            doc_id='S100TEST',
            doc_type_code='240',
        )
        assert report.acquirer is None


class TestParseDispatchTenderOffer:
    """Test parse() dispatches to tender offer parser."""

    def test_dispatches_doc_240(self):
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '240'
        report = parse(doc)
        assert isinstance(report, TenderOfferReport)

    def test_dispatches_doc_250(self):
        doc = Mock()
        doc.doc_id = 'S100TEST'
        doc.doc_type_code = '250'
        report = parse(doc)
        assert isinstance(report, TenderOfferReport)


class TestParseTenderOffer:
    """Test parse_tender_offer with mocked document data."""

    def _make_csv_row(self, element_id, context_id, value):
        return {
            '要素ID': element_id,
            'コンテキストID': context_id,
            '値': value,
        }

    def _make_zip_with_rows(self, rows):
        """Create a ZIP containing a CSV with the given rows."""
        import io
        import zipfile

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            lines = []
            for row in rows:
                # 9 tab-separated columns matching EDINET CSV format
                line = f"{row['要素ID']}\tlabel\t{row['コンテキストID']}\t0\t連結\t期間\tunit1\t円\t{row['値']}"
                lines.append(line)
            content = '\n'.join(lines)
            zf.writestr('XBRL_TO_CSV/test.csv', content.encode('utf-16le'))
        return zip_buffer.getvalue()

    def _make_doc(self, doc_id='S100TEST', doc_type='240', rows=None):
        doc = Mock()
        doc.doc_id = doc_id
        doc.doc_type_code = doc_type
        doc.filer_name = ''
        doc.filer_edinet_code = ''
        if rows is not None:
            doc.fetch.return_value = self._make_zip_with_rows(rows)
        else:
            doc.fetch.return_value = b''
        return doc

    def test_empty_zip_returns_empty_report(self):
        doc = self._make_doc(rows=None)
        report = parse_tender_offer(doc)
        assert isinstance(report, TenderOfferReport)
        assert report.doc_id == 'S100TEST'
        assert report.acquirer_name is None
        assert report.source_files == []

    def test_extracts_acquirer_from_cover_page(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['acquirer_name'],
                'FilingDateInstant',
                'KDDI株式会社',
            ),
            self._make_csv_row(
                ELEMENT_MAP['filer_name_en'],
                'FilingDateInstant',
                'KDDI CORPORATION',
            ),
            self._make_csv_row(
                ELEMENT_MAP['edinet_code'],
                'FilingDateInstant',
                'E04425',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.acquirer_name == 'KDDI株式会社'
        assert report.acquirer_name_en == 'KDDI CORPORATION'
        assert report.acquirer_edinet_code == 'E04425'

    def test_acquirer_falls_back_to_dei_filer_name(self):
        """If cover page acquirer_name missing, falls back to DEI filer_name."""
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['filer_name'],
                'FilingDateInstant',
                'テスト株式会社',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.acquirer_name == 'テスト株式会社'

    def test_acquirer_falls_back_to_document_filer(self):
        """If no XBRL acquirer data, falls back to document.filer_name."""
        # Need at least one non-acquirer row so CSV is readable
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['target_name'],
                'FilingDateInstant',
                '対象会社',
            ),
        ]
        doc = self._make_doc(rows=rows)
        doc.filer_name = 'Document Filer Corp'
        report = parse_tender_offer(doc)
        assert report.acquirer_name == 'Document Filer Corp'

    def test_extracts_filing_date(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['filing_date'],
                'FilingDateInstant',
                '2024-03-28',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.filing_date == date(2024, 3, 28)

    def test_extracts_voting_rights_and_ratios(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['voting_rights_to_purchase'],
                'FilingDateInstant',
                '479238',
            ),
            self._make_csv_row(
                ELEMENT_MAP['purchase_ratio'],
                'FilingDateInstant',
                '0.4784',
            ),
            self._make_csv_row(
                ELEMENT_MAP['holding_ratio_after'],
                'FilingDateInstant',
                '1.0000',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.voting_rights_to_purchase == 479238
        assert report.purchase_ratio == Decimal('0.4784')
        assert report.holding_ratio_after == Decimal('1.0000')

    def test_amendment_flag_true(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['amendment_flag'],
                'FilingDateInstant',
                'true',
            ),
        ]
        doc = self._make_doc(doc_type='250', rows=rows)
        report = parse_tender_offer(doc)
        assert report.is_amendment is True

    def test_amendment_flag_false(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['amendment_flag'],
                'FilingDateInstant',
                'false',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.is_amendment is False

    def test_extracts_text_blocks(self):
        rows = [
            self._make_csv_row(
                ELEMENT_MAP['target_name'],
                'FilingDateInstant',
                '株式会社ローソン',
            ),
            self._make_csv_row(
                ELEMENT_MAP['purpose_text'],
                'FilingDateInstant',
                '本公開買付けの目的は...',
            ),
            self._make_csv_row(
                ELEMENT_MAP['price_text'],
                'FilingDateInstant',
                '普通株式１株につき金10,360円',
            ),
            self._make_csv_row(
                ELEMENT_MAP['period_text'],
                'FilingDateInstant',
                '2024年３月28日から2024年５月13日まで',
            ),
        ]
        doc = self._make_doc(rows=rows)
        report = parse_tender_offer(doc)
        assert report.target_name == '株式会社ローソン'
        assert '目的' in report.purpose_text
        assert '10,360' in report.price_text
        assert '2024' in report.period_text

    def test_none_voting_rights_when_missing(self):
        """Missing numeric fields return None, not 0."""
        doc = self._make_doc(rows=[])
        report = parse_tender_offer(doc)
        assert report.voting_rights_to_purchase is None
        assert report.purchase_ratio is None
        assert report.holding_ratio_after is None


class TestElementMap:
    """Test ELEMENT_MAP completeness and correctness."""

    def test_element_map_has_required_keys(self):
        required = [
            'edinet_code', 'filer_name', 'filing_date',
            'acquirer_name', 'target_name',
            'voting_rights_to_purchase', 'purchase_ratio', 'holding_ratio_after',
            'purpose_text', 'price_text', 'period_text',
        ]
        for key in required:
            assert key in ELEMENT_MAP, f"Missing required key: {key}"

    def test_element_map_values_are_namespaced(self):
        """All element IDs should have a namespace prefix."""
        for key, elem_id in ELEMENT_MAP.items():
            assert ':' in elem_id, f"Element {key} missing namespace: {elem_id}"

    def test_tender_offer_namespace(self):
        """Tender-offer-specific elements use jptoo-ton_cor namespace."""
        tender_keys = [
            'acquirer_name', 'target_name', 'voting_rights_to_purchase',
            'purchase_ratio', 'purpose_text', 'price_text',
        ]
        for key in tender_keys:
            assert ELEMENT_MAP[key].startswith('jptoo-ton_cor:'), \
                f"{key} should use jptoo-ton_cor namespace"

    def test_dei_elements_use_dei_namespace(self):
        """DEI elements use jpdei_cor namespace."""
        dei_keys = ['edinet_code', 'filer_name', 'filer_name_en',
                    'security_code', 'amendment_flag']
        for key in dei_keys:
            assert ELEMENT_MAP[key].startswith('jpdei_cor:'), \
                f"{key} should use jpdei_cor namespace"


class TestTargetNameLabelStrip:
    # Both real label shapes observed in EDINET tender-offer CSVs:
    # registrations lead with '１【対象者名】', results with '（１）【対象者名】'
    def test_strips_numbered_label(self):
        from edinet_tools.parsers.extraction import strip_form_label
        assert strip_form_label('１【対象者名】株式会社サンプル') == '株式会社サンプル'

    def test_strips_parenthesized_label(self):
        from edinet_tools.parsers.extraction import strip_form_label
        assert strip_form_label('（１）【対象者名】サンプル工業株式会社') == 'サンプル工業株式会社'

    def test_unlabeled_name_unchanged(self):
        from edinet_tools.parsers.extraction import strip_form_label
        assert strip_form_label('株式会社サンプル') == '株式会社サンプル'

    def test_none_passes_through(self):
        from edinet_tools.parsers.extraction import strip_form_label
        assert strip_form_label(None) is None

    def test_idempotent(self):
        from edinet_tools.parsers.extraction import strip_form_label
        once = strip_form_label('１【対象者名】株式会社サンプル')
        assert strip_form_label(once) == once
