# GSA Deal Finder

Finds undervalued federal surplus on [GSA Auctions](https://www.gsaauctions.gov/auctions/search?status=active) (gsaauctions.gov) and checks it against a public resale reference. Live dashboard: https://honeybbear.github.io/gsa-deal-finder/

## The method

1. Pull live lots from GSA Auctions' public trending feed.
2. Keep only lots with a specific model identifier (year/make/model or brand+model).
3. Find a public resale reference from search-result snippets (value guides, dealer and auction listings). A published value range uses its low end; otherwise the median of snippet figures from at least two domains.
4. Flag a **DEAL** only when **current bid + shipping allowance is under 50% of the resale reference**. GSA lists no buyer's premium; verify on the lot page before bidding.
5. Prefer local pickup where possible — shipping is the fastest margin killer.

## Sources (all free, public, no keys, no logins)

- GSA/PPMS trending feed: `https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/trending-auctions` (works without auth — verified live 2026-10-25)
- GSA/PPMS category counts: `https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/categoryCounts` (works without auth)
- Resale references: DuckDuckGo HTML search snippets (KBB/Edmunds-style value ranges, dealer/auction listings)

## Honest limitations

- **Partial coverage.** GSA's full lot search API requires a bearer token issued by the PPMS shell to a logged-in browser session. This project does not create accounts, so the automated checker scans the public trending feed (10 lots per run) out of ~700 total lots. The dashboard says this plainly and links to the public GSA search for the rest.
- **eBay sold prices are NOT used.** eBay returns 403 to automated fetching. Resale references are therefore snippet-based (asking prices and value guides), labelled LOW or MEDIUM confidence, and they move between runs. Re-verify any lot's resale value before bidding.
- **As-is condition.** Surplus is sold as-is, where-is. Inspect before bidding; condition problems can erase the margin.
- **Shipping allowances are planning numbers** (vehicles $750, heavy equipment $500, other $100), not quotes.
- **No guaranteed profit.** This page is educational only, not financial advice. It never buys anything, contacts anyone, or moves money.

## How it runs

- `checker.py` — fetches GSA lots, establishes resale references, applies the 50% rule, writes `data/*.json`.
- `build.py` — renders `index.html` from `data/*.json`. If a run finds no deals, the page says so.
- `.github/workflows/refresh.yml` — runs the checker + build every 6 hours (plus manual dispatch) and commits the results. GitHub Pages serves the site from `main`.

## Local use

```sh
python3 checker.py   # refresh data/*.json
python3 build.py     # rebuild index.html
```

Python 3 + `requests` only. No keys, no accounts, no purchases — ever.
