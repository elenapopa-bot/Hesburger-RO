#!/usr/bin/env python3
"""Pull Hesburger Romania metrics from Looker and publish the HTML report."""

import calendar
import html
import os
import re
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import browser_cookie3
import requests
from github import Github

SCRIPT_DIR = Path(__file__).resolve().parent

LOOKER_HOST = "https://bolt.cloud.looker.com"
PUBLIC_QUERY = LOOKER_HOST + "/api/4.0/queries/run/json"
INTERNAL_QUERY = LOOKER_HOST + "/api/internal/core/4.0/queries/run/json"
REPO_NAME = "elenapopa-bot/Hesburger-RO"
ENV_FILE = Path.home() / ".hesburger_ro_env"
LOG_FILE = Path.home() / "scripts" / "hesburger_ro.log"
# Partner-approved layout (Claude artifact). CSS and static sections always come from here.
TEMPLATE_FILE = Path.home() / "scripts" / "hesburger_ro_template.html"
REPO_TEMPLATE_FILE = SCRIPT_DIR / "hesburger_ro_template.html"

PROVIDER_IDS = (
    "154778,154770,155192,135583,172927,173425,"
    "135582,135581,135580,170143,190389,135579"
)

LOC_FIELDS = [
    "dim_provider_common.provider_name",
    "dim_delivery_city.city_name",
    "fact_additive.courier_delivered_orders_count",
    "fact_additive.failed_orders_count",
    "fact_additive.total_gmv_before_discounts_platform_orders_eur",
    "fact_additive.gmv_before_discounts_per_order_eur",
    "fact_additive.campaign_orders_count",
    "fact_additive.delivered_bolt_plus_orders_count",
    "fact_additive.total_campaign_spend_bolt_eur",
    "fact_additive.total_campaign_spend_provider_eur",
    "fact_additive.provider_rating_per_order",
    "fact_additive.bad_provider_rating_rate",
    "fact_additive.good_provider_rating_rate",
    "fact_additive.provider_preparation_minutes_per_order",
    "fact_additive.provider_acceptance_minutes_per_order",
    "fact_additive.courier_minutes_per_order",
    "fact_additive.provider_impressions_count",
    "fact_additive.provider_menu_viewed_sessions_count",
    "fact_additive.provider_product_added_sessions_count",
    "fact_additive.provider_order_placed_sessions_count",
    "fact_additive.bad_provider_rating_rate",
    "fact_additive.good_provider_rating_rate",
]

YTD_FIELDS = [
    "fact_provider_non_additive.metric_timestamp_local_month",
    "fact_additive.courier_delivered_orders_count",
    "fact_additive.total_gmv_before_discounts_platform_orders_eur",
    "fact_additive.delivered_bolt_plus_orders_count",
    "fact_additive.failed_orders_count",
]

F_NAME = "dim_provider_common.provider_name"
F_CITY = "dim_delivery_city.city_name"
F_DELIV = "fact_additive.courier_delivered_orders_count"
F_FAIL = "fact_additive.failed_orders_count"
F_GMV = "fact_additive.total_gmv_before_discounts_platform_orders_eur"
F_AOV = "fact_additive.gmv_before_discounts_per_order_eur"
F_CAMP = "fact_additive.campaign_orders_count"
F_PLUS = "fact_additive.delivered_bolt_plus_orders_count"
F_SBOLT = "fact_additive.total_campaign_spend_bolt_eur"
F_SPROV = "fact_additive.total_campaign_spend_provider_eur"
F_RATE = "fact_additive.provider_rating_per_order"
F_BAD = "fact_additive.bad_provider_rating_rate"
F_GOOD = "fact_additive.good_provider_rating_rate"
F_PREP = "fact_additive.provider_preparation_minutes_per_order"
F_ACC = "fact_additive.provider_acceptance_minutes_per_order"
F_COUR = "fact_additive.courier_minutes_per_order"
F_IMP = "fact_additive.provider_impressions_count"
F_MENU = "fact_additive.provider_menu_viewed_sessions_count"
F_CART = "fact_additive.provider_product_added_sessions_count"
F_PLACE = "fact_additive.provider_order_placed_sessions_count"
F_MONTH = "fact_provider_non_additive.metric_timestamp_local_month"

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CITY_PRETTY = {
    "Buzau": "Buzău",
    "Galati": "Galați",
    "Ramnicu Valcea": "Rm. Vâlcea",
    "Iasi": "Iași",
    "Brasov": "Brașov",
    "Pitesti": "Pitești",
    "Braila": "Brăila",
    "Bucharest": "Bucharest",
    "Craiova": "Craiova",
}

OFFER_HTML = """
  <div class="tip" style="margin-top:20px">
    <strong>Offer — Smart Promo (joint Bolt × Hesburger)</strong><br>
    An automatic Bolt promo mechanic to acquire new customers and win back dormant ones — without a permanent discount and without manual setup.
  </div>
  <div class="offer-grid" style="margin-top:14px">
    <div class="ocard">
      <div class="otag otag-rec">Recommended</div>
      <div class="o-pct">30%</div>
      <div class="o-title">First order discount</div>
      <div class="o-body"><strong>For whom:</strong> new app users + those who haven't ordered in 60+ days<br><strong>Terms:</strong> −30% on first order + free delivery from 15 €<br><strong>Cost:</strong> 50/50 Bolt and partner</div>
      <div class="o-cost">Most aggressive — converts cold &amp; dormant customers</div>
    </div>
    <div class="ocard">
      <div class="otag otag-opt">Optional</div>
      <div class="o-pct">10%</div>
      <div class="o-title">Loyal app user discount</div>
      <div class="o-body"><strong>For whom:</strong> active Bolt Food users who haven't ordered from Hesburger yet<br><strong>Terms:</strong> −10% on first order + free delivery from 15 €<br><strong>Cost:</strong> 100% partner</div>
      <div class="o-cost">Small nudge — already loyal Bolt customers</div>
    </div>
    <div class="ocard">
      <div class="otag otag-opt">Monthly</div>
      <div class="o-pct">15%</div>
      <div class="o-title">Bolt+ exclusive — 1 week/month</div>
      <div class="o-body"><strong>For whom:</strong> Bolt+ subscribers only<br><strong>Terms:</strong> −15% on full menu, 1 week/month<br><strong>Cost:</strong> 50/50 Bolt and partner</div>
      <div class="o-cost">Boosts Bolt+ share (currently 15–17% chain)</div>
    </div>
  </div>
"""


def log(msg):
    line = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_token():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if not ENV_FILE.exists():
        raise RuntimeError(f"Missing {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith("GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("GITHUB_TOKEN not found in env file")


def num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def n0(value):
    v = num(value)
    return 0.0 if v is None else v


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def fmt_int(value):
    return f"{int(round(value)):,}"


def fmt_eur(value, digits=0):
    if digits:
        return f"{value:,.{digits}f} €"
    return f"{int(round(value)):,} €"


def fmt_num(value, digits=0):
    if digits:
        return f"{value:,.{digits}f}"
    return f"{int(round(value)):,}"


def pct(part, whole):
    if not whole:
        return None
    return part / whole * 100.0


def pretty_city(name):
    raw = (name or "").strip()
    return CITY_PRETTY.get(raw, raw or "—")


def clean_name(name):
    text = (name or "Unknown").strip()
    if text.lower().startswith("hesburger "):
        text = text[len("hesburger "):]
    return text.strip() or "Unknown"


def stars(rating):
    if rating is None:
        return ""
    if rating >= 4.5:
        n = 5
    elif rating >= 4.0:
        n = 4
    elif rating >= 3.0:
        n = 3
    elif rating >= 2.0:
        n = 2
    else:
        n = 1
    return "★" * n + "☆" * (5 - n)


def trend_text(curr, prev, kind="pct", higher_is_better=True, vs=""):
    """Return (label, hero_class up/dn/neu, card_class kup/kdn/kneu)."""
    if curr is None or prev is None:
        return "—", "neu", "kneu"
    diff = curr - prev
    if kind == "pct":
        if prev == 0:
            return "—", "neu", "kneu"
        delta = diff / abs(prev) * 100.0
        if abs(delta) < 0.05:
            label = f"= {vs}" if vs else "flat"
            return label, "neu", "kneu"
        arrow = "▲" if delta > 0 else "▼"
        label = f"{arrow}{abs(delta):.1f}%"
    elif kind == "pp":
        if abs(diff) < 0.05:
            label = f"= {vs}" if vs else "flat"
            return label, "neu", "kneu"
        arrow = "▲" if diff > 0 else "▼"
        label = f"{arrow}{abs(diff):.1f}pp"
    else:
        if abs(diff) < 0.005:
            label = f"= {vs}" if vs else "flat"
            return label, "neu", "kneu"
        arrow = "▲" if diff > 0 else "▼"
        digits = 2 if kind == "rating" else 1
        label = f"{arrow}{abs(diff):.{digits}f}"
    if vs:
        label = f"{label} vs {vs}"
    improved = diff > 0 if higher_is_better else diff < 0
    if improved:
        return label, "up", "kup"
    return label, "dn", "kdn"


def mom_td(curr, prev, inactive_label=None):
    if inactive_label and (curr or 0) <= 0 and (prev or 0) > 0:
        return f'<td class="kneu" style="color:var(--ink-l)">{esc(inactive_label)}</td>'
    if not prev and not curr:
        return '<td class="kneu">—</td>'
    if not prev:
        return '<td class="tg">new</td>'
    delta = (curr - prev) / abs(prev) * 100.0
    if abs(delta) < 0.05:
        return '<td class="kneu">0.0%</td>'
    if delta > 0:
        return f'<td class="tg">▲{delta:.1f}%</td>'
    return f'<td class="tr">▼{abs(delta):.1f}%</td>'


def dash_or(value, renderer):
    if value is None:
        return "—"
    return renderer(value)


def blank_loc():
    return {
        "name": "",
        "city": "—",
        "delivered": 0.0,
        "failed": 0.0,
        "gmv": 0.0,
        "aov_weighted": 0.0,
        "aov_den": 0.0,
        "campaign": 0.0,
        "bolt_plus": 0.0,
        "spend_bolt": 0.0,
        "spend_provider": 0.0,
        "rating_num": 0.0,
        "rating_den": 0.0,
        "bad_num": 0.0,
        "bad_den": 0.0,
        "good_num": 0.0,
        "good_den": 0.0,
        "prep_num": 0.0,
        "prep_den": 0.0,
        "acc_num": 0.0,
        "acc_den": 0.0,
        "cour_num": 0.0,
        "cour_den": 0.0,
        "impressions": 0.0,
        "menu": 0.0,
        "cart": 0.0,
        "placed": 0.0,
    }


def add_row(bucket, row):
    name = clean_name(row.get(F_NAME))
    loc = bucket.get(name)
    if loc is None:
        loc = blank_loc()
        loc["name"] = name
        loc["city"] = pretty_city(row.get(F_CITY))
        bucket[name] = loc
    delivered = n0(row.get(F_DELIV))
    loc["delivered"] += delivered
    loc["failed"] += n0(row.get(F_FAIL))
    loc["gmv"] += n0(row.get(F_GMV))
    aov = num(row.get(F_AOV))
    if aov is not None and delivered:
        loc["aov_weighted"] += aov * delivered
        loc["aov_den"] += delivered
    loc["campaign"] += n0(row.get(F_CAMP))
    loc["bolt_plus"] += n0(row.get(F_PLUS))
    loc["spend_bolt"] += n0(row.get(F_SBOLT))
    loc["spend_provider"] += n0(row.get(F_SPROV))
    rating = num(row.get(F_RATE))
    if rating is not None and delivered:
        loc["rating_num"] += rating * delivered
        loc["rating_den"] += delivered
    for src, num_key, den_key in (
        (F_PREP, "prep_num", "prep_den"),
        (F_ACC, "acc_num", "acc_den"),
        (F_COUR, "cour_num", "cour_den"),
        (F_BAD, "bad_num", "bad_den"),
        (F_GOOD, "good_num", "good_den"),
    ):
        val = num(row.get(src))
        if val is not None and delivered:
            loc[num_key] += val * delivered
            loc[den_key] += delivered
    loc["impressions"] += n0(row.get(F_IMP))
    loc["menu"] += n0(row.get(F_MENU))
    loc["cart"] += n0(row.get(F_CART))
    loc["placed"] += n0(row.get(F_PLACE))


def finalize(loc):
    delivered = loc["delivered"]
    loc["aov"] = (loc["gmv"] / delivered) if delivered else (
        loc["aov_weighted"] / loc["aov_den"] if loc["aov_den"] else None
    )
    loc["rating"] = loc["rating_num"] / loc["rating_den"] if loc["rating_den"] else None
    loc["bad_rate"] = loc["bad_num"] / loc["bad_den"] if loc["bad_den"] else None
    loc["good_rate"] = loc["good_num"] / loc["good_den"] if loc["good_den"] else None
    loc["prep"] = loc["prep_num"] / loc["prep_den"] if loc["prep_den"] else None
    loc["accept"] = loc["acc_num"] / loc["acc_den"] if loc["acc_den"] else None
    loc["courier"] = loc["cour_num"] / loc["cour_den"] if loc["cour_den"] else None
    loc["promo_share"] = pct(loc["campaign"], delivered)
    loc["plus_share"] = pct(loc["bolt_plus"], delivered)
    loc["fail_rate"] = pct(loc["failed"], delivered) if delivered else None
    return loc


def rows_to_locs(rows):
    bucket = {}
    for row in rows:
        add_row(bucket, row)
    return [finalize(loc) for loc in bucket.values()]


def chain(locs):
    total = blank_loc()
    total["name"] = "Chain"
    for loc in locs:
        for key in (
            "delivered", "failed", "gmv", "campaign", "bolt_plus",
            "spend_bolt", "spend_provider", "impressions", "menu", "cart", "placed",
            "rating_num", "rating_den", "bad_num", "bad_den", "good_num", "good_den",
            "prep_num", "prep_den",
            "acc_num", "acc_den", "cour_num", "cour_den",
        ):
            total[key] += loc[key]
    return finalize(total)


def month_window(year, month):
    last = calendar.monthrange(year, month)[1]
    start = f"{year}/{month:02d}/01"
    end = f"{year}/{month:02d}/{last:02d}"
    label = f"{year}-{month:02d}"
    return start, end, label


def base_filters(partition, grain="monthly"):
    return {
        "fact_additive.provider_id": PROVIDER_IDS,
        "fact_provider_non_additive.time_granularity": grain,
        "fact_provider_non_additive.entity_granularity": "provider",
        "fact_provider_non_additive.metric_partition_date": partition,
    }


def reporting_month(today):
    """Completed month shown in the monthly report.

    The page refreshes on the 2nd with the month that just finished.
    On the 1st it still shows the month published on the previous 2nd.
    """
    year, month = today.year, today.month
    shift = 1 if today.day >= 2 else 2
    month -= shift
    while month <= 0:
        month += 12
        year -= 1
    return year, month


def last_complete_week(today):
    """Monday of the last week that has already ended (Mon–Sun)."""
    monday = today.date() - timedelta(days=today.weekday())
    return monday - timedelta(days=7)


def last_full_week_in_month(year, month):
    """Monday of the last Mon–Sun week that sits entirely inside the month."""
    last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()
    sunday = last_day - timedelta(days=(last_day.weekday() + 1) % 7)
    monday = sunday - timedelta(days=6)
    if monday < datetime(year, month, 1).date():
        monday -= timedelta(days=7)
    return monday


def open_period(today):
    """In-progress month, once a finished week already falls inside it.

    Compared with the same day count in the previous month, through yesterday.
    Today is left out because the day is still open.
    """
    week = last_complete_week(today)
    yesterday = today.date() - timedelta(days=1)
    if (week.year, week.month) != (today.year, today.month):
        return None
    if yesterday.month != today.month or yesterday.year != today.year:
        return None
    year, month = today.year, today.month
    if month == 1:
        prev_y, prev_m = year - 1, 12
    else:
        prev_y, prev_m = year, month - 1
    end_day = yesterday.day
    prev_end = min(end_day, calendar.monthrange(prev_y, prev_m)[1])
    if prev_m == 1:
        before_y, before_m = prev_y - 1, 12
    else:
        before_y, before_m = prev_y, prev_m - 1
    before_end = min(end_day, calendar.monthrange(before_y, before_m)[1])
    return {
        "year": year,
        "month": month,
        "end_day": end_day,
        "prev_year": prev_y,
        "prev_month": prev_m,
        "prev_end_day": prev_end,
        "before_year": before_y,
        "before_month": before_m,
        "before_end_day": before_end,
    }


def location_body(partition, month_label, grain):
    return {
        "model": "curated_delivery",
        "view": "fact_provider",
        "fields": LOC_FIELDS,
        "filters": {
            **base_filters(partition, grain),
            F_MONTH: month_label,
        },
        "sorts": [F_DELIV + " desc"],
        "limit": "500",
    }


def looker_session():
    jar = list(browser_cookie3.chrome(domain_name="bolt.cloud.looker.com"))
    session = requests.Session()
    csrf = None
    for cookie in jar:
        session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        if cookie.name == "CSRF-TOKEN":
            csrf = cookie.value
    if not csrf:
        raise RuntimeError(
            "No Looker CSRF cookie in Chrome. Log in to bolt.cloud.looker.com and retry."
        )
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": LOOKER_HOST,
        "Referer": LOOKER_HOST + "/explore/curated_delivery/fact_provider",
    })
    log(f"Loaded {len(jar)} Looker cookies from Chrome")
    return session


def run_query(session, endpoint, body):
    params = {"apply_formatting": "false", "cache": "false"}
    last = None
    for url in (PUBLIC_QUERY, INTERNAL_QUERY) if endpoint is None else (endpoint,):
        response = session.post(url, params=params, json=body, timeout=180)
        if response.status_code == 200 and response.text.lstrip().startswith("["):
            data = response.json()
            log(f"Looker query ok via {url} ({len(data)} rows)")
            return data, url
        snippet = response.text[:240].replace("\n", " ")
        last = f"{url} -> {response.status_code} {snippet}"
        log(f"Looker query not accepted: {last}")
    raise RuntimeError("Looker query failed: " + (last or "no response"))


F_WEEK = "fact_provider_non_additive.metric_timestamp_local_week"


def week_body(week_start):
    week_end = week_start + timedelta(days=6)
    partition = f"{week_start:%Y/%m/%d} to {week_end:%Y/%m/%d}"
    return {
        "model": "curated_delivery",
        "view": "fact_provider",
        "fields": LOC_FIELDS,
        "filters": {
            **base_filters(partition, "weekly"),
            F_WEEK: week_start.strftime("%Y-%m-%d"),
        },
        "sorts": [F_DELIV + " desc"],
        "limit": "500",
    }

def fetch_queries(session):
    today = datetime.now()
    year, month = reporting_month(today)
    if month == 1:
        prev_y, prev_m = year - 1, 12
    else:
        prev_y, prev_m = year, month - 1
    cur_start, cur_end, cur_label = month_window(year, month)
    prev_start, prev_end, prev_label = month_window(prev_y, prev_m)
    cur_part = f"{cur_start} to {cur_end}"
    prev_part = f"{prev_start} to {prev_end}"
    ytd_end_day = calendar.monthrange(year, month)[1]
    ytd_partition = f"{year}/01/01 to {year}/{month:02d}/{ytd_end_day:02d}"

    current_body = location_body(cur_part, cur_label, "monthly")
    previous_body = location_body(prev_part, prev_label, "monthly")
    ytd_body = {
        "model": "curated_delivery",
        "view": "fact_provider",
        "fields": YTD_FIELDS,
        "filters": base_filters(ytd_partition),
        "sorts": [F_MONTH],
        "limit": "24",
    }

    current, endpoint = run_query(session, None, current_body)
    previous, _ = run_query(session, endpoint, previous_body)
    ytd, _ = run_query(session, endpoint, ytd_body)
    if not current:
        raise RuntimeError(f"Current month query returned no rows for {cur_label}")
    if not previous:
        raise RuntimeError(f"Previous month query returned no rows for {prev_label}")
    if not ytd:
        raise RuntimeError("YTD query returned no rows")
    sl_current, endpoint = fetch_sl(session, endpoint, cur_label)
    sl_previous, _ = fetch_sl(session, endpoint, prev_label)
    week_start = last_complete_week(today)
    prev_week_start = week_start - timedelta(days=7)
    week_rows, endpoint = run_query(session, endpoint, week_body(week_start))
    prev_week_rows, _ = run_query(session, endpoint, week_body(prev_week_start))
    if not week_rows:
        raise RuntimeError(f"Weekly query returned no rows for {week_start}")
    if not prev_week_rows:
        raise RuntimeError(f"Weekly query returned no rows for {prev_week_start}")
    log(f"Weeks {prev_week_start} vs {week_start}: {len(prev_week_rows)} / {len(week_rows)} rows")
    mtd = None
    yesterday = today.date() - timedelta(days=1)
    if (
        yesterday.year == today.year
        and yesterday.month == today.month
        and (yesterday.year, yesterday.month) > (year, month)
    ):
        end_day = yesterday.day
        mtd_label = f"{yesterday.year}-{yesterday.month:02d}"
        mtd_part = f"{yesterday.year}/{yesterday.month:02d}/01 to {yesterday.year}/{yesterday.month:02d}/{end_day:02d}"
        cmp_end = min(end_day, calendar.monthrange(year, month)[1])
        cmp_part = f"{year}/{month:02d}/01 to {year}/{month:02d}/{cmp_end:02d}"
        mtd_rows, endpoint = run_query(session, endpoint, location_body(mtd_part, mtd_label, "daily"))
        cmp_rows, _ = run_query(session, endpoint, location_body(cmp_part, cur_label, "daily"))
        if not mtd_rows:
            raise RuntimeError(f"Month-to-date query returned no rows for {mtd_label}")
        mtd = {
            "year": yesterday.year,
            "month": yesterday.month,
            "end_day": end_day,
            "compare_end": cmp_end,
            "current": rows_to_locs(mtd_rows),
            "compare": rows_to_locs(cmp_rows),
        }
        log(f"Oct-style TD 1–{end_day} {mtd_label} vs 1–{cmp_end} {cur_label}: {len(mtd_rows)} rows")
    return {
        "today": today,
        "year": year,
        "month": month,
        "prev_year": prev_y,
        "prev_month": prev_m,
        "current": rows_to_locs(current),
        "previous": rows_to_locs(previous),
        "ytd": ytd,
        "mtd": mtd,
        "sl_current": sl_current,
        "sl_previous": sl_previous,
        "week_start": week_start,
        "prev_week_start": prev_week_start,
        "week_current": rows_to_locs(week_rows),
        "week_previous": rows_to_locs(prev_week_rows),
    }


# Dashboard 29830 labels this "Total Spend (EUR)". It is the merchant's SL investment.
F_SL_SPEND = "provider_sponsored_listing_attribution.total_gross_revenue_eur"
F_SL_IMP = "provider_sponsored_listing_performance.impressions_total"
F_SL_STATE = "provider_sponsored_listing_performance.sponsored_listing_state"
F_SL_NAME = "dim_provider_v2.provider_name"
F_SL_ROAS = "provider_sponsored_listing_attribution.roas_eur"


def fetch_sl(session, endpoint, month_label):
    """Sponsored Listing investment for Hesburger Romania in one month.

    Same filters as dashboard 29830: brand HESBURGER, country Romania, listing date.
    An empty result means the brand did not spend in that month.
    """
    body = {
        "model": "incentives",
        "view": "provider_sponsored_listing_all",
        "fields": [F_SL_NAME, F_SL_SPEND, F_SL_IMP, F_SL_STATE, F_SL_ROAS],
        "filters": {
            "dim_provider_v2.brand_name": "HESBURGER",
            "admin_system_country.country_name": "Romania",
            "provider_sponsored_listing_attribution.sponsored_listing_date": month_label,
        },
        "limit": "500",
    }
    rows, endpoint = run_query(session, endpoint, body)
    by_name = {}
    spend = impressions = 0.0
    active = set()
    for row in rows:
        name = clean_name(row.get(F_SL_NAME))
        amount = n0(row.get(F_SL_SPEND))
        imps = n0(row.get(F_SL_IMP))
        state = str(row.get(F_SL_STATE) or "").lower()
        spend += amount
        impressions += imps
        rec = by_name.setdefault(name, {"spend": 0.0, "impressions": 0.0, "roas_num": 0.0, "roas_den": 0.0})
        rec["spend"] += amount
        rec["impressions"] += imps
        roas = num(row.get(F_SL_ROAS))
        if roas is not None and amount:
            rec["roas_num"] += roas * amount
            rec["roas_den"] += amount
        if state == "active" or amount > 0:
            active.add(name)
    log(f"SL {month_label}: {len(rows)} rows, {len(active)} with spend, {spend:.2f} EUR")
    return {"spend": spend, "impressions": impressions, "active": len(active), "by_name": by_name}, endpoint


def ytd_by_month(rows, year, through_month):
    found = {}
    for row in rows:
        raw = str(row.get(F_MONTH) or "")
        match = re.match(r"(\d{4})-(\d{2})", raw)
        if not match:
            continue
        y, m = int(match.group(1)), int(match.group(2))
        if y != year or m < 1 or m > through_month:
            continue
        found[m] = {
            "delivered": n0(row.get(F_DELIV)),
            "gmv": n0(row.get(F_GMV)),
            "bolt_plus": n0(row.get(F_PLUS)),
            "failed": n0(row.get(F_FAIL)),
        }
    series = []
    for m in range(1, through_month + 1):
        series.append(found.get(m, {"delivered": 0.0, "gmv": 0.0, "bolt_plus": 0.0, "failed": 0.0}))
    return series


def section_by_id(original, div_id, next_id):
    marker = f'id="{div_id}"'
    start = original.find(marker)
    if start < 0:
        return ""
    comment = original.rfind("<!--", 0, start)
    if comment >= 0 and start - comment < 280:
        start = comment
    else:
        start = original.rfind("<div", 0, start)
    next_marker = f'id="{next_id}"'
    end = original.find(next_marker, start + 1)
    if end < 0:
        return original[start:]
    comment = original.rfind("<!--", start, end)
    if comment > start:
        end = comment
    return original[start:end].rstrip() + "\n\n"


def style_block(original):
    match = re.search(r"<style>.*?</style>", original, flags=re.S)
    if not match:
        raise RuntimeError("Current index.html has no <style> block")
    return match.group(0)


def ops_status(loc):
    rank = 0
    accept, prep, courier = loc.get("accept"), loc.get("prep"), loc.get("courier")
    if accept is not None:
        rank = 2 if accept > 1 else max(rank, 1 if accept > 0.5 else 0)
    if prep is not None:
        rank = 2 if prep > 16 else max(rank, 1 if prep > 12 else rank)
    if courier is not None:
        rank = 2 if courier > 30 else max(rank, 1 if courier > 25 else rank)
    return ("Good", "Attention", "Critical")[rank]


def badge(status):
    css = {"Good": "bg", "Attention": "ba", "Critical": "br"}.get(status, "bb")
    return f'<span class="badge {css}">{status}</span>'


def time_cell(value, kind):
    if value is None:
        return "<td>—</td>"
    text = f"{value:.2f}"
    css = ""
    if kind == "accept" and value > 1:
        css = "tr"
    elif kind == "accept" and value > 0.5:
        css = "ta"
    elif kind == "prep" and value > 16:
        css = "tr"
    elif kind == "prep" and value > 12:
        css = "ta"
    elif kind == "courier" and value > 28:
        css = "tr"
    elif kind == "courier" and value <= 22:
        css = "tg"
    if css:
        return f'<td class="{css}">{text}</td>'
    return f"<td>{text}</td>"


def hero_kpis(title_id, display, totals, compare, vs_label, ytd_delivered, ytd_gmv, ytd_label, locations):
    delivered_l, delivered_c, _ = trend_text(totals["delivered"], compare["delivered"], "pct", True, vs_label)
    revenue_l, revenue_c, _ = trend_text(totals["gmv"], compare["gmv"], "pct", True, vs_label)
    aov_l, aov_c, _ = trend_text(totals["aov"], compare["aov"], "pct", True, vs_label)
    promo_l, promo_c, _ = trend_text(totals["promo_share"], compare.get("promo_share"), "pp", True, vs_label)
    if compare.get("rating") is not None and totals.get("rating") is not None:
        rate_l, rate_c, _ = trend_text(totals["rating"], compare["rating"], "rating", True, vs_label)
    else:
        rate_l, rate_c = f"{locations} locations", "neu"
    promo = "—" if totals["promo_share"] is None else f"{totals['promo_share']:.1f}%"
    aov = "—" if totals["aov"] is None else fmt_eur(totals["aov"], 2)
    rating = "—" if totals["rating"] is None else f"{totals['rating']:.2f} ★"
    hidden = "" if display else ' style="display:none"'
    return f"""
    <div class="hero-kpis" id="{title_id}"{hidden}>
      <div class="hero-kpi"><div class="hero-kpi-l">Delivered</div><div class="hero-kpi-v">{fmt_int(totals['delivered'])}</div><div class="hero-kpi-d {delivered_c}">{esc(delivered_l)}</div></div>
      <div class="hero-kpi"><div class="hero-kpi-l">Revenue</div><div class="hero-kpi-v">{fmt_eur(totals['gmv'])}</div><div class="hero-kpi-d {revenue_c}">{esc(revenue_l)}</div></div>
      <div class="hero-kpi"><div class="hero-kpi-l">AOV</div><div class="hero-kpi-v">{aov}</div><div class="hero-kpi-d {aov_c}">{esc(aov_l)}</div></div>
      <div class="hero-kpi"><div class="hero-kpi-l">Promo share</div><div class="hero-kpi-v">{promo}</div><div class="hero-kpi-d {promo_c}">{esc(promo_l)}</div></div>
      <div class="hero-kpi"><div class="hero-kpi-l">Chain rating</div><div class="hero-kpi-v">{rating}</div><div class="hero-kpi-d {rate_c}">{esc(rate_l)}</div></div>
      <div class="hero-kpi"><div class="hero-kpi-l">YTD {esc(ytd_label)}</div><div class="hero-kpi-v">{fmt_int(ytd_delivered)}</div><div class="hero-kpi-d neu">{fmt_eur(ytd_gmv)}</div></div>
    </div>"""


def card(label, value, detail, css):
    return (
        f'<div class="kcard"><div class="kcard-l">{esc(label)}</div>'
        f'<div class="kcard-v">{value}</div>'
        f'<div class="kcard-d {css}">{esc(detail)}</div></div>'
    )


def bar_svg(values, labels, value_fmt, axis_fmt, color):
    n = max(len(values), 1)
    peak = max(values) if values else 1
    peak = peak or 1
    width = max(380, 50 + n * 46)
    baseline = 138
    max_h = 112
    parts = [
        f'<svg viewBox="0 0 {width} 170" xmlns="http://www.w3.org/2000/svg" style="width:100%;overflow:visible">',
        f'<line x1="40" y1="18" x2="{width - 8}" y2="18" stroke="var(--border)" stroke-width="1"/>',
        f'<line x1="40" y1="58" x2="{width - 8}" y2="58" stroke="var(--border)" stroke-width="1"/>',
        f'<line x1="40" y1="98" x2="{width - 8}" y2="98" stroke="var(--border)" stroke-width="1"/>',
        f'<line x1="40" y1="138" x2="{width - 8}" y2="138" stroke="var(--border)" stroke-width="1"/>',
        f'<text x="36" y="21" text-anchor="end" font-size="9" fill="var(--ink-l)">{axis_fmt(peak)}</text>',
        f'<text x="36" y="61" text-anchor="end" font-size="9" fill="var(--ink-l)">{axis_fmt(peak * 0.66)}</text>',
        f'<text x="36" y="101" text-anchor="end" font-size="9" fill="var(--ink-l)">{axis_fmt(peak * 0.33)}</text>',
        '<text x="36" y="141" text-anchor="end" font-size="9" fill="var(--ink-l)">0</text>',
    ]
    for i, (value, label) in enumerate(zip(values, labels)):
        h = max(2, round(value / peak * max_h)) if value else 2
        y = baseline - h
        x = 48 + i * 46
        last = i == len(values) - 1
        fill = "var(--ink)" if last else color
        opacity = "0.9" if last else "0.55"
        weight = "700" if last else "400"
        parts.append(
            f'<rect x="{x}" y="{y}" width="30" height="{h}" fill="{fill}" opacity="{opacity}" rx="3"/>'
        )
        parts.append(
            f'<text x="{x + 15}" y="153" text-anchor="middle" font-size="8" font-weight="{weight}" fill="var(--ink)">{esc(label)}</text>'
        )
        if last and value:
            parts.append(
                f'<text x="{x + 15}" y="{max(y - 4, 12)}" text-anchor="middle" font-size="8" font-weight="600" fill="var(--ink)">{esc(value_fmt(value))}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def axis_count(value):
    if value >= 1000:
        return f"{value / 1000:.1f}k".replace(".0k", "k")
    return str(int(round(value)))


def axis_eur(value):
    if value >= 1000:
        return f"{value / 1000:.0f}k"
    return str(int(round(value)))


def funnel_card(title, totals):
    imp = totals["impressions"] or 0
    menu = totals["menu"] or 0
    cart = totals["cart"] or 0
    placed = totals["placed"] or totals["delivered"] or 0
    imp_menu = pct(menu, imp) or 0
    menu_cart = pct(cart, menu) or 0
    cart_order = pct(placed, cart) or 0

    def width(value):
        if not imp:
            return 2
        return max(1.2, min(100, value / imp * 100))

    return f"""
    <div class="ccard">
      <div class="ccard-t">{esc(title)}</div>
      <div class="funnel">
        <div class="fn-step"><div class="fn-lbl">Impressions</div><div class="fn-bar-w"><div class="fn-outer"><div class="fn-inner" style="width:100%;background:#0B1F16"><span>baseline</span></div></div></div><div class="fn-val">{fmt_int(imp)}</div></div>
        <div class="fn-arrow">↓ {imp_menu:.1f}% open menu</div>
        <div class="fn-step"><div class="fn-lbl">Viewed menu</div><div class="fn-bar-w"><div class="fn-outer"><div class="fn-inner" style="width:{width(menu):.2f}%;background:var(--green)"><span></span></div></div></div><div class="fn-val">{fmt_int(menu)}</div></div>
        <div class="fn-arrow">↓ {menu_cart:.1f}% add to cart</div>
        <div class="fn-step"><div class="fn-lbl">Added to cart</div><div class="fn-bar-w"><div class="fn-outer"><div class="fn-inner" style="width:{width(cart):.2f}%;background:var(--green)"><span></span></div></div></div><div class="fn-val">{fmt_int(cart)}</div></div>
        <div class="fn-arrow">↓ {cart_order:.1f}% place order</div>
        <div class="fn-step"><div class="fn-lbl">Placed order</div><div class="fn-bar-w"><div class="fn-outer"><div class="fn-inner" style="width:{width(placed):.2f}%;background:var(--green-d)"><span></span></div></div></div><div class="fn-val">{fmt_int(placed)}</div></div>
      </div>
      <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
        <div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;flex:1;min-width:70px"><div style="font-size:17px;font-weight:700;color:var(--green-d)">{imp_menu:.1f}%</div><div style="font-size:9px;color:var(--ink-l)">Imp → menu</div></div>
        <div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;flex:1;min-width:70px"><div style="font-size:17px;font-weight:700;color:var(--green-d)">{menu_cart:.1f}%</div><div style="font-size:9px;color:var(--ink-l)">Menu → cart</div></div>
        <div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;flex:1;min-width:70px"><div style="font-size:17px;font-weight:700;color:var(--green-d)">{cart_order:.1f}%</div><div style="font-size:9px;color:var(--ink-l)">Cart → order</div></div>
      </div>
    </div>"""


def week_span(start):
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}–{end.day} {MON[start.month - 1]} {start.year}"
    return f"{start.day} {MON[start.month - 1]} – {end.day} {MON[end.month - 1]} {end.year}"


def weekly_section(data, block_id=None, hidden=False):
    current = {loc["name"]: loc for loc in data["week_current"]}
    previous = {loc["name"]: loc for loc in data["week_previous"]}
    names = sorted(set(current) | set(previous), key=lambda name: (
        -(current.get(name) or {"delivered": 0})["delivered"],
        name,
    ))
    cur_chain = chain(list(current.values()))
    prev_chain = chain(list(previous.values()))
    this_label = week_span(data["week_start"])
    prior_label = week_span(data["prev_week_start"])
    deliv_l, _, deliv_card = trend_text(cur_chain["delivered"], prev_chain["delivered"], "pct", True, "prior week")
    rev_l, _, rev_card = trend_text(cur_chain["gmv"], prev_chain["gmv"], "pct", True, "prior week")
    aov_l, _, aov_card = trend_text(cur_chain["aov"], prev_chain["aov"], "pct", True, "")
    rate_l, _, rate_card = trend_text(cur_chain["rating"], prev_chain["rating"], "rating", True, "prior week")
    rows = []
    for name in names:
        cur = current.get(name) or finalize(blank_loc() | {"name": name, "city": previous[name]["city"]})
        prev = previous.get(name) or finalize(blank_loc() | {"name": name, "city": cur["city"]})
        if cur["delivered"] <= 0 and prev["delivered"] <= 0:
            continue
        aov = "—" if not cur["delivered"] or cur["aov"] is None else f"{cur['aov']:.2f}"
        promo = "—" if not cur["delivered"] or cur["promo_share"] is None else f"{cur['promo_share']:.1f}%"
        rating = "—" if not cur["delivered"] or cur["rating"] is None else f"{cur['rating']:.2f}"
        bad = "—" if not cur["delivered"] or cur.get("bad_rate") is None else f"{cur['bad_rate'] * 100:.1f}%"
        good = "—" if not cur["delivered"] or cur.get("good_rate") is None else f"{cur['good_rate'] * 100:.1f}%"
        rows.append(
            "<tr>"
            f'<td class="bold">{esc(cur["name"])}</td><td>{esc(cur["city"])}</td>'
            f"<td>{fmt_int(prev['delivered'])}</td>"
            f'<td class="bold">{fmt_int(cur["delivered"]) if cur["delivered"] else "—"}</td>'
            f"{mom_td(cur['delivered'], prev['delivered'])}"
            f"<td>{fmt_int(cur['gmv']) if cur['delivered'] else '—'}</td>"
            f"<td>{aov}</td><td>{promo}</td>"
            f"<td>{fmt_int(cur['bolt_plus']) if cur['delivered'] else '—'}</td>"
            f"<td>{fmt_int(cur['failed']) if cur['delivered'] else '—'}</td>"
            f"<td>{rating}</td><td>{bad}</td><td>{good}</td>"
            "</tr>"
        )
    active = sum(1 for loc in current.values() if loc["delivered"] > 0)
    rating_value = f"{cur_chain['rating']:.2f} ★" if cur_chain["rating"] else "—"
    aov_value = fmt_eur(cur_chain["aov"], 2) if cur_chain["aov"] else "—"
    hide = ' style="display:none"' if hidden else ""
    wrap_id = f' id="{block_id}"' if block_id else ""
    anchor = "" if block_id else '<div id="weekly"></div>\n'
    return f"""
{anchor}<div{wrap_id}{hide}>
<div class="wrap"><div class="section">
  <p class="sec-title">Weekly report — {esc(this_label)}</p>
  <p class="sec-sub">Network summary and every location · vs {esc(prior_label)} · refreshes every Monday at 13:00</p>
  <div class="kpi-row">
    {card("Delivered", fmt_int(cur_chain["delivered"]), deliv_l, deliv_card)}
    {card("Revenue", fmt_eur(cur_chain["gmv"]), rev_l, rev_card)}
    {card("AOV", aov_value, aov_l, aov_card)}
    {card("Chain rating", rating_value, rate_l, rate_card)}
    {card("Fail rate", f"{(cur_chain['fail_rate'] or 0):.1f}%", f"{fmt_int(cur_chain['failed'])} failed", "kneu")}
    {card("Locations", str(active), "with delivered orders", "kneu")}
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Location</th><th>City</th>
        <th>Delivered prior</th><th>Delivered</th><th>WoW</th>
        <th>Revenue €</th><th>AOV €</th><th>Promo%</th>
        <th>Bolt+</th><th>Failed</th><th>Rating ★</th><th>Bad%</th><th>Good%</th>
      </tr></thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
</div></div>
<hr class="divider">
</div>
"""


def build_html(original, data):
    today = data["today"]
    year = data["year"]
    month = data["month"]
    prev_m = data["prev_month"]
    before_m = 12 if prev_m == 1 else prev_m - 1
    cur_name, prev_name = MONTHS[month - 1], MONTHS[prev_m - 1]
    cur_ab, prev_ab = MON[month - 1], MON[prev_m - 1]
    before_ab = MON[before_m - 1]
    month_note = "completed month, refreshes on the 2nd"
    ytd_cur_label = f"Jan–{cur_ab}"
    ytd_prev_label = f"Jan–{prev_ab}"
    generated = today.strftime("%d %B %Y").lstrip("0")

    current = {loc["name"]: loc for loc in data["current"]}
    previous = {loc["name"]: loc for loc in data["previous"]}
    names = sorted(set(current) | set(previous), key=lambda n: (
        -(current.get(n) or blank_loc())["delivered"],
        -(previous.get(n) or blank_loc())["delivered"],
        n,
    ))
    paired = []
    for name in names:
        cur = current.get(name) or finalize(blank_loc() | {"name": name, "city": (previous.get(name) or {}).get("city", "—")})
        prev = previous.get(name) or finalize(blank_loc() | {"name": name, "city": cur["city"]})
        if cur["city"] == "—" and prev["city"] != "—":
            cur["city"] = prev["city"]
        paired.append((cur, prev))

    cur_chain = chain(list(current.values()))
    prev_chain = chain(list(previous.values()))
    series = ytd_by_month(data["ytd"], year, month)
    ytd_del = sum(item["delivered"] for item in series)
    ytd_gmv = sum(item["gmv"] for item in series)
    ytd_plus = sum(item["bolt_plus"] for item in series)
    ytd_fail = sum(item["failed"] for item in series)
    ytd_through_prev = sum(item["delivered"] for item in series[:prev_m])
    ytd_gmv_prev = sum(item["gmv"] for item in series[:prev_m])

    before = series[before_m - 1] if before_m <= len(series) else {"delivered": 0, "gmv": 0, "bolt_plus": 0, "failed": 0}
    prev_month_chain = series[prev_m - 1]
    prev_compare = {
        "delivered": before["delivered"],
        "gmv": before["gmv"],
        "aov": (before["gmv"] / before["delivered"]) if before["delivered"] else None,
        "promo_share": None,
        "rating": None,
        "failed": before["failed"],
        "bolt_plus": before["bolt_plus"],
    }
    prev_for_hero = {
        "delivered": prev_chain["delivered"],
        "gmv": prev_chain["gmv"],
        "aov": prev_chain["aov"],
        "promo_share": prev_chain["promo_share"],
        "rating": prev_chain["rating"],
        "failed": prev_chain["failed"],
        "bolt_plus": prev_chain["bolt_plus"],
    }

    active = [pair[0] for pair in paired if pair[0]["delivered"] > 0]
    total_locs = len(paired)
    active_n = len(active)
    loc_label = f"{active_n}–{total_locs}" if active_n != total_locs else str(active_n)
    # Hero subtitle city order/naming follows the partner artifact.
    hero_order = ["Bucharest", "Galați", "Craiova", "Buzău", "Rm. Vâlcea", "Brăila", "Iași", "Brașov", "Pitești"]
    hero_names = {"Rm. Vâlcea": "Râmnicu Vâlcea"}
    present = {cur["city"] for cur, _prev in paired if cur["city"] != "—"}
    ordered = [c for c in hero_order if c in present] + sorted(c for c in present if c not in hero_order)
    city_list = ", ".join(hero_names.get(c, c) for c in ordered)

    deliv_l, _, deliv_card = trend_text(cur_chain["delivered"], prev_chain["delivered"], "pct", True, prev_ab)
    aov_l, _, aov_card = trend_text(cur_chain["aov"], prev_chain["aov"], "pct", True, "")
    fail_now = cur_chain["fail_rate"] or 0
    fail_prev = prev_chain["fail_rate"] or 0
    fail_l, _, fail_card = trend_text(fail_now, fail_prev, "pp", False, "")
    if abs(fail_now - fail_prev) < 0.15:
        fail_l, fail_card = "Stable", "kneu"
    plus_now = cur_chain["plus_share"] or 0
    plus_prev = prev_chain["plus_share"] or 0

    overview_rows = []
    for cur, prev in paired:
        inactive = cur["delivered"] <= 0 and prev["delivered"] > 0
        promo_c = "—" if inactive or cur["promo_share"] is None else f"{cur['promo_share']:.1f}%"
        promo_p = "—" if prev["promo_share"] is None else f"{prev['promo_share']:.1f}%"
        aov_c = "—" if inactive or cur["aov"] is None else f"{cur['aov']:.2f}"
        aov_p = "—" if prev["aov"] is None else f"{prev['aov']:.2f}"
        fail_css = ' class="tr"' if cur["failed"] >= 5 else ""
        if inactive:
            delivered_cur = "—"
            gmv_cur = "—"
            plus_cur = "—"
            fail_cur = "—"
            mom = mom_td(0, prev["delivered"], "inactive " + cur_ab)
        else:
            delivered_cur = fmt_int(cur["delivered"])
            gmv_cur = fmt_int(cur["gmv"])
            plus_cur = fmt_int(cur["bolt_plus"])
            fail_cur = fmt_int(cur["failed"])
            mom = mom_td(cur["delivered"], prev["delivered"])
        overview_rows.append(
            "<tr>"
            f'<td class="bold">{esc(cur["name"])}</td><td>{esc(cur["city"])}</td>'
            f"<td>{fmt_int(prev['delivered'])}</td>"
            f'<td class="bold">{delivered_cur}</td>'
            f"{mom}"
            f"<td>{fmt_int(prev['gmv'])}</td><td>{gmv_cur}</td>"
            f"<td>{aov_p}</td><td>{aov_c}</td>"
            f"<td>{promo_p}</td><td>{promo_c}</td>"
            f"<td>{fmt_int(prev['bolt_plus'])}</td><td>{plus_cur}</td>"
            f"<td>{fmt_int(prev['failed'])}</td>"
            f"<td{fail_css}>{fail_cur}</td>"
            "</tr>"
        )

    fail_pairs = []
    for cur, prev in paired:
        if cur["failed"] > 0:
            fail_pairs.append((f"{cur['name']} ({cur_ab})", cur["failed"], "var(--red)", "tr"))
        if prev["failed"] > 0:
            fail_pairs.append((f"{prev['name']} ({prev_ab})", prev["failed"], "var(--amber)", "ta"))
    fail_pairs.sort(key=lambda item: item[1], reverse=True)
    top_fails = fail_pairs[:6]
    max_fail = top_fails[0][1] if top_fails else 1
    fail_bars = []
    for label, value, color, css in top_fails:
        width = max(8, round(value / max_fail * 100))
        fail_bars.append(
            f'<div class="br-row"><div class="br-lbl">{esc(label)}</div>'
            f'<div class="br-track"><div class="br-fill" style="width:{width}%;background:{color}"></div></div>'
            f'<div class="br-val {css}">{fmt_int(value)}</div></div>'
        )
    ranked_fail = sorted(
        [cur for cur, _prev in paired if cur["delivered"] >= 30],
        key=lambda loc: (loc["fail_rate"] or 0),
        reverse=True,
    )
    slowest = sorted(
        [cur for cur, _prev in paired if cur["accept"] is not None and cur["delivered"] > 0],
        key=lambda loc: loc["accept"],
        reverse=True,
    )
    alert_bits = []
    if ranked_fail:
        top = ranked_fail[0]
        prev_match = previous.get(top["name"])
        prev_fail = int(prev_match["failed"]) if prev_match else 0
        alert_bits.append(
            f"<strong>{esc(top['name'])} — {fmt_int(top['failed'])} cancellations in {cur_name} "
            f"({(top['fail_rate'] or 0):.1f}% fail rate)</strong>, compared with {prev_fail} in {prev_name}."
        )
    if len(ranked_fail) > 1:
        second = ranked_fail[1]
        alert_bits.append(
            f"<strong>{esc(second['name'])} — {fmt_int(second['failed'])} cancellations "
            f"({(second['fail_rate'] or 0):.1f}%)</strong>."
        )
    if slowest:
        alert_bits.append(
            f"<strong>{esc(slowest[0]['name'])}</strong> has the slowest acceptance "
            f"({slowest[0]['accept']:.2f} min)."
        )
    prio = ", ".join(f"{esc(cur['name'])} ({fmt_int(cur['failed'])})" for cur, _prev in paired if cur["failed"] >= 3)
    if not prio:
        prio = "no location above 3 failed orders"

    month_labels = MON[:month]
    delivered_vals = [item["delivered"] for item in series]
    gmv_vals = [item["gmv"] for item in series]
    peak_i = max(range(len(delivered_vals)), key=lambda i: delivered_vals[i]) if delivered_vals else 0
    peak_share = pct(series[-1]["delivered"], ytd_del) or 0
    plus_share_ytd = pct(ytd_plus, ytd_del) or 0
    header_cells = "".join(f"<th>{label}</th>" for label in month_labels)
    def month_row(label, values, money=False):
        cells = []
        for i, value in enumerate(values):
            text = fmt_int(value)
            css = " class=\"bold\"" if i == len(values) - 1 else ""
            cells.append(f"<td{css}>{text}</td>")
        total = sum(values)
        return f"<tr><td class=\"bold\">{label}</td>{''.join(cells)}<td class=\"bold\">{fmt_int(total)}</td></tr>"

    promo_sorted = sorted(paired, key=lambda pair: pair[0]["campaign"], reverse=True)
    promo_rows = []
    for cur, prev in promo_sorted:
        if cur["delivered"] <= 0 and prev["delivered"] <= 0:
            continue
        def share(loc):
            return "—" if loc["delivered"] <= 0 or loc["promo_share"] is None else f"{loc['promo_share']:.1f}%"
        spend_css = ' class="ta"' if cur["spend_provider"] >= 80 else ""
        partner_cell = fmt_int(cur["spend_provider"]) if cur["delivered"] else "—"
        bolt_cell = fmt_int(cur["spend_bolt"]) if cur["delivered"] else "—"
        total_cell = fmt_int(cur["spend_bolt"] + cur["spend_provider"]) if cur["delivered"] else "—"
        promo_rows.append(
            "<tr>"
            f'<td class="bold">{esc(cur["name"])}</td>'
            f"<td>{fmt_int(prev['campaign']) if prev['delivered'] else '—'}</td><td>{share(prev)}</td>"
            f"<td>{fmt_int(cur['campaign']) if cur['delivered'] else '—'}</td><td>{share(cur)}</td>"
            f"<td>{bolt_cell}</td>"
            f"<td{spend_css}>{partner_cell}</td>"
            f'<td class="bold">{total_cell}</td>'
            "</tr>"
        )
    promo_delta, _, promo_card = trend_text(cur_chain["campaign"], prev_chain["campaign"], "pct", True, "")
    bolt_spend_share = pct(cur_chain["spend_bolt"], cur_chain["spend_bolt"] + cur_chain["spend_provider"]) or 0
    partner_spend_share = 100 - bolt_spend_share if cur_chain["spend_bolt"] + cur_chain["spend_provider"] else 0

    ops_sorted = sorted(
        [pair for pair in paired if pair[0]["delivered"] > 0],
        key=lambda pair: (pair[0]["courier"] is None, pair[0]["courier"] or 999),
    )
    ops_rows = []
    for cur, prev in ops_sorted:
        ops_rows.append(
            "<tr>"
            f"<td class=\"bold\">{esc(cur['name'])}</td><td>{esc(cur['city'])}</td>"
            f"{time_cell(prev['accept'], 'accept')}{time_cell(cur['accept'], 'accept')}"
            f"{time_cell(prev['prep'], 'prep')}{time_cell(cur['prep'], 'prep')}"
            f"{time_cell(prev['courier'], 'courier')}{time_cell(cur['courier'], 'courier')}"
            f"<td>{badge(ops_status(cur))}</td>"
            "</tr>"
        )
    worst_prep = sorted(
        [cur for cur, _prev in paired if cur["prep"] is not None and cur["delivered"] > 0],
        key=lambda loc: loc["prep"],
        reverse=True,
    )
    ops_alert = "Operational times are within the published thresholds."
    if worst_prep:
        leader = worst_prep[0]
        prev_leader = previous.get(leader["name"])
        prev_prep = f"{prev_leader['prep']:.2f} min in {prev_name}" if prev_leader and prev_leader["prep"] is not None else prev_name
        ops_alert = (
            f"<strong>{esc(leader['name'])} — prep {leader['prep']:.2f} min in {cur_name}</strong> "
            f"(from {prev_prep}). "
        )
        if slowest:
            ops_alert += (
                f"<strong>{esc(slowest[0]['name'])}</strong> has the slowest acceptance "
                f"({slowest[0]['accept']:.2f} min)."
            )

    imp_l, _, imp_card = trend_text(cur_chain["impressions"], prev_chain["impressions"], "pct", True, prev_ab)
    imp_menu_c = pct(cur_chain["menu"], cur_chain["impressions"]) or 0
    imp_menu_p = pct(prev_chain["menu"], prev_chain["impressions"]) or 0
    cart_c = pct(cur_chain["placed"] or cur_chain["delivered"], cur_chain["cart"]) or 0
    cart_p = pct(prev_chain["placed"] or prev_chain["delivered"], prev_chain["cart"]) or 0
    funnel_note = (
        f"Impressions moved <strong>{esc(imp_l)}</strong> "
        f"({fmt_int(prev_chain['impressions'])} → {fmt_int(cur_chain['impressions'])}). "
        f"Cart-to-order conversion went from {cart_p:.1f}% to {cart_c:.1f}%."
    )

    plus_l, _, plus_card = trend_text(cur_chain["bolt_plus"], prev_chain["bolt_plus"], "pct", True, "")
    plus_sorted = sorted(paired, key=lambda pair: pair[0]["bolt_plus"], reverse=True)
    plus_rows = []
    for cur, prev in plus_sorted:
        if cur["delivered"] <= 0 and prev["bolt_plus"] <= 0:
            continue
        share = "—" if not cur["delivered"] or cur["plus_share"] is None else f"{cur['plus_share']:.1f}%"
        plus_rows.append(
            "<tr>"
            f"<td class=\"bold\">{esc(cur['name'])}</td>"
            f"<td>{fmt_int(prev['bolt_plus'])}</td>"
            f"<td class=\"bold\">{fmt_int(cur['bolt_plus']) if cur['delivered'] else '—'}</td>"
            f"{mom_td(cur['bolt_plus'], prev['bolt_plus'])}"
            f"<td>{share}</td>"
            "<td>—</td>"
            "</tr>"
        )
    top_plus = plus_sorted[0][0] if plus_sorted else None
    shares = [cur for cur, _prev in paired if cur["delivered"] > 0 and cur["plus_share"] is not None]
    high_share = max(shares, key=lambda loc: loc["plus_share"]) if shares else None
    low_share = min(shares, key=lambda loc: loc["plus_share"]) if shares else None
    growers = []
    for cur, prev in paired:
        if prev["bolt_plus"] > 0 and cur["delivered"] > 0:
            growers.append((cur, (cur["bolt_plus"] - prev["bolt_plus"]) / prev["bolt_plus"] * 100))
    growers.sort(key=lambda item: item[1], reverse=True)
    plus_note_parts = []
    if growers:
        g_loc, g_delta = growers[0]
        plus_note_parts.append(
            f"<strong>{esc(g_loc['name'])} Bolt+ {('▲' if g_delta >= 0 else '▼')}{abs(g_delta):.0f}%</strong> "
            f"({fmt_int(previous[g_loc['name']]['bolt_plus'])} → {fmt_int(g_loc['bolt_plus'])})."
        )
    if high_share:
        plus_note_parts.append(
            f"<strong>{esc(high_share['name'])}</strong> has the highest Bolt+ share ({high_share['plus_share']:.1f}%)."
        )
    if low_share and (not high_share or low_share["name"] != high_share["name"]):
        plus_note_parts.append(
            f"<strong>{esc(low_share['name'])}</strong> has the lowest Bolt+ share ({low_share['plus_share']:.1f}%)."
        )

    rate_sorted = sorted(
        [pair for pair in paired if pair[0]["rating"] is not None and pair[0]["delivered"] > 0],
        key=lambda pair: pair[0]["rating"],
        reverse=True,
    )
    rate_l, _, rate_card = trend_text(cur_chain["rating"], prev_chain["rating"], "rating", True, prev_ab)
    rate_rows = []
    for cur, prev in rate_sorted:
        delta = None if prev["rating"] is None else cur["rating"] - prev["rating"]
        if delta is None:
            delta_cell = "<td>—</td>"
        elif delta >= 0.005:
            delta_cell = f'<td class="tg">▲{delta:.2f}</td>'
        elif delta <= -0.005:
            delta_cell = f'<td class="tr">▼{abs(delta):.2f}</td>'
        else:
            delta_cell = "<td>0.00</td>"
        cur_css = "tg" if cur["rating"] >= 4.3 else "tr" if cur["rating"] < 4 else "ta" if cur["rating"] < 4.1 else ""
        cur_td = f'<td class="{cur_css}">{cur["rating"]:.2f}</td>' if cur_css else f"<td>{cur['rating']:.2f}</td>"
        prev_txt = "—" if prev["rating"] is None else f"{prev['rating']:.2f}"
        bad_txt = "—" if cur["bad_rate"] is None else f"{cur['bad_rate'] * 100:.1f}%"
        good_txt = "—" if cur["good_rate"] is None else f"{cur['good_rate'] * 100:.1f}%"
        bad_css = "tr" if (cur["bad_rate"] or 0) >= 0.10 else ""
        bad_td = f'<td class="{bad_css}">{bad_txt}</td>' if bad_css else f"<td>{bad_txt}</td>"
        rate_rows.append(
            "<tr>"
            f"<td class=\"bold\">{esc(cur['name'])}</td><td>{esc(cur['city'])}</td>"
            f"<td>{prev_txt}</td>{cur_td}{delta_cell}{bad_td}<td>{good_txt}</td>"
            "</tr>"
        )
    best = rate_sorted[0][0] if rate_sorted else None
    worst = rate_sorted[-1][0] if rate_sorted else None
    rating_changes = []
    for cur, prev in paired:
        if cur["rating"] is not None and prev["rating"] is not None and cur["delivered"] > 0:
            rating_changes.append((cur, cur["rating"] - prev["rating"]))
    rating_changes.sort(key=lambda item: item[1])
    rate_note = ""
    if rating_changes:
        down_loc, down_d = rating_changes[0]
        up_loc, up_d = rating_changes[-1]
        rate_note = (
            f"<strong>Largest drop:</strong> {esc(down_loc['name'])} {down_d:+.2f} to {down_loc['rating']:.2f}★. "
            f"<strong>Largest gain:</strong> {esc(up_loc['name'])} {up_d:+.2f} to {up_loc['rating']:.2f}★."
        )
        if worst and worst["rating"] < 4:
            rate_note += f" <strong>{esc(worst['name'])}</strong> is below 4.0★."
    rated = [cur for cur, _prev in paired if cur.get("bad_rate") is not None and cur["delivered"] > 0]
    if rated:
        highest = max(rated, key=lambda loc: loc["bad_rate"])
        rate_note += (
            f" <strong>{esc(highest['name'])}</strong> has the highest bad-rating rate "
            f"at {highest['bad_rate'] * 100:.1f}%."
        )

    # Same pattern as the partner artifact: 8 cards — rating < 4.0 warnings first,
    # then lower-volume locations (first one "High priority"), best-rated last as "Base".
    sl_cards = []
    below = sorted([l for l in active if (l["rating"] or 0) < 4], key=lambda l: l["rating"] or 0)
    above = [l for l in active if (l["rating"] or 0) >= 4]
    best_loc = max(above, key=lambda l: l["rating"] or 0) if above else None
    rest = sorted([l for l in above if l is not best_loc], key=lambda l: l["delivered"])
    slots = max(0, 8 - len(below) - (1 if best_loc else 0))
    picked = below + rest[:slots] + ([best_loc] if best_loc else [])
    for idx, loc in enumerate(picked):
        rating = loc["rating"] or 0
        meta = f"{esc(loc['city'])} · {rating:.2f}★ · {fmt_int(loc['delivered'])} orders ({cur_ab})"
        imps = f"Impressions {cur_ab}: {fmt_int(loc['impressions'])}"
        if rating < 4:
            border = "var(--red)" if rating < 3.9 else "var(--amber)"
            note = (
                f"⚠ Fix rating first ({rating:.2f}★ → target 4.2★+) before activating SL"
                if rating < 3.9 else "⚠ Rating below 4.0★ — address ops first"
            )
            sl_cards.append(
                f'<div class="sl-card" style="border-color:{border}"><div class="sl-name">{esc(loc["name"])}</div>'
                f'<div class="sl-meta">{meta}</div><div class="sl-imp">{imps}</div>'
                f'<div style="font-size:11px;color:{border};font-weight:600;margin-top:4px">{note}</div></div>'
            )
        else:
            spent = (data.get("sl_current") or {}).get("by_name", {}).get(loc["name"])
            if spent and spent["spend"] > 0:
                roas = spent["roas_num"] / spent["roas_den"] if spent["roas_den"] else None
                cost_line = fmt_eur(spent["spend"], 2) + (f" · ROAS {roas:.1f}×" if roas else "")
                badge_html = '<span class="sl-priority badge bg">Live</span>'
            elif loc is best_loc:
                cost_line, badge_html = "58.31 €/week", '<span class="sl-priority badge bb">Base</span>'
            elif idx == len(below):
                cost_line, badge_html = "58.31 €/week · High priority", '<span class="sl-priority badge bg">High priority</span>'
            else:
                cost_line, badge_html = "58.31 €/week", '<span class="sl-priority badge bg">Recommended</span>'
            sl_cards.append(
                f'<div class="sl-card"><div class="sl-name">{esc(loc["name"])}</div>'
                f'<div class="sl-meta">{meta}</div><div class="sl-imp">{imps}</div>'
                f'<div class="sl-cost">{cost_line}</div>{badge_html}</div>'
            )

    loc_cards = []
    volume_leader = max(active, key=lambda loc: loc["delivered"])["name"] if active else ""
    for cur, prev in sorted(paired, key=lambda pair: pair[0]["delivered"], reverse=True):
        if cur["delivered"] <= 0:
            continue
        border = ""
        status = ops_status(cur)
        if (cur["rating"] or 5) < 4 or status == "Critical" or (cur["fail_rate"] or 0) >= 5:
            border = ' style="border-color:var(--red);border-width:2px"'
        elif status == "Attention" or (cur["fail_rate"] or 0) >= 3:
            border = ' style="border-color:var(--amber);border-width:2px"'
        rating_css = ' style="color:var(--red)"' if cur["rating"] is not None and cur["rating"] < 4 else ""
        rating_txt = f"{cur['rating']:.2f} ★" if cur["rating"] is not None else "—"
        mom_label, _, _ = trend_text(cur["delivered"], prev["delivered"], "pct", True, "")
        good = []
        if cur["name"] == volume_leader:
            good.append("#1 volume")
        if prev["delivered"] and abs(cur["delivered"] - prev["delivered"]) / prev["delivered"] >= 0.01:
            good.append(mom_label + " MoM")
        if cur["rating"] and cur["rating"] >= 4.5:
            good.append(f"rating {cur['rating']:.2f}★")
        if cur["failed"] == 0:
            good.append("0 cancellations")
        if cur["prep"] is not None and cur["prep"] <= 12:
            good.append(f"prep {cur['prep']:.1f} min")
        bad = []
        if cur["fail_rate"] and cur["fail_rate"] >= 3:
            bad.append(f"{fmt_int(cur['failed'])} cancellations ({cur['fail_rate']:.1f}% fail)")
        if cur["accept"] and cur["accept"] > 0.5:
            bad.append(f"acceptance {cur['accept']:.2f} min")
        if cur["prep"] and cur["prep"] > 16:
            bad.append(f"prep {cur['prep']:.1f} min")
        if cur["courier"] and cur["courier"] > 28:
            bad.append(f"delivery {cur['courier']:.1f} min")
        if cur["rating"] and cur["rating"] < 4:
            bad.append(f"rating {cur['rating']:.2f}★")
        if not good:
            good.append(f"AOV {cur['aov']:.2f} €" if cur["aov"] else "open this month")
        if not bad:
            bad.append(f"Bolt+ {(cur['plus_share'] or 0):.1f}% · promo {(cur['promo_share'] or 0):.0f}%")
        aov_txt = fmt_eur(cur["aov"], 2) if cur["aov"] is not None else "—"
        loc_cards.append(
            f'<div class="lcard"{border}>'
            '<div class="lcard-h"><div>'
            f'<div class="lname">{esc(cur["name"])}</div><div class="lcity">{esc(cur["city"])}</div></div>'
            f'<div style="text-align:right"><div class="lrating"{rating_css}>{rating_txt}</div>'
            f'<div class="lstars">{stars(cur["rating"])}</div></div></div>'
            '<div class="lmetrics">'
            f'<div class="lm"><div class="lm-v">{fmt_int(cur["delivered"])}</div><div class="lm-l">Delivered</div></div>'
            f'<div class="lm"><div class="lm-v">{fmt_eur(cur["gmv"])}</div><div class="lm-l">Revenue</div></div>'
            f'<div class="lm"><div class="lm-v">{aov_txt}</div><div class="lm-l">AOV</div></div>'
            '</div>'
            f'<div class="ltag" style="color:var(--green-d)">✓ {esc(" · ".join(good))}</div>'
            f'<div class="ltag" style="color:var(--amber);margin-top:4px">△ {esc(" · ".join(bad))}</div>'
            '</div>'
        )

    dishes = section_by_id(original, "dishes", "availability")
    refunds = section_by_id(original, "refunds", "sponsored")
    top_plus_label = "—"
    top_plus_detail = "—"
    if top_plus and top_plus["delivered"]:
        top_plus_label = top_plus["name"]
        top_plus_detail = f"{fmt_int(top_plus['bolt_plus'])} orders · {(top_plus['plus_share'] or 0):.1f}%"

    sl_now = data.get("sl_current") or {"spend": 0.0, "active": 0, "impressions": 0.0, "by_name": {}}
    sl_prev = data.get("sl_previous") or {"spend": 0.0, "active": 0, "impressions": 0.0, "by_name": {}}
    sl_gmv_share = (sl_now["spend"] / cur_chain["gmv"] * 100.0) if cur_chain["gmv"] else 0.0
    if sl_now["active"] == 0 and sl_prev["active"] == 0:
        sl_tip = (
            f"No Hesburger location had active Sponsored Listing in {prev_name} or {cur_name} {year}. "
            f"All {active_n} locations are candidates for launch."
        )
    else:
        sl_tip = (
            f"Sponsored Listing investment in {cur_name}: {fmt_eur(sl_now['spend'], 2)} "
            f"({sl_gmv_share:.1f}% of GMV), across {sl_now['active']} locations."
        )

    prev_aov = prev_for_hero["aov"]
    cur_aov = cur_chain["aov"]
    hero_prev = hero_kpis(
        "h-jul", True, prev_for_hero, prev_compare, before_ab,
        ytd_through_prev, ytd_gmv_prev, ytd_prev_label, active_n,
    )
    hero_cur = hero_kpis(
        "h-aug", False, cur_chain, prev_chain, prev_ab,
        ytd_del, ytd_gmv, ytd_cur_label, active_n,
    )
    hero_mtd = ""
    mtd_button = ""
    mtd = data.get("mtd")
    if mtd:
        mtd_chain = chain(mtd["current"])
        mtd_compare = chain(mtd["compare"])
        mtd_locs = sum(1 for loc in mtd["current"] if loc["delivered"] > 0)
        mtd_vs = f"1–{mtd['compare_end']} {MON[month - 1]}"
        hero_mtd = hero_kpis(
            "h-mtd", False, mtd_chain, mtd_compare, mtd_vs,
            ytd_del + mtd_chain["delivered"], ytd_gmv + mtd_chain["gmv"],
            f"Jan–{mtd['end_day']} {MON[mtd['month'] - 1]}", mtd_locs or active_n,
        )
        mtd_button = (
            f'<button class="tab" onclick="showMonth(\'mtd\')">'
            f'{MON[mtd["month"] - 1]} TD</button>'
        )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hesburger × Bolt Food — {prev_ab}–{cur_ab} {year} · Romania</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=DM+Serif+Display:ital@0;1&display=swap" rel="stylesheet">
{style_block(original)}
</head>
<body>

<nav class="topnav">
  <div class="topnav-brand">Hesburger × Bolt Food · RO</div>
  <a href="#weekly">Weekly</a>
  <a href="#overview">Overview</a>
  <a href="#cancellations">Cancellations</a>
  <a href="#monthly">Monthly</a>
  <a href="#promo">Promo</a>
  <a href="#dishes">Top dishes</a>
  <a href="#availability">Availability</a>
  <a href="#funnel">Funnel</a>
  <a href="#boltplus">Bolt+</a>
  <a href="#ratings">Rating</a>
  <a href="#refunds">Refunds</a>
  <a href="#sponsored">Sponsored Listing</a>
  <a href="#locations">Locations</a>
</nav>

<div class="hero" id="hero">
  <div class="wrap">
    <div class="hero-pill">Bolt Food Romania · Partner Analytics</div>
    <h1>Hesburger × Bolt Food<br>Performance Report</h1>
    <p class="hero-sub">{esc(loc_label)} locations · {esc(city_list)} · {prev_ab}–{cur_ab} {year} · Generated on {esc(generated)}</p>
    <div class="tab-bar">
      <button class="tab active" onclick="showMonth('jul')">{prev_name} {data['prev_year']}</button>
      <button class="tab" onclick="showMonth('aug')">{cur_name} {year}</button>
      {mtd_button}
    </div>
    {hero_prev}
    {hero_cur}
    {hero_mtd}
  </div>
</div>

{weekly_section(data)}

<div id="overview"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Chain overview</p>
  <p class="sec-sub">All locations · {prev_ab} vs {cur_ab} {year} · {esc(month_note)}</p>
  <div class="kpi-row">
    {card(f"Delivered — {prev_ab}", fmt_int(prev_chain['delivered']), trend_text(prev_chain['delivered'], before['delivered'], 'pct', True, before_ab)[0], trend_text(prev_chain['delivered'], before['delivered'], 'pct', True, before_ab)[2])}
    {card(f"Delivered — {cur_ab}", fmt_int(cur_chain['delivered']), deliv_l, deliv_card)}
    {card(f"AOV {prev_ab} / {cur_ab}", (f"{prev_aov:.2f} / {cur_aov:.2f} €" if prev_aov and cur_aov else "—"), aov_l, aov_card)}
    {card(f"Fail rate {prev_ab} / {cur_ab}", f"{fail_prev:.1f}% / {fail_now:.1f}%", fail_l, fail_card)}
    {card(f"Bolt+ share {prev_ab} / {cur_ab}", f"{plus_prev:.1f}% / {plus_now:.1f}%", f"{fmt_int(prev_chain['bolt_plus'])} → {fmt_int(cur_chain['bolt_plus'])}", "kneu")}
    {card(f"YTD delivered {ytd_cur_label}", fmt_int(ytd_del), f"{fmt_eur(ytd_gmv)} YTD", "kneu")}
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Location</th><th>City</th>
        <th>Delivered {prev_ab}</th><th>Delivered {cur_ab}</th><th>MoM</th>
        <th>Revenue {prev_ab} €</th><th>Revenue {cur_ab} €</th>
        <th>AOV {prev_ab} €</th><th>AOV {cur_ab} €</th>
        <th>Promo% {prev_ab}</th><th>Promo% {cur_ab}</th>
        <th>Bolt+ {prev_ab}</th><th>Bolt+ {cur_ab}</th>
        <th>Failed {prev_ab}</th><th>Failed {cur_ab}</th>
      </tr></thead>
      <tbody>
        {''.join(overview_rows)}
      </tbody>
    </table>
  </div>
</div></div>

<hr class="divider">

<div id="cancellations"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Cancellation reasons</p>
  <p class="sec-sub">Failed orders breakdown by location · {prev_ab} &amp; {cur_ab} {year}</p>
  <div class="chart-2">
    <div class="ccard">
      <div class="ccard-t">Failed orders — chain total</div>
      <div class="kpi-row" style="grid-template-columns:1fr 1fr;margin-bottom:16px;">
        {card(f"Failed — {prev_name}", fmt_int(prev_chain['failed']), f"{fail_prev:.1f}% fail rate", "kneu")}
        {card(f"Failed — {cur_name}", fmt_int(cur_chain['failed']), f"{fail_now:.1f}% fail rate", "kneu")}
      </div>
      <div class="bars">
        {''.join(fail_bars)}
      </div>
    </div>
    <div class="ccard">
      <div class="ccard-t">What drives failed orders</div>
      <p style="font-size:12px;color:var(--ink-m);line-height:1.6;margin-bottom:12px">All cancellations in {cur_ab} {year} fall into one of four categories — each with a different action owner:</p>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <div style="background:var(--red-pale);border-radius:8px;padding:10px 12px"><div style="font-weight:700;font-size:11px;color:var(--red);margin-bottom:3px">Restaurant</div><div style="font-size:11px;color:var(--ink-m)">Did not accept / late confirmation / out-of-stock item → {prio}</div></div>
        <div style="background:var(--amber-pale);border-radius:8px;padding:10px 12px"><div style="font-weight:700;font-size:11px;color:var(--amber);margin-bottom:3px">Courier</div><div style="font-size:11px;color:var(--ink-m)">Did not pick up on time, couldn't find the venue</div></div>
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px"><div style="font-weight:700;font-size:11px;color:var(--ink-l);margin-bottom:3px">Customer</div><div style="font-size:11px;color:var(--ink-m)">Cancelled due to long wait, placed by mistake</div></div>
        <div style="background:var(--blue-pale);border-radius:8px;padding:10px 12px"><div style="font-weight:700;font-size:11px;color:var(--blue);margin-bottom:3px">Bolt / System</div><div style="font-size:11px;color:var(--ink-m)">No courier found in zone</div></div>
      </div>
    </div>
  </div>
  <div class="alert">{' '.join(alert_bits)}</div>
</div></div>

<hr class="divider">

<div id="monthly"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Monthly dynamics — January–{cur_name} {year}</p>
  <p class="sec-sub">Chain total YTD · {cur_name} vs {prev_name}</p>
  <div class="kpi-row">
    {card(f"YTD Delivered {ytd_cur_label}", fmt_int(ytd_del), f"{cur_ab}: {fmt_int(series[-1]['delivered'])} ({peak_share:.1f}% of YTD)", "kneu")}
    {card(f"YTD Revenue {ytd_cur_label}", fmt_eur(ytd_gmv), f"{cur_ab}: {fmt_eur(series[-1]['gmv'])}", "kneu")}
    {card("YTD Bolt+ orders", fmt_int(ytd_plus), f"{plus_share_ytd:.1f}% YTD share", "kneu")}
    {card("Peak month", MONTHS[peak_i], f"{fmt_int(delivered_vals[peak_i])} orders · {fmt_eur(gmv_vals[peak_i])}", "kneu")}
  </div>
  <div class="chart-2">
    <div class="ccard">
      <div class="ccard-t">Delivered orders by month</div>
      {bar_svg(delivered_vals, month_labels, fmt_int, axis_count, "var(--green)")}
    </div>
    <div class="ccard">
      <div class="ccard-t">Revenue by month (€)</div>
      {bar_svg(gmv_vals, month_labels, lambda v: f"{v/1000:.0f}k" if v >= 1000 else fmt_int(v), axis_eur, "#60C4A0")}
    </div>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Metric</th>{header_cells}<th>YTD</th></tr></thead>
      <tbody>
        {month_row("Delivered", delivered_vals)}
        {month_row("Revenue €", gmv_vals)}
        {month_row("Bolt+ orders", [item['bolt_plus'] for item in series])}
        {month_row("Failed orders", [item['failed'] for item in series])}
      </tbody>
    </table>
  </div>
</div></div>

<hr class="divider">

<div id="promo"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Promo analytics — {prev_ab} &amp; {cur_ab} {year}</p>
  <p class="sec-sub">Campaign spend Bolt vs. partner · promo order share per location</p>
  <div class="kpi-row">
    {card(f"Promo orders — {prev_ab}", fmt_int(prev_chain['campaign']), f"{(prev_chain['promo_share'] or 0):.1f}% of delivered", "kneu")}
    {card(f"Promo orders — {cur_ab}", fmt_int(cur_chain['campaign']), f"{promo_delta} · {(cur_chain['promo_share'] or 0):.1f}%", promo_card)}
    {card(f"Bolt promo spend — {cur_ab}", fmt_eur(cur_chain['spend_bolt']), f"{bolt_spend_share:.1f}% of total", "kneu")}
    {card(f"Partner promo spend — {cur_ab}", fmt_eur(cur_chain['spend_provider']), f"{partner_spend_share:.1f}% of total", "kneu")}
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Location</th><th>Promo {prev_ab}</th><th>%</th><th>Promo {cur_ab}</th><th>%</th>
        <th>Bolt spend {cur_ab} €</th><th>Partner spend {cur_ab} €</th><th>Total {cur_ab} €</th>
      </tr></thead>
      <tbody>
        {''.join(promo_rows)}
      </tbody>
    </table>
  </div>
  {OFFER_HTML}
</div></div>

<hr class="divider">

{dishes}
<hr class="divider">

<div id="availability"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Location availability &amp; operations</p>
  <p class="sec-sub">Acceptance · preparation · delivery times per location · {prev_ab} vs {cur_ab} {year}</p>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Location</th><th>City</th>
        <th>Acceptance {prev_ab}</th><th>Acceptance {cur_ab}</th>
        <th>Prep {prev_ab}</th><th>Prep {cur_ab}</th>
        <th>Delivery {prev_ab}</th><th>Delivery {cur_ab}</th>
        <th>Status {cur_ab}</th>
      </tr></thead>
      <tbody>
        {''.join(ops_rows)}
      </tbody>
    </table>
  </div>
  <p style="font-size:10px;color:var(--ink-l);margin-top:6px">Acceptance: ≤0.5 good · 0.5–1 attention · &gt;1 critical. Prep: ≤12 min good · 12–16 attention · &gt;16 critical.</p>
  <div class="alert">{ops_alert}</div>
</div></div>

<hr class="divider">

<div id="funnel"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Customer journey funnel</p>
  <p class="sec-sub">From impression to placed order · Hesburger chain total · {prev_ab} vs {cur_ab} {year}</p>
  <div class="chart-2">
    {funnel_card(f"{prev_name} {data['prev_year']} — chain funnel", prev_chain)}
    {funnel_card(f"{cur_name} {year} — chain funnel", cur_chain)}
  </div>
  <div class="insight">{funnel_note} Menu-open rate moved from {imp_menu_p:.1f}% to {imp_menu_c:.1f}%.</div>
</div></div>

<hr class="divider">

<div id="boltplus"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Bolt+ — subscriber analytics</p>
  <p class="sec-sub">Bolt+ orders and delivery investment · {prev_ab} &amp; {cur_ab} {year}</p>
  <div class="kpi-row">
    {card(f"Bolt+ orders — {prev_ab}", fmt_int(prev_chain['bolt_plus']), f"{plus_prev:.1f}% share", "kneu")}
    {card(f"Bolt+ orders — {cur_ab}", fmt_int(cur_chain['bolt_plus']), f"{plus_l} · {plus_now:.1f}% share", plus_card)}
    {card(f"Bolt delivery invest. {cur_ab}", "—", "not in this Looker extract", "kneu")}
    {card(f"Top Bolt+ location ({cur_ab})", esc(top_plus_label), top_plus_detail, "kneu")}
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Location</th><th>Bolt+ {prev_ab}</th><th>Bolt+ {cur_ab}</th><th>MoM</th><th>Share {cur_ab}</th><th>Bolt invest. {cur_ab} €</th></tr></thead>
      <tbody>
        {''.join(plus_rows)}
      </tbody>
    </table>
  </div>
  <div class="insight">{' '.join(plus_note_parts)}</div>
</div></div>

<hr class="divider">

<div id="ratings"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Rating &amp; quality</p>
  <p class="sec-sub">Average customer ratings per location · {prev_ab} &amp; {cur_ab} {year}</p>
  <div class="kpi-row">
    {card(f"Avg chain rating — {prev_ab}", f"{prev_chain['rating']:.2f} ★" if prev_chain['rating'] is not None else "—", f"{len(previous)} locations", "kneu")}
    {card(f"Avg chain rating — {cur_ab}", f"{cur_chain['rating']:.2f} ★" if cur_chain['rating'] is not None else "—", rate_l, rate_card)}
    {card(f"Best ({cur_ab})", f"{best['rating']:.2f} ★" if best else "—", best['name'] if best else "—", "kneu")}
    {card(f"Critical ({cur_ab})", f"{worst['rating']:.2f} ★" if worst else "—", worst['name'] if worst else "—", "kdn" if worst and worst['rating'] < 4 else "kneu")}
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Location</th><th>City</th><th>Rating {prev_ab} ★</th><th>Rating {cur_ab} ★</th><th>Change</th><th>Bad rating% {cur_ab}</th><th>Good rating% {cur_ab}</th></tr></thead>
      <tbody>
        {''.join(rate_rows)}
      </tbody>
    </table>
  </div>
  <div class="insight">{rate_note}</div>
</div></div>

<hr class="divider">

{refunds}
<hr class="divider">

<div id="sponsored"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Sponsored Listing — paid promotion</p>
  <p class="sec-sub">A tool to boost venue visibility in the Bolt Food app · 8.33 € / day per location</p>
  <div class="kpi-row">
    {card("Cost per location", "8.33 €/day", "58.31 €/week", "kneu")}
    {card("Active SL locations", f"{sl_now['active']} / {active_n}", f"No SL active in {cur_ab}" if sl_now['active'] == 0 else f"{sl_now['active']} locations spending", "kdn" if sl_now['active'] == 0 else "kup")}
    {card(f"SL investment — {cur_ab}", fmt_eur(sl_now['spend'], 2 if sl_now['spend'] else 0), f"{sl_gmv_share:.1f}% of GMV · {fmt_eur(sl_prev['spend'], 2 if sl_prev['spend'] else 0)} in {prev_ab}", "kneu")}
    {card(f"Total {cur_ab} impressions", fmt_int(cur_chain['impressions']), imp_l, imp_card)}
  </div>
  <div class="tip">
    <strong>{sl_tip}</strong> SL is most effective during peak hours: lunch 12:00–14:00, dinner 18:00–21:00. For locations with rating below 4.0★ — improve quality first, then activate SL. Typical ROI is 3–8× per € spent → GMV.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:20px">
    {''.join(sl_cards)}
  </div>
</div></div>

<hr class="divider">

<div id="locations"></div>
<div class="wrap"><div class="section">
  <p class="sec-title">Detailed location analytics — {cur_name} {year}</p>
  <p class="sec-sub">Strengths, growth areas and key metrics per location</p>
  <div class="loc-grid">
    {''.join(loc_cards)}
  </div>
</div></div>

<footer class="footer">
  Bolt Food Romania × Hesburger · Confidential report · {prev_name}–{cur_name} {year}<br>
  Account Management Team · Data: Bolt Looker (curated_delivery / fact_provider · incentives / sponsored listings)<br>
  Generated on {esc(generated)}
</footer>

<script>
function showMonth(m){{
  document.getElementById('h-jul').style.display = m==='jul'?'grid':'none';
  document.getElementById('h-aug').style.display = m==='aug'?'grid':'none';
  var hm = document.getElementById('h-mtd');
  if (hm) hm.style.display = m==='mtd'?'grid':'none';
  document.querySelectorAll('.tab').forEach((t,i)=>{{
    t.classList.toggle('active',(i===0&&m==='jul')||(i===1&&m==='aug')||(i===2&&m==='mtd'));
  }});
}}
</script>
</body>
</html>
"""
    if "Generated on" not in page:
        raise RuntimeError("Generated date missing from report")
    if 'id="dishes"' not in page or 'id="refunds"' not in page:
        raise RuntimeError("Static dishes or refunds section was not preserved")
    return page


def publish(token, page):
    github = Github(token)
    repo = github.get_repo(REPO_NAME)
    contents = repo.get_contents("index.html", ref=repo.default_branch)
    current = contents.decoded_content.decode("utf-8")
    if current == page:
        log("index.html already matches this run; no commit created")
        return repo.default_branch
    repo.update_file(
        "index.html",
        f"Update Hesburger RO report {datetime.now().strftime('%Y-%m-%d')}",
        page,
        contents.sha,
        branch=repo.default_branch,
    )
    log(f"Pushed index.html to {REPO_NAME} branch {repo.default_branch}")
    return repo.default_branch


def main():
    log("Hesburger RO update started")
    token = load_token()
    session = looker_session()
    data = fetch_queries(session)
    log(
        f"Months {MON[data['prev_month']-1]} vs {MON[data['month']-1]} {data['year']}: "
        f"{len(data['current'])} current locations, {len(data['previous'])} previous, "
        f"{len(data['ytd'])} YTD rows"
    )
    if TEMPLATE_FILE.exists():
        original = TEMPLATE_FILE.read_text(encoding="utf-8")
        log(f"Using partner template {TEMPLATE_FILE} ({len(original)} bytes)")
    elif REPO_TEMPLATE_FILE.exists():
        original = REPO_TEMPLATE_FILE.read_text(encoding="utf-8")
        log(f"Using repo template {REPO_TEMPLATE_FILE} ({len(original)} bytes)")
    else:
        github = Github(token)
        repo = github.get_repo(REPO_NAME)
        original = repo.get_contents("index.html", ref=repo.default_branch).decoded_content.decode("utf-8")
        log(f"Template missing; fetched index.html from {REPO_NAME} ({len(original)} bytes)")
    page = build_html(original, data)
    publish(token, page)
    log(f"SUCCESS report generated on {data['today'].strftime('%d %B %Y').lstrip('0')}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FAILED\n" + traceback.format_exc())
        raise
