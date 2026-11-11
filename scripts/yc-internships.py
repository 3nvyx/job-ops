#!/usr/bin/env python3
"""List YC startup internships from the public Y Combinator job pages that fit your search.

Usage: python3 -I yc-internships.py [--json]

Reads the job data embedded in workatastartup.com/internships and the ycombinator.com/jobs
role pages (no sign-in, so only the public subset: the full list needs a Work at a Startup
account, which the morning check reads in the browser pane). Keeps internships that are
Technical PM or software roles in the US for Summer 2027 (or with no season stated and
posted within ~6 months), using the same title and location filters as new-internships.py,
and drops anything already in career-ops (scan history, pipeline, tracker).
"""
import html
import importlib.util
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
PAGES = [
    "https://www.workatastartup.com/internships",
    "https://www.ycombinator.com/jobs/role/software-engineer",
    "https://www.ycombinator.com/jobs/role/product-manager",
]
BASE = "https://www.ycombinator.com"
OLD_SEASON = re.compile(r"\b20(2[0-6])\b")
MONTHS = re.compile(r"(\d+)\s+months?", re.I)
URL = re.compile(r"https?://[^\s|)\]>\"']+")


def load_filters():
    spec = importlib.util.spec_from_file_location("new_internships", os.path.join(HERE, "new-internships.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def postings(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (internship-search)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r'data-page="([^"]+)"', page)
    if not m:
        return []
    return json.loads(html.unescape(m.group(1))).get("props", {}).get("jobPostings") or []


def too_old(created):
    """createdAt is relative ("4 months", "over 6 months", "about 1 year"); keep under 6 months."""
    created = (created or "").lower()
    if "year" in created:
        return True
    m = MONTHS.search(created)
    if not m:
        return False
    months = int(m.group(1))
    return months > 6 or (months == 6 and "over" in created)


def fits(f, j):
    title = j.get("title") or ""
    if (j.get("type") or "").lower() != "internship":
        return False
    if not (f.SWE_TITLE.search(title) or f.PM_TITLE.search(title)) or f.EXCLUDE_TITLE.search(title):
        return False
    # An older season anywhere in the title ("Fall 2026 (graduates 2027)") means it is not Summer 2027.
    if OLD_SEASON.search(title) or ("2027" not in title and too_old(j.get("createdAt"))):
        return False
    locs = [l.strip() for l in (j.get("location") or "").split("/") if l.strip()]
    return any((f.US.search(l) or "Remote (US)" in l) and not f.FOREIGN.search(l) for l in locs)


def seen_urls(f):
    urls = set()
    for path in f.SEEN_FILES:
        try:
            urls.update(u.lower().rstrip(".,;") for u in URL.findall(open(path).read()))
        except FileNotFoundError:
            pass
    return urls


def main():
    f = load_filters()
    seen = seen_urls(f)
    out, urls, errors = [], set(), []
    for page in PAGES:
        try:
            jobs = postings(page)
        except Exception as e:  # one bad page shouldn't stop the rest
            errors.append(f"{page}: {e}")
            continue
        for j in jobs:
            url = BASE + j["url"] if (j.get("url") or "").startswith("/") else j.get("url")
            if not url or url.lower() in urls or url.lower() in seen or not fits(f, j):
                continue
            urls.add(url.lower())
            out.append({
                "company": j.get("companyName"),
                "title": j.get("title"),
                "url": url,
                "locations": "; ".join(l.strip() for l in j["location"].split("/")),
                "posted": f"~{j.get('createdAt')} ago" if j.get("createdAt") else None,
                "batch": j.get("companyBatchName"),
                "visa": j.get("visa"),
                "preferred_area": bool(f.AREAS.search(j.get("location") or "")),
            })
    out.sort(key=lambda j: not j["preferred_area"])
    for e in errors:
        print(f"warning: {e}", file=sys.stderr)
    if len(errors) == len(PAGES):
        sys.exit("error: no YC page could be read")
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1))
    else:
        for j in out:
            print(f"{j['company']} (YC {j['batch']}) | {j['title']} | {j['locations']} | {j['visa']} | {j['url']}")
        print(f"{len(out)} new YC internship(s)")


if __name__ == "__main__":
    main()
