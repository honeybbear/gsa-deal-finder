#!/usr/bin/env python3
"""Render the GSA Deal Finder dashboard (index.html) from data/*.json.

No numbers are invented here: everything shown comes from checker.py output.
If a run found no deals, the page says so instead of filling the space.
"""

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else default


def money(x):
    return f"${x:,.0f}" if float(x) == int(float(x)) else f"${x:,.2f}"


def esc(x):
    return html.escape(str(x))


def fmt_close(raw):
    """GSA lists closing times in Central Time on its search pages; the API
    returns a naive timestamp, so show it as listed and say so."""
    if not raw:
        return "not listed"
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%b %d, %Y %I:%M %p") + " (as listed by GSA)"
    except ValueError:
        return esc(raw)


def deal_card(d):
    conf = esc(d["resale_confidence"])
    conf_note = ("published value range, low end used" if conf == "medium"
                 else "median of public snippet figures — rough estimate")
    srcs = "".join(
        f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["title"][:90])}</a></li>'
        for s in d["resale_sources"])
    return f"""
<article class="card deal">
  <h2>{esc(d["lot_name"])}</h2>
  <p class="meta">{esc(d["city"])}, {esc(d["state"])} &middot; closes {fmt_close(d["closing_date"])}<br>
  Sale {esc(d["sale_number"])}, lot {esc(d["lot_number"])}</p>
  <table>
    <tr><td>Current bid</td><td><b>{money(d["current_bid"])}</b></td></tr>
    <tr><td>Shipping allowance (est.)</td><td>{money(d["shipping_allowance"])} <span class="note">planning allowance, not a quote</span></td></tr>
    <tr><td>Fees assumed</td><td>$0 <span class="note">GSA lists no buyer&rsquo;s premium — verify on the lot page</span></td></tr>
    <tr><td><b>Total cost estimate</b></td><td><b>{money(d["total_cost_estimate"])}</b></td></tr>
    <tr><td>Resale reference</td><td>{money(d["resale_reference"])} <span class="badge {conf}">{conf} confidence</span><br><span class="note">{conf_note}</span></td></tr>
    <tr class="margin"><td>Estimated margin</td><td><b>{money(d["estimated_margin"])} ({d["estimated_margin_pct"]}%)</b></td></tr>
  </table>
  <p class="sources"><b>Resale reference sources:</b></p>
  <ul class="sources">{srcs}</ul>
  <p><a class="btn" href="{esc(d["gsa_search_url"])}" target="_blank" rel="noopener">Find this lot on GSA Auctions &rarr;</a><br>
  <span class="note">{esc(d["gsa_search_hint"])}</span></p>
</article>"""


def evaluated_row(e):
    return (f"<tr><td>{esc(e['lot_name'])}</td><td>{money(e['current_bid'])}</td>"
            f"<td>{money(e['total_cost_estimate'])}</td><td>{money(e['resale_reference'])} "
            f"({esc(e['resale_confidence'])})</td><td>{e['estimated_margin_pct']}%</td></tr>")


def main():
    deals = load("deals.json", {"deals": []})
    ev = load("evaluated.json", {"evaluated": [], "skipped": []})
    inv = load("inventory.json", {"categories": [], "total_lots": 0})
    log = load("run_log.json", {})
    generated = deals.get("generated_utc", "unknown")
    try:
        gen = datetime.fromisoformat(generated).strftime("%b %d, %Y %I:%M %p UTC")
    except ValueError:
        gen = esc(generated)

    if deals["deals"]:
        deals_html = "".join(deal_card(d) for d in deals["deals"])
    else:
        deals_html = ('<p class="empty">No lots cleared the 50% bar on this run. '
                      'That is a real result, not a missing page — the checker only flags a lot '
                      'when bid + shipping allowance is under half of a public resale reference. '
                      'Check back after the next refresh.</p>')

    ev_rows = "".join(evaluated_row(e) for e in ev["evaluated"]) or \
        '<tr><td colspan="5">None this run.</td></tr>'
    skips = "".join(f"<li>{esc(s['lot_name'])} — {esc(s['reason'])}</li>"
                    for s in ev["skipped"]) or "<li>None.</li>"
    cats = sorted(inv["categories"], key=lambda c: c["total"] or 0, reverse=True)[:10]
    cat_rows = "".join(
        f"<tr><td>{esc(c['name'])}</td><td>{c['total']}</td></tr>" for c in cats)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GSA Deal Finder — undervalued federal surplus</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;padding:0 14px 40px;color:#1a1a1a;background:#f7f7f5;line-height:1.5}}
main{{max-width:720px;margin:0 auto}}
h1{{font-size:1.6rem;margin:18px 0 4px}}h2{{font-size:1.15rem;margin:0 0 6px}}
.sub{{color:#555;margin:0 0 16px}}
.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:16px;margin:14px 0}}
.deal{{border-color:#2a7d4f;border-width:2px}}
.meta{{color:#555;font-size:.9rem}}
table{{width:100%;border-collapse:collapse;font-size:.95rem}}
td{{padding:5px 4px;border-bottom:1px solid #eee;vertical-align:top}}
td:last-child{{text-align:right}}
tr.margin td{{font-size:1.05rem}}
.note{{color:#666;font-size:.82rem}}
.badge{{display:inline-block;padding:1px 8px;border-radius:99px;font-size:.78rem;font-weight:700}}
.badge.low{{background:#fde8c8;color:#7a4a00}}
.badge.medium{{background:#d8ecff;color:#0b4f8a}}
.badge.none{{background:#eee;color:#555}}
ul.sources{{font-size:.85rem;padding-left:18px}}
.btn{{display:inline-block;background:#2a7d4f;color:#fff!important;text-decoration:none;padding:9px 16px;border-radius:8px;font-weight:700;margin:6px 0}}
.box{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:16px;margin:14px 0}}
.warn{{border-color:#b45309;background:#fffaf0}}
.empty{{background:#fff;border:1px dashed #aaa;border-radius:12px;padding:16px}}
footer{{color:#666;font-size:.82rem;margin-top:24px}}
a{{color:#0b5cab}}
</style>
</head>
<body><main>
<h1>🏛️ GSA Deal Finder</h1>
<p class="sub">Undervalued federal surplus on GSA Auctions, checked against public resale references. Last refresh: <b>{gen}</b></p>

<section>
<h2>Flagged deals ({len(deals["deals"])})</h2>
<p class="note">A lot is flagged ONLY when current bid + a shipping allowance is under 50% of a public resale reference. Margins are estimates, not promises.</p>
{deals_html}
</section>

<section class="box">
<h2>Checked but not flagged</h2>
<table>
<tr><th style="text-align:left">Lot</th><th>Bid</th><th>Total est.</th><th>Resale ref.</th><th>Margin</th></tr>
{ev_rows}
</table>
<p class="note">Skipped this run:</p>
<ul class="sources">{skips}</ul>
</section>

<section class="box">
<h2>How the method works</h2>
<ol>
<li>Pull live lots from GSA Auctions' public trending feed.</li>
<li>Keep only lots with a specific model identifier (year/make/model or brand+model).</li>
<li>Find a public resale reference from search-result snippets (value guides, dealer and auction listings). A published value range uses its low end; otherwise the median of snippet figures from at least two domains.</li>
<li>Flag a DEAL only when bid + shipping allowance is under 50% of that reference. GSA lists no buyer's premium; verify on the lot page before bidding.</li>
<li>Prefer local pickup where possible — shipping is the fastest margin killer.</li>
</ol>
</section>

<section class="box warn">
<h2>Honest limitations — read before acting</h2>
<ul>
<li><b>Coverage is partial.</b> GSA's full lot search requires a logged-in session token; this checker does not create accounts, so it scans the public trending feed (10 lots per run) against {inv["total_lots"]} total lots across {len(inv["categories"])} categories. Most inventory is NOT scanned. Browse the <a href="https://www.gsaauctions.gov/auctions/search?status=active" target="_blank" rel="noopener">public GSA search</a> yourself for the rest.</li>
<li><b>eBay sold prices are unavailable to automation</b> (eBay returns 403 to bots), so resale references come from public search snippets — asking prices and value guides, not completed sales. Treat every margin as rough, and re-verify a specific lot's resale value before bidding.</li>
<li><b>References move between runs</b> as search results change. A deal flagged today can disappear tomorrow.</li>
<li><b>As-is condition.</b> Surplus is sold as-is, where-is. Inspection is strongly recommended; condition problems can erase the whole margin.</li>
<li><b>Shipping allowances are planning numbers, not quotes.</b> Heavy items can cost far more to move than the allowance.</li>
<li><b>No guaranteed profit.</b> Bids rise, items disappoint, resale markets move. This page is educational only, not financial advice, and it never buys anything on your behalf.</li>
</ul>
</section>

<section class="box">
<h2>GSA inventory right now ({inv["total_lots"]} lots)</h2>
<table>
<tr><th style="text-align:left">Category</th><th>Lots</th></tr>
{cat_rows}
</table>
<p class="note">Source: GSA/PPMS public category-counts feed, same refresh as above.</p>
</section>

<footer>
<p>Sources: GSA Auctions public trending feed (ppms.gov gateway), GSA/PPMS category counts, DuckDuckGo HTML search snippets for resale references. Every number on this page traces to a fetched source listed with it. No affiliate links. No earnings claims. No account creation, no purchases, no contact with sellers — this page only finds and shows.</p>
<p>Built by an automated checker. Note: scheduled runs from GitHub's network are currently blocked by GSA's gateway (HTTP 403), so refreshes happen from an unblocked host — the timestamp above is the last successful refresh. A failed refresh never overwrites good data. If a run finds nothing, the page says so.</p>
</footer>
</main></body></html>"""
    (ROOT / "index.html").write_text(page)
    print(f"wrote index.html with {len(deals['deals'])} deals")


if __name__ == "__main__":
    main()
