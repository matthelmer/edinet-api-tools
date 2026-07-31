"""Unit tests for the extraction-validation framework (bounds + flags).

Bounds withhold: a value structurally impossible under the field's name means
the element mapping is wrong, so the typed field is emptied and a flag records
why. Rules encode possibility, never plausibility.
"""
from decimal import Decimal

import pytest

from edinet_tools.parsers.validation import Bound, ExtractionFlag, apply_bounds
from edinet_tools.parsers.securities import SecuritiesReport


def make_report(**overrides) -> SecuritiesReport:
    defaults = dict(doc_id='TEST0001', doc_type_code='120',
                    accounting_standard='Japan GAAP')
    defaults.update(overrides)
    return SecuritiesReport(**defaults)


BOUNDS = [
    Bound(field='equity_ratio', max_value=Decimal('1')),
    Bound(field='total_assets', min_value=0),
]


class TestBoundsWithhold:
    def test_impossible_ratio_is_withheld_with_flag(self):
        # The 0.7.1 costly instance: a "ratio" element carrying yen-per-share
        report = make_report(equity_ratio=Decimal('27056.2'))
        flags = apply_bounds(report, BOUNDS,
                             provenance={'equity_ratio': 'jpcrp_cor:SomeElement'})
        assert report.equity_ratio is None
        assert len(flags) == 1
        f = flags[0]
        assert f.field == 'equity_ratio'
        assert f.element_id == 'jpcrp_cor:SomeElement'
        assert f.value == '27056.2'
        assert f.severity == 'withheld'
        assert f.accounting_standard == 'Japan GAAP'

    def test_negative_equity_ratio_passes(self):
        # No lower bound: insolvent companies with negative equity ratios are real
        report = make_report(equity_ratio=Decimal('-3.926'))
        assert apply_bounds(report, BOUNDS) == []
        assert report.equity_ratio == Decimal('-3.926')

    def test_boundary_value_passes(self):
        report = make_report(equity_ratio=Decimal('1'))
        assert apply_bounds(report, BOUNDS) == []
        assert report.equity_ratio == Decimal('1')

    def test_none_field_writes_no_flag(self):
        # Nothing extracted -> no claim to withhold, no record
        report = make_report(equity_ratio=None)
        assert apply_bounds(report, BOUNDS) == []

    def test_min_bound_withholds_negative_total_assets(self):
        report = make_report(total_assets=-500)
        flags = apply_bounds(report, BOUNDS)
        assert report.total_assets is None
        assert flags[0].rule == 'bound:total_assets>=0'
        assert flags[0].element_id is None  # no provenance supplied

    def test_standards_scope_skips_other_standards(self):
        scoped = [Bound(field='equity_ratio', max_value=Decimal('1'),
                        standards=('IFRS',))]
        report = make_report(equity_ratio=Decimal('27056.2'))  # J-GAAP report
        assert apply_bounds(report, scoped) == []
        assert report.equity_ratio == Decimal('27056.2')

    def test_flag_to_dict_round_trips(self):
        f = ExtractionFlag(field='equity_ratio', element_id='x', value='2',
                           rule='bound:equity_ratio<=1', severity='withheld',
                           accounting_standard='IFRS')
        d = f.to_dict()
        assert d == {'field': 'equity_ratio', 'element_id': 'x', 'value': '2',
                     'rule': 'bound:equity_ratio<=1', 'severity': 'withheld',
                     'accounting_standard': 'IFRS'}
