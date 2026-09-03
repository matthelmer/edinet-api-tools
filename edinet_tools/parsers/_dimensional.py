"""
Axis-context extraction primitive.

Per spec §4.2: extract_dimensional() returns a list of DimensionalFact
objects for a given element_id, parsing axis members heuristically from
each row's context_id string.

Axis member parsing convention:
- Context IDs in EDINET XBRL follow the pattern:
    <BaseContext>[_<namespace>:<MemberName>Member]*
- We split context_id on '_' and look for tokens matching
  '<prefix>:<MemberName>Member' or '<MemberName>Member' patterns.
- For each member token, the axis name is inferred via convention
  (commonly the member-name suffix; e.g., 'No1MajorShareholdersMember'
  belongs to 'MajorShareholdersAxis'). Without a taxonomy registry,
  we return ('', member_name) tuples and let the caller resolve the
  axis name from context.

This primitive is used by items #1 (segments), #3 (top-shareholders),
and #5 (directors+comp) in the 0.7.0+ release family.
"""
import re

from .extraction import unescape_entities
from dataclasses import dataclass, field


_MEMBER_SUFFIX = 'Member'

# Per-filer extension-namespace prefix that filers prepend to custom member
# names: 'E03847-000DomesticLifeInsuranceReportableSegmentsMember' →
# 'DomesticLifeInsuranceReportableSegments'. Stripping yields the canonical
# axis-member name the spec describes (and matches segments.py's own
# _clean_member_name); without it, every caller would have to re-implement
# cleaning. See test_extract_dimensional_preserves_filer_extension_member_names.
_EDINET_FILER_PREFIX_RE = re.compile(r'^E\d{5}-\d{3}')


@dataclass
class DimensionalFact:
    """A fact paired with axis members parsed from its context_id."""
    element_id: str
    base_context: str
    axis_members: list[tuple[str, str]] = field(default_factory=list)
    value: str = ''
    unit_id: str | None = None


def _parse_axis_members(context_id: str) -> tuple[str, list[tuple[str, str]]]:
    """Split context_id into (base_context, axis_members).

    Returns:
        (base_context, [(axis_name, member_name), ...])

    axis_name is empty string when the taxonomy isn't known to the parser;
    caller resolves via convention or a registry.

    EDINET context_id format examples:
        CurrentYearDuration
        CurrentYearDuration_jpcrp_cor:ReportableSegment1Member
        CurrentYearDuration_jpcrp_cor:SegmentAMember_jpcrp_cor:NonConsolidatedMember

    The namespace prefix (e.g. 'jpcrp_cor') may itself contain underscores
    (e.g. 'jpcrp030000-asr_E03615-000'), so we cannot simply split on '_'.
    Instead we split on the colon-containing token boundaries: any '_'-delimited
    run of fragments up to (and including) the fragment containing ':' forms one
    logical token.
    """
    if not context_id:
        return '', []

    # Reassemble '_'-split fragments into logical tokens by grouping prefix
    # fragments (no colon) with the immediately following colon-containing fragment.
    raw_parts = context_id.split('_')
    tokens: list[str] = []
    pending: list[str] = []

    for part in raw_parts:
        if ':' in part:
            # This fragment has the colon — combine with any pending prefix parts
            pending.append(part)
            tokens.append('_'.join(pending))
            pending = []
        else:
            # No colon yet — could be a namespace prefix fragment or a base segment
            # We flush pending first (shouldn't happen, but defensive)
            if pending:
                tokens.append('_'.join(pending))
                pending = []
            pending.append(part)

    # Flush any remaining pending (plain context fragments like 'CurrentYearDuration')
    if pending:
        tokens.append('_'.join(pending))

    base_parts = []
    members: list[tuple[str, str]] = []

    for token in tokens:
        # Strip namespace prefix if present (e.g., 'jpcrp_cor:FooMember' -> 'FooMember')
        local_name = token.split(':')[-1] if ':' in token else token
        if local_name.endswith(_MEMBER_SUFFIX) and len(local_name) > len(_MEMBER_SUFFIX):
            member_name = local_name[:-len(_MEMBER_SUFFIX)]
            # Strip the per-filer EDINET extension-namespace prefix so callers
            # get the canonical member name regardless of which filer emitted it.
            member_name = _EDINET_FILER_PREFIX_RE.sub('', member_name)
            members.append(('', member_name))
        else:
            base_parts.append(token)

    base_context = '_'.join(base_parts)
    return base_context, members


def extract_dimensional(csv_files: list, element_id: str) -> list:
    """Extract all DimensionalFact rows for a given element_id.

    Args:
        csv_files: List of dicts with 'filename' + 'data' keys (the shape
            returned by extract_csv_from_zip).
        element_id: XBRL element ID to filter on (exact match).

    Returns:
        List of DimensionalFact objects, one per CSV row matching element_id.
        Empty list if no matches.
    """
    results: list[DimensionalFact] = []

    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            elem_id = row.get('要素ID', '') or ''
            if elem_id != element_id:
                continue

            context_id = row.get('コンテキストID', '') or ''
            value = unescape_entities(row.get('値', '') or '')
            unit_id = row.get('ユニットID', '') or None
            if unit_id == '':
                unit_id = None

            base_context, axis_members = _parse_axis_members(context_id)
            results.append(DimensionalFact(
                element_id=elem_id,
                base_context=base_context,
                axis_members=axis_members,
                value=value,
                unit_id=unit_id,
            ))

    return results
