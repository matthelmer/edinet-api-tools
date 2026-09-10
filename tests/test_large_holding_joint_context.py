"""Joint Doc 350 filings: the group total lives in the un-dimensioned context
(`FilingDateInstant` in every filed case seen); each co-reporter's own figures
live under `...FilerLargeVolumeHolder<N>Member` and, on some filings, a second
axis `...JointHolder<N>Member`.

Before 0.8.4 the parser selected by document position: `ownership_pct` and
`shares_held` took the LAST match (which happened to be the total),
`prior_ownership_pct` took the FIRST (holder 1's own prior). A group total
minus one holder's prior is not a change. Measured on prod 2026-09-09: 375 of
400 sampled joint filings since 2024 stored a prior that disagreed with the
filed total-context prior (mean gap 8.1 pts); the second axis was invisible to
`_detect_joint_filing` on ~3% of filings flagged single-filer.
"""
from decimal import Decimal

from edinet_tools.parsers.large_holding import parse_large_holding
from tests.conftest import load_fixture
from tests.test_parser_extraction import make_csv_row


def _parse(rows):
    files = [{'filename': 'x.csv', 'data': [make_csv_row(*r) for r in rows]}]
    return parse_large_holding(csv_files=files, doc_id='X', doc_type_code='350')


H1 = 'FilingDateInstant_jplvh010000-lvh_E99999-000FilerLargeVolumeHolder1Member'
H2 = 'FilingDateInstant_jplvh010000-lvh_E99999-000FilerLargeVolumeHolder2Member'
H3 = 'FilingDateInstant_jplvh010000-lvh_E99999-000FilerLargeVolumeHolder3Member'
J1 = 'FilingDateInstant_jplvh010000-lvh_E99999-000JointHolder1Member'
TOTAL = 'FilingDateInstant'
RATIO = 'jplvh_cor:HoldingRatioOfShareCertificatesEtc'
PRIOR = 'jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport'
SHARES = 'jplvh_cor:TotalNumberOfStocksEtcHeld'
PROPOSAL = 'jplvh_cor:ActOfMakingImportantProposalEtc'
PURPOSE = 'jplvh_cor:PurposeOfHolding'
NAME = 'jplvh_cor:Name'


class TestRealFilings:
    def test_hikari_4491_change_report_no19_reads_group_totals(self):
        """S100YZFS (2026-09-03): 光通信 + ＵＨ Partners on コンピューターマネージメント.
        Filed: holder 1 own 0.0670 (prior 0.0670); group 0.1309 (prior 0.1409) — a
        1.0-pt SALE. 0.8.3 stored prior 0.0670 and reported +6.4 pts. Both holders
        file `－` for important_proposal, so the any-holder read must stay `－`."""
        r = parse_large_holding(csv_files=load_fixture('large_holding', 'hikari_4491_joint_2026'),
                                doc_id='S100YZFS', doc_type_code='350')
        assert r.is_joint_filing is True
        assert r.joint_holder_count == 2
        assert r.ownership_pct == Decimal('0.1309')
        assert r.prior_ownership_pct == Decimal('0.1409')
        assert r.ownership_change == Decimal('-0.0100')
        assert r.shares_held == 266800
        assert r.filer_name == '光通信株式会社'
        assert r.joint_holders[0].name_jp == '光通信株式会社'
        assert r.important_proposal == '－'

    def test_mitsubishi_2597_jointholder_axis_is_a_joint_filing(self):
        """S100SKDY: 三菱商事 (Holder1, 9.50%) + UCCジャパン (JointHolder1, 50.53%)
        + UCC Capital (JointHolder2, 0%) on ユニカフェ; group 60.04%, prior 60.04% —
        an intra-group transfer, change 0. 0.8.3 flagged it single-filer with prior
        0.095 and reported +50.5 pts."""
        r = parse_large_holding(csv_files=load_fixture('large_holding', 'mitsubishi_2597_jointholder_axis'),
                                doc_id='S100SKDY', doc_type_code='350')
        assert r.is_joint_filing is True
        assert r.joint_holder_count == 3
        assert r.ownership_pct == Decimal('0.6004')
        assert r.prior_ownership_pct == Decimal('0.6004')
        assert r.ownership_change == Decimal('0')
        assert r.shares_held == 8326700
        assert [h.name_jp for h in r.joint_holders] == ['三菱商事株式会社', 'UCCジャパン株式会社', 'UCC Capital株式会社']
        assert [h.holder_number for h in r.joint_holders] == [1, 2, 3]


class TestGroupTotalSelection:
    def test_total_row_wins_regardless_of_document_order(self):
        """The total is selected by context shape, not by being last in the file."""
        r = _parse([
            (RATIO, TOTAL, '0.2000'), (PRIOR, TOTAL, '0.1500'), (SHARES, TOTAL, '2000'),
            (RATIO, H1, '0.1200'), (PRIOR, H1, '0.0100'), (SHARES, H1, '1200'),
            (RATIO, H2, '0.0800'), (PRIOR, H2, '0.1400'), (SHARES, H2, '800'),
        ])
        assert r.ownership_pct == Decimal('0.2000')
        assert r.prior_ownership_pct == Decimal('0.1500')
        assert r.shares_held == 2000
        assert r.ownership_change == Decimal('0.0500')

    def test_total_under_a_differently_named_bare_context_is_still_the_total(self):
        """No filed case uses anything but FilingDateInstant (1,500-filing census),
        but matching by name would send such a filing to holder 1's stake — the
        one path where 0.8.4 could be worse than 0.8.3's last-match. Match by shape."""
        r = _parse([(RATIO, H1, '0.0600'), (RATIO, H2, '0.0500'), (RATIO, 'CurrentYearInstant', '0.1100')])
        assert r.ownership_pct == Decimal('0.1100')

    def test_blank_total_is_an_empty_total_not_holder_1(self):
        """A filed-but-empty total row must not fall through to one holder's stake."""
        r = _parse([(RATIO, TOTAL, ''), (RATIO, H1, '0.0600'), (RATIO, H2, '0.0500')])
        assert r.ownership_pct is None

    def test_single_filer_without_total_row_reads_holder_1(self):
        """Single-filer filings tag only Holder1 and usually omit the bare row."""
        r = _parse([(RATIO, H1, '0.0512'), (PRIOR, H1, '0.0498'), (SHARES, H1, '512')])
        assert r.is_joint_filing is False
        assert r.ownership_pct == Decimal('0.0512')
        assert r.prior_ownership_pct == Decimal('0.0498')
        assert r.shares_held == 512

    def test_legacy_filing_with_neither_axis_nor_total_reads_first_match(self):
        r = _parse([(RATIO, 'SomeOtherContext', '0.0700'), (PRIOR, 'SomeOtherContext', '0.0600')])
        assert r.ownership_pct == Decimal('0.0700')
        assert r.prior_ownership_pct == Decimal('0.0600')


class TestCoReporterAxes:
    def test_jointholder_axis_alone_marks_joint_and_counts_the_holder(self):
        """is_joint_filing and joint_holder_count must agree: a holder exists as
        soon as its axis appears, labelled fields or not."""
        r = _parse([(RATIO, H1, '0.05'), (RATIO, J1, '0.10'), (RATIO, TOTAL, '0.15')])
        assert r.is_joint_filing is True
        assert r.joint_holder_count == 2
        assert r.ownership_pct == Decimal('0.15')

    def test_holder_numbers_are_dense_with_the_primary_first(self):
        """A gapped single-axis filing (1, 3) is emitted as (1, 2); the second
        axis follows the first. Consumers must not read holder_number as the filed N."""
        label = '氏名又は名称'  # the 項目名 the holder extractor keys name_jp on
        r = _parse([
            (NAME, J1, 'joint-one', label), (NAME, H3, 'third', label), (NAME, H1, 'primary', label),
        ])
        assert [(h.holder_number, h.name_jp) for h in r.joint_holders] == \
            [(1, 'primary'), (2, 'third'), (3, 'joint-one')]


class TestImportantProposalAcrossHolders:
    def test_first_co_reporter_that_states_an_act_wins(self):
        """The intent field is per-holder only (no total row). Holder 1's `－`
        must not hide holder 2's stated act (~2% of joint filings differ by holder)."""
        r = _parse([(PROPOSAL, H1, '－'), (PROPOSAL, H2, '取締役の選任に関する株主提案')])
        assert r.important_proposal == '取締役の選任に関する株主提案'

    def test_every_blank_spelling_is_blank(self):
        """EDINET filers spell "nothing" many ways; any of them on holder 1 must
        still yield to a stated act on holder 2."""
        for blank in ('－', 'ー', '無し', '該当事項なし。', '該当事項はありません。'):
            r = _parse([(PROPOSAL, H1, blank), (PROPOSAL, H2, '増配の提案')])
            assert r.important_proposal == '増配の提案', blank


class TestPurposeIsThePrimaryFilers:
    def test_purpose_comes_from_holder_1_even_when_a_co_reporter_is_listed_first(self):
        """`purpose` has no group row; it is the primary filer's, chosen by axis
        context. In 2 of 600 sampled joint filings the co-reporter's purpose row
        came first in the file (census 2026-09-09)."""
        r = _parse([(PURPOSE, H2, '政策投資'), (PURPOSE, H1, '純投資')])
        assert r.purpose == '純投資'

    def test_purpose_on_a_jointholder_only_filing_is_the_first_holder(self):
        """Holders on the second axis only: the primary is JointHolder1 by the
        same ordering joint_holders uses, not whichever row comes first."""
        r = _parse([(PURPOSE, 'FilingDateInstant_x-000JointHolder2Member', 'partner'),
                    (PURPOSE, J1, 'primary')])
        assert r.purpose == 'primary'

    def test_purpose_falls_back_to_first_match_on_legacy_filings(self):
        r = _parse([(PURPOSE, 'SomeOtherContext', '純投資')])
        assert r.purpose == '純投資'


class TestJointFilingWithoutTotalRow:
    def test_joint_filing_without_total_row_reports_no_group_figure(self):
        """Two co-reporters and no un-dimensioned row: there is no group total
        in the filing. Holder 1's own stake is not the group's; honest None."""
        r = _parse([(RATIO, H1, '0.0600'), (PRIOR, H1, '0.0500'), (SHARES, H1, '600'),
                    (RATIO, H2, '0.0500'), (PRIOR, H2, '0.0400'), (SHARES, H2, '500')])
        assert r.is_joint_filing is True
        assert r.ownership_pct is None
        assert r.prior_ownership_pct is None
        assert r.shares_held is None
        assert r.ownership_change is None

    def test_single_holder_on_the_jointholder_axis_without_total_row_reads_that_holder(self):
        """One holder, tagged on the second axis only: the only row is the group."""
        r = _parse([(RATIO, J1, '0.0512'), (PRIOR, J1, '0.0498'), (SHARES, J1, '512')])
        assert r.joint_holder_count == 1
        assert r.ownership_pct == Decimal('0.0512')
        assert r.prior_ownership_pct == Decimal('0.0498')
        assert r.shares_held == 512
