"""
job_search.py  —  Version 1 (steps 2 and 3)

Pulls open roles from the Greenhouse, Lever and Ashby public job feeds for the
companies in companies.csv, keeps recent roles whose titles match your
keywords, and saves them to output/matches_<date>.csv.

Run:  python job_search.py
"""

import csv
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ============================================================
# SETTINGS — edit these freely
# ============================================================
DAYS_BACK = 14

# A role is kept if its TITLE contains any of these (whole words, any case).
TITLE_KEYWORDS = [
    "clinical", "implementation", "enablement", "adoption",
    "RN", "registered nurse", "nurse",
    "customer success", "solutions", "field reimbursement", "reimbursement",
    "onboarding", "deployment",
]

# ...unless its title also contains any of these.
EXCLUDE_KEYWORDS = [
    "intern", "internship", "software engineer", "data engineer",
    "machine learning engineer", "ml engineer", "data scientist",
    "sales development", "SDR", "recruiter", "physician", "senior", "sr", "principal", "staff", "director", "head of", "VP", "architect", "legal", "ads", "UK", "London", "EMEA", "APAC", "Europe", "data center",
]

# Locations that count as "ok" (remote or commutable from Yardley, PA).
LOCATION_OK_WORDS = [
    "remote", "united states", "usa", "us",
    "philadelphia", "pennsylvania", "PA", "new jersey", "NJ",
    "yardley", "princeton", "trenton", "king of prussia", "new york", "NYC",
]

# False = keep everything but tag it "ok"/"review". True = drop "review" rows.
KEEP_ONLY_GOOD_LOCATIONS = True

COMPANIES_FILE = "companies.csv"
OUTPUT_DIR = Path("output")
HEADERS = {"User-Agent": "personal-job-search-script"}
TIMEOUT = 20
# ============================================================


def make_pattern(words):
    """Build one case-insensitive, whole-word search pattern from a list."""
    joined = "|".join(re.escape(w) for w in words)
    return re.compile(r"\b(" + joined + r")\b", re.IGNORECASE)


TITLE_RE = make_pattern(TITLE_KEYWORDS)
EXCLUDE_RE = make_pattern(EXCLUDE_KEYWORDS)
LOCATION_RE = make_pattern(LOCATION_OK_WORDS)


def parse_date(value):
    """Turn the different date formats the job boards use into one format."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):          # Lever: milliseconds
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError):
        return None


def get_json(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------- One small function per job board ----------

def fetch_greenhouse(company, slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    return [{
        "company": company,
        "title": j.get("title", ""),
        "location": (j.get("location") or {}).get("name", ""),
        "workplace": "",
        "url": j.get("absolute_url", ""),
        # first_published = original post date; updated_at is a fallback
        # (updated_at changes whenever a posting is edited).
        "posted": parse_date(j.get("first_published") or j.get("updated_at")),
        "source": "greenhouse",
    } for j in data.get("jobs", [])]


def fetch_lever(company, slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        jobs.append({
            "company": company,
            "title": j.get("text", ""),
            "location": cats.get("location", ""),
            "workplace": j.get("workplaceType", ""),
            "url": j.get("hostedUrl", ""),
            "posted": parse_date(j.get("createdAt")),
            "source": "lever",
        })
    return jobs


def fetch_ashby(company, slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = []
    for j in data.get("jobs", []):
        workplace = j.get("workplaceType") or ("Remote" if j.get("isRemote") else "")
        jobs.append({
            "company": company,
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "workplace": workplace,
            "url": j.get("jobUrl") or j.get("applyUrl", ""),
            "posted": parse_date(j.get("publishedAt")),
            "source": "ashby",
        })
    return jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


# ---------- Filtering ----------

def filter_jobs(all_jobs):
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    kept, no_date = [], 0
    for job in all_jobs:
        if job["posted"] is None:
            no_date += 1
            continue
        if job["posted"] < cutoff:
            continue
        if not TITLE_RE.search(job["title"]) or EXCLUDE_RE.search(job["title"]):
            continue
        location_text = f"{job['location']} {job['workplace']} {job['title']}"
        job["location_check"] = "ok" if LOCATION_RE.search(location_text) else "review"
        if KEEP_ONLY_GOOD_LOCATIONS and job["location_check"] != "ok":
            continue
        job["matched_keywords"] = ", ".join(sorted({m.lower() for m in TITLE_RE.findall(job["title"])}))
        kept.append(job)
    kept.sort(key=lambda j: j["posted"], reverse=True)
    return kept, no_date


def save_csv(jobs):
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"matches_{datetime.now():%Y-%m-%d}.csv"
    now = datetime.now(timezone.utc)
    columns = ["posted", "days_ago", "company", "title", "location", "workplace",
               "location_check", "matched_keywords", "source", "url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for j in jobs:
            row = {c: j.get(c, "") for c in columns}
            row["posted"] = j["posted"].strftime("%Y-%m-%d")
            row["days_ago"] = (now - j["posted"]).days
            writer.writerow(row)
    return path


def load_companies():
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    companies = load_companies()
    all_jobs, failures, skipped = [], [], []

    print(f"Checking {len(companies)} companies...\n")
    for c in companies:
        ats = (c.get("ats") or "").strip().lower()
        slug = (c.get("slug") or "").strip()
        fetch = FETCHERS.get(ats)
        if not fetch or not slug:
            skipped.append(c["company"])
            continue
        try:
            jobs = fetch(c["company"], slug)
            print(f"  {c['company']:<25} {len(jobs):>4} open roles")
            all_jobs.extend(jobs)
        except Exception as e:  # one broken company shouldn't stop the run
            failures.append(f"{c['company']} ({ats}/{slug}): {e}")
        time.sleep(0.5)

    matches, no_date = filter_jobs(all_jobs)
    path = save_csv(matches)

    print(f"\nTotal open roles pulled: {len(all_jobs)}")
    print(f"Matches (last {DAYS_BACK} days, keyword hit): {len(matches)}")
    if no_date:
        print(f"Skipped {no_date} roles with no posting date.")
    if skipped:
        print(f"Skipped (no supported board set): {', '.join(skipped)}")
    if failures:
        print("Errors:")
        for f in failures:
            print(f"  - {f}")
    print(f"\nSaved to {path}\n")
    for j in matches[:15]:
        print(f"  {j['posted']:%m-%d}  {j['company']:<20} {j['title'][:55]:<55} [{j['location_check']}]")


if __name__ == "__main__":
    main()
