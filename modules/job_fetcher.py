"""
Module 1: Job Fetcher
─────────────────────────────────────────────────────────────
Sources (all free tier):
  1. Greenhouse Public API  — companies using Greenhouse ATS
  2. Lever Public API       — companies using Lever ATS
  3. JSearch (RapidAPI)     — broad search, 200 req/month free
  4. Adzuna API             — targeted search, 1000 req/month free

Output: data/raw_jobs.json
─────────────────────────────────────────────────────────────
"""

import re
import json
import hashlib
import os
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# SIGNAL DICTIONARIES  (CPT / Visa / Role Type)
# ─────────────────────────────────────────────────────────────

CPT_POSITIVE = [
    "cpt", "opt", "f-1", "f1 visa", "open to international",
    "visa sponsorship available", "sponsor work authorization",
    "international students welcome", "all work authorizations",
    "any work authorization", "eligible to work in the us",
    "work authorization will be considered",
]

CPT_NEGATIVE = [
    "must be authorized to work without sponsorship",
    "must be authorized without sponsorship",
    "authorized to work without sponsorship",
    "no sponsorship", "no visa sponsorship",
    "us citizens only", "u.s. citizens only",
    "citizens and permanent residents only",
    "security clearance required", "secret clearance",
    "top secret clearance", "must be a u.s. citizen",
    "requires u.s. citizenship", "usc or gc only",
    "green card holders only", "permanent authorization required",
    "must be eligible to work in the us without sponsorship",
]

SUMMER_SIGNALS = [
    "summer 2026", "summer '26", "summer internship 2026",
    "may 2026", "june 2026", "july 2026", "august 2026",
    "spring/summer 2026", "summer/fall 2026",
]

EXCLUDE_TITLE_WORDS = [
    "senior", "staff", "principal", "director", "vp ", "vice president",
    "manager", " lead ", "head of", "full-time", "full time", "permanent",
    "part-time contractor", "contract to hire",
]

INTERN_SIGNALS = [
    "intern", "internship", "co-op", "coop", "co op",
    "summer 2026", "summer analyst",
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def strip_html(html: str) -> str:
    """Remove HTML tags and clean whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html or "")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def make_id(company: str, title: str, url: str) -> str:
    raw = f"{company.lower().strip()}|{title.lower().strip()}|{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def detect_cpt(description: str) -> Dict:
    desc = description.lower()
    pos = [s for s in CPT_POSITIVE if s in desc]
    neg = [s for s in CPT_NEGATIVE if s in desc]
    summer = [s for s in SUMMER_SIGNALS if s in desc]

    if neg:
        signal = "negative"       # Explicitly excludes sponsorship → skip
    elif pos:
        signal = "positive"       # Explicitly supports international → great
    else:
        signal = "neutral"        # No mention → assume possible, flag for manual check

    return {
        "cpt_signal": signal,
        "cpt_positive_hits": pos,
        "cpt_negative_hits": neg,
        "summer_2026_mentioned": bool(summer),
    }


def is_intern_role(title: str, description: str) -> bool:
    """Return True if the role looks like an internship."""
    t = title.lower()
    d = description.lower()

    # Must have at least one intern signal in title OR description
    if not any(s in t or s in d for s in INTERN_SIGNALS):
        return False

    # Exclude senior/FT/leadership roles
    for bad in EXCLUDE_TITLE_WORDS:
        if bad in t:
            return False

    return True


def build_job(
    title: str,
    company: str,
    location: str,
    description: str,
    apply_url: str,
    posted_at: Optional[str],
    source: str,
) -> Dict:
    cpt_info = detect_cpt(description)
    return {
        "id": make_id(company, title, apply_url),
        "title": title.strip(),
        "company": company.strip(),
        "location": (location or "Not specified").strip(),
        "description": description[:4000],          # Cap at 4k chars for storage
        "apply_url": apply_url.strip(),
        "posted_at": posted_at,
        "source": source,
        "is_intern": is_intern_role(title, description),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "new",                            # new | applied | saved | skipped
        "connection_flag": None,                    # Filled by Module 4
        "relevance_score": None,                    # Filled by Module 2
        **cpt_info,
    }


# ─────────────────────────────────────────────────────────────
# SOURCE 1 — GREENHOUSE PUBLIC API  (completely free, no key needed)
# boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
# ─────────────────────────────────────────────────────────────

def fetch_greenhouse(board_token: str, company_name: str, title_keywords: List[str]) -> List[Dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        logger.warning(f"  ✗ Greenhouse [{company_name}]: {e}")
        return []

    jobs = []
    for job in raw.get("jobs", []):
        title = job.get("title", "")
        title_l = title.lower()

        # Filter: must match at least one target keyword
        if not any(kw in title_l for kw in title_keywords):
            continue

        description = strip_html(job.get("content", ""))

        if not is_intern_role(title, description):
            continue

        location_obj = job.get("location", {})
        location = location_obj.get("name", "") if isinstance(location_obj, dict) else str(location_obj)

        jobs.append(build_job(
            title=title,
            company=company_name,
            location=location,
            description=description,
            apply_url=job.get("absolute_url", ""),
            posted_at=job.get("updated_at"),
            source="greenhouse_api",
        ))

    logger.info(f"  ✓ Greenhouse [{company_name}]: {len(jobs)} matching roles")
    return jobs


# ─────────────────────────────────────────────────────────────
# SOURCE 2 — LEVER PUBLIC API  (completely free, no key needed)
# api.lever.co/v0/postings/{slug}?mode=json
# ─────────────────────────────────────────────────────────────

def fetch_lever(slug: str, company_name: str, title_keywords: List[str]) -> List[Dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        logger.warning(f"  ✗ Lever [{company_name}]: {e}")
        return []

    jobs = []
    for post in postings:
        title = post.get("text", "")
        title_l = title.lower()

        if not any(kw in title_l for kw in title_keywords):
            continue

        # Skip explicit full-time roles
        commitment = (post.get("categories") or {}).get("commitment", "").lower()
        if commitment and "full" in commitment and "intern" not in commitment:
            continue

        # Build description from lever's list format
        parts = []
        for section in (post.get("lists") or []):
            parts.append(section.get("text", ""))
            for item in (section.get("content") or []):
                parts.append(strip_html(str(item)))
        description = " ".join(parts)

        if not is_intern_role(title, description):
            continue

        cats = post.get("categories") or {}
        location = cats.get("location", "")
        apply_url = post.get("hostedUrl") or post.get("applyUrl") or ""

        ts = post.get("createdAt")
        posted_at = (
            datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            if ts else None
        )

        jobs.append(build_job(
            title=title,
            company=company_name,
            location=location,
            description=description,
            apply_url=apply_url,
            posted_at=posted_at,
            source="lever_api",
        ))

    logger.info(f"  ✓ Lever [{company_name}]: {len(jobs)} matching roles")
    return jobs


# ─────────────────────────────────────────────────────────────
# SOURCE 3 — JSEARCH via RapidAPI  (200 req/month free)
# We hard-cap at 5 calls/day to stay well within free tier.
# ─────────────────────────────────────────────────────────────

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_DAY_CAP = 5  # Conservative cap per run to stay in free tier


def fetch_jsearch(query: str, api_key: str) -> List[Dict]:
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": query,
        "page": "1",
        "num_pages": "2",
        "date_posted": "today",
        "employment_types": "INTERN",
    }
    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"  ✗ JSearch ['{query[:40]}']: {e}")
        return []

    jobs = []
    for job in data.get("data", []):
        title = job.get("job_title", "")
        description = job.get("job_description", "")

        if not is_intern_role(title, description):
            continue

        # JSearch often provides the direct employer apply link
        apply_url = (
            job.get("job_apply_link")
            or job.get("job_google_link")
            or ""
        )

        city = job.get("job_city") or ""
        state = job.get("job_state") or ""
        location = ", ".join(filter(None, [city, state]))

        jobs.append(build_job(
            title=title,
            company=job.get("employer_name", ""),
            location=location,
            description=description,
            apply_url=apply_url,
            posted_at=job.get("job_posted_at_datetime_utc"),
            source="jsearch",
        ))

    logger.info(f"  ✓ JSearch ['{query[:40]}']: {len(jobs)} matching roles")
    return jobs


def build_jsearch_queries(job_titles: List[str], general_companies: List[str]) -> List[str]:
    """
    Build a small set of efficient OR-queries to cover all titles
    within the daily 5-call budget.
    """
    analyst_group = "business analyst OR data analyst OR BI analyst"
    ops_group = "operations analyst OR strategy analyst OR product analyst"
    ds_group = "data science OR marketing analyst OR business intelligence"

    top_companies = " OR ".join(general_companies[:6])

    return [
        f"({analyst_group}) intern summer 2026",
        f"({ops_group}) intern summer 2026",
        f"({ds_group}) intern summer 2026",
        f"analyst intern ({top_companies}) 2026",
        f"data analyst intern boston OR new york OR remote 2026",
    ]


# ─────────────────────────────────────────────────────────────
# SOURCE 4 — ADZUNA API  (1,000 req/month free)
# We use up to 15 targeted queries per run.
# ─────────────────────────────────────────────────────────────

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"
ADZUNA_DAY_CAP = 15


def fetch_adzuna(query: str, app_id: str, app_key: str) -> List[Dict]:
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query,
        "what_and": "internship",
        "max_days_old": 1,
        "results_per_page": 20,
        "sort_by": "date",
        "content-type": "application/json",
    }
    try:
        resp = requests.get(ADZUNA_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"  ✗ Adzuna ['{query[:40]}']: {e}")
        return []

    jobs = []
    for job in data.get("results", []):
        title = job.get("title", "")
        description = job.get("description", "")

        if not is_intern_role(title, description):
            continue

        loc_obj = job.get("location") or {}
        location = loc_obj.get("display_name", "") if isinstance(loc_obj, dict) else ""

        co_obj = job.get("company") or {}
        company = co_obj.get("display_name", "") if isinstance(co_obj, dict) else ""

        jobs.append(build_job(
            title=title,
            company=company,
            location=location,
            description=description,
            apply_url=job.get("redirect_url", ""),
            posted_at=job.get("created"),
            source="adzuna",
        ))

    logger.info(f"  ✓ Adzuna ['{query[:40]}']: {len(jobs)} matching roles")
    return jobs


def build_adzuna_queries(job_titles: List[str], general_companies: List[str]) -> List[str]:
    queries = []
    # Title-level queries (one per title)
    for title in job_titles:
        queries.append(f"{title} summer 2026")
    # Company-specific (for companies not on Greenhouse/Lever)
    for company in general_companies:
        queries.append(f"analyst intern {company} 2026")
    return queries[:ADZUNA_DAY_CAP]


# ─────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────

def load_seen_ids(path: str = "data/seen_jobs.json") -> set:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(seen: set, path: str = "data/seen_jobs.json"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def deduplicate(jobs: List[Dict], seen_ids: set) -> List[Dict]:
    unique: Dict[str, Dict] = {}
    for job in jobs:
        jid = job["id"]
        if jid not in seen_ids and jid not in unique:
            unique[jid] = job
    return list(unique.values())


def split_by_cpt(jobs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Returns (viable, cpt_negative_flagged)."""
    viable = [j for j in jobs if j["cpt_signal"] != "negative"]
    flagged = [j for j in jobs if j["cpt_signal"] == "negative"]
    return viable, flagged


# ─────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

class JobFetcher:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            self.settings = json.load(f)
        with open(f"{config_dir}/job_titles.json") as f:
            self.job_titles = json.load(f)["titles"]
        with open(f"{config_dir}/target_companies.json") as f:
            companies = json.load(f)
            self.greenhouse = companies.get("greenhouse", {})   # {display_name: board_token}
            self.lever = companies.get("lever", {})             # {display_name: slug}
            self.general = companies.get("general", [])         # [company names for API search]

        # Title keywords for ATS matching (stripped of "intern/internship")
        self.title_keywords = list({
            t.lower()
             .replace(" intern", "")
             .replace(" internship", "")
             .strip()
            for t in self.job_titles
        })

        # API keys from environment variables
        self.jsearch_key = os.environ.get("JSEARCH_API_KEY", "")
        self.adzuna_id = os.environ.get("ADZUNA_APP_ID", "")
        self.adzuna_key = os.environ.get("ADZUNA_APP_KEY", "")

    # ── Run ──────────────────────────────────────────────────

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("JOB FETCHER — starting run")
        logger.info(f"Targeting {len(self.job_titles)} roles across "
                    f"{len(self.greenhouse) + len(self.lever) + len(self.general)} companies")
        logger.info("═" * 60)

        all_jobs: List[Dict] = []

        # 1. Greenhouse (free, no rate limit concerns)
        if self.greenhouse:
            logger.info(f"\n[1/4] Greenhouse API ({len(self.greenhouse)} companies)")
            for name, token in self.greenhouse.items():
                jobs = fetch_greenhouse(token, name, self.title_keywords)
                all_jobs.extend(jobs)
                time.sleep(1)

        # 2. Lever (free, no rate limit concerns)
        if self.lever:
            logger.info(f"\n[2/4] Lever API ({len(self.lever)} companies)")
            for name, slug in self.lever.items():
                jobs = fetch_lever(slug, name, self.title_keywords)
                all_jobs.extend(jobs)
                time.sleep(1)

        # 3. JSearch (budget: max 5/day)
        if self.jsearch_key:
            logger.info(f"\n[3/4] JSearch API (max {JSEARCH_DAY_CAP} queries)")
            queries = build_jsearch_queries(self.job_titles, self.general)
            for q in queries[:JSEARCH_DAY_CAP]:
                jobs = fetch_jsearch(q, self.jsearch_key)
                all_jobs.extend(jobs)
                time.sleep(2)  # Respectful pacing
        else:
            logger.info("\n[3/4] JSearch skipped — JSEARCH_API_KEY not set")

        # 4. Adzuna (budget: max 15/day)
        if self.adzuna_id and self.adzuna_key:
            logger.info(f"\n[4/4] Adzuna API (max {ADZUNA_DAY_CAP} queries)")
            queries = build_adzuna_queries(self.job_titles, self.general)
            for q in queries[:ADZUNA_DAY_CAP]:
                jobs = fetch_adzuna(q, self.adzuna_id, self.adzuna_key)
                all_jobs.extend(jobs)
                time.sleep(1)
        else:
            logger.info("\n[4/4] Adzuna skipped — ADZUNA_APP_ID / ADZUNA_APP_KEY not set")

        # Dedup, split, save
        seen = load_seen_ids()
        fresh = deduplicate(all_jobs, seen)
        viable, flagged = split_by_cpt(fresh)

        # Update seen IDs so we never show same job twice
        save_seen_ids(seen | {j["id"] for j in fresh})

        # Persist output
        output = {
            "run_date": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_fetched": len(all_jobs),
                "new_unique": len(fresh),
                "viable": len(viable),
                "cpt_flagged": len(flagged),
            },
            "viable_jobs": viable,
            "cpt_flagged_jobs": flagged,
        }

        out_path = Path("data/raw_jobs.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(f"DONE — {len(viable)} viable jobs | {len(flagged)} CPT-flagged | "
                    f"{len(all_jobs)} total fetched")
        logger.info(f"Output written to {out_path}")
        logger.info("═" * 60)

        return output
