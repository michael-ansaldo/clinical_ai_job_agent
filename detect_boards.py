"""
detect_boards.py  —  Step 1 helper

For every company in companies.csv whose "ats" column is blank, this script
tries the Greenhouse, Lever and Ashby public feeds with a few slug guesses
and fills in the ones it finds. A backup of your original file is saved first.

Run:  python detect_boards.py
"""

import csv
import re
import shutil
import time

import requests

COMPANIES_FILE = "companies.csv"
BACKUP_FILE = "companies_backup.csv"
HEADERS = {"User-Agent": "personal-job-search-script"}
TIMEOUT = 15

# (board name, feed URL pattern, test that the response looks like a real board)
CHECKS = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
     lambda d: isinstance(d, dict) and "jobs" in d),
    ("lever", "https://api.lever.co/v0/postings/{}?mode=json",
     lambda d: isinstance(d, list)),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{}",
     lambda d: isinstance(d, dict) and "jobs" in d),
]


def slug_guesses(company, slug):
    """A few spellings to try: your slug, then versions of the company name."""
    name = company.lower()
    guesses = [
        slug.strip().lower(),
        re.sub(r"[^a-z0-9]", "", name),   # "Hippocratic AI" -> "hippocraticai"
        re.sub(r"[^a-z0-9]+", "-", name).strip("-"),  # -> "hippocratic-ai"
        re.sub(r"[^a-z0-9]", "", name.split()[0]),    # -> "hippocratic"
    ]
    seen, unique = set(), []
    for g in guesses:
        if g and g not in seen:
            seen.add(g)
            unique.append(g)
    return unique


def find_board(company, slug):
    for guess in slug_guesses(company, slug):
        for ats, pattern, looks_valid in CHECKS:
            try:
                r = requests.get(pattern.format(guess), headers=HEADERS, timeout=TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    if looks_valid(data):
                        count = len(data) if isinstance(data, list) else len(data["jobs"])
                        return ats, guess, count
            except (requests.RequestException, ValueError):
                pass
            time.sleep(0.3)  # be polite to the servers
    return None, slug, 0


def main():
    shutil.copy(COMPANIES_FILE, BACKUP_FILE)
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    not_found = []
    for row in rows:
        if row.get("ats", "").strip():
            print(f"  {row['company']:<25} already set: {row['ats']}")
            continue
        ats, slug, count = find_board(row["company"], row.get("slug", ""))
        if ats:
            row["ats"], row["slug"] = ats, slug
            print(f"  {row['company']:<25} FOUND  {ats}/{slug}  ({count} open roles)")
        else:
            not_found.append(row["company"])
            print(f"  {row['company']:<25} not found")

    with open(COMPANIES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated {COMPANIES_FILE} (backup in {BACKUP_FILE}).")
    if not_found:
        print("\nNot found — check these by hand:")
        for c in not_found:
            print(f"  - {c}")
        print("\nTip: open one of their job postings and look at the web address.")
        print("  boards.greenhouse.io/SLUG or job-boards.greenhouse.io/SLUG -> greenhouse")
        print("  jobs.lever.co/SLUG                                           -> lever")
        print("  jobs.ashbyhq.com/SLUG                                        -> ashby")
        print("  Anything else (Workday, iCIMS, etc.) isn't supported in version 1.")


if __name__ == "__main__":
    main()
