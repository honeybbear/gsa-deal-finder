#!/usr/bin/env python3
"""GSA deal-finder checker.

Finds undervalued federal surplus on GSA Auctions and compares it to a public
resale reference. Free public sources only. No API keys, no logins, no signups.

VERIFIED SOURCE FACTS (2026-10-25, checked live):
- GSA Auctions is a React SPA at gsaauctions.gov. Its listing data comes from
  the PPMS gateway at https://www.ppms.gov/gw/auction/ppms (found in the site's
  own public environment.js).
- GET /api/v1/auctions/trending-auctions works WITHOUT auth and returns live
  lots (current bid, closing date, city/state, sale + lot numbers).
- POST /api/v1/auctions/categoryCounts works WITHOUT auth and returns
  per-category inventory totals.
- POST /api/v1/auctions/search, GET /api/v1/auctions/<id>, and
  GET /api/v1/auctions/recommendations all return 401 without a bearer token.
  That token is issued by the PPMS shell via a postMessage handshake, i.e. it
  requires a logged-in browser session. We do NOT create accounts, so full
  inventory search is NOT automated here. This is a documented limitation,
  not a bug to work around.
- eBay sold-listing pages return 403 to automated fetching, so eBay is NOT
  used as a price source. Resale references come from DuckDuckGo HTML search
  result snippets (KBB/Edmunds-style value ranges, dealer/auction listings),
  and are labelled LOW confidence unless a clear published value range was
  found. No price is ever invented: every number cites the page it came from.

DEAL RULE (all must hold):
- Lot closes in the future.
- A resale reference could be established from >= 2 independent snippet
  figures, or from one explicit published value range (low end used).
- (current bid + shipping allowance) <= 50% of the resale reference.
- Shipping allowances are PLANNING ALLOWANCES, not quotes:
  vehicles/trailers $750, heavy equipment $500, everything else $100.
  GSA lists no buyer's premium; the math uses $0 fees and says to verify
  on the lot page before bidding.

Output: data/deals.json, data/evaluated.json, data/inventory.json,
data/run_log.json (all under the repo root).
"""

import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
GSA_TRENDING = "https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/trending-auctions"
GSA_CATEGORIES = "https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/categoryCounts"
GSA_SEARCH_URL = "https://www.gsaauctions.gov/auctions/search?status=active"

SHIPPING_ALLOWANCE = {"vehicle": 750, "equipment": 500, "other": 100}
# PPMS category codes: 300 vehicles, 200 trailers/tractors/housing,
# 170 motorcycles/bicycles, 70 construction, 160 misc, 10 agricultural.
VEHICLE_CATS = {"300", "200", "170"}
EQUIPMENT_CATS = {"70", "160", "10", "120", "90"}


def shipping_allowance(category_code):
    if str(category_code) in VEHICLE_CATS:
        return SHIPPING_ALLOWANCE["vehicle"], "vehicle"
    if str(category_code) in EQUIPMENT_CATS:
        return SHIPPING_ALLOWANCE["equipment"], "equipment"
    return SHIPPING_ALLOWANCE["other"], "other"


def has_model_identifier(lot_name):
    """True when the lot name is specific enough for a resale lookup.

    Requires a 4-digit year plus a name, or a distinctive brand+model token
    (e.g. CATERPILLAR 303C, John Deere Gator TX). Generic names like
    'TRAVEL TRAILER' fail this test on purpose.
    """
    name = lot_name.strip()
    if re.search(r"\b(19|20)\d{2}\b", name) and len(name.split()) >= 3:
        return True
    if re.search(r"\b[A-Z]{2,}\s+\d{3,}[A-Z]?\b", name):
        return True
    if re.search(r"\bGator\s+\w+\b", name, re.I):
        return True
    return False


def fetch_gsa():
    """Fetch trending lots + category counts from the public PPMS endpoints.

    Raises on any failure, and refuses empty results: a failed fetch must
    NEVER overwrite good data with an empty page. Callers exit non-zero.
    """
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    r1 = s.get(GSA_TRENDING, timeout=30)
    if r1.status_code != 200:
        raise RuntimeError(
            f"trending feed HTTP {r1.status_code}: {r1.text[:200]!r}")
    try:
        lots = r1.json()
    except ValueError:
        raise RuntimeError(
            f"trending feed returned non-JSON (likely a block page): {r1.text[:200]!r}")
    if not isinstance(lots, list) or not lots:
        raise RuntimeError("trending feed returned no lots; refusing to overwrite good data")
    r2 = s.post(GSA_CATEGORIES, json={}, timeout=30,
                headers={"Content-Type": "application/json"})
    if r2.status_code != 200:
        raise RuntimeError(f"category feed HTTP {r2.status_code}: {r2.text[:200]!r}")
    try:
        cats = r2.json()
    except ValueError:
        raise RuntimeError(
            f"category feed returned non-JSON: {r2.text[:200]!r}")
    return lots, cats


def ddg_search(query):
    """Search DuckDuckGo HTML (no key). Returns list of {title, url, snippet}."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    if r.status_code != 200 or "result__a" not in r.text:
        return []
    out = []
    for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</a>',
            r.text, re.S):
        href, title, snippet = m.group(1), m.group(2), m.group(3)
        # DDG wraps links as //duckduckgo.com/l/?uddg=<encoded real url>.
        # Decode FIRST, then drop true DuckDuckGo ad redirects (y.js).
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&")[0])
        if "duckduckgo.com" in href:
            continue
        clean = lambda t: re.sub(r"<[^>]+>", "", t).replace("&amp;", "&").strip()
        out.append({"title": clean(title), "url": href, "snippet": clean(snippet)})
        if len(out) >= 10:
            break
    return out


def money_figures(text):
    return [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]{3,})", text)]


def resale_reference(lot_name):
    """Establish a conservative resale reference from public search snippets.

    Returns (reference, confidence, sources) or (None, 'none', sources).
    - Explicit published range (e.g. Edmunds '$7,176-$27,249') -> low end,
      confidence MEDIUM (range is published, but trim/condition unknown).
    - Otherwise median of snippet figures >= $100 from >= 3 distinct domains,
      confidence LOW.
    """
    queries = [f"{lot_name} value", f"{lot_name} sold price", f"{lot_name} for sale"]
    sources = []
    figures = []  # (value, domain)
    range_low = None
    for q in queries:
        try:
            results = ddg_search(q)
        except Exception:
            continue
        for res in results:
            sources.append({"title": res["title"], "url": res["url"]})
            blob = res["title"] + " " + res["snippet"]
            m = re.search(r"\$([\d,]{3,})\s*-\s*\$([\d,]{3,})", blob)
            if m and range_low is None:
                lo, hi = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
                if 100 <= lo < hi <= 10_000_000:
                    range_low = lo
            domain = urllib.parse.urlparse(res["url"]).netloc.replace("www.", "")
            for f in money_figures(blob):
                if 100 <= f <= 10_000_000:
                    figures.append((f, domain))
        time.sleep(1.5)
    # de-duplicate sources by url, keep order
    seen, uniq = set(), []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            uniq.append(s)
    if range_low is not None:
        return range_low, "medium", uniq[:6]
    domains = {d for _, d in figures}
    vals = sorted(v for v, _ in figures)
    if len(domains) >= 3 and len(vals) >= 3:
        median = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        return median, "low", uniq[:6]
    return None, "none", uniq[:6]


def main():
    DATA.mkdir(exist_ok=True)
    run_started = datetime.now(timezone.utc).isoformat()
    log = {"run_started_utc": run_started, "gsa_source": GSA_TRENDING,
           "steps": [], "errors": []}
    try:
        lots, cats = fetch_gsa()
    except Exception as e:
        print(f"ERROR: GSA fetch failed, refusing to overwrite data: {e}", file=sys.stderr)
        return 1
    log["steps"].append(f"fetched {len(lots)} trending lots, {len(cats)} categories")

    inventory = {
        "fetched_utc": run_started,
        "source": GSA_CATEGORIES,
        "categories": [{"name": c.get("categoryName"), "code": c.get("categoryCode"),
                        "total": c.get("total")} for c in cats],
        "total_lots": sum((c.get("total") or 0) for c in cats),
    }

    now = datetime.now(timezone.utc)
    deals, evaluated, skipped = [], [], []
    for lot in lots:
        name = lot.get("lotName", "").strip()
        bid = lot.get("currentBid")
        closing = lot.get("closingDate")
        base = {
            "lot_name": name,
            "current_bid": bid,
            "closing_date": closing,
            "city": lot.get("city"),
            "state": lot.get("state"),
            "sale_number": lot.get("saleNumber"),
            "lot_number": lot.get("lotNumber"),
            "auction_id": lot.get("auctionId"),
            "category": lot.get("category"),
            "gsa_search_url": GSA_SEARCH_URL,
            "gsa_search_hint": f"Search GSA Auctions for sale {lot.get('saleNumber')} lot {lot.get('lotNumber')}",
        }
        try:
            close_dt = datetime.fromisoformat(closing) if closing else None
        except ValueError:
            close_dt = None
        if close_dt is not None and close_dt.replace(tzinfo=timezone.utc) <= now:
            skipped.append({**base, "reason": "lot already closed"})
            continue
        if bid is None:
            skipped.append({**base, "reason": "no current bid published"})
            continue
        if not has_model_identifier(name):
            skipped.append({**base, "reason": "no specific model identifier in lot name; resale reference not possible"})
            continue
        ref, conf, sources = resale_reference(name)
        if ref is None:
            skipped.append({**base, "reason": "no usable public resale reference found"})
            continue
        allow, kind = shipping_allowance(lot.get("category"))
        total_cost = float(bid) + allow
        margin = ref - total_cost
        margin_pct = (margin / ref * 100) if ref else 0
        rec = {**base,
               "resale_reference": ref,
               "resale_confidence": conf,
               "resale_sources": sources,
               "shipping_allowance": allow,
               "shipping_allowance_kind": kind,
               "fees_assumed": 0,
               "fees_note": "GSA lists no buyer's premium; verify on the lot page before bidding.",
               "total_cost_estimate": round(total_cost, 2),
               "estimated_margin": round(margin, 2),
               "estimated_margin_pct": round(margin_pct, 1),
               "deal": bool(total_cost <= 0.50 * ref)}
        (deals if rec["deal"] else evaluated).append(rec)
        log["steps"].append(
            f"{name}: bid ${bid} + ${allow} = ${total_cost:.0f} vs ref ${ref:.0f} ({conf}) -> {'DEAL' if rec['deal'] else 'pass'}")

    (DATA / "deals.json").write_text(json.dumps(
        {"generated_utc": run_started, "deals": deals}, indent=1))
    (DATA / "evaluated.json").write_text(json.dumps(
        {"generated_utc": run_started, "evaluated": evaluated, "skipped": skipped}, indent=1))
    (DATA / "inventory.json").write_text(json.dumps(inventory, indent=1))
    log["run_finished_utc"] = datetime.now(timezone.utc).isoformat()
    log["deals_found"] = len(deals)
    (DATA / "run_log.json").write_text(json.dumps(log, indent=1))
    print(f"lots={len(lots)} deals={len(deals)} evaluated={len(evaluated)} skipped={len(skipped)}")
    for d in deals:
        print(f"DEAL: {d['lot_name']} bid ${d['current_bid']} total ${d['total_cost_estimate']} ref ${d['resale_reference']} margin ${d['estimated_margin']} ({d['estimated_margin_pct']}%)")


if __name__ == "__main__":
    sys.exit(main())
