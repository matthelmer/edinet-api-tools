"""
Extraction validation: structural bounds and accounting identities.

Every rule encodes what is structurally POSSIBLE for a field — never what is
typical. Two rule kinds with different powers:

- Bounds WITHHOLD: a bound violation is localized (the value is impossible
  under the field's name, so the element mapping is wrong). The typed field is
  emptied and a flag records field, element, value, rule. The raw value stays
  in raw_fields untouched.
- Identities ANNOTATE: an identity has multiple operands and cannot localize
  the culprit, so it writes a flag but empties nothing.

A rule that cannot be evaluated (missing operand) is skipped, never failed.
Only positively-contradicted values are withheld.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

# Spec tolerance for ratio identities: "within 2 points" (0.02 on a 0-1 ratio).
IDENTITY_TOLERANCE = Decimal('0.02')

# A stated cover-page filing date more than this many days AFTER the submit
# date is flagged (annotated, never overwritten). Stated-before-submit never
# flags: that is the legitimate late-filer signal.
FILING_DATE_SANITY_DAYS = 30


@dataclass(frozen=True)
class ExtractionFlag:
    """One validation finding. severity 'withheld' means the typed field was
    emptied (bounds); 'annotated' means the field kept its value (identities,
    date sanity)."""
    field: str
    element_id: Optional[str]
    value: str
    rule: str
    severity: str  # 'withheld' | 'annotated'
    accounting_standard: Optional[str]

    def to_dict(self) -> dict:
        return {
            'field': self.field,
            'element_id': self.element_id,
            'value': self.value,
            'rule': self.rule,
            'severity': self.severity,
            'accounting_standard': self.accounting_standard,
        }


@dataclass(frozen=True)
class Bound:
    """Structural bound on a single field. standards=None applies to all
    accounting standards (an explicit declaration, not an omission)."""
    field: str
    max_value: Optional[Decimal] = None
    min_value: Optional[Decimal] = None
    standards: Optional[tuple] = None

    def rule_name(self) -> str:
        parts = []
        if self.max_value is not None:
            parts.append(f'{self.field}<={self.max_value}')
        if self.min_value is not None:
            parts.append(f'{self.field}>={self.min_value}')
        return 'bound:' + ','.join(parts)


def _in_scope(standards, accounting_standard) -> bool:
    return standards is None or accounting_standard in standards


def _as_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def apply_bounds(report, bounds, provenance=None) -> list:
    """Check every bound against the report. Violations empty the typed field
    and produce a 'withheld' flag. Returns the flags; caller appends them to
    report.extraction_flags. provenance maps field name -> winning element_id
    where the extraction site captured it."""
    provenance = provenance or {}
    standard = getattr(report, 'accounting_standard', None)
    flags = []
    for bound in bounds:
        if not _in_scope(bound.standards, standard):
            continue
        raw = getattr(report, bound.field, None)
        value = _as_decimal(raw)
        if value is None:
            continue  # nothing extracted -> no claim to withhold
        violated = ((bound.max_value is not None and value > bound.max_value)
                    or (bound.min_value is not None and value < bound.min_value))
        if violated:
            setattr(report, bound.field, None)
            flags.append(ExtractionFlag(
                field=bound.field,
                element_id=provenance.get(bound.field),
                value=str(raw),
                rule=bound.rule_name(),
                severity='withheld',
                accounting_standard=standard,
            ))
    return flags


@dataclass(frozen=True)
class Identity:
    """Accounting identity across multiple operand fields. check() receives
    the operand values as Decimals in declared order and returns True (holds),
    False (violated), or None (cannot evaluate -> skip). Violations ANNOTATE
    only — identities never empty a field."""
    name: str
    operands: tuple
    check: Callable
    standards: Optional[tuple] = None


def apply_identities(report, identities) -> list:
    """Check every identity against the report. Violations produce an
    'annotated' flag but DO NOT modify the report. Returns the flags; caller
    appends them to report.extraction_flags."""
    standard = getattr(report, 'accounting_standard', None)
    flags = []
    for identity in identities:
        if not _in_scope(identity.standards, standard):
            continue
        values = [_as_decimal(getattr(report, op, None))
                  for op in identity.operands]
        if any(v is None for v in values):
            continue  # skip, never fail
        result = identity.check(*values)
        if result is None or result:
            continue
        rendered = ', '.join(f'{op}={val}'
                             for op, val in zip(identity.operands, values))
        flags.append(ExtractionFlag(
            field=identity.operands[0],
            element_id=None,
            value=rendered,
            rule=identity.name,
            severity='annotated',
            accounting_standard=standard,
        ))
    return flags


def apply_validation(report, bounds, identities, provenance=None) -> None:
    """Run bounds (withhold) then identities (annotate) and extend
    report.extraction_flags. Bounds run first deliberately: a withheld operand
    makes dependent identities skip rather than annotate garbage."""
    flags = apply_bounds(report, bounds, provenance=provenance)
    flags.extend(apply_identities(report, identities))
    report.extraction_flags.extend(flags)
