"""C1 per-standard highlights scoping (0.8.0 stage-5, ratified).

IFRS-transition-era filings carry TWO consolidated highlights tables: the
legacy J-GAAP table (current-year column at the bare context) alongside the
IFRS table. The pre-fix standard-agnostic waterfalls tried the J-GAAP
summary elements first, so IFRS-classified rows served J-GAAP-basis
equity_ratio / total_assets / net_assets_total — cross-standard operands on
an IFRS row. The ratified fix: IFRS filers prefer the IFRS-specific
elements; standard-neutral/J-GAAP legacy tiers only when no IFRS-specific
value exists. Scoped to exactly these three fields.

Numbers below follow the adjudication's Sumitomo Bakelite worked example
(values rounded to millions for readability — the mechanism, not the filer,
is what is pinned here).
"""
from decimal import Decimal

from edinet_tools.parsers.securities import parse_securities_report

CYI = 'CurrentYearInstant'
CYI_NC = 'CurrentYearInstant_NonConsolidatedMember'
FDI = 'FilingDateInstant'

ER_JG = 'jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults'
ER_IFRS = 'jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults'
TA_JG = 'jpcrp_cor:TotalAssetsSummaryOfBusinessResults'
TA_IFRS = 'jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults'
NA_JG = 'jpcrp_cor:NetAssetsSummaryOfBusinessResults'
NA_OWNERS_IFRS = 'jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults'
EQ_IFRS_FS = 'jpigp_cor:EquityIFRS'


def _cf(*rows):
    return [{
        'filename': 'test.csv',
        'data': [
            {'要素ID': e, '項目名': '', 'コンテキストID': c, '相対年度': '',
             '連結・個別': '', '期間・時点': '', 'ユニットID': 'JPY',
             '単位': '', '値': v}
            for e, c, v in rows
        ],
    }]


def _dei(standard='IFRS', consolidated='true'):
    return [
        ('jpdei_cor:EDINETCodeDEI', FDI, 'E00000'),
        ('jpdei_cor:AccountingStandardsDEI', FDI, standard),
        ('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',
         FDI, consolidated),
    ]


DUAL_TABLE = [
    # Legacy J-GAAP highlights table (bare current-year context)
    (ER_JG, CYI, '0.631'),
    (TA_JG, CYI, '279879000000'),
    (NA_JG, CYI, '178504000000'),
    # IFRS highlights + FS equity
    (ER_IFRS, CYI, '0.619'),
    (TA_IFRS, CYI, '272247000000'),
    (NA_OWNERS_IFRS, CYI, '168450000000'),
    (EQ_IFRS_FS, CYI, '172000000000'),
]


def _parse(rows, **dei_kw):
    return parse_securities_report(csv_files=_cf(*_dei(**dei_kw), *rows),
                                   doc_id='TEST', doc_type_code='120')


class TestIfrsDualTablePrefersIfrsOperands:
    def test_the_three_ratified_fields_read_the_ifrs_table(self):
        r = _parse(DUAL_TABLE)
        assert r.equity_ratio == Decimal('0.619')
        assert r.total_assets == 272_247_000_000
        assert r.net_assets_total == 172_000_000_000
        # net_assets_owners was already IFRS-only by construction — unchanged.
        assert r.net_assets_owners == 168_450_000_000

    def test_identity_reconciles_on_all_ifrs_operands(self):
        """The adjudication's check #2: with per-standard operands the
        equity-ratio identity passes — the C1 rows stop being annotated."""
        r = _parse(DUAL_TABLE)
        assert [f for f in r.extraction_flags
                if f.rule.startswith('identity:equity_ratio')] == []

    def test_nonconsolidated_parent_only_ifrs_dual_table(self):
        """Parent-only IFRS filers (real class, DEI consolidated=false) carry
        the same dual tables at the _NonConsolidatedMember context — same
        mechanism, same fix, via the ordinary context-pattern machinery."""
        rows = [
            (ER_JG, CYI_NC, '0.496'),
            (TA_JG, CYI_NC, '23113207000'),
            (NA_JG, CYI_NC, '11456538000'),
            (ER_IFRS, CYI_NC, '0.412'),
            (TA_IFRS, CYI_NC, '27024920000'),
            (EQ_IFRS_FS, CYI_NC, '11140000000'),
        ]
        r = _parse(rows, consolidated='false')
        assert r.equity_ratio == Decimal('0.412')
        assert r.total_assets == 27_024_920_000
        assert r.net_assets_total == 11_140_000_000


class TestScopingIsExactlyIfrs:
    def test_jgaap_filing_unchanged(self):
        rows = [
            (ER_JG, CYI, '0.55'),
            (TA_JG, CYI, '1000000'),
            (NA_JG, CYI, '550000'),
        ]
        r = _parse(rows, standard='Japan GAAP')
        assert r.equity_ratio == Decimal('0.55')
        assert r.total_assets == 1_000_000
        assert r.net_assets_total == 550_000

    def test_missing_standard_keeps_legacy_order(self):
        """DEI-missing filers are NOT rescoped: the IFRS-preferred tiers are
        whitelisted to 'IFRS' and a None standard matches only unscoped
        tiers — legacy (J-GAAP-first) order is preserved."""
        r = _parse(DUAL_TABLE, standard=None)
        assert r.equity_ratio == Decimal('0.631')
        assert r.total_assets == 279_879_000_000
        assert r.net_assets_total == 178_504_000_000

    def test_usgaap_filing_unchanged(self):
        rows = [
            ('jpcrp_cor:TotalAssetsUSGAAPSummaryOfBusinessResults', CYI, '999'),
            ('jpcrp_cor:EquityToAssetRatioUSGAAPSummaryOfBusinessResults',
             CYI, '0.42'),
        ]
        r = _parse(rows, standard='US GAAP')
        assert r.total_assets == 999
        assert r.equity_ratio == Decimal('0.42')


class TestLegacyFallbackWhenNoIfrsSpecificValue:
    def test_ifrs_filer_without_ifrs_elements_falls_back(self):
        """Ratified shape: 'neutral/legacy only when no IFRS-specific
        exists' — an IFRS row with only the legacy table keeps serving it
        (honest fallback, not honest-None)."""
        rows = [
            (ER_JG, CYI, '0.631'),
            (TA_JG, CYI, '279879000000'),
            (NA_JG, CYI, '178504000000'),
        ]
        r = _parse(rows)
        assert r.equity_ratio == Decimal('0.631')
        assert r.total_assets == 279_879_000_000
        assert r.net_assets_total == 178_504_000_000

    def test_marker_valued_ifrs_ratio_falls_back_to_legacy(self):
        """The IFRS-preference stage uses coerce semantics: a null-marker
        IFRS ratio does not win (and does not blank the field) — the legacy
        scan resolves exactly as pre-fix."""
        rows = [
            (ER_JG, CYI, '0.631'),
            (ER_IFRS, CYI, '－'),
        ]
        r = _parse(rows)
        assert r.equity_ratio == Decimal('0.631')

    def test_ordinary_ifrs_filer_resolves_identically(self):
        """The IFRS majority (no dual table): same winners as pre-fix."""
        rows = [
            (ER_IFRS, CYI, '0.3803'),
            (TA_IFRS, CYI, '1300897000000'),
            (NA_OWNERS_IFRS, CYI, '494733000000'),
            (EQ_IFRS_FS, CYI, '500000000000'),
        ]
        r = _parse(rows)
        assert r.equity_ratio == Decimal('0.3803')
        assert r.total_assets == 1_300_897_000_000
        assert r.net_assets_owners == 494_733_000_000
        assert r.net_assets_total == 500_000_000_000
