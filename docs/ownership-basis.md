# Ownership basis: owners-only vs. total

Consolidated financial statements sometimes include subsidiaries that
aren't 100% owned — outside investors hold a stake directly in the
subsidiary, not in the parent company. Accounting rules (Japanese GAAP,
IFRS, and US-GAAP alike) call that outside stake a **non-controlling
interest** (NCI; 非支配株主持分, sometimes "minority interest"). Because of
that, a single "net income" or "net assets" figure is ambiguous on its
own — does it include the outside investors' share, or only the piece
that belongs to the parent company's own shareholders?

edinet-tools never picks one silently. Every field where this is
ambiguous ships as an explicit pair:

- **`*_owners`** — attributable to the owners of the parent (親会社株主に帰属する /
  the IFRS and US-GAAP "attributable to [Company]" line). This is
  normally the headline figure in an earnings release, and the number
  EPS is computed from.
- **`*_total`** — includes the non-controlling interests' share too.

The two usually move together, but don't have to: if a subsidiary's
minority shareholders happen to lose money in a period, the parent's
owners-only figure can come out *higher* than the total-including-everyone
figure. That's a real, correctly-filed result, not a bug — so
edinet-tools never assumes `owners <= total` or the reverse. It ships
both numbers exactly as filed and leaves the comparison to you. See the
README's "Known limitations" section for a real-filing example of this
inversion (HOYA).

## Fields

| Field | Meaning | Notes |
|---|---|---|
| `net_assets_owners` | Equity attributable to owners of parent | **J-GAAP: always `None`** — Japanese GAAP never files this as a single element. The filed components are `shareholders_equity` + `valuation_translation_adjustments` (below). IFRS and US-GAAP filers populate it directly. |
| `net_assets_total` | Net assets including non-controlling interests (純資産) | Filed for all three standards. |
| `net_income_owners` | Profit attributable to owners of parent (親会社株主に帰属する当期純利益) | Filed for all three standards. |
| `net_income_total` | Profit including non-controlling interests' share | **US-GAAP: structurally `None`** for nearly all filers — no total-basis net-income element exists in that taxonomy tier. |
| `prior_net_income_owners` / `prior_net_income_total` | Same split, prior fiscal year | Same per-standard routing, read from the prior-year XBRL context. |
| `shareholders_equity` | 株主資本 — filed J-GAAP component | J-GAAP only. Never summed into `net_assets_owners` — it's a fact as filed, not a derived aggregate. |
| `valuation_translation_adjustments` | 評価換算差額等 — filed J-GAAP component | J-GAAP only, same rule as above. |
| `non_controlling_interests` | 非支配株主持分 (NCI) | Filed for all three standards; `None` when a filer has no minority-owned subsidiaries. |

If you need an owners-only equity figure for a J-GAAP filer, compute it
yourself from the two filed components
(`shareholders_equity + valuation_translation_adjustments`) — edinet-tools
ships the facts as filed and leaves that arithmetic to you.

Upgrading from before 0.8.0? `net_assets`, `net_income`, and
`prior_net_income` were removed — see [MIGRATING.md](../MIGRATING.md) for
the full field-by-field replacement table.
