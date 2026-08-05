"""Value-pinned tests for the tender-results numeric-field remap (0.8.0
stage-5 Task 10).

A full census of every jptoo-tor_cor numeric element across the 609-doc
results corpus found the results filing family uses its own voting-rights
letter scheme (a, d, g), distinct from the registration family's (a, d, g,
j) despite near-identical 項目名 labels. Two of the four target fields were
mapped to the registration letters and had 0/609 real fills;
`voting_rights_special_interest` and `total_voting_rights` are remapped
below to the results-side elements the census confirmed present. The other
two target fields, `voting_rights_purchased` and `purchase_ratio`, have NO
backing numeric element anywhere in the namespace and stay honest-None —
their dead map entries are retired, not derived from other fields.

Fixture: a real, genuinely completed purchase (S100L6T1 in EDINET's own doc
ID space) with the full CSV preserved -- every value below is pinned to the
filing's own stated table, verified directly against the raw CSV.
"""
import io
import zipfile
from decimal import Decimal

from edinet_tools.parsers.tender_offer_report import (
    ELEMENT_MAP,
    parse_tender_offer_report,
    TENDER_RESULT_BOUNDS,
)
from tests.conftest import load_tender_fixture


def _parse_fixture(name, doc_type_code='270'):
    cf = load_tender_fixture(name)
    return parse_tender_offer_report(csv_files=cf, doc_id=name,
                                      doc_type_code=doc_type_code)


# ---------------------------------------------------------------------------
# Real-filing fixture panel: a completed tender offer, non-zero special
# interest holders (the "nonzero case" the census flagged as worth pinning
# separately from the zero-special-interest majority).
# ---------------------------------------------------------------------------

class TestCompletedPurchaseFixture:
    def test_voting_rights_owned_by_offeror(self):
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.voting_rights_owned_by_offeror == 60_694

    def test_voting_rights_special_interest_remapped_nonzero(self):
        """Was 0/609 under the old registration-letter (G) mapping; the
        results-side D element carries a genuine nonzero value here."""
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.voting_rights_special_interest == 16_298

    def test_total_voting_rights_remapped(self):
        """Was 0/609 under the old registration-letter (J) mapping; the
        results-side G element (itself carrying a doubled 'NumberNumber'
        prefix in the real taxonomy name, not a typo) is populated."""
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.total_voting_rights == 108_857

    def test_holding_ratio_after_unaffected_by_remap(self):
        """Already-healthy field (463/473 fills pre-Task-10) -- pinned here
        to prove the remap didn't disturb it."""
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.holding_ratio_after == Decimal('0.7039')

    def test_voting_rights_purchased_honest_none(self):
        """No backing element exists anywhere in the namespace -- retired,
        never filled, even on a real completed-purchase filing."""
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.voting_rights_purchased is None

    def test_purchase_ratio_honest_none(self):
        """Same reason as voting_rights_purchased -- retired."""
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.purchase_ratio is None

    def test_zero_flags_on_well_formed_filing(self):
        r = _parse_fixture('skt_holdings_shoko_tsusho')
        assert r.extraction_flags == [], (
            f'expected zero flags on a well-formed real filing, got '
            f'{r.extraction_flags}'
        )


# ---------------------------------------------------------------------------
# ELEMENT_MAP retirement — the two no-element fields must not resurface a
# dead mapping (never-derive discipline: a future edit re-adding either key
# would silently reintroduce the 0-fill class this task retired).
# ---------------------------------------------------------------------------

class TestRetiredFieldsHaveNoElementMapping:
    def test_voting_rights_purchased_not_in_element_map(self):
        assert 'voting_rights_purchased' not in ELEMENT_MAP

    def test_purchase_ratio_not_in_element_map(self):
        assert 'purchase_ratio' not in ELEMENT_MAP

    def test_remapped_fields_use_results_side_letters(self):
        """Guards against the remap regressing back to a registration-side
        letter (the defect class this task fixes)."""
        assert ELEMENT_MAP['voting_rights_special_interest'].endswith(
            'OwnedBySpecialInterestPartiesD'
        )
        assert ELEMENT_MAP['total_voting_rights'].endswith(
            'OfSubjectCompanyG'
        )


# ---------------------------------------------------------------------------
# Structural bounds — non-negative only (D7 ratification: ratios are stored
# 0-1 scale but a legitimate >1.0 over-tender case exists, so no upper
# bound). Synthetic mock CSV -- no real filing carries an impossible
# negative voting-rights count, so this exercises the withhold path
# directly rather than waiting for one to turn up in the corpus.
# ---------------------------------------------------------------------------

def _make_csv_row(element_id: str, context_id: str, value: str) -> str:
    return f"{element_id}\tlabel\t{context_id}\t0\t連結\t期間\t\t\t{value}"


def _make_zip(rows: list[str]) -> bytes:
    content = '\n'.join(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('XBRL_TO_CSV/test.csv', content.encode('utf-16le'))
    return buf.getvalue()


def _parse_rows(rows):
    # Round-trips through the real zip/extract path so this exercises the
    # same code the production parser runs, not a hand-built csv_files
    # shortcut.
    from edinet_tools.parsers.extraction import extract_csv_from_zip
    csv_files = extract_csv_from_zip(_make_zip(rows))
    return parse_tender_offer_report(csv_files=csv_files, doc_id='TEST',
                                      doc_type_code='270')


class TestNonNegativeBoundsWithhold:
    def test_negative_special_interest_withheld(self):
        rows = [
            _make_csv_row(ELEMENT_MAP['voting_rights_special_interest'],
                          'FilingDateInstant', '-100'),
        ]
        report = _parse_rows(rows)
        assert report.voting_rights_special_interest is None
        flags = [f for f in report.extraction_flags
                 if f.field == 'voting_rights_special_interest']
        assert len(flags) == 1
        assert flags[0].severity == 'withheld'
        assert flags[0].rule == 'bound:voting_rights_special_interest>=0'

    def test_negative_total_voting_rights_withheld(self):
        rows = [
            _make_csv_row(ELEMENT_MAP['total_voting_rights'],
                          'FilingDateInstant', '-1'),
        ]
        report = _parse_rows(rows)
        assert report.total_voting_rights is None
        assert any(f.field == 'total_voting_rights' and f.severity == 'withheld'
                   for f in report.extraction_flags)

    def test_negative_holding_ratio_after_withheld(self):
        rows = [
            _make_csv_row(ELEMENT_MAP['holding_ratio_after'],
                          'FilingDateInstant', '-0.01'),
        ]
        report = _parse_rows(rows)
        assert report.holding_ratio_after is None
        assert any(f.field == 'holding_ratio_after' and f.severity == 'withheld'
                   for f in report.extraction_flags)

    def test_over_tender_ratio_above_one_not_withheld(self):
        """D7 ratification: ratios are stored on the 0-1 scale but a legit
        over-tender case (final holding exceeding 1.0) exists -- no upper
        bound, so this must NOT be withheld."""
        rows = [
            _make_csv_row(ELEMENT_MAP['holding_ratio_after'],
                          'FilingDateInstant', '1.2500'),
        ]
        report = _parse_rows(rows)
        assert report.holding_ratio_after == Decimal('1.2500')
        assert report.extraction_flags == []

    def test_bounds_table_is_non_negative_only(self):
        """No max_value anywhere in the bounds table -- guards against a
        future edit reintroducing an upper-bound rule the census ruled
        out."""
        for bound in TENDER_RESULT_BOUNDS:
            assert bound.max_value is None, (
                f'{bound.field} has a max_value bound; D7 ratified '
                f'non-negative-only for this parser'
            )
            assert bound.min_value == 0


# ---------------------------------------------------------------------------
# jptoi self-tender filings (issuer tender offers, 137/610 in the census)
# carry NO jptoo-tor rows at all -- structurally honest-None for every
# numeric field, not a failure. Synthetic: the census already confirmed
# `jptoi_cor` carries zero numeric elements across all 283 such docs
# (results + registration); a jptoo-tor-free CSV reproduces that shape.
# ---------------------------------------------------------------------------

class TestIssuerSelfTenderHonestAbsence:
    def test_all_four_target_fields_none_with_no_tor_rows(self):
        rows = [
            _make_csv_row('jptoi_cor:CalculationForPurchaseEtcByMethodOfProportionalDistributionNA',
                          'FilingDateInstant', '該当事項はありません。'),
        ]
        report = _parse_rows(rows)
        assert report.voting_rights_owned_by_offeror is None
        assert report.voting_rights_special_interest is None
        assert report.total_voting_rights is None
        assert report.voting_rights_purchased is None
        assert report.purchase_ratio is None
        assert report.holding_ratio_after is None

    def test_no_flags_on_absent_operands(self):
        """Bounds skip (never fail) when nothing was extracted -- absence of
        a value is not a claim to withhold."""
        rows = [
            _make_csv_row('jptoi_cor:CalculationForPurchaseEtcByMethodOfProportionalDistributionNA',
                          'FilingDateInstant', '該当事項はありません。'),
        ]
        report = _parse_rows(rows)
        assert report.extraction_flags == []
