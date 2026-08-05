"""
Tests for the tender offer family parsers (Doc types 260-340).

Covers routing, basic dataclass structure, and parse function behaviour
for all five new parser modules:
  - TenderOfferWithdrawalReport  (260)
  - TenderOfferResultReport      (270, 280)
  - OpinionReport                (290, 300)
  - QuestionResponseReport       (310, 320)
  - ExemptionApplicationReport   (330, 340)
"""
import io
import zipfile
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, Mock
from edinet_tools.parsers import parse
from edinet_tools.parsers.generic import RawReport
from edinet_tools.parsers.tender_offer_withdrawal import (
    TenderOfferWithdrawalReport,
    parse_tender_offer_withdrawal,
    ELEMENT_MAP as WITHDRAWAL_MAP,
)
from edinet_tools.parsers.tender_offer_report import (
    TenderOfferResultReport,
    parse_tender_offer_report,
    ELEMENT_MAP as REPORT_MAP,
)
from edinet_tools.parsers.opinion_report import (
    OpinionReport,
    parse_opinion_report,
    ELEMENT_MAP as OPINION_MAP,
)
from edinet_tools.parsers.question_response import (
    QuestionResponseReport,
    parse_question_response,
    ELEMENT_MAP as QUESTION_MAP,
)
from edinet_tools.parsers.exemption_application import (
    ExemptionApplicationReport,
    parse_exemption_application,
    ELEMENT_MAP as EXEMPTION_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(doc_type_code: str, doc_id: str = 'TEST_DOC') -> Mock:
    doc = Mock()
    doc.doc_id = doc_id
    doc.doc_type_code = doc_type_code
    doc.filer_name = ''
    doc.filer_edinet_code = ''
    doc.fetch.return_value = b''  # Empty ZIP → empty CSV list
    return doc


def _make_minimal_routing_zip() -> bytes:
    """Build a minimal valid EDINET-shaped ZIP containing a single CSV row.

    Used by the routing test to make parsers walk the real parse body
    (extract_csv_from_zip → field extraction → categorize_elements) rather
    than short-circuiting on the empty-csv_files branch.
    """
    row = 'jpdei_cor:EDINETCodeDEI\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\tE12345'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('XBRL_TO_CSV/test.csv', row.encode('utf-16le'))
    return buf.getvalue()


def _make_routing_doc(code: str) -> MagicMock:
    doc = MagicMock()
    doc.doc_type_code = code
    doc.doc_id = f"TEST_{code}"
    doc.filer_name = ''
    doc.filer_edinet_code = ''
    doc.fetch.return_value = _make_minimal_routing_zip()
    return doc


# ---------------------------------------------------------------------------
# Routing tests — parse() must NOT fall through to RawReport
# ---------------------------------------------------------------------------

DOC_TYPES = ['260', '270', '280', '290', '300', '310', '320', '330', '340']


@pytest.mark.parametrize("code", DOC_TYPES)
def test_tender_offer_family_does_not_fall_through(code):
    """parse() must route to a typed parser, never RawReport, for all new codes."""
    doc = _make_routing_doc(code)
    result = parse(doc)
    assert not isinstance(result, RawReport), (
        f"Doc type {code} fell through to RawReport — add it to the router"
    )
    # The CSV row we fed in has the DEI EDINET code 'E12345' — proves
    # the parse body actually ran rather than short-circuiting on empty input.
    assert result.raw_fields.get('jpdei_cor:EDINETCodeDEI') == 'E12345', (
        f"Doc type {code}: parse body did not consume the input CSV row"
    )


@pytest.mark.parametrize("code", ['260'])
def test_doc_260_routes_to_withdrawal(code):
    doc = _make_mock_doc(code)
    result = parse(doc)
    assert isinstance(result, TenderOfferWithdrawalReport)


@pytest.mark.parametrize("code", ['270', '280'])
def test_doc_270_280_routes_to_result_report(code):
    doc = _make_mock_doc(code)
    result = parse(doc)
    assert isinstance(result, TenderOfferResultReport)


@pytest.mark.parametrize("code", ['290', '300'])
def test_doc_290_300_routes_to_opinion(code):
    doc = _make_mock_doc(code)
    result = parse(doc)
    assert isinstance(result, OpinionReport)


@pytest.mark.parametrize("code", ['310', '320'])
def test_doc_310_320_routes_to_question_response(code):
    doc = _make_mock_doc(code)
    result = parse(doc)
    assert isinstance(result, QuestionResponseReport)


@pytest.mark.parametrize("code", ['330', '340'])
def test_doc_330_340_routes_to_exemption(code):
    doc = _make_mock_doc(code)
    result = parse(doc)
    assert isinstance(result, ExemptionApplicationReport)


# ---------------------------------------------------------------------------
# Dataclass field tests
# ---------------------------------------------------------------------------

class TestTenderOfferWithdrawalReport:
    def test_basic_fields(self):
        report = TenderOfferWithdrawalReport(
            doc_id='TEST',
            doc_type_code='260',
            filer_name='テスト株式会社',
            filer_edinet_code='E12345',
            security_code='1234',
            is_amendment=False,
        )
        assert report.filer_name == 'テスト株式会社'
        assert report.filer_edinet_code == 'E12345'
        assert report.is_amendment is False

    def test_defaults_to_none(self):
        report = TenderOfferWithdrawalReport(doc_id='X', doc_type_code='260')
        assert report.filer_name is None
        assert report.security_code is None
        assert report.is_amendment is False

    def test_repr(self):
        report = TenderOfferWithdrawalReport(
            doc_id='X', doc_type_code='260', filer_name='テスト株式会社'
        )
        assert 'TenderOfferWithdrawalReport' in repr(report)
        assert 'テスト' in repr(report)

    def test_repr_truncates_long_name(self):
        report = TenderOfferWithdrawalReport(
            doc_id='X', doc_type_code='260', filer_name='A' * 50
        )
        assert '...' in repr(report)

    def test_empty_zip_returns_empty_report(self):
        doc = _make_mock_doc('260')
        result = parse_tender_offer_withdrawal(doc)
        assert isinstance(result, TenderOfferWithdrawalReport)
        assert result.filer_name is None
        assert result.source_files == []


class TestTenderOfferResultReport:
    def test_basic_fields(self):
        from decimal import Decimal
        from datetime import date
        report = TenderOfferResultReport(
            doc_id='TEST',
            doc_type_code='270',
            acquirer_name='買付者株式会社',
            target_name='対象会社',
            voting_rights_purchased=100000,
            purchase_ratio=Decimal('0.51'),
            holding_ratio_after=Decimal('0.51'),
            is_amendment=False,
        )
        assert report.acquirer_name == '買付者株式会社'
        assert report.target_name == '対象会社'
        assert report.voting_rights_purchased == 100000
        assert report.purchase_ratio == Decimal('0.51')
        assert report.is_amendment is False

    def test_amendment_flag(self):
        report = TenderOfferResultReport(
            doc_id='TEST', doc_type_code='280', is_amendment=True
        )
        assert report.is_amendment is True
        assert 'AMENDED' in repr(report)

    def test_defaults_to_none(self):
        report = TenderOfferResultReport(doc_id='X', doc_type_code='270')
        assert report.acquirer_name is None
        assert report.target_name is None
        assert report.voting_rights_purchased is None
        assert report.purchase_ratio is None
        assert report.is_amendment is False

    def test_repr(self):
        report = TenderOfferResultReport(
            doc_id='X', doc_type_code='270',
            acquirer_name='買付者', target_name='対象会社'
        )
        r = repr(report)
        assert 'TenderOfferResultReport' in r
        assert '買付者' in r
        assert '対象会社' in r

    def test_empty_zip_returns_empty_report(self):
        doc = _make_mock_doc('270')
        result = parse_tender_offer_report(doc)
        assert isinstance(result, TenderOfferResultReport)
        assert result.acquirer_name is None
        assert result.source_files == []


class TestOpinionReport:
    def test_basic_fields(self):
        report = OpinionReport(
            doc_id='TEST',
            doc_type_code='290',
            filer_name='対象会社株式会社',
            filer_edinet_code='E99999',
            security_code='9999',
            is_amendment=False,
        )
        assert report.filer_name == '対象会社株式会社'
        assert report.filer_edinet_code == 'E99999'
        assert report.is_amendment is False

    def test_amendment(self):
        report = OpinionReport(doc_id='X', doc_type_code='300', is_amendment=True)
        assert report.is_amendment is True
        assert 'AMENDED' in repr(report)

    def test_repr(self):
        report = OpinionReport(
            doc_id='X', doc_type_code='290', filer_name='テスト会社'
        )
        assert 'OpinionReport' in repr(report)
        assert 'テスト会社' in repr(report)

    def test_empty_zip_returns_empty_report(self):
        doc = _make_mock_doc('290')
        result = parse_opinion_report(doc)
        assert isinstance(result, OpinionReport)
        assert result.filer_name is None


class TestQuestionResponseReport:
    def test_basic_fields(self):
        report = QuestionResponseReport(
            doc_id='TEST',
            doc_type_code='310',
            filer_name='回答会社',
            filer_edinet_code='E11111',
            is_amendment=False,
        )
        assert report.filer_name == '回答会社'
        assert report.is_amendment is False

    def test_amendment(self):
        report = QuestionResponseReport(
            doc_id='X', doc_type_code='320', is_amendment=True
        )
        assert report.is_amendment is True
        assert 'AMENDED' in repr(report)

    def test_repr(self):
        report = QuestionResponseReport(
            doc_id='X', doc_type_code='310', filer_name='テスト会社'
        )
        assert 'QuestionResponseReport' in repr(report)

    def test_empty_zip_returns_empty_report(self):
        doc = _make_mock_doc('310')
        result = parse_question_response(doc)
        assert isinstance(result, QuestionResponseReport)
        assert result.filer_name is None


class TestExemptionApplicationReport:
    def test_basic_fields(self):
        report = ExemptionApplicationReport(
            doc_id='TEST',
            doc_type_code='330',
            filer_name='申請会社',
            filer_edinet_code='E22222',
            is_amendment=False,
        )
        assert report.filer_name == '申請会社'
        assert report.is_amendment is False

    def test_amendment(self):
        report = ExemptionApplicationReport(
            doc_id='X', doc_type_code='340', is_amendment=True
        )
        assert report.is_amendment is True
        assert 'AMENDED' in repr(report)

    def test_repr(self):
        report = ExemptionApplicationReport(
            doc_id='X', doc_type_code='330', filer_name='テスト会社'
        )
        assert 'ExemptionApplicationReport' in repr(report)

    def test_empty_zip_returns_empty_report(self):
        doc = _make_mock_doc('330')
        result = parse_exemption_application(doc)
        assert isinstance(result, ExemptionApplicationReport)
        assert result.filer_name is None


# ---------------------------------------------------------------------------
# ELEMENT_MAP sanity checks
# ---------------------------------------------------------------------------

class TestElementMaps:
    """All ELEMENT_MAPs must have DEI baseline and namespaced values."""

    @pytest.mark.parametrize("element_map,label", [
        (WITHDRAWAL_MAP, 'TenderOfferWithdrawal'),
        (REPORT_MAP, 'TenderOfferResult'),
        (OPINION_MAP, 'Opinion'),
        (QUESTION_MAP, 'QuestionResponse'),
        (EXEMPTION_MAP, 'ExemptionApplication'),
    ])
    def test_has_dei_baseline(self, element_map, label):
        for key in ('filer_name', 'filer_edinet_code', 'amendment_flag'):
            assert key in element_map, f"{label}: missing key '{key}'"

    @pytest.mark.parametrize("element_map,label", [
        (WITHDRAWAL_MAP, 'TenderOfferWithdrawal'),
        (REPORT_MAP, 'TenderOfferResult'),
        (OPINION_MAP, 'Opinion'),
        (QUESTION_MAP, 'QuestionResponse'),
        (EXEMPTION_MAP, 'ExemptionApplication'),
    ])
    def test_values_are_namespaced(self, element_map, label):
        for key, elem_id in element_map.items():
            assert ':' in elem_id, (
                f"{label}: element '{key}' missing namespace prefix: {elem_id}"
            )

    @pytest.mark.parametrize("element_map,label", [
        (WITHDRAWAL_MAP, 'TenderOfferWithdrawal'),
        (OPINION_MAP, 'Opinion'),
        (QUESTION_MAP, 'QuestionResponse'),
        (EXEMPTION_MAP, 'ExemptionApplication'),
    ])
    def test_dei_keys_use_dei_namespace(self, element_map, label):
        for key in ('filer_name', 'filer_edinet_code', 'security_code', 'amendment_flag'):
            if key in element_map:
                assert element_map[key].startswith('jpdei_cor:'), (
                    f"{label}: '{key}' should use jpdei_cor namespace"
                )


# ---------------------------------------------------------------------------
# to_dict and inherited base behaviour
# ---------------------------------------------------------------------------

class TestBaseInheritance:
    def test_to_dict_excludes_raw_fields(self):
        report = OpinionReport(
            doc_id='X',
            doc_type_code='290',
            filer_name='テスト',
            raw_fields={'k': 'v'},
            unmapped_fields={'u': 'v'},
        )
        d = report.to_dict()
        assert d['filer_name'] == 'テスト'
        assert 'raw_fields' not in d
        assert 'unmapped_fields' not in d

    def test_fields_returns_list(self):
        report = TenderOfferResultReport(doc_id='X', doc_type_code='270')
        f = report.fields()
        assert isinstance(f, list)
        assert 'acquirer_name' in f
        assert 'target_name' in f
        assert 'voting_rights_purchased' in f


# ---------------------------------------------------------------------------
# Field-level extraction helpers (shared)
# ---------------------------------------------------------------------------

def _make_csv_row(element_id: str, context_id: str, value: str) -> str:
    """Return one tab-separated CSV line in EDINET format (9 columns)."""
    return f"{element_id}\tlabel\t{context_id}\t0\t連結\t期間\t\t\t{value}"


def _make_zip(rows: list[str]) -> bytes:
    content = '\n'.join(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('XBRL_TO_CSV/test.csv', content.encode('utf-16le'))
    return buf.getvalue()


def _make_family_doc(doc_id: str = 'S100TEST', doc_type: str = '270', rows: list[str] | None = None):
    doc = Mock()
    doc.doc_id = doc_id
    doc.doc_type_code = doc_type
    doc.filer_name = ''
    doc.filer_edinet_code = ''
    doc.fetch.return_value = _make_zip(rows) if rows is not None else b''
    return doc


# ---------------------------------------------------------------------------
# TenderOfferResultReport (270/280) — field-level extraction tests
# ---------------------------------------------------------------------------

class TestParseTenderOfferResultReport:
    """Prove ELEMENT_MAP extracts correctly from mock XBRL CSV for Doc 270/280."""

    def test_empty_zip_returns_empty_report(self):
        doc = _make_family_doc(doc_type='270', rows=None)
        result = parse_tender_offer_report(doc)
        assert isinstance(result, TenderOfferResultReport)
        assert result.acquirer_name is None
        assert result.source_files == []

    def test_extracts_acquirer_name(self):
        rows = [
            _make_csv_row(REPORT_MAP['acquirer_name'], 'FilingDateInstant', 'KDDI株式会社'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.acquirer_name == 'KDDI株式会社'

    def test_acquirer_falls_back_to_dei_filer_name(self):
        """If cover page acquirer_name absent, falls back to DEI filer_name."""
        rows = [
            _make_csv_row(REPORT_MAP['filer_name'], 'FilingDateInstant', 'フォールバック株式会社'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.acquirer_name == 'フォールバック株式会社'

    def test_extracts_holding_ratio_after(self):
        rows = [
            _make_csv_row(REPORT_MAP['holding_ratio_after'], 'FilingDateInstant', '0.9876'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.holding_ratio_after == Decimal('0.9876')

    def test_purchase_ratio_stays_none_no_backing_element(self):
        """purchase_ratio was retired (v0.8.0 stage-5 Task 10): a full-namespace
        census found no numeric ratio-of-shares-purchased element in any real
        results filing. It must stay None even when an unrelated ratio row is
        present -- proving the field is never populated, not merely untested."""
        rows = [
            _make_csv_row('jptoo-tor_cor:RatioOfNumberOfVotingRightsRepresentedByShareCertificatesEtcPurchasedAmongNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompany',
                          'FilingDateInstant', '0.4784'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.purchase_ratio is None

    def test_extracts_filing_date(self):
        rows = [
            _make_csv_row(REPORT_MAP['filing_date'], 'FilingDateInstant', '2024-05-20'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.filing_date == date(2024, 5, 20)

    def test_result_text_block_captured(self):
        rows = [
            _make_csv_row(REPORT_MAP['result_text'], 'FilingDateInstant', '公開買付けは成立しました。'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        # The result_text field should be populated directly
        assert report.result_text == '公開買付けは成立しました。'
        # TextBlock elements are also captured in text_blocks dict
        assert 'SuccessOrFailureOfTenderOfferTextBlock' in report.text_blocks

    def test_amendment_flag_true(self):
        rows = [
            _make_csv_row(REPORT_MAP['amendment_flag'], 'FilingDateInstant', 'true'),
        ]
        doc = _make_family_doc(doc_type='280', rows=rows)
        report = parse_tender_offer_report(doc)
        assert report.is_amendment is True

    def test_amendment_flag_false(self):
        rows = [
            _make_csv_row(REPORT_MAP['amendment_flag'], 'FilingDateInstant', 'false'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.is_amendment is False

    def test_none_ratios_when_missing(self):
        doc = _make_family_doc(rows=[])
        report = parse_tender_offer_report(doc)
        assert report.holding_ratio_after is None
        assert report.purchase_ratio is None
        assert report.voting_rights_purchased is None

    def test_multiple_fields_extracted_together(self):
        rows = [
            _make_csv_row(REPORT_MAP['acquirer_name'], 'FilingDateInstant', 'テスト買付者株式会社'),
            _make_csv_row(REPORT_MAP['holding_ratio_after'], 'FilingDateInstant', '1.0000'),
            _make_csv_row(REPORT_MAP['filing_date'], 'FilingDateInstant', '2024-06-01'),
            _make_csv_row(REPORT_MAP['filer_edinet_code'], 'FilingDateInstant', 'E07777'),
        ]
        report = parse_tender_offer_report(_make_family_doc(rows=rows))
        assert report.acquirer_name == 'テスト買付者株式会社'
        assert report.holding_ratio_after == Decimal('1.0000')
        assert report.filing_date == date(2024, 6, 1)
        assert report.acquirer_edinet_code == 'E07777'


# ---------------------------------------------------------------------------
# OpinionReport (290/300) — field-level extraction tests
# ---------------------------------------------------------------------------

class TestParseOpinionReport:
    """Prove ELEMENT_MAP extracts correctly from mock XBRL CSV for Doc 290/300."""

    def test_empty_zip_returns_empty_report(self):
        doc = _make_family_doc(doc_type='290', rows=None)
        result = parse_opinion_report(doc)
        assert isinstance(result, OpinionReport)
        assert result.target_company_name is None
        assert result.source_files == []

    def test_extracts_target_company_name(self):
        rows = [
            _make_csv_row(OPINION_MAP['target_company_name'], 'FilingDateInstant', '株式会社ローソン'),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.target_company_name == '株式会社ローソン'

    def test_target_company_name_falls_back_to_dei_filer_name(self):
        rows = [
            _make_csv_row(OPINION_MAP['filer_name'], 'FilingDateInstant', 'フォールバック対象会社'),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.target_company_name == 'フォールバック対象会社'

    def test_opinion_text_block_captured(self):
        rows = [
            _make_csv_row(
                OPINION_MAP['opinion_text'],
                'FilingDateInstant',
                '本公開買付けに賛同する意見を表明いたします。',
            ),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.opinion_text == '本公開買付けに賛同する意見を表明いたします。'
        # TextBlock elements are also captured in text_blocks
        assert 'OpinionAndBasisAndReasonOfOpinionRegardingSaidTenderOfferTextBlock' in report.text_blocks

    def test_extracts_filing_date(self):
        rows = [
            _make_csv_row(OPINION_MAP['filing_date'], 'FilingDateInstant', '2024-04-10'),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.filing_date == date(2024, 4, 10)

    def test_extracts_filer_edinet_code(self):
        rows = [
            _make_csv_row(OPINION_MAP['filer_edinet_code'], 'FilingDateInstant', 'E08888'),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.filer_edinet_code == 'E08888'

    def test_amendment_flag_true(self):
        rows = [
            _make_csv_row(OPINION_MAP['amendment_flag'], 'FilingDateInstant', 'true'),
        ]
        doc = _make_family_doc(doc_type='300', rows=rows)
        report = parse_opinion_report(doc)
        assert report.is_amendment is True

    def test_amendment_flag_false(self):
        rows = [
            _make_csv_row(OPINION_MAP['amendment_flag'], 'FilingDateInstant', 'false'),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.is_amendment is False

    def test_multiple_fields_extracted_together(self):
        rows = [
            _make_csv_row(OPINION_MAP['target_company_name'], 'FilingDateInstant', 'テスト対象会社'),
            _make_csv_row(OPINION_MAP['filing_date'], 'FilingDateInstant', '2024-04-05'),
            _make_csv_row(OPINION_MAP['filer_edinet_code'], 'FilingDateInstant', 'E09876'),
            _make_csv_row(
                OPINION_MAP['opinion_text'],
                'FilingDateInstant',
                '賛同の意見を表明いたします。',
            ),
        ]
        report = parse_opinion_report(_make_family_doc(doc_type='290', rows=rows))
        assert report.target_company_name == 'テスト対象会社'
        assert report.filing_date == date(2024, 4, 5)
        assert report.filer_edinet_code == 'E09876'
        assert '賛同' in report.opinion_text
