"""Golden-fixture panel for the ownership-basis split (0.8.0 stage-4): eight
real securities-report filings spanning J-GAAP, IFRS, and US-GAAP, chosen to
exercise mega-cap and small-cap filers, a filer with material non-controlling
interests, a filer with none, a financial-sector filer, and the HOYA
owners-exceeds-total counterexample. Every pinned value below was
cross-checked to the yen (or nearest reported million) against the ISSUER's
own published financial results document -- never against any internal
tooling or database. See each test class's docstring for the source
citation.

Contract: parsing any of these real, correctly-filed reports must produce
ZERO extraction flags (withheld or annotated) -- these are the release's
"well-formed filing" acceptance corpus for the ownership-basis identity
rewire (see TestOwnershipBasisEquityRatioIdentity in test_grain_split.py for
the synthetic identity-behavior coverage this panel extends).
"""
import csv as _csv
from decimal import Decimal
from pathlib import Path

from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']


def _parse(name):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    with open(p, encoding='utf-8') as fh:
        rows = list(_csv.reader(fh, delimiter='\t'))
    cf = [{'filename': f'{name}.csv', 'data': [dict(zip(_COLS, r)) for r in rows[1:]]}]
    return parse_securities_report(csv_files=cf, doc_id=name, doc_type_code='120')


def _assert_no_flags(report, fixture_name):
    assert report.extraction_flags == [], (
        f'{fixture_name}: expected zero flags on a well-formed real filing, '
        f'got {report.extraction_flags}'
    )


# =====================================================================
# Toyota (IFRS mega-cap)
# Source: Toyota Motor Corporation, "FY2026 Consolidated Financial Results"
# (English translation from the original Japanese-language document),
# May 8, 2026 -- Financial Summary FY2026 (April 1, 2025 through
# March 31, 2026), page 2 tables "(1) Consolidated financial results" and
# "(2) Consolidated financial position".
# https://global.toyota/pages/global_toyota/ir/financial-results/2026_4q_summary_en.pdf
# =====================================================================

class TestToyotaIFRS:
    def test_net_income_split_and_prior_year(self):
        r = _parse('toyota_ifrs')
        assert r.accounting_standard == 'IFRS'
        assert r.fiscal_year_end.isoformat() == '2026-03-31'
        assert r.net_income_owners == 3_848_098_000_000  # "Net income attributable to Toyota Motor Corporation"
        assert r.net_income_total == 3_985_761_000_000    # "Net income"
        assert r.prior_net_income_owners == 4_765_086_000_000
        assert r.prior_net_income_total == 4_789_755_000_000

    def test_net_assets_split_and_total_assets(self):
        r = _parse('toyota_ifrs')
        assert r.net_assets_owners == 39_918_854_000_000  # "Toyota Motor Corporation shareholders' equity"
        assert r.net_assets_total == 41_020_068_000_000    # "Total shareholders' equity"
        assert r.total_assets == 105_522_331_000_000
        assert r.equity_ratio == Decimal('0.378')          # "Ratio of Toyota Motor Corporation shareholders' equity" 37.8%

    def test_zero_flags(self):
        _assert_no_flags(_parse('toyota_ifrs'), 'toyota_ifrs')


# =====================================================================
# ITOCHU (IFRS mega-cap)
# Source: ITOCHU Corporation, "Financial Information Report 2026, For the
# Fiscal Year Ended March 31, 2026" -- Summary (p.2), Consolidated Statement
# of Financial Position (p.33-34), Consolidated Statement of Comprehensive
# Income (p.35).
# https://www.itochu.co.jp/en/ir/download/__icsFiles/afieldfile/2026/06/12/FIR2026E.pdf
# =====================================================================

class TestItochuIFRS:
    def test_net_income_split_and_prior_year(self):
        r = _parse('itochu_ifrs')
        assert r.accounting_standard == 'IFRS'
        assert r.fiscal_year_end.isoformat() == '2026-03-31'
        assert r.net_income_owners == 900_283_000_000     # "Net profit attributable to ITOCHU"
        assert r.net_income_total == 937_458_000_000       # "Net profit"
        assert r.prior_net_income_owners == 880_251_000_000
        assert r.prior_net_income_total == 933_015_000_000

    def test_net_assets_split_and_total_assets(self):
        r = _parse('itochu_ifrs')
        assert r.net_assets_owners == 6_589_966_000_000    # "Total shareholders' equity"
        assert r.net_assets_total == 7_188_259_000_000      # "Total equity"
        assert r.total_assets == 16_732_815_000_000
        assert r.non_controlling_interests == 598_293_000_000

    def test_zero_flags(self):
        _assert_no_flags(_parse('itochu_ifrs'), 'itochu_ifrs')


# =====================================================================
# HOYA (IFRS counterexample -- Task 3's load-bearing fixture). Original
# filing S100Y90T chosen over the amendment S100YD7J (see task report for
# rationale); the figures below match HOYA's own contemporaneously
# published kessan tanshin, filed BEFORE the amendment, confirming the
# amendment did not restate these fields.
# Source: HOYA CORPORATION, "Quarterly Report" (4th Quarter: 3 months ended
# March 31, 2026; Annual: Fiscal year ended March 31, 2026) -- an excerpt
# translation of the Japanese "Kessan Tanshin", April 30, 2026. Part 2
# "1. Consolidated Financial Highlights" (p.13), "(1) Consolidated
# Statement of Financial Position" (p.15), "(3) Consolidated Statement of
# Comprehensive Income" (p.17).
# =====================================================================

class TestHoyaIFRSCounterexample:
    def test_owners_exceeds_total_net_income_inversion(self):
        # The load-bearing counterexample: minorities LOST money this
        # period (NCI's own profit share is -1,633M), so the
        # owners-attributable figure exceeds the total-including-NCI
        # figure. This is a real, correctly-filed inversion -- not a data
        # error -- and Decision 4 exists precisely so no rule flags it.
        r = _parse('hoya_ifrs')
        assert r.accounting_standard == 'IFRS'
        assert r.fiscal_year_end.isoformat() == '2026-03-31'
        assert r.net_income_owners == 253_085_000_000   # "Profit attributable to: Owners of the Company"
        assert r.net_income_total == 251_451_000_000     # "Profit for the term from all operations"
        assert r.net_income_owners > r.net_income_total
        assert r.prior_net_income_owners == 202_101_000_000
        assert r.prior_net_income_total == 201_750_000_000

    def test_net_assets_and_nci(self):
        r = _parse('hoya_ifrs')
        assert r.net_assets_owners == 1_020_460_000_000  # "Equity attributable to owners of the Company"
        assert r.net_assets_total == 1_035_004_000_000     # "Total equity"
        assert r.non_controlling_interests == 14_544_000_000
        assert r.total_assets == 1_300_897_000_000
        assert r.equity_ratio == Decimal('0.784')          # "Ratio of assets attributable to owners of the Company" 78.4%

    def test_zero_flags_despite_the_inversion(self):
        # The central assertion: a real owners>total inversion parses with
        # NO annotation from any containment or identity rule (Decision 4 --
        # see TestHoyaOwnersExceedsTotalNoFalseFlag in test_grain_split.py
        # for the synthetic construction of this same guarantee).
        _assert_no_flags(_parse('hoya_ifrs'), 'hoya_ifrs')


# =====================================================================
# Kansai Paint (J-GAAP, material non-controlling interests -- NCI is
# ~21.3% of net assets, confirming the census's estimate and the primary
# fixture-panel pick over the Stanley Electric alternate).
# Source: 関西ペイント株式会社, "2026年３月期 決算短信〔日本基準〕（連結）",
# 2026年5月11日 -- 連結貸借対照表 (p.7), 連結損益計算書 (p.8).
# https://asset.kansai.co.jp/uploads/2026/05/FY2025_4Q_summary.pdf
# =====================================================================

class TestKansaiPaintJGAAP:
    def test_balance_sheet_components(self):
        r = _parse('kansaipaint_jgaap')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.fiscal_year_end.isoformat() == '2026-03-31'
        assert r.shareholders_equity == 246_625_000_000              # 株主資本合計
        assert r.valuation_translation_adjustments == 53_209_000_000  # その他の包括利益累計額合計
        assert r.non_controlling_interests == 81_145_000_000          # 非支配株主持分
        assert r.net_assets_total == 381_203_000_000                  # 純資産合計
        assert r.total_assets == 801_693_000_000                      # 資産合計
        assert r.net_assets_owners is None  # J-GAAP: always None, never derived from the components

    def test_net_income_split_and_prior_year(self):
        r = _parse('kansaipaint_jgaap')
        assert r.net_income_owners == 31_641_000_000   # 親会社株主に帰属する当期純利益
        assert r.net_income_total == 34_601_000_000      # 当期純利益
        assert r.prior_net_income_owners == 38_306_000_000
        assert r.prior_net_income_total == 45_234_000_000

    def test_zero_flags(self):
        _assert_no_flags(_parse('kansaipaint_jgaap'), 'kansaipaint_jgaap')


# =====================================================================
# Shimamura (J-GAAP, no non-controlling interests -- owners and total
# basis coincide exactly).
# Source: 株式会社しまむら, "2026年２月期 決算短信〔日本基準〕（連結）",
# 2026年3月30日 -- summary table (p.1), 連結貸借対照表 (p.10-11), 連結損益
# 計算書 (p.12).
# =====================================================================

class TestShimamuraJGAAP:
    def test_no_nci_owners_equals_total(self):
        r = _parse('shimamura_jgaap')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.fiscal_year_end.isoformat() == '2026-02-20'
        assert r.non_controlling_interests is None  # no NCI line in the filing at all
        assert r.net_income_owners == r.net_income_total == 44_460_000_000
        assert r.prior_net_income_owners == r.prior_net_income_total == 41_885_000_000

    def test_balance_sheet_components(self):
        r = _parse('shimamura_jgaap')
        assert r.shareholders_equity == 479_749_000_000              # 株主資本合計
        assert r.valuation_translation_adjustments == 8_796_000_000   # その他の包括利益累計額合計
        assert r.net_assets_total == 488_545_000_000                  # 純資産合計
        assert r.total_assets == 554_667_000_000                      # 資産合計
        assert r.equity_ratio == Decimal('0.881')                     # 自己資本比率 88.1%

    def test_zero_flags(self):
        _assert_no_flags(_parse('shimamura_jgaap'), 'shimamura_jgaap')


# =====================================================================
# Horii Food Service (J-GAAP small-cap). This is the company's FIRST year
# preparing consolidated financial statements (連結財務諸表を作成しているた
# め, per the filing's own note) -- prior_net_income_owners/total are
# structurally None, not a parsing gap.
# Source: ホリイフードサービス株式会社, "2025年３月期 決算短信〔日本基準〕
# （連結）", 2025年5月16日 -- summary table (p.1), 連結貸借対照表 (p.4-5),
# 連結損益計算書 (p.6).
# =====================================================================

class TestHoriiFoodServiceJGAAP:
    def test_small_cap_balance_sheet(self):
        r = _parse('horiifood_jgaap')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.fiscal_year_end.isoformat() == '2025-03-31'
        assert r.shareholders_equity == 421_413_000              # 株主資本合計
        assert r.valuation_translation_adjustments == 53_097_000  # その他の包括利益累計額合計
        assert r.non_controlling_interests == 42_884_000          # 非支配株主持分
        assert r.net_assets_total == 517_395_000                  # 純資産合計
        assert r.total_assets == 3_018_702_000                    # 資産合計

    def test_net_income_split_first_consolidated_year_no_prior(self):
        r = _parse('horiifood_jgaap')
        assert r.net_income_owners == 175_313_000   # 親会社株主に帰属する当期純利益
        assert r.net_income_total == 179_093_000      # 当期純利益
        # First year of consolidated statements -- no prior-year consolidated
        # figures exist in the filing at all (honest None, not a bug).
        assert r.prior_net_income_owners is None
        assert r.prior_net_income_total is None

    def test_zero_flags(self):
        _assert_no_flags(_parse('horiifood_jgaap'), 'horiifood_jgaap')


# =====================================================================
# Shiga Bank (J-GAAP financial sector -- 経常収益 net_sales tier, no NCI).
# Source: 株式会社滋賀銀行, "2025年３月期 決算短信〔日本基準〕（連結）",
# 2025年５月９日 -- summary table (p.1), 連結貸借対照表 (p.5), 連結損益計算書
# (p.6).
# https://www.shigagin.com/pdf/investor_kessan_statement_2025.pdf
# =====================================================================

class TestShigaBankJGAAP:
    def test_financial_sector_net_sales_tier(self):
        # Banks report 経常収益 (ordinary income), not 売上高 -- the
        # net_sales waterfall's bank/insurer tier.
        r = _parse('shigagin_jgaap')
        assert r.accounting_standard == 'Japan GAAP'
        assert r.fiscal_year_end.isoformat() == '2025-03-31'
        assert r.net_sales == 133_109_000_000
        assert r.prior_net_sales == 122_630_000_000

    def test_no_nci_owners_equals_total(self):
        r = _parse('shigagin_jgaap')
        assert r.non_controlling_interests is None
        assert r.net_income_owners == r.net_income_total == 18_720_000_000
        assert r.prior_net_income_owners == r.prior_net_income_total == 15_940_000_000

    def test_balance_sheet_components(self):
        r = _parse('shigagin_jgaap')
        assert r.shareholders_equity == 321_698_000_000              # 株主資本合計
        assert r.valuation_translation_adjustments == 123_112_000_000  # その他の包括利益累計額合計
        assert r.net_assets_total == 444_811_000_000                  # 純資産の部合計
        assert r.total_assets == 7_528_217_000_000                    # 資産合計
        assert r.equity_ratio == Decimal('0.0590')                    # 自己資本比率 5.9%

    def test_zero_flags(self):
        _assert_no_flags(_parse('shigagin_jgaap'), 'shigagin_jgaap')


# =====================================================================
# Komatsu (US-GAAP). net_income_total is structurally None -- no US-GAAP
# taxonomy tier in this filing carries a total-basis (incl. NCI) net-income
# concept.
# Source: Komatsu Ltd., "Consolidated Business Results for the Fiscal Year
# Ended March 31, 2026 (U.S. GAAP)", April 28, 2026 -- "(1) Consolidated
# Financial Highlights" and "(2) Consolidated Financial Position" (p.1-2).
# =====================================================================

class TestKomatsuUSGAAP:
    def test_net_income_owners_only_total_structurally_none(self):
        r = _parse('komatsu_usgaap')
        assert r.accounting_standard == 'US GAAP'
        assert r.fiscal_year_end.isoformat() == '2026-03-31'
        assert r.net_income_owners == 376_391_000_000   # "Net income attributable to Komatsu Ltd."
        assert r.net_income_total is None                 # no US-GAAP total-basis element in this taxonomy tier
        assert r.prior_net_income_owners == 439_614_000_000
        assert r.prior_net_income_total is None

    def test_net_assets_split_and_total_assets(self):
        r = _parse('komatsu_usgaap')
        assert r.net_assets_owners == 3_510_768_000_000  # "Komatsu Ltd. shareholders' equity"
        assert r.net_assets_total == 3_708_427_000_000     # "Total equity"
        assert r.total_assets == 6_423_941_000_000
        assert r.equity_ratio == Decimal('0.547')          # "Komatsu Ltd. shareholders' equity ratio" 54.7%

    def test_zero_flags(self):
        _assert_no_flags(_parse('komatsu_usgaap'), 'komatsu_usgaap')
