"""Unit tests for the extraction-validation framework (bounds + flags).

Bounds withhold: a value structurally impossible under the field's name means
the element mapping is wrong, so the typed field is emptied and a flag records
why. Rules encode possibility, never plausibility.

Identities annotate: an identity has multiple operands and cannot localize
the culprit, so it writes a flag but empties nothing.
"""
from decimal import Decimal

import pytest

from edinet_tools.parsers.validation import (
    Bound, ExtractionFlag, Identity, apply_bounds, apply_identities,
    apply_validation, IDENTITY_TOLERANCE,
)
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


def equity_ratio_reconciles(er, na, ta):
    if ta == 0:
        return None  # cannot evaluate -> skip
    return abs(er - na / ta) <= IDENTITY_TOLERANCE


EQUITY_IDENTITY = Identity(
    name='identity:equity_ratio~net_assets/total_assets',
    operands=('equity_ratio', 'net_assets', 'total_assets'),
    check=equity_ratio_reconciles,
)


class TestIdentitiesAnnotate:
    def test_violation_annotates_and_keeps_all_values(self):
        # 0.30 stated vs 0.60 computed: annotate, never empty — an identity
        # cannot localize the culprit (spec: the J-GAAP grain case is a
        # correct filed ratio disagreeing with a differently-grained operand)
        report = make_report(equity_ratio=Decimal('0.30'),
                             net_assets=600, total_assets=1000)
        flags = apply_identities(report, [EQUITY_IDENTITY])
        assert len(flags) == 1
        assert flags[0].severity == 'annotated'
        assert flags[0].rule == 'identity:equity_ratio~net_assets/total_assets'
        assert report.equity_ratio == Decimal('0.30')  # KEPT
        assert report.net_assets == 600                 # KEPT
        assert 'equity_ratio=0.30' in flags[0].value

    def test_within_tolerance_no_flag(self):
        report = make_report(equity_ratio=Decimal('0.601'),
                             net_assets=600, total_assets=1000)
        assert apply_identities(report, [EQUITY_IDENTITY]) == []

    def test_missing_operand_skips(self):
        report = make_report(equity_ratio=Decimal('0.30'),
                             net_assets=None, total_assets=1000)
        assert apply_identities(report, [EQUITY_IDENTITY]) == []

    def test_check_returning_none_skips(self):
        report = make_report(equity_ratio=Decimal('0.30'),
                             net_assets=600, total_assets=0)
        assert apply_identities(report, [EQUITY_IDENTITY]) == []

    def test_standards_scope_respected(self):
        scoped = Identity(name=EQUITY_IDENTITY.name,
                          operands=EQUITY_IDENTITY.operands,
                          check=EQUITY_IDENTITY.check, standards=('IFRS',))
        report = make_report(equity_ratio=Decimal('0.30'),
                             net_assets=600, total_assets=1000)  # J-GAAP
        assert apply_identities(report, [scoped]) == []


class TestExtractionFlagsOnBaseType:
    def test_default_empty_on_any_report(self):
        from edinet_tools.parsers.base import ParsedReport
        r = ParsedReport(doc_id='X', doc_type_code='350')
        assert r.extraction_flags == []

    def test_to_dict_serializes_flags_as_plain_dicts(self):
        report = make_report(equity_ratio=Decimal('27056.2'))
        apply_validation(report, BOUNDS, [])
        d = report.to_dict()
        assert isinstance(d['extraction_flags'], list)
        assert d['extraction_flags'][0]['severity'] == 'withheld'
        assert d['extraction_flags'][0]['field'] == 'equity_ratio'

    def test_to_dict_empty_flags_is_empty_list(self):
        report = make_report()
        assert report.to_dict()['extraction_flags'] == []


class TestApplyValidation:
    def test_extends_report_flags_with_both_kinds(self):
        report = make_report(equity_ratio=Decimal('27056.2'),
                             net_assets=600, total_assets=1000,
                             total_liabilities=-5)
        bounds = BOUNDS + [Bound(field='total_liabilities', min_value=0)]
        apply_validation(report, bounds, [EQUITY_IDENTITY])
        severities = {f.severity for f in report.extraction_flags}
        # equity_ratio withheld by bound BEFORE the identity runs, so the
        # identity is skipped (missing operand) — order is load-bearing
        assert severities == {'withheld'}
        assert report.equity_ratio is None
        assert report.total_liabilities is None
