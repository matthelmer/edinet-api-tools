"""Golden tests: operating_income must never be the parent J-GAAP line for
IFRS/US-GAAP consolidated filers. Trading houses (no IFRS operating subtotal)
get honest None; filers that DO report an IFRS/US-GAAP operating line keep it.
"""
import csv as _csv
from pathlib import Path
import pytest
from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']

def _load(name):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    rows = list(_csv.reader(open(p, encoding='utf-8'), delimiter='\t'))
    return [{'filename': f'{name}.csv', 'data': [dict(zip(_COLS, r)) for r in rows[1:]]}]

def _parse(name):
    return parse_securities_report(csv_files=_load(name), doc_id='TEST', doc_type_code='120')

def test_ifrs_trading_house_operating_income_is_none():
    # 8001 Itochu: IFRS P&L has no operating-profit subtotal -> honest None,
    # NOT the parent J-GAAP jppfs_cor:OperatingIncome leak.
    r = _parse('itochu_fy25_op_income')
    assert r.accounting_standard == 'IFRS'
    assert r.operating_income is None, f'expected None, got {r.operating_income}'
    # regression guard: revenue still correct
    assert r.net_sales and r.net_sales > 10_000_000_000_000

def test_ifrs_filer_with_real_operating_line_preserved():
    # 8015 Toyota Tsusho: reports jpigp_cor:OperatingProfitLossIFRS (consolidated) -> keep it.
    # EXACT pin: a magnitude check alone would also pass on a leaked parent value.
    r = _parse('toyotatsusho_fy25_op_income')
    assert r.accounting_standard == 'IFRS'
    assert r.operating_income == 497_174_000_000
    assert r.prior_operating_income == 441_589_000_000

def test_usgaap_operating_income_from_summary_element():
    # Sony US-GAAP: has jpcrp_cor:OperatingIncomeLossUSGAAPSummaryOfBusinessResults.
    # EXACT pin: only the exact value proves the right element won.
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.accounting_standard == 'US GAAP'
    assert r.operating_income == 845_459_000_000
    assert r.prior_operating_income == 894_235_000_000

def test_jgaap_operating_income_unchanged():
    # Control: J-GAAP path must keep working (jppfs_cor:OperatingIncome).
    r = _parse('jgaap_control_revenue')
    assert r.accounting_standard == 'Japan GAAP'
    # EXACT pins: the fixture also carries parent values at _NonConsolidatedMember
    # (2,023,920,000 current / 1,677,158,000 prior) — a context regression that
    # picks the parent would still be "not None", so only exact values protect.
    assert r.operating_income == 3_311_340_000
    assert r.prior_operating_income == 3_145_292_000


def test_ifrs_custom_namespace_operating_profit_mapped():
    # JXTG Holdings (now ENEOS) FY2018/3: reports
    # OperatingProfitLossIFRSSummaryOfBusinessResults under a filer-custom
    # namespace prefix (jpcrp030000-asr_E24050-000:...) instead of the fixed
    # jpcrp_cor: id -> the fixed-id ELEMENT_MAP lookup can never match this,
    # so it must be caught by suffix match. IR-verified: Nikkei reported
    # 営業利益は30%増の4875億円 for this filing (487,546,000,000 exact).
    r = _parse('ifrs_custom_ns_opincome')
    assert r.accounting_standard == 'IFRS'
    assert r.operating_income == 487_546_000_000, f'expected 487546000000, got {r.operating_income}'
    assert r.prior_operating_income == 271_138_000_000

def test_insurer_operating_income_stays_none():
    # Dai-ichi Life Holdings FY2025/3: jppfs_cor:OperatingIncomeINS ("経常収益、
    # 保険業") is the insurance-ordinance GROSS REVENUE line, not an operating-
    # profit concept -> must NOT be mapped into operating_income. Honest None
    # is the correct answer here, same as any other filer with no operating-
    # profit concept in its P&L.
    r = _parse('insurer_jgaap')
    assert r.accounting_standard == 'Japan GAAP'
    assert r.operating_income is None, f'expected None, got {r.operating_income}'
    assert r.prior_operating_income is None

def test_bank_operating_income_stays_none():
    # Resona Holdings FY2026/3: GrossOperatingProfit (業務粗利益) /
    # NetOperatingProfitLessCreditCost / ActualNetOperatingProfit (実質業務純益
    # family) are bank-specific profit concepts distinct from 営業利益, AND
    # only ever appear at per-segment contexts (no bare consolidated context
    # exists in this filing at all) -> honest None either way.
    r = _parse('bank_jgaap')
    assert r.accounting_standard == 'Japan GAAP'
    assert r.operating_income is None, f'expected None, got {r.operating_income}'
    assert r.prior_operating_income is None


def _synthetic_filing(accounting_standard):
    """Minimal SYNTHETIC csv_files for gate-pinning. Not a real filing: a scan
    of 2,229 IFRS/US-GAAP securities reports (2026-06-09) found ZERO with a
    bare-context jppfs_cor:OperatingIncome row — so the gate below can only be
    pinned synthetically. It defends against future filings/refactors.
    """
    rows = [
        {'要素ID': 'jpdei_cor:AccountingStandardsDEI', '項目名': '会計基準',
         'コンテキストID': 'FilingDateInstant', '値': accounting_standard},
        {'要素ID': 'jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',
         '項目名': '連結決算の有無', 'コンテキストID': 'FilingDateInstant', '値': 'true'},
        # The leak shape: parent J-GAAP operating income AT THE BARE context.
        {'要素ID': 'jppfs_cor:OperatingIncome', '項目名': '営業利益',
         'コンテキストID': 'CurrentYearDuration', 'ユニットID': 'JPY', '値': '999000000'},
        {'要素ID': 'jppfs_cor:OperatingIncome', '項目名': '営業利益',
         'コンテキストID': 'Prior1YearDuration', 'ユニットID': 'JPY', '値': '888000000'},
    ]
    return [{'filename': 'synthetic.csv', 'data': rows}]

@pytest.mark.parametrize('standard', ['IFRS', 'US GAAP'])
def test_gate_blocks_bare_context_parent_op_income(standard):
    # Without the per-standard gate, the bare-context jppfs_cor:OperatingIncome
    # above would win the coalesce and leak 999000000 into operating_income.
    r = parse_securities_report(csv_files=_synthetic_filing(standard),
                                doc_id='SYNTH', doc_type_code='120')
    assert r.accounting_standard == standard
    assert r.operating_income is None
    assert r.prior_operating_income is None
