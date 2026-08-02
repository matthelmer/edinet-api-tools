"""Golden tests: net_assets_per_share (BPS) must populate for IFRS and
US-GAAP filers whose summary tables carry the concept under a mapping the
J-GAAP-first waterfall previously missed.

IFRS: jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults is a taxonomy
misnomer (name says "ratio", label says 1株当たり親会社所有者帰属持分) that
already fed ifrs_summary_bps (v0.7.2+) but was never wired into the
net_assets_per_share waterfall itself.

US-GAAP: Sony tags its US-GAAP summary BPS under a filer-custom namespace
(jpcrp030000-asr_E01777-000:StockholdersEquityPerShareOfCommonStockUSGAAP
SummaryOfBusinessResults) instead of the fixed jpcrp_cor:
EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBusinessResults id
the existing tier matches — needs a suffix-match tier, same pattern as
get_revenue_by_suffix / get_operating_income_by_suffix.
"""
import csv as _csv
from pathlib import Path
from decimal import Decimal
from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']


def _load(name):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    rows = list(_csv.reader(open(p, encoding='utf-8'), delimiter='\t'))
    return [{'filename': f'{name}.csv', 'data': [dict(zip(_COLS, r)) for r in rows[1:]]}]


def _parse(name):
    return parse_securities_report(csv_files=_load(name), doc_id='TEST', doc_type_code='120')


def test_ifrs_bps_element_feeds_net_assets_per_share():
    # Honda Motor (E02166) FY2018/3 (第94期): IFRS consolidated filer.
    # The fixed J-GAAP jpcrp_cor:NetAssetsPerShareSummaryOfBusinessResults
    # element IS present in this filing but only at the
    # _NonConsolidatedMember (parent-only, 単体) context -- Honda's own
    # yuho page 4 shows 1株当たり純資産額 = 1,168.66円 (提出会社/単体) for
    # 第94期, NOT the consolidated figure. The strict consolidated context
    # patterns correctly refuse to borrow that parent value.
    # IR-verified from the primary EDINET filing PDF
    # (disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100D7P7.pdf, p.2,
    # 主要な経営指標等の推移 / IFRS table, 第94期 column):
    # 1株当たり親会社所有者帰属持分 = 4,461.36円.
    r = _parse('ifrs_bps_filer')
    assert r.accounting_standard == 'IFRS'
    assert r.net_assets_per_share == Decimal('4461.36'), \
        f'expected 4461.36, got {r.net_assets_per_share}'
    # Same element also feeds ifrs_summary_bps (v0.7.2+) -- both must agree,
    # since they read the identical XBRL element/context.
    assert r.net_assets_per_share == r.ifrs_summary_bps


def test_usgaap_custom_namespace_bps_variant_feeds_net_assets_per_share():
    # Sony Group Corporation (E01777) FY2021/3 (第101期/2020年度): US-GAAP
    # summary filer. Tags 1株当たり純資産額 under a filer-custom namespace
    # (jpcrp030000-asr_E01777-000:StockholdersEquityPerShareOfCommonStock
    # USGAAPSummaryOfBusinessResults) instead of the fixed jpcrp_cor:
    # EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBusinessResults
    # id (absent from this filing entirely).
    # IR-verified from the primary EDINET filing PDF
    # (disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100LM4N.pdf, p.2,
    # 主要な経営指標等の推移 / 連結経営指標等 table, 2020年度 column):
    # 1株当たり純資産額 = 4,499.45円. Same page also confirms net sales
    # ¥8,999,360m and net income ¥1,171,776m attributable to Sony Corp
    # stockholders, both matching this fixture's fixed-element values --
    # cross-check that the right filing/period was selected.
    r = _parse('usgaap_bps_variant')
    assert r.accounting_standard == 'US GAAP'
    assert r.net_assets_per_share == Decimal('4499.45'), \
        f'expected 4499.45, got {r.net_assets_per_share}'
