"""Semi-annual parser context/standard pins (0.8.0 stage-5 Task 9).

Task 7 migrated the 8 financial fields onto the declarative tier core
context-BLIND (period=None -- first match in file order), deliberately
preserving the pre-migration defect so the ratified context fix would land
as its own predicted diff. This file is that diff: the parser now reads
`accounting_standard` + `is_consolidated` DEI (honest-None), resolves a
per-document period-token regime (bimodal: `Interim*` for the -ssr taxonomy
vs `CurrentQuarter*`/`CurrentYTD*` for the transitional -q2r taxonomy), and
applies strict bare-context-only reads when the filer is consolidated (the
OKWAVE rule: no borrowing the non-consolidated/parent figure).
"""
from edinet_tools.parsers.semi_annual import parse_semi_annual_report

FDI = 'FilingDateInstant'


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


def _parse(*rows, doc_type_code='160', dei=()):
    base_dei = [('jpdei_cor:EDINETCodeDEI', FDI, 'E00000')]
    return parse_semi_annual_report(csv_files=_cf(*base_dei, *dei, *rows),
                                    doc_id='TEST', doc_type_code=doc_type_code)


class TestPeriodRegimeDetection:
    """Doc-level period token: prefer Interim* if any Interim context
    exists anywhere in the filing, else CurrentQuarter*/CurrentYTD*
    (census-validated rule, unambiguous on the full sampled corpus)."""

    def test_interim_regime_wins_over_prior_row(self):
        """A Prior1YearInstant row earlier in file order no longer beats
        the current-period InterimInstant row -- this is the DEFECT the
        context fix removes."""
        r = _parse(('jppfs_cor:Assets', 'Prior1YearInstant', '111'),
                   ('jppfs_cor:Assets', 'InterimInstant', '222'))
        assert r.total_assets == 222

    def test_q2r_regime_when_no_interim_context_present(self):
        """FY2024 transitional semi-annuals use the quarterly-taxonomy
        contexts; no 'Interim' context anywhere in the doc selects the
        CurrentQuarter*/CurrentYTD* vocabulary instead."""
        r = _parse(('jppfs_cor:Assets', 'Prior1YearInstant', '111'),
                   ('jppfs_cor:Assets', 'CurrentQuarterInstant', '333'))
        assert r.total_assets == 333

    def test_duration_field_uses_ytd_regime_in_q2r_docs(self):
        r = _parse(('jppfs_cor:ProfitLoss', 'Prior1YTDDuration', '111'),
                   ('jppfs_cor:ProfitLoss', 'CurrentYTDDuration', '444'))
        assert r.profit_loss == 444

    def test_duration_field_uses_interim_regime_when_any_interim_context_present(self):
        """Regime is doc-wide: an Interim context anywhere (even on a
        different field) selects InterimDuration for THIS field too."""
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '1'),
                   ('jppfs_cor:ProfitLoss', 'Prior1InterimDuration', '111'),
                   ('jppfs_cor:ProfitLoss', 'InterimDuration', '555'))
        assert r.profit_loss == 555


class TestConsolidationContextPreference:
    """Bare context = consolidated; _NonConsolidatedMember suffix =
    parent-only (identical convention to securities reports)."""

    def test_non_consolidated_prefers_suffix_context(self):
        r = _parse(('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', FDI, 'false'),
                   ('jppfs_cor:Assets', 'InterimInstant_NonConsolidatedMember', '777'),
                   ('jppfs_cor:Assets', 'InterimInstant', '888'))
        assert r.total_assets == 777

    def test_consolidated_reads_bare_context_even_with_a_nonconsolidated_row_present(self):
        r = _parse(('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', FDI, 'true'),
                   ('jppfs_cor:Assets', 'InterimInstant_NonConsolidatedMember', '111'),
                   ('jppfs_cor:Assets', 'InterimInstant', '999'))
        assert r.total_assets == 999

    def test_okwave_rule_consolidated_never_borrows_nonconsolidated_only_value(self):
        """OKWAVE-class filing: is_consolidated=true, but this element is
        tagged ONLY at the NonConsolidatedMember suffix for the current
        period (no bare context row at all). The strict-consolidated read
        must withhold honestly (None), never silently borrow the
        parent/non-consolidated figure for a consolidated filer."""
        r = _parse(('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', FDI, 'true'),
                   ('jppfs_cor:CurrentLiabilities', 'InterimInstant_NonConsolidatedMember', '999'))
        assert r.current_liabilities is None


class TestDeiAccountingStandardAndConsolidation:
    def test_accounting_standard_honest_none_when_absent(self):
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '1'))
        assert r.accounting_standard is None

    def test_accounting_standard_read_from_dei(self):
        r = _parse(('jpdei_cor:AccountingStandardsDEI', FDI, 'IFRS'))
        assert r.accounting_standard == 'IFRS'

    def test_accounting_standard_strips_whitespace(self):
        """A handful of real filings carry the DEI value with trailing
        tab/whitespace noise ('Japan GAAP' + stray tabs) -- strip it so it
        matches a standards tuple downstream."""
        r = _parse(('jpdei_cor:AccountingStandardsDEI', FDI, 'Japan GAAP\t\t\t\t'))
        assert r.accounting_standard == 'Japan GAAP'

    def test_is_consolidated_honest_none_when_dei_absent(self):
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '1'))
        assert r.is_consolidated is None

    def test_is_consolidated_true(self):
        r = _parse(('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', FDI, 'true'))
        assert r.is_consolidated is True

    def test_is_consolidated_false(self):
        r = _parse(('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', FDI, 'false'))
        assert r.is_consolidated is False


class TestIfrsFallbackStillFiresAtMatchingContext:
    def test_ifrs_fallback_fires_when_primary_absent(self):
        r = _parse(('jpigp_cor:AssetsIFRS', 'CurrentQuarterInstant', '333'))
        assert r.total_assets == 333

    def test_ifrs_fallback_fires_when_primary_is_marker(self):
        r = _parse(('jppfs_cor:Assets', 'CurrentQuarterInstant', '－'),
                   ('jpigp_cor:AssetsIFRS', 'CurrentQuarterInstant', '444'))
        assert r.total_assets == 444


class TestAllEightFieldsResolve:
    def test_all_eight_fields_resolve_in_interim_regime(self):
        pairs = [
            ('jppfs_cor:Assets', 'total_assets', 'InterimInstant'),
            ('jppfs_cor:CurrentAssets', 'current_assets', 'InterimInstant'),
            ('jppfs_cor:Liabilities', 'total_liabilities', 'InterimInstant'),
            ('jppfs_cor:CurrentLiabilities', 'current_liabilities', 'InterimInstant'),
            ('jppfs_cor:NetAssets', 'net_assets', 'InterimInstant'),
            ('jppfs_cor:OperatingIncome', 'operating_income', 'InterimDuration'),
            ('jppfs_cor:OrdinaryIncome', 'ordinary_income', 'InterimDuration'),
            ('jppfs_cor:ProfitLoss', 'profit_loss', 'InterimDuration'),
        ]
        rows = [(elem, ctx, str(100 + i)) for i, (elem, _, ctx) in enumerate(pairs)]
        r = _parse(*rows)
        for i, (_, field, _) in enumerate(pairs):
            assert getattr(r, field) == 100 + i, field


class TestDoc170Parity:
    """Doc 170 (semi-annual amendment) files the same taxonomy as Doc 160
    -- the parser applies identical context/standard logic regardless of
    doc_type_code."""

    def test_doc_170_resolves_context_aware(self):
        r = _parse(('jppfs_cor:Assets', 'Prior1YearInstant', '111'),
                   ('jppfs_cor:Assets', 'InterimInstant', '222'),
                   doc_type_code='170')
        assert r.total_assets == 222
        assert r.doc_type_code == '170'


class TestValidationWiring:
    def test_negative_total_assets_withheld(self):
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '-500'))
        assert r.total_assets is None
        assert any(f.severity == 'withheld' and f.field == 'total_assets'
                   for f in r.extraction_flags)

    def test_net_assets_exceeding_total_assets_annotated_not_withheld(self):
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '100'),
                   ('jppfs_cor:NetAssets', 'InterimInstant', '200'))
        assert r.total_assets == 100
        assert r.net_assets == 200  # identities annotate, never empty
        assert any(f.severity == 'annotated'
                   and f.rule == 'identity:net_assets<=total_assets'
                   and f.operands == {'net_assets': '200', 'total_assets': '100'}
                   for f in r.extraction_flags)

    def test_well_formed_filing_yields_zero_flags(self):
        r = _parse(('jppfs_cor:Assets', 'InterimInstant', '1000'),
                   ('jppfs_cor:Liabilities', 'InterimInstant', '400'),
                   ('jppfs_cor:CurrentLiabilities', 'InterimInstant', '200'),
                   ('jppfs_cor:NetAssets', 'InterimInstant', '600'))
        assert r.extraction_flags == []
