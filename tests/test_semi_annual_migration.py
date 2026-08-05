"""Semi-annual parser tier-table migration pins (0.8.0 stage-5 Task 7).

STRUCTURAL migration only: the 8 financial fields become tier tables
resolved context-BLIND (resolve_tiers period=None — first match in file
order, exactly the legacy extract_value-without-patterns behavior). The
ratified context fix is a separate, predicted change; these pins make the
blind behavior explicit so that fix shows up as its own deliberate diff,
never as migration drift.
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


def _parse(*rows):
    dei = [('jpdei_cor:EDINETCodeDEI', FDI, 'E00000')]
    return parse_semi_annual_report(csv_files=_cf(*dei, *rows),
                                    doc_id='TEST', doc_type_code='160')


class TestBlindSemanticsPreserved:
    def test_first_row_in_file_order_wins_regardless_of_context(self):
        """Context-blind legacy: a Prior2 row earlier in the file beats the
        current-period row. This is the DEFECT the ratified semi-annual
        context fix will change — pinned here so the fix arrives as its own
        predicted flip, not as silent migration drift."""
        r = _parse(('jppfs_cor:Assets', 'Prior2YearInstant', '111'),
                   ('jppfs_cor:Assets', 'CurrentYearInstant', '222'))
        assert r.total_assets == 111

    def test_ifrs_fallback_fires_when_primary_absent(self):
        r = _parse(('jpigp_cor:AssetsIFRS', 'CurrentYearInstant', '333'))
        assert r.total_assets == 333

    def test_ifrs_fallback_fires_when_primary_is_marker(self):
        r = _parse(('jppfs_cor:Assets', 'CurrentYearInstant', '－'),
                   ('jpigp_cor:AssetsIFRS', 'CurrentYearInstant', '444'))
        assert r.total_assets == 444

    def test_all_eight_fields_resolve(self):
        pairs = [
            ('jppfs_cor:Assets', 'total_assets'),
            ('jppfs_cor:CurrentAssets', 'current_assets'),
            ('jppfs_cor:Liabilities', 'total_liabilities'),
            ('jppfs_cor:CurrentLiabilities', 'current_liabilities'),
            ('jppfs_cor:NetAssets', 'net_assets'),
            ('jppfs_cor:OperatingIncome', 'operating_income'),
            ('jppfs_cor:OrdinaryIncome', 'ordinary_income'),
            ('jppfs_cor:ProfitLoss', 'profit_loss'),
        ]
        rows = [(elem, 'Interim', str(100 + i)) for i, (elem, _) in enumerate(pairs)]
        r = _parse(*rows)
        for i, (_, field) in enumerate(pairs):
            assert getattr(r, field) == 100 + i, field
