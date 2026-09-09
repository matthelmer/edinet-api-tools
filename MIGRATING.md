# Migrating to 0.8.0

0.8.0 removes several fields and a few long-deprecated shims. Every removal
raises immediately and by name — an `AttributeError` naming the replacement,
or (for the dataclass fields) a `TypeError` on construction — so nothing
breaks silently. This page is the fix-it checklist; see
[CHANGELOG.md](CHANGELOG.md) for the full reasoning behind each change.

## 0.8.4 — behaviour changes to know about

Patch release, no removals from the parsed-report dataclasses. Four things a
caller can observe; each is a defect fixed rather than a redesign, and the
[CHANGELOG](CHANGELOG.md) carries the reasoning.

- **Joint 5%+ filings now use the group totals.** `ownership_pct`,
  `prior_ownership_pct`, `ownership_change`, and `shares_held` on a joint
  `LargeHoldingReport` are the group total (the un-dimensioned row). Before
  0.8.4 the prior was holder 1's own figure. If you stored these, re-parse
  joint filings; per-holder figures are unchanged on `joint_holders`.
  `holder_number` is now a dense `1..K` ordering (primary filer first) rather
  than the filed axis index — a gapped axis `(1, 3)` is emitted as `(1, 2)`.
- **Convenience paths fail loud.** `Entity.documents()` and
  `get_documents_for_date_range()` raise `AuthenticationError` on a rejected
  key and `APIError` when every day in the window failed, instead of
  returning `[]`. A transient failure on one day is still tolerated.
- **No key, no request.** `fetch_documents_list` / `fetch_document` raise
  `AuthenticationError` before contacting EDINET when no key is available
  (argument, `configure()`, or `EDINET_API_KEY`). Previously the request went
  out with the literal string `None`. The key is now resolved per call, so
  setting the environment variable after `import edinet_tools` works.
- **Code-list download.** `edinet_tools.data_loader.EDINET_CSV_URL` is
  removed (the FSA path it named now serves HTML); `EDINET_CODES_ZIP_URL`
  is the address the loader fetches, and `EDINET_CODES_URL` now points at
  the EDINET site for a manual download. `DOCUMENT_TYPES` has 42 entries
  (was 39) and its English names now match `doc_types` — 21 strings changed
  (`Large Holding Report` → `Large Shareholding Report`, and so on). Match on
  the codes, not the names.

## `SecuritiesReport`: ownership-basis field split

`net_assets`, `net_income`, and `prior_net_income` are removed. Each used to
silently pick one of two possible figures — attributable to the parent
company's own shareholders ("owners"), or including non-controlling
interests ("total") — depending on accounting standard and what the filer
happened to tag. They're now always an explicit pair.

| Old field | Standard | What the old value actually was | Replacement |
|---|---|---|---|
| `net_assets` | J-GAAP | Always total-basis (incl. NCI) | `net_assets_total` |
| `net_assets` | IFRS / US-GAAP | Owners-basis when the filing tagged it; silently fell back to total-basis otherwise | `net_assets_owners`, falling back to `net_assets_total` for the old fallback behavior |
| `net_income` | J-GAAP / IFRS / US-GAAP | Owners-basis for almost every filer; silently fell back to total-basis for the minority of filers whose owners-basis element was absent | `net_income_owners`, falling back to `net_income_total` for the old fallback behavior (`net_income_total` is `None` for nearly all US-GAAP filers) |
| `prior_net_income` | all | Same mixed routing as `net_income`, prior-year context | `prior_net_income_owners` / `prior_net_income_total`, same fallback pattern |

Three new filed-fact fields also ship the J-GAAP balance-sheet components
directly: `shareholders_equity` (株主資本), `valuation_translation_adjustments`
(評価換算差額等), `non_controlling_interests` (非支配株主持分 / NCI). None are
summed into `net_assets_owners` for you; see the README's "Ownership basis"
section. A J-GAAP owners-only equity figure is `shareholders_equity +
valuation_translation_adjustments`, computed by you.

**Fix:** replace `report.net_assets` with `net_assets_owners` or
`net_assets_total` depending on which basis your code needs; same for
`net_income` / `prior_net_income`.

## `EdinetClient` removed

Deprecated since 0.2.0, removed in 0.8.0. Use the module-level functions
instead:

| Old | New |
|---|---|
| `EdinetClient().get_documents_by_date(...)` | `edinet_tools.documents(date)` |
| `EdinetClient().get_recent_filings(...)` | `entity.documents(...)` |
| `EdinetClient().get_company_filings(...)` | `entity.documents(...)` |
| `EdinetClient().search_companies(...)` | `edinet_tools.search(...)` / `search_entities(...)` |
| `EdinetClient().download_filing(...)` | `doc.fetch()` |
| `EdinetClient().extract_filing_data(...)` | `doc.parse()` |

## Deprecated boolean shims removed

Retired (with a `DeprecationWarning`) in the 0.6.1 fact-shaped API
transition; removed outright in 0.8.0.

| Old | New |
|---|---|
| `Entity.is_listed` | `entity.entity_type == EntityType.LISTED_COMPANY` |
| `Entity.is_fund_issuer` | `entity.entity_type == EntityType.FUND_ISSUER` |
| `EntityClassifier.is_listed(code)` | `classifier.get_entity_type(code) == EntityType.LISTED_COMPANY` |
| `TreasuryStockReport.has_board_authorization` | `bool(parsed.by_board_meeting and parsed.by_board_meeting.strip())` |
| `TreasuryStockReport.has_shareholder_authorization` | `bool(parsed.by_shareholders_meeting and parsed.by_shareholders_meeting.strip())` |
| `utils.process_zip_directory()` | `extract_csv_from_zip()` (in-memory) or `extract_csv_to_disk()` (disk output) |

## `EntityType.FUND` → `EntityType.FUND_ISSUER`

The classification comes from the fund registry's *issuer* column: it
means "has issued fund products" (trust banks qualify), not "is a fund".
The member, its value string, and the classifier helper are renamed to
say so.

| Old | New |
|---|---|
| `EntityType.FUND` | `EntityType.FUND_ISSUER` |
| `"fund"` (the `.value` string) | `"fund_issuer"` |
| `EntityClassifier.is_fund(code)` | `classifier.is_fund_issuer(code)` |

If you persist `EntityType.value` strings, map stored `"fund"` values on
read or migrate them — the enum no longer accepts `EntityType("fund")`.

## Legacy `processors.py` / `parser.py` pipeline removed

`BaseDocumentProcessor` and its five subclasses, `process_raw_csv_data`,
`EdinetXbrlCsvParser`, `extract_xbrl_financial_data`, `FinancialMetric`,
`TextBlock`, and `utils.process_zip_file` are gone. An exposure audit
found these reachable only from each other and their own tests — never
from `__init__.py`, README, or the typed-parser pipeline
(`edinet_tools.parsers`) that has been the supported path since 0.2.0. If
you were importing directly from `edinet_tools.processors` or
`edinet_tools.parser` (undocumented; no public API referenced either
module), switch to `doc.parse()` / `edinet_tools.parsers`.
`utils.read_csv_file` / `detect_encoding` / `clean_text` are unaffected.

## `[analysis]` install extra removed

`pip install edinet-tools[analysis]` pulled in llm, pydantic, matplotlib,
and plotly for an analysis module removed back in 0.4.1. If your install
command still names the extra, drop it — `pip install edinet-tools` is
equivalent and no longer pulls the unused packages.

## `.env` files are no longer loaded automatically

`edinet_tools` reads `EDINET_API_KEY` from the process environment only —
importing it no longer has the side effect of loading a `.env` file. If
you keep your key in `.env`, call `load_dotenv()` yourself before
importing `edinet_tools`:

```python
from dotenv import load_dotenv
load_dotenv()

import edinet_tools  # EDINET_API_KEY is now set
```

No change needed if you already export the variable into your
environment directly.

## No code changes needed

- **`python-dateutil` and `chardet` dependency removal** — both were
  internal implementation details (fiscal-quarter arithmetic and TSV
  encoding detection, respectively). No public API changed; behavior is
  pinned equivalent by tests.
- **Financial-parser internals migrated to per-field tier tables** — an
  internal refactor of how `securities`, `quarterly`, and `semi_annual`
  parsers resolve elements. Proven behavior-equivalent by a full-corpus
  old-vs-new re-parse; see CHANGELOG for the one intentional data-quality
  fix that came with it (the per-standard highlights-table fix).
