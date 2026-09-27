# Clinical AI Job-Search Agent

A personal job-search agent built by an ICU RN moving into clinical AI and health tech.
It pulls openings from public Greenhouse, Lever and Ashby job feeds for a curated list of
health-tech and AI companies, filters them to recent, relevant roles, and (in later versions)
scores each one against my resume with Amazon Bedrock.

## Status
- [x] v1: company list, feed collection, date and keyword filtering (runs locally)
- [ ] v2: AI fit scoring with Amazon Bedrock (score, gaps, one-line pitch)
- [ ] v3: Google Sheet / email output, skip roles already seen
- [ ] v4: weekly run on AWS Lambda + EventBridge

## Run it
```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python detect_boards.py          # fills in which job board each company uses
python job_search.py             # writes output/matches_<date>.csv
```

## Files
- `companies.csv` — target companies, job-board type (ats) and board slug
- `detect_boards.py` — finds each company's board automatically
- `job_search.py` — fetches, filters and saves matching roles; settings at the top
