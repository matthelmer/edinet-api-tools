"""IFRS balance-sheet debt: split, don't force (v0.8.0+).

IFRS filers report combined bonds-and-borrowings and pure-borrowings lines
that have NO clean 1:1 mapping onto the J-GAAP debt fields
(short_term_loans_payable / long_term_loans_payable / bonds_payable /
current_portion_long_term_loans_payable). Two grains get two names: they
become new `*_ifrs` fields, never coerced onto the J-GAAP fields above.

Census (corpjapan prod, 2026-08-01, Task 1 gate): 2,331 IFRS securities_reports
rows. Element frequency: BondsAndBorrowingsCLIFRS 842, BondsAndBorrowingsNCLIFRS
888, BorrowingsCLIFRS 683, BorrowingsNCLIFRS 553. All four appear at real
frequency -> all four ship.

Co-occurrence check (this task, re-run against the same census): the two pairs
are MUTUALLY EXCLUSIVE per filer -- a filer reports EITHER the combined
"社債及び借入金" (bonds-and-borrowings) line OR the separate "借入金"
(borrowings-only) line, never both:
  (BondsAndBorrowingsCLIFRS & NCLIFRS, no Borrowings*): 810 rows
  (BorrowingsCLIFRS & NCLIFRS, no BondsAndBorrowings*):   505 rows
  no row has 3+ of the 4 elements together.
The task brief's "fixtures with >=3 of 4 elements" selection criterion could
not be met by any real prod row; two fixtures (one per pair) were built
instead, jointly covering all four elements. See task-6-report.md for the
full adjudication.

Fixture selection (real EDINET filings, FY ended 2026-03-31):
  ifrs_debt_a = TDK Corporation (6762.T, S100YD2Y)      -- combined-line style
  ifrs_debt_b = Murata Manufacturing (6981.T, S100YHPY) -- separate-line style

IR verification: both fixtures carry the filing's own
NotesBondsAndBorrowingsConsolidatedFinancialStatementsIFRSTextBlock note,
whose itemized yen breakdown reconciles EXACTLY to the structured XBRL tag
value pinned below (two independent representations inside the same primary
filing). See task-6-report.md for the full reconciliation and the (unreliable)
external secondary-source cross-check attempt.
"""
import csv as _csv
from pathlib import Path
from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']


def _parse(name):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    with open(p, encoding='utf-8') as fh:
        rows = list(_csv.reader(fh, delimiter='\t'))
    cf = [{'filename': f'{name}.csv', 'data': [dict(zip(_COLS, r)) for r in rows[1:]]}]
    return parse_securities_report(csv_files=cf, doc_id='TEST', doc_type_code='120')


# --- ifrs_debt_a (TDK): combined bonds-and-borrowings style ---

def test_ifrs_bonds_and_borrowings_current_populates():
    # jpigp_cor:BondsAndBorrowingsCLIFRS, CurrentYearInstant = 210,953,000,000
    # (社債及び借入金、流動負債（IFRS）; reconciles to the note's 合計210,953).
    r = _parse('ifrs_debt_a')
    assert r.accounting_standard == 'IFRS'
    assert r.bonds_and_borrowings_current_ifrs == 210_953_000_000


def test_ifrs_bonds_and_borrowings_noncurrent_populates():
    # jpigp_cor:BondsAndBorrowingsNCLIFRS, CurrentYearInstant = 332,678,000,000
    # (社債及び借入金、非流動負債（IFRS）; reconciles to the note's 合計332,678).
    r = _parse('ifrs_debt_a')
    assert r.bonds_and_borrowings_noncurrent_ifrs == 332_678_000_000


def test_ifrs_debt_a_borrowings_only_fields_stay_none():
    # TDK reports the combined line, not the separate Borrowings{CL,NCL}IFRS
    # elements -- honest None, no cross-pair leakage.
    r = _parse('ifrs_debt_a')
    assert r.borrowings_current_ifrs is None
    assert r.borrowings_noncurrent_ifrs is None


def test_ifrs_debt_a_jgaap_debt_fields_stay_none():
    # The new IFRS concepts must NEVER populate the J-GAAP debt fields --
    # this is the core "split, don't force" guarantee.
    r = _parse('ifrs_debt_a')
    assert r.short_term_loans_payable is None
    assert r.long_term_loans_payable is None
    assert r.bonds_payable is None
    assert r.current_portion_long_term_loans_payable is None


# --- ifrs_debt_b (Murata): separate borrowings-only style ---

def test_ifrs_borrowings_current_populates():
    # jpigp_cor:BorrowingsCLIFRS, CurrentYearInstant = 1,745,000,000
    # (借入金、流動負債（IFRS）; reconciles to the note's 684 + 1,061 = 1,745).
    r = _parse('ifrs_debt_b')
    assert r.accounting_standard == 'IFRS'
    assert r.borrowings_current_ifrs == 1_745_000_000


def test_ifrs_borrowings_noncurrent_populates():
    # jpigp_cor:BorrowingsNCLIFRS, CurrentYearInstant = 1,516,000,000
    # (借入金、非流動負債（IFRS）; reconciles to the note's 長期借入金1,516).
    r = _parse('ifrs_debt_b')
    assert r.borrowings_noncurrent_ifrs == 1_516_000_000


def test_ifrs_debt_b_bonds_and_borrowings_fields_stay_none():
    # Murata reports the separate borrowings-only line, not the combined
    # BondsAndBorrowings{CL,NCL}IFRS elements -- honest None.
    r = _parse('ifrs_debt_b')
    assert r.bonds_and_borrowings_current_ifrs is None
    assert r.bonds_and_borrowings_noncurrent_ifrs is None


def test_ifrs_debt_b_jgaap_debt_fields_stay_none():
    r = _parse('ifrs_debt_b')
    assert r.short_term_loans_payable is None
    assert r.long_term_loans_payable is None
    assert r.bonds_payable is None
    assert r.current_portion_long_term_loans_payable is None


# --- J-GAAP fixture: new IFRS fields must never populate ---

def test_jgaap_fixture_ifrs_debt_fields_stay_none():
    # bank_jgaap.csv is Japan GAAP with real J-GAAP debt fields populated
    # (used by test_operating_income_mapping.py); the new IFRS-only fields
    # must stay None here.
    r = _parse('bank_jgaap')
    assert r.accounting_standard == 'Japan GAAP'
    assert r.bonds_and_borrowings_current_ifrs is None
    assert r.bonds_and_borrowings_noncurrent_ifrs is None
    assert r.borrowings_current_ifrs is None
    assert r.borrowings_noncurrent_ifrs is None
