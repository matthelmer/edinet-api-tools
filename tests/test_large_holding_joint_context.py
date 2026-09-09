"""Joint Doc 350 filings: the group total lives in the bare `FilingDateInstant`
context; each co-reporter's own figures live under `...FilerLargeVolumeHolder<N>Member`
(and, on some filings, a second axis `...JointHolder<N>Member`).

Before 0.8.4 the parser selected by document position: `ownership_pct` and
`shares_held` took the LAST match (which happened to be the total),
`prior_ownership_pct` took the FIRST match (holder 1's own prior). A group
total minus one holder's prior is not a change. Measured on prod 2026-09-09:
375 of 400 sampled joint filings since 2024 stored a prior that disagreed with
the filed total-context prior (mean gap 8.1 pts); the second axis was invisible
to `_detect_joint_filing` on ~3% of filings flagged single-filer.
"""
from decimal import Decimal

from edinet_tools.parsers.large_holding import parse_large_holding
from tests.conftest import load_fixture
from tests.test_parser_extraction import make_csv_row


def _files(rows):
    return [{'filename': 'x.csv', 'data': [make_csv_row(*r) for r in rows]}]


H1 = 'FilingDateInstant_jplvh010000-lvh_E99999-000FilerLargeVolumeHolder1Member'
H2 = 'FilingDateInstant_jplvh010000-lvh_E99999-000FilerLargeVolumeHolder2Member'
J1 = 'FilingDateInstant_jplvh010000-lvh_E99999-000JointHolder1Member'
TOTAL = 'FilingDateInstant'
RATIO = 'jplvh_cor:HoldingRatioOfShareCertificatesEtc'
PRIOR = 'jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport'
SHARES = 'jplvh_cor:TotalNumberOfStocksEtcHeld'
PROPOSAL = 'jplvh_cor:ActOfMakingImportantProposalEtc'


class TestRealFilings:
    def test_hikari_4491_change_report_no19_reads_group_totals(self):
        """S100YZFS (2026-09-03): 光通信 + ＵＨ Partners on コンピューターマネージメント.
        Holder 1 own: 0.0670 (prior 0.0670); group: 0.1309 (prior 0.1409) — a SELL.
        The old parser stored prior 0.0670 and called it +6.4 pts."""
        r = parse_large_holding(csv_files=load_fixture('large_holding', 'hikari_4491_joint_2026'),
                                doc_id='S100YZFS', doc_type_code='350')
        assert r.is_joint_filing is True
        assert r.joint_holder_count == 2
        assert r.ownership_pct == Decimal('0.1309')
        assert r.prior_ownership_pct == Decimal('0.1409')
        assert r.ownership_change == Decimal('-0.0100')
        assert r.shares_held == 266800
        assert r.joint_holders[0].name_jp == '光通信株式会社'
        assert r.filer_name == '光通信株式会社'

    def test_mitsubishi_2597_jointholder_axis_is_a_joint_filing(self):
        """S100SKDY: 三菱商事 (Holder1, 9.50%) + UCCジャパン (JointHolder1, 50.53%)
        + UCC Capital (JointHolder2, 0%) on ユニカフェ; group 60.04%.
        The old parser flagged it single-filer with prior 0.095 vs group prior 0.6004."""
        r = parse_large_holding(csv_files=load_fixture('large_holding', 'mitsubishi_2597_jointholder_axis'),
                                doc_id='S100SKDY', doc_type_code='350')
        assert r.is_joint_filing is True
        assert r.joint_holder_count == 3
        assert r.ownership_pct == Decimal('0.6004')
        assert r.prior_ownership_pct == Decimal('0.6004')
        assert r.shares_held == 8326700
        names = [h.name_jp for h in r.joint_holders]
        assert names == ['三菱商事株式会社', 'UCCジャパン株式会社', 'UCC Capital株式会社']
        assert [h.holder_number for h in r.joint_holders] == [1, 2, 3]


class TestContextSelection:
    def test_total_context_wins_regardless_of_document_order(self):
        rows = [
            (RATIO, TOTAL, '0.2000'), (PRIOR, TOTAL, '0.1500'), (SHARES, TOTAL, '2000'),
            (RATIO, H1, '0.1200'), (PRIOR, H1, '0.0100'), (SHARES, H1, '1200'),
            (RATIO, H2, '0.0800'), (PRIOR, H2, '0.1400'), (SHARES, H2, '800'),
        ]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert (r.ownership_pct, r.prior_ownership_pct, r.shares_held) == (Decimal('0.2000'), Decimal('0.1500'), 2000)
        assert r.ownership_change == Decimal('0.0500')

    def test_single_filer_without_total_context_falls_back_to_holder_1(self):
        rows = [(RATIO, H1, '0.0512'), (PRIOR, H1, '0.0498'), (SHARES, H1, '512')]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert r.is_joint_filing is False
        assert (r.ownership_pct, r.prior_ownership_pct, r.shares_held) == (Decimal('0.0512'), Decimal('0.0498'), 512)

    def test_legacy_unaxised_filing_still_reads_first_match(self):
        rows = [(RATIO, 'SomeOtherContext', '0.0700'), (PRIOR, 'SomeOtherContext', '0.0600')]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert (r.ownership_pct, r.prior_ownership_pct) == (Decimal('0.0700'), Decimal('0.0600'))

    def test_important_proposal_is_any_co_reporter(self):
        """The intent field is per-holder only (no total context). Holder 1 saying
        '－' must not hide holder 2's stated act."""
        rows = [(PROPOSAL, H1, '－'), (PROPOSAL, H2, '取締役の選任に関する株主提案')]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert r.important_proposal == '取締役の選任に関する株主提案'

    def test_important_proposal_all_blank_stays_blank(self):
        rows = [(PROPOSAL, H1, '－'), (PROPOSAL, H2, '－')]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert r.important_proposal == '－'

    def test_jointholder_axis_alone_marks_joint(self):
        rows = [(RATIO, H1, '0.05'), (RATIO, J1, '0.10'), (RATIO, TOTAL, '0.15')]
        r = parse_large_holding(csv_files=_files(rows), doc_id='X', doc_type_code='350')
        assert r.is_joint_filing is True
        assert r.ownership_pct == Decimal('0.15')
