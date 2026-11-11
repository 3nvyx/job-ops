#!/usr/bin/env python3
"""List new Summer 2027 internships from SimplifyJobs and speedyapply that fit your search.

Usage: python3 -I new-internships.py [--days N] [--json]

Downloads SimplifyJobs/Summer2027-Internships listings.json and the US tables of
speedyapply/2027-SWE-College-Jobs, keeps active US Summer 2027 postings that are Technical PM or software (full-stack/frontend/web/
general SWE) internships anywhere in the US (OC/LA, Bay Area and remote sorted first), and
drops anything already in career-ops (scan history, pipeline, tracker).
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request

URLS = [
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/main/.github/scripts/listings.json",
]
SPEEDYAPPLY_URL = "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/README.md"
SEEN_FILES = [
    "<<CAREER_OPS>>/data/scan-history.tsv",
    "<<CAREER_OPS>>/data/pipeline.md",
    "<<CAREER_OPS>>/data/applications.md",
]
# EDIT ME: your preferred areas (sorted first in the output). This is only an example.
AREAS = re.compile(
    r"New York|NYC|Brooklyn|Manhattan|Jersey City|Hoboken|"
    r"Seattle|Bellevue|Redmond|Kirkland|"
    r"San Francisco|SF|Bay Area|Palo Alto|Mountain View|Sunnyvale|San Jose|Oakland",
    re.I,
)
SPEEDYAPPLY_TABLES = re.compile(r"<!-- TABLE(?:_FAANG)?_START -->(.*?)<!-- TABLE(?:_FAANG)?_END -->", re.S)
SPEEDYAPPLY_ROW = re.compile(
    r'^\| <a href="[^"]*"><strong>(?P<company>.*?)</strong></a> \| (?P<title>.*?) \| (?P<locations>.*?) \| '
    r'(?:(?P<salary>[^|]*?) \| )?<a href="(?P<url>[^"]+)"><img [^|]*</a> \| (?P<age>\d+)d \|$',
    re.M,
)


def normalize_url(url):
    """Comparison key: the two lists write one posting with different case, locale and tracking bits."""
    url = re.sub(r"/application(\?embed=true)?$", "", url.strip()).replace("?embed=true", "").lower()
    parts = urllib.parse.urlsplit(url)
    path = re.sub(r"^/[a-z]{2}-[a-z]{2}(?=/)", "", parts.path).rstrip("/")  # a locale only comes right after the host
    # Workday lists one posting under several career sites, and only the segment ending in its id is stable.
    if parts.netloc.endswith(".myworkdayjobs.com"):
        workday = re.search(r"/job/(?:.*/)?([^/]*_[a-z0-9-]*\d[a-z0-9-]*)(?:/apply.*)?$", path)
        if workday:
            return "%s/%s" % (parts.netloc, re.sub(r"-\d{1,2}$", "", workday.group(1)))  # -1 marks a repost
    amazon = re.match(r"(?:/[a-z]{2})?/jobs/(\d+)", path)
    if amazon and parts.netloc in ("amazon.jobs", "www.amazon.jobs"):
        return "amazon.jobs/" + amazon.group(1)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    rebuilt = "%s://%s%s" % (parts.scheme, parts.netloc, path)
    return rebuilt + ("?" + urllib.parse.urlencode(query) if query else "")


def parse_speedyapply(text):
    """Rows of the FAANG+ and Other tables. The quant table is left out on purpose."""
    rows = []
    for table in SPEEDYAPPLY_TABLES.findall(text):
        for m in SPEEDYAPPLY_ROW.finditer(table):
            row = {k: html.unescape(v or "").strip() for k, v in m.groupdict().items()}
            row["age"] = int(row["age"])
            rows.append(row)
    return rows


def speedyapply_jobs(rows, days, seen, today=None):
    """Same filters as the Simplify loop. Adds what it keeps to seen, so Simplify's copy wins."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    out = []
    for x in rows:
        title = x["title"]
        if x["age"] > days or EXCLUDE_TITLE.search(title) or OTHER_TERM.search(title) or NOT_A_FIT.search(title):
            continue
        if OTHER_YEAR.search(title) and "2027" not in title:
            continue
        if PM_TITLE.search(title):
            track = "Technical PM"
        elif SWE_TITLE.search(title):
            track = "Full-Stack SWE"
        else:
            continue
        loc = x["locations"].strip()
        if not US.search(loc) or FOREIGN.search(loc):
            continue
        key = normalize_url(x["url"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "company": x["company"], "title": title, "track": track, "url": x["url"],
            "locations": loc, "posted": (today - dt.timedelta(days=x["age"])).strftime("%Y-%m-%d"),
            "sponsorship": None, "degrees": [],
            "preferred_area": bool(AREAS.search(loc) or BARE_AREAS.match(loc)),
            "source": "speedyapply", "salary": x["salary"],
        })
    return out


def load_speedyapply():
    """A second source only: if it's down, warn and carry on with Simplify."""
    try:
        with urllib.request.urlopen(SPEEDYAPPLY_URL, timeout=60) as r:
            rows = parse_speedyapply(r.read().decode("utf-8"))
    except Exception as e:
        print(f"speedyapply skipped: {e}", file=sys.stderr)
        return []
    if not rows:  # its README layout changed; don't mistake that for "nothing new"
        print("speedyapply skipped: no rows parsed", file=sys.stderr)
    return rows


def load_listings():
    for url in URLS:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # try the next branch
            last = e
    sys.exit(f"Could not download Simplify listings: {last}")


def main():
    days = 3
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    seen = set()
    for path in SEEN_FILES:
        try:
            seen |= {normalize_url(u) for u in re.findall(r"https?://[^\s|)]+", open(path).read())}
        except FileNotFoundError:
            pass
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out = []
    for x in load_listings():
        if not (x.get("active") and x.get("is_visible")):
            continue
        if "Summer 2027" not in (x.get("terms") or []):
            continue
        if x.get("sponsorship") == "U.S. Citizenship is Required":
            continue
        posted = dt.datetime.fromtimestamp(x.get("date_posted") or 0, dt.timezone.utc)
        if posted < cutoff:
            continue
        title, cat = x.get("title", ""), x.get("category", "")
        if EXCLUDE_TITLE.search(title):
            continue
        if cat.startswith("Product") and PM_TITLE.search(title):
            track = "Technical PM"
        elif cat.startswith("Software") and SWE_TITLE.search(title):
            track = "Full-Stack SWE"
        else:
            continue
        locs = x.get("locations") or []
        us_locs = [l for l in locs if US.search(l.strip()) and not FOREIGN.search(l)]
        if not us_locs:
            continue
        preferred = any(AREAS.search(l) or BARE_AREAS.match(l.strip()) for l in locs)
        url = re.sub(r"/application(\?embed=true)?$", "", x["url"]).replace("?embed=true", "")
        if normalize_url(url) in seen:
            continue
        seen.add(normalize_url(url))
        out.append({
            "company": x["company_name"], "title": title, "track": track, "url": url,
            "locations": "; ".join(locs), "posted": posted.strftime("%Y-%m-%d"),
            "sponsorship": x.get("sponsorship"), "degrees": x.get("degrees") or [],
            "preferred_area": preferred, "source": "simplify",
        })
    out += speedyapply_jobs(load_speedyapply(), days, seen)
    out.sort(key=lambda o: (o["preferred_area"], o["posted"]), reverse=True)
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1))
    else:
        for o in out:
            print(f"{o['posted']} | {o['track']} | {o['company']} | {o['title']} | {o['locations']} | {o['url']}")
        print(f"{len(out)} new in the last {days} days")


if __name__ == "__main__":
    main()
