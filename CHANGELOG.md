# Changelog

## Unreleased

### Breaking

- **`SecuritiesReport.net_assets` / `net_income` / `prior_net_income` split by ownership basis.** Any filing that consolidates a not-fully-owned subsidiary carries two distinct figures — one attributable to the parent company's own shareholders, one including the non-controlling interests' (minority interests') share — and the old single-field names silently picked one or the other depending on accounting standard and what the filer happened to tag. All three are removed. See the README's "Ownership basis" section for the full migration table.
  - `net_assets` → `net_assets_owners` (attributable to owners of parent) and `net_assets_total` (includes non-controlling interests). `net_assets_owners` is always `None` for J-GAAP filers — Japanese GAAP never files a single owners-only net-assets element; the filed components ship instead, below.
  - `net_income` → `net_income_owners` and `net_income_total`. `net_income_total` is structurally `None` for nearly all US-GAAP filers — no total-basis element exists in that taxonomy tier.
  - `prior_net_income` → `prior_net_income_owners` / `prior_net_income_total`, same split, read from the prior-year XBRL context.
  - Three new filed-fact fields ship the J-GAAP balance-sheet components directly instead of requiring anyone to reconstruct them: `shareholders_equity` (株主資本), `valuation_translation_adjustments` (評価換算差額等), `non_controlling_interests` (非支配株主持分 / NCI). None are summed to derive `net_assets_owners` — component facts stay components.
  - **Tombstones, not silent breakage.** Reading `report.net_assets`, `report.net_income`, or `report.prior_net_income` raises `AttributeError` naming the replacement field(s) and which ownership basis each carries. Constructing a `SecuritiesReport` with any of the three as a keyword argument raises `TypeError` (the dataclass rejects unknown fields for free).
  - **The equity-ratio identity check is now scoped to the correct ownership basis per standard**, rather than comparing an owners-only ratio against a mismatched-basis net-assets figure: IFRS/US-GAAP check `equity_ratio` against `net_assets_owners`; J-GAAP checks it against `shareholders_equity + valuation_translation_adjustments` (an in-check-only sum, never shipped as data). There is deliberately no `owners <= total` rule anywhere: a subsidiary's minority shareholders can themselves post a loss, so a filer's owners-attributable figure can legitimately exceed its total-including-non-controlling-interests figure. Both directions are pinned on a real-filing counterexample in the new golden-fixture panel (Tests, below).
  - Extracted figures reconcile with issuer-stated ratios within tolerance across a full-corpus verification run of 36,686 real filings, externally verified against issuer publications for an 8-company fixture panel spanning J-GAAP, IFRS, and US-GAAP.

### Added

- Extraction validation: typed numeric fields are checked against structural
  bounds and accounting identities at parse time. A value that is structurally
  impossible under its field's name is withheld (field set to None) and
  recorded in the new `extraction_flags` list on every parsed report; identity
  mismatches are annotated without altering any field. Raw values always
  remain in `raw_fields`.
- Tender-offer registration filings annotate a sanity flag when the stated cover-page filing date exceeds the API submit date by more than 30 days; the stated date is never overwritten.
- New IFRS debt fields (bonds_and_borrowings / borrowings, current and non-current); IFRS debt is no longer silently absent, and is never coerced onto the J-GAAP debt fields.
- **`net_income_total` / `prior_net_income_total` gain an IFRS-only last-resort tier**, on `jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults`. Some IFRS filers tag this total-basis element but tag no owners-basis element anywhere, leaving `net_income_total` structurally `None` even though the filing states a total-basis profit figure. Fills only when every earlier tier is `None`; never overrides a value from an earlier tier; never read by non-IFRS filers. Full-corpus re-parse: 363 `net_income_total` fills, 361 `prior_net_income_total` fills (2 rows have no prior-period context, e.g. IPO-year filings) — fills only, 0 changes to previously-populated values.

### Fixed

- Securities brokers' operating revenue (営業収益) now populates net_sales; previously None for broker-ordinance filers.
- IFRS filers tagging operating profit under filer-custom namespaces now populate operating_income; financial-sector revenue and bank-profit elements are deliberately not mapped (different concepts).
- IFRS and US-GAAP filers now populate net assets per share (IFRS via the per-share equity element previously exposed only as ifrs_summary_bps; US-GAAP via an alternate stockholders-equity-per-share element).
- IFRS and US-GAAP filers whose highlight table discloses only a single combined equity line (no owners-of-parent / non-controlling-interest split) now populate `net_assets_total` via the total-equity element instead of returning None. `net_assets_owners` correctly stays None for these rows — the filing simply doesn't tag an owners-only figure — so the owners-basis equity-ratio identity check now skips them instead of annotating a false ownership-basis mismatch.
- Tender-offer family: the leading 【対象者名】 form label is stripped from target company names.
- **Company search now matches across character widths.** Full-width Latin and digit queries (ＱＰＳ, ＫＥＹＥＮＣＥ — what Japanese IMEs naturally produce) and half-width katakana returned zero results from `search_companies` and `resolve_company_identifier`, because the search compared raw lowercased strings while catalog names mix widths (三菱ＵＦＪ carries full-width ＵＦＪ). Queries and index keys are now width-normalized, matching the behavior `search_entities` already had.
- **The company-not-found error now suggests a function that exists.** The message pointed at `search_companies()` / `get_supported_companies()`, which were removed from the package surface in 0.2.0; it now points at `search_entities()`.
- **`extract_csv_from_zip` (the reader every typed parser uses) could silently mojibake a non-BOM UTF-8 CSV into one garbage row.** Its encoding-trial order tried `utf-16le` before `utf-8`; `utf-16le` barely validates anything, so a UTF-8 file with an even byte count could decode "successfully" into nonsense before `utf-8` ever got a turn. Pre-dates 0.8.0 and is unrelated to the chardet retirement (this function never used chardet) — latent because every existing test happened to feed it only `utf-16le`-encoded content; surfaced by the 0.8.0 zero-dependency smoke test parsing a real, non-BOM fixture. Fixed by trying `utf-8` first (it rejects non-utf-8 bytes outright, so it fails fast and falls through correctly). Real EDINET files are UTF-16-LE with a BOM and are unaffected — those BOM bytes are never valid UTF-8.
- **IFRS-transition filings were serving J-GAAP figures on `equity_ratio` / `total_assets` / `net_assets_total`, tagged as IFRS.** A filing from a company transitioning to IFRS (or filed during the transition year) sometimes carries two consolidated highlights tables — a legacy J-GAAP table alongside the IFRS one — both tagged at the same bare current-year context. The waterfalls tried the J-GAAP elements first regardless of the filing's own accounting standard, so these three fields served J-GAAP-basis figures on rows the filing itself tagged IFRS, while `net_assets_owners` (IFRS-only by construction) correctly read the IFRS side — a cross-standard chimera on the same row. Fixed by trying the IFRS-specific elements first whenever `AccountingStandardsDEI` = IFRS, falling back to the legacy tiers only when no IFRS-specific element exists; other standards are unaffected. Found by a full-corpus cross-field identity check (see Tests, below): every one of the 138 filings the check flagged was re-verified against the raw CSV — 136 (101 distinct filers) were this defect, 2 were genuine filer-house-definition ratios (unrelated, unchanged). Affects 222 filings in the verification corpus: 194 served a J-GAAP figure on at least one of the three fields under the old order; the remaining 28 are IFRS filings whose diffs were confirmed against the raw CSVs by the same re-parse. A full-corpus old-vs-new re-parse confirmed diffs land on exactly this set and nothing else.
- **Semi-annual reports (Doc 160/170) now read financial figures context-aware, and expose `accounting_standard` + `is_consolidated`.** The parser previously took the first matching row in file order for a given element — but EDINET's semi-annual CSVs list the prior period's row before the current period's, so this systematically returned the prior period's value under the current-period field name. The parser now resolves the filing's own current-period context token (the taxonomy is bimodal: `Interim*` for the older regime, `CurrentQuarter*` for the newer one) instead of taking the first row; consolidated filers use a strict bare-context read that never borrows the parent/non-consolidated figure. `accounting_standard` and `is_consolidated` are read from DEI, honest-`None` when the filing doesn't tag them. Applies to all 16 financial fields: 8 core (`total_assets`, `current_assets`, `total_liabilities`, `current_liabilities`, `net_assets`, `operating_income`, `ordinary_income`, `profit_loss`) and 8 fund-specific (`principal`, `surplus_deficit`, `reserve_for_distribution`, `operating_revenue`, `operating_expenses`, `management_fee`, `trustee_fee`, `distributions`). Full-corpus re-parse against the currently-stored values (18,484 rows: fund cohort 9,465 / 51.2%, listed_company 7,700 / 41.7%, unlisted_company 1,319 / 7.1%): roughly 17,100–17,400 rows change at least one financial column. Separately, 40 rows (22 documents, fund filers only) recover a management fee, trustee fee, or P&L figure the earlier read missed entirely — the old first-row read stopped at a null-tagged prior-period row while an independently-tagged current-period row carried the real value; for 3 of those documents the recovered figure was independently cross-checked against the filer's own printed expense total and matched exactly.
- **Tender-offer results (Doc 270/280): two voting-rights fields remapped, two retired.** The results filing uses its own voting-rights letter scheme (a, d, g), distinct from the registration filing's (a, d, g, j) despite near-identical labels. `total_voting_rights` and `voting_rights_special_interest` were mapped to the registration-side letters and had 0 real fills; remapped to the results-side elements a full-namespace census confirmed present. `voting_rights_purchased` and `purchase_ratio` have no backing element anywhere in the namespace on either side; retired to honest `None` rather than derived. Added non-negative-only bounds (over-tender ratios legitimately exceed 1.0) and a real completed-purchase fixture pinned against the raw CSV. Full-corpus re-parse (610 filings): `total_voting_rights` 473 fills, `voting_rights_special_interest` 298 fills (175 of the 473 mapped-cohort rows are present-but-stated-`－`, stay honest `None`); the two previously-working fields (`voting_rights_owned_by_offeror`, `holding_ratio_after`) unchanged (456/473 and 463/473 numeric, respectively); the two retired fields are `None` for all 610 filings; the 137-filing issuer-self-tender cohort is honest-`None` on all six fields structurally, not a gap.

### Known gaps (deferred)

- **Quarterly reports (Doc 140/150) do not yet get the per-standard element gate.** The same internal-refactor pass that migrated the securities parser to tier tables (and fixed the highlights-table defect above) also moved the quarterly parser to tier tables, but deliberately without a per-standard gate — an IFRS or US-GAAP quarterly filer can still read a J-GAAP element ahead of their own standard's element on a filing where both exist, the same defect class 0.7.1 closed for `operating_income` on annual reports. No user-facing field or value changed in 0.8.0 — a full-corpus old-vs-new re-parse confirmed zero diffs on quarterly reports. Scoped and deferred to 0.9.0, not silently dropped.

### Removed

- **pandas (and transitively numpy) as dependencies** (suggested by Ben Allen). TSV parsing now uses the standard library's `csv` module. No behavior change; installation footprint drops accordingly.
- **`python-dateutil` as a dependency.** `_derive_quarter_number`'s only use of it — subtracting one year and adding one day to derive a fiscal-year start — is now stdlib `date.replace()` (with the Feb-29-clamps-to-Feb-28 case handled explicitly, matching `relativedelta`'s default) plus `date + timedelta(days=1)`. No behavior change, verified against the old `relativedelta`-based implementation across leap-year and year-boundary dates.
- **`python-dotenv` as a dependency.** The package no longer loads `.env` files as an import side effect — `config.py` reads `EDINET_API_KEY` from `os.environ` only. Apps that keep their key in a `.env` file should call `load_dotenv()` themselves before importing `edinet_tools` (see the README's Configuration section). No change for anyone already exporting the variable into their environment.
- **`chardet` as a dependency — edinet-tools now has zero runtime dependencies.** `chardet`'s one call site (`utils.detect_encoding`) is gone; `read_csv_file` tries a fixed, explicit encoding order instead of a statistical guess. Reader unification: both TSV readers (`utils.read_csv_file`, file-path-based; `parsers.extraction._read_csv_from_zip`, in-zip-bytes-based, used by every typed parser) now parse rows through the same fail-loud core (`utils.parse_strict_tsv`) — an unterminated quoted field or a row with more columns than the schema raises `csv.Error` instead of silently absorbing or truncating; a short row is padded with `None`, not rejected. In `extract_csv_from_zip`, a row-shape failure excludes that one CSV file from the archive (logged) — sibling files in the same zip are unaffected. Encoding-detection semantics are unchanged for every stored EDINET filing class: real filings are UTF-16-LE with a BOM, decoded correctly on the first or second encoding tried in both readers, with or without chardet. One real behavior change surfaced and fixed during the retirement: `read_csv_file`'s encoding order previously tried the (barely-validating) UTF-16 family before UTF-8; chardet's statistical guess masked this by usually getting tried first. Without chardet, a short UTF-8-encoded fixture with an even byte count could decode as UTF-16 "successfully" into mojibake rather than raising. Fixed by trying `utf-8` before the UTF-16 family (UTF-8 rejects almost any non-UTF-8 byte sequence outright, so it fails fast and correctly falls through for real UTF-16-LE-BOM files — the BOM bytes are never valid UTF-8). Caught by the existing pandas-migration behavior pins (`tests/test_read_csv_file.py`), not a new test.
- **The legacy `EdinetClient` class**, deprecated since 0.2.0. Use the module-level functions instead: `edinet_tools.configure()`, `edinet_tools.documents()`, `entity.documents()`, and `doc.fetch()` / `doc.parse()`. The migration table in the 0.2.0 notes still applies.
- **The deprecated boolean shims** retired in the 0.6.1 fact-shaped API transition: `Entity.is_listed`, `Entity.is_fund_issuer`, `EntityClassifier.is_listed()` (use `entity_type` / `get_entity_type()` — an `EntityType` enum that preserves the unknown case), `TreasuryStockReport.has_board_authorization` / `has_shareholder_authorization` (read the `by_board_meeting` / `by_shareholders_meeting` text blocks directly), and `utils.process_zip_directory()` (use `extract_csv_from_zip` / `extract_csv_to_disk`).
- **The legacy `processors.py` / `parser.py` document-processing pipeline** (`BaseDocumentProcessor` and its five subclasses, `process_raw_csv_data`, `EdinetXbrlCsvParser`, `extract_xbrl_financial_data`, `FinancialMetric`, `TextBlock`), plus `utils.process_zip_file` — the file-path-based glue that dispatched into it. An exposure audit found these reachable only from each other, `utils.process_zip_file`, and their own tests — never from `__init__.py`, never from README/docs/examples, and never from the modern typed-parser pipeline (`edinet_tools.parsers`, which has used `extract_csv_from_zip` + per-doc-type parsers since 0.2.0). Nothing to extract-then-keep, unlike the `EdinetClient` precedent — this was dead code, removed outright. `utils.read_csv_file` / `detect_encoding` / `clean_text` are unaffected and remain.
- **The dead `[analysis]` install extra.** `pip install edinet-tools[analysis]` pulled in llm, pydantic, matplotlib, and plotly for nothing — the analysis module was removed in 0.4.1. The unused LLM config block went with it, so importing the package without an LLM API key no longer logs a spurious "LLM analysis disabled" warning.

### Tests

- **Full-corpus equivalence proof for the 0.8.0 parser-internals migration.** Every stored filing with cached CSVs (176,460 docs: 79,935 securities, 77,425 quarterly, 19,100 semi-annual) was re-parsed with both the pre-migration and post-migration parser and diffed. Zero unexplained diffs — every diff landed on the pre-registered, mechanism-verified set the highlights-table fix above predicted, and nothing else. Quarterly and semi-annual: zero diffs (both migrations are behavior-preserving as shipped; semi-annual's context/standard-aware read above ships as a separate, additive change, not part of this proof).
- **Full-corpus cross-field identity check (independent of the equivalence proof above).** `equity_ratio` computed from each filing's own `total_assets` and owners-equity operands, compared against the filer's own stated ratio, absolute tolerance ±0.02: J-GAAP 30,338 of 30,340 evaluable filings agree (99.99%; the 2 exceptions are known filer-side reporting outliers, not extraction defects), US-GAAP 77 of 77. This is the check that surfaced the highlights-table defect above for IFRS; the post-fix full-corpus re-run has since completed and leaves two outliers, both filer-side — the agreement rate itself is not published here pending the maintainer's decision on where it belongs in public copy.
- **Eight-company golden-fixture panel for the ownership-basis split** (Toyota, ITOCHU, HOYA, Kansai Paint, Shimamura, Horii Food Service, Shiga Bank, Komatsu) — J-GAAP, IFRS, and US-GAAP; mega-cap and small-cap; with and without non-controlling interests; a financial-sector filer; and HOYA as the owners-exceeds-total counterexample. Every figure cross-checked to the yen against the issuer's own published results, on both ownership bases where both are published.
- Test count: 836 → 908 (4 xfailed).
- **Test count: 908 → 1030 across the parser-migration work** — new golden-fixture panels for the highlights-table fix, the semi-annual context/standard fix, the tender-results remap, and the `ProfitLossIFRS` last-resort tier (all above), plus the tier-table migration's own behavior-pin tests.
- **Test count: 1030 → 990 (4 xfailed) across the dependency-retirement work.** The drop is entirely `test_processors.py` (675 lines) and `test_document_processing_core.py` (562 lines) — dedicated test files for the `processors.py` / `parser.py` legacy pipeline removed above, plus the `TestZipFileProcessing` class in `test_file_processing.py` (same removal). No behavior-pin test for surviving code was touched or weakened; a new regression test (`TestExtractCsvFromZipEncodingOrder`) was added for the encoding-order fix in the chardet-retirement work.

## v0.7.1 — 2026-06-12

Correctness release for the securities report parser. Income-statement fields are now selected per accounting standard, several element mappings pointed at XBRL ids that don't exist in real filings, and banks, insurers, and securities firms now get real revenue figures.

### Fixed

- **`operating_income` is now selected per accounting standard.** Previously every filer was read through the J-GAAP element first, so IFRS and US-GAAP companies could pick up a parent-company figure. Each standard now reads its own operating-profit elements, including `OperatingIncomeLossUSGAAPSummaryOfBusinessResults` (v0.7.0 wrongly claimed no US-GAAP element exists; Sony and others tag it). Filers whose statements have no operating-profit subtotal, like IFRS trading houses, return `None` instead of a wrong number. Applies to current and prior year.
- **IFRS `equity_ratio` was storing equity per share, in yen.** The element it read (`EquityToAssetRatioIFRSSummaryOfBusinessResults`) is named misleadingly; its real meaning is per-share equity. `equity_ratio` now reads the actual ratio element. The per-share value still feeds `ifrs_summary_bps`.
- **IFRS `current_liabilities` was always `None`.** It was mapped to an element that doesn't exist in real filings; the real one is `TotalCurrentLiabilitiesIFRS`. Also added the missing deferred-tax-assets and depreciation fallbacks.
- **The J-GAAP cash-flow fallback tier never fired.** All three element ids were wrong. Replaced with the real `jppfs_cor:NetCashProvidedByUsedIn*Activities` elements.

### Added

- **Revenue for financial-sector filers.** Banks and insurers report 経常収益 and securities firms 営業収益 rather than net sales. `net_sales` now reads those elements when the standard ones are absent. Previously these filers returned `None` or picked up a small sub-business line. Known gap: securities firms that tag only `OperatingRevenueSEC`-style variants still return `None`; mapping planned.
- **US-GAAP balance sheet and cash flows.** Total assets, equity, equity ratio, book value per share, and the three cash-flow figures now populate for US-GAAP filers, via the `...USGAAPSummaryOfBusinessResults` elements.

### Tests

- Five new golden fixtures from real, unedited filings (Itochu, Toyota Tsusho, HS Holdings, MUFG, Canon), pinned to exact values. Test count: 798 → 832.
- Output cross-checked against the issuers' own earnings releases for 20 filings across J-GAAP, IFRS, and US GAAP. Every populated figure matched to the yen.

### Note for existing databases

Parser fixes apply on re-parse. Rows extracted with earlier versions keep their old values. Re-extract IFRS, US-GAAP, and financial-sector filings — and make sure your update path writes `None` over old values rather than skipping them, since some fields are now correctly `None`.

## v0.7.0 — 2026-05-29

Segment-information parsing, a consolidated-revenue data-quality fix for IFRS/US-GAAP filers, registry-based filer classification, and the fact-shaped API transition (`Entity.entity_type`).

### Added

- **`SegmentRow` + `parse_segments_from_csv()`** — per-segment metrics from annual securities reports. Anchored-union discriminator (anchor on segment-name suffixes; admit aggregation rows only when they carry a segment-exclusive element), plus a no-anchor path that recovers industry/sector-named segments by seeding from segment-specific aggregation rows. Zero over-extraction across the broad-sample harness.
- **`SecuritiesReport` fields**: `segments`, `segments_text_only` (segment data in HTML text-blocks, not CSV), `segments_extraction_incomplete` (aggregation rows present but no segments extracted — honest miss flag).
- **US-GAAP summary income-statement elements** mapped (revenue, profit-before-tax, net income, EPS, ROE) — US-GAAP filers previously extracted as `None`. No operating-income line in the US-GAAP summary, so `operating_income` is honestly `None`.
- **`LargeHoldingReport.is_joint_filing`** — derived from `FilerLargeVolumeHolder<N>Member` axis presence (N ≥ 2), not hardcoded `False`.
- **`Fact` + `ParsedReport.raw_facts`** — typed access to the full XBRL fact set, alongside `raw_fields` / `text_blocks` / `unmapped_fields`.
- **`extract_dimensional()`** — axis-context primitive with member-name cleaning; substrate for segments and future schedule-table parsers.
- **`Entity.entity_type`** (`EntityType` enum) — fact-shaped FSA-registry classification; replaces the deprecated `is_listed` / `is_fund_issuer` booleans.
- **`extract_csv_to_disk()` + `Document.save_extracted_csvs()`** — disk-output helpers complementing in-memory `extract_csv_from_zip()`.

### Fixed

- **Consolidated revenue for IFRS / US-GAAP filers** — `net_sales` (and other income-statement metrics) returned the non-consolidated **parent** figure (e.g. ¥18T parent vs ¥48T consolidated). Now a consolidated filer never substitutes the parent value: a missing consolidated value falls through to the next element/tier or to honest `None` (parent stays in the fact-bag). With IFRS/US-GAAP/custom-namespace revenue elements mapped, the full cohort reads consolidated. Pinned by real-filing golden fixtures.
- **Holder names HTML-unescaped** — `_normalize_holder_value` applies `html.unescape`, so Doc 350 filer names with `&amp;` etc. are clean text.
- **`ExtraordinaryReport` / `SemiAnnualReport` filer classification** — `is_fund` returned `True` for ~all recent corporate filings (EDINET `'－'` placeholders broke the DEI heuristic). Now classified via the FSA registry (`report.filer.entity_type`); parsers expose `filer_edinet_code` as a fact.
- **`TreasuryStockReport` authorization flags** — `has_board_authorization` / `has_shareholder_authorization` no longer return `True` for empty/whitespace text blocks.
- **`QuarterlyReport.is_consolidated` and `SecuritiesReport.is_consolidated`** now return `None` when the `WhetherConsolidatedFinancialStatementsArePreparedDEI` element is missing, rather than silently defaulting to `True`. Honest unknowns over silent-failure-as-default.
- **`extract_dimensional()` member names** are stripped of per-filer extension namespace prefixes (e.g., `E03847-000DomesticLifeInsuranceReportableSegments` → `DomesticLifeInsuranceReportableSegments`), matching `segments.py`'s `_clean_member_name()`. Avoids requiring every consumer to re-implement the cleaning.

### Deprecated

The deprecations below all emit `DeprecationWarning`. They will be removed in a future major release; consumers should migrate to the fact-shaped equivalents.

- **`Entity.is_listed`** — use `entity.entity_type == EntityType.LISTED_COMPANY`.
- **`Entity.is_fund_issuer`** — use `entity.entity_type == EntityType.FUND`.
- **`EntityClassifier.is_listed(edinet_code)`** — use `classifier.get_entity_type(code) == EntityType.LISTED_COMPANY`.
- **`TreasuryStockReport.has_board_authorization`** — use `bool(parsed.by_board_meeting and parsed.by_board_meeting.strip())` directly.
- **`TreasuryStockReport.has_shareholder_authorization`** — use `bool(parsed.by_shareholders_meeting and parsed.by_shareholders_meeting.strip())` directly.
- **`utils.process_zip_directory()`** — use `extract_csv_from_zip()` for in-memory CSV extraction or `extract_csv_to_disk()` for disk output (both in `edinet_tools.parsers.extraction`).
- **All public methods on `EdinetClient`** (`get_documents_by_date`, `get_recent_filings`, `get_company_filings`, `search_companies`, `download_filing_raw`, `download_filing`, `download_filings_batch`, `extract_filing_data`) — use the module-level functions and `Document` / `Entity` classes instead. Migration paths are named in each method's `DeprecationWarning` message.

### Removed

- **`ExtraordinaryReport.is_fund` / `SemiAnnualReport.is_fund`** and the intermediate `filer_namespace` field — replaced by registry-based classification via `report.filer.entity_type`.
- **`parsers.namespace_helpers`** (`infer_filer_type()`) — namespace inference conflated the shared `jppfs_cor:` taxonomy with corporate-only signal; parsers now expose facts, consumers classify via the FSA registry.
- **`parser.extract_mtp_targets()`** — dead code, zero callers.

### Tests

- Audit-closure remediation across routing / processor / API test families (real-ZIP body-execution assertions, dead-fixture removal).
- Real-EDINET golden fixtures per failure class (segments incl. no-anchor, consolidated-revenue, blast-radius characterization).
- Test count: 612 → 798.

## v0.6.0 — 2026-05-12

### Added

- `normalize_for_matching(s)` — public name-matching helper. NFKC normalization, `(株)` → `株式会社` / `(有)` → `有限会社` rewrites, katakana / Latin middle-dot stripping (`・` U+30FB, `·` U+00B7), whitespace collapse (runs folded to a single ASCII space; whitespace preserved between words so `Toyota` doesn't match `Toyo Tanso`), lowercase. Idempotent.
- `entity_by_corporate_number(num)` — O(1) lookup by 13-digit 法人番号 (Japan Corporate Number).
- `Entity.name_phonetic` and `Entity.corporate_number` now populated for classifier-path entities. Sourced from the `Submitter Name (phonetic)` and `Submitter's Japan Corporate Number` columns of `EdinetcodeDlInfo.csv`.
- GitHub Actions CI workflow (`.github/workflows/test.yml`) — multi-Python test matrix on push and pull_request.

### Changed

- `search_entities()` — O(1) exact-match via reverse index; substring-fallback path uses pre-normalized forms on both sides. Visually-identical strings with different Unicode encodings (full-width vs half-width Latin, `（` vs `(`, `㈱` vs `株式会社`, middle-dot variants like `モルガン・スタンレー` vs `モルガンスタンレー`) now resolve to the same entity.
- `search_entities()` bidirectional whitespace handling — when a query like `山田太郎` doesn't exact-match, falls back to the whitespace-collapsed catalog form, recovering names where the catalog stores them with internal spaces (`山田 太郎`). Particularly relevant for Japanese individual-filer names.
- `entity_by_ticker()` — O(N) scan replaced with O(1) reverse-index lookup. Now also handles alphanumeric tickers (`192A`, `263A`, `275A`-class).

### Not changed

- Public API signatures and return shapes — drop-in upgrade for existing callers.

### Known limitations (documented as xfail tests)

- Punctuation / symbol / abbreviation variance (`Co Ltd` ↔ `Co., Ltd.`, `&` ↔ `and`, `Inc` ↔ `Incorporated`).
- Queries with trailing parentheticals longer than the catalog name (e.g. `(信託口)` trust-account suffixes) — downstream consumers needing this should pre-strip before calling `search_entities`.
- Trust banks (`日本マスタートラスト信託銀行` etc.) are not in the EDINET catalog at all — they exist in the 法人番号 corporate registry only. v0.7.0+ may add a `法人番号公表サイト` ingestion layer to cover them.

## v0.5.1

- More robust EN/JP catalog loader — resolves columns by header alias, accepts both Japanese and English variants of FSA's `EdinetcodeDlInfo.csv` and `FundcodeDlInfo.csv`, fails loudly on schema renames.
- Fund-precedence fix in `EntityClassifier` — listed-company status now wins over fund-registry membership (Credit Saison, JAFCO etc. no longer misclassified as funds).
- Industry translation — `industry` field normalized to English regardless of CSV variant; raw Japanese preserved separately. New `translate_industry_to_english()` public helper.
- `scripts/refresh_csvs.py` — downloads fresh CSVs from FSA.
- CSVs refreshed.

## v0.5.0

Typed parsers for all 42 EDINET document types.

## v0.4.3

Add `fetch_and_parse` API. Expose `industry` field on `Entity`.
