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
# CONSTANTS
# ─────────────────────────────────────────────────────────────

# Hard cap on total jobs sent to scorer — prevents 2hr Gemini runs
MAX_JOBS_TO_SCORE = 40

# US-only: any location containing these strings is kept
US_LOCATION_SIGNALS = [
    "remote", "united states", ", us", ", usa", "u.s.", "u.s.a",
    # US state abbreviations — use ", xx" format to avoid matching "ca" in "canada"
    ", al",", ak",", az",", ar",", ca",", co",", ct",", de",", fl",", ga",
    ", hi",", id",", il",", in",", ia",", ks",", ky",", la",", me",", md",
    ", ma",", mi",", mn",", ms",", mo",", mt",", ne",", nv",", nh",", nj",
    ", nm",", ny",", nc",", nd",", oh",", ok",", or",", pa",", ri",", sc",
    ", sd",", tn",", tx",", ut",", vt",", va",", wa",", wv",", wi",", wy",
    # Common US city names
    "new york", "san francisco", "seattle", "boston", "chicago",
    "austin", "los angeles", "denver", "atlanta", "washington dc",
    "washington, d.c", "mountain view", "menlo park", "palo alto",
    "new york city", "nyc", "portland, or", "portland, me",
]

CPT_POSITIVE = [
    "cpt", "opt", "f-1", "f1 visa", "open to international",
    "visa sponsorship available", "sponsor work authorization",
    "international students welcome", "all work authorizations",
    "any work authorization", "work authorization will be considered",
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
    "green card holders only",
    "must be eligible to work in the us without sponsorship",
    "us citizenship required", "u.s. citizenship required",
    "must be a us citizen", "requires us citizenship",
    "citizenship is required", "only us citizens",
    # JPMorgan-style language that explicitly excludes CPT/OPT
    "will not provide any assistance or sign any documentation",
    "including optional practical training",
    "including curricular practical training",
    "curricular practical training (cpt)",
    "optional practical training (opt) or curricular",
    "does not offer any type of employment-based immigration",
    "not sponsor employment visas",
    "unable to sponsor",
    "cannot sponsor",
    "not able to sponsor",
]

# Title must contain one of these — strict list
INTERN_TITLE_SIGNALS = [
    "intern", "internship", "co-op", "coop", "co op",
    "summer analyst", "summer associate",
]

# Title must ALSO contain at least one of these role keywords
# This prevents "Engineering Intern", "Cybersecurity Intern", "AI/ML Intern" etc.
ROLE_KEYWORDS = [
    "analyst", "analytics", "business", "data", "strategy", "strategic",
    "operations", "operational", "intelligence", "marketing", "insights",
    "reporting", "visualization", "bi ", "b.i.", "product", "finance",
    "consulting", "research", "quant", "quantitative",
]

EXCLUDE_TITLE_WORDS = [
    "senior", "sr.", "staff", "principal", "director", "vp ",
    "vice president", "manager", " lead ", "head of",
    "full-time", "full time", "permanent", "contract to hire",
    "part-time contractor",
]

# Domain exclusions — these are irrelevant fields even if they have "analyst"
EXCLUDE_DOMAIN_WORDS = [
    "cybersecurity", "cyber security", "security operations",
    "network", "software engineer", "devops", "cloud engineer",
    "machine learning engineer", "ai engineer", "hardware",
    "mechanical", "electrical", "civil", "manufacturing",
]

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def strip_html(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html or "")
    return re.sub(r'\s+', ' ', text).strip()


def make_id(company: str, title: str, url: str) -> str:
    raw = f"{company.lower().strip()}|{title.lower().strip()}|{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def detect_cpt(description: str) -> Dict:
    desc  = description.lower()
    pos   = [s for s in CPT_POSITIVE if s in desc]
    neg   = [s for s in CPT_NEGATIVE if s in desc]
    if neg:   signal = "negative"
    elif pos: signal = "positive"
    else:     signal = "neutral"
    return {
        "cpt_signal":         signal,
        "cpt_positive_hits":  pos,
        "cpt_negative_hits":  neg,
        "summer_2026_mentioned": any(
            s in desc for s in ["summer 2026","summer internship","summer analyst"]
        ),
    }


def is_intern_role(title: str, description: str = "") -> bool:
    """
    STRICT: title must have BOTH an intern signal AND a relevant role keyword.
    Prevents "Engineering Intern", "Cybersecurity Intern", etc.
    """
    t = title.lower()

    # Must have explicit intern signal in title
    if not any(s in t for s in INTERN_TITLE_SIGNALS):
        return False

    # Must have a relevant business/data/analytics role keyword in title
    if not any(kw in t for kw in ROLE_KEYWORDS):
        return False

    # Exclude senior/FT roles
    for bad in EXCLUDE_TITLE_WORDS:
        if bad in t:
            return False

    # Exclude irrelevant technical domains
    for bad in EXCLUDE_DOMAIN_WORDS:
        if bad in t:
            return False

    return True


def is_us_location(location: str) -> bool:
    """Return True if location appears to be in the US (or Remote)."""
    if not location:
        return True   # Unknown location — let Gemini decide; don't discard
    loc = location.lower().strip()

    # Explicit non-US signals — bail early
    non_us = ["canada", "mexico", "india", "china", "uk", "england",
               "germany", "france", "australia", "singapore", "japan",
               "brazil", "netherlands", "ireland", "spain", "italy"]
    if any(f in loc for f in non_us):
        return False

    # Check US signals
    return any(sig in loc for sig in US_LOCATION_SIGNALS)


def build_job(
    title: str, company: str, location: str, description: str,
    apply_url: str, posted_at: Optional[str], source: str,
) -> Dict:
    cpt_info = detect_cpt(description)
    return {
        "id":               make_id(company, title, apply_url),
        "title":            title.strip(),
        "company":          company.strip(),
        "location":         (location or "Not specified").strip(),
        "description":      description[:4000],
        "apply_url":        apply_url.strip(),
        "posted_at":        posted_at,
        "source":           source,
        "fetched_at":       datetime.now(timezone.utc).isoformat(),
        "status":           "new",
        "connection_flag":  None,
        "relevance_score":  None,
        **cpt_info,
    }


# ─────────────────────────────────────────────────────────────
# SOURCE 1 — GREENHOUSE
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
        title   = job.get("title", "") or ""
        title_l = title.lower()

        if not any(kw in title_l for kw in title_keywords):
            continue
        if not is_intern_role(title):
            continue

        description = strip_html(job.get("content", ""))
        loc_obj     = job.get("location", {})
        location    = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)

        if not is_us_location(location):
            continue

        jobs.append(build_job(
            title=title, company=company_name, location=location,
            description=description, apply_url=job.get("absolute_url", ""),
            posted_at=job.get("updated_at"), source="greenhouse_api",
        ))

    logger.info(f"  ✓ Greenhouse [{company_name}]: {len(jobs)} matching roles")
    return jobs


# ─────────────────────────────────────────────────────────────
# SOURCE 2 — LEVER
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
        title   = post.get("text", "") or ""
        title_l = title.lower()

        if not any(kw in title_l for kw in title_keywords):
            continue
        if not is_intern_role(title):
            continue

        commitment = (post.get("categories") or {}).get("commitment", "").lower()
        if commitment and "full" in commitment and "intern" not in commitment:
            continue

        parts = []
        for section in (post.get("lists") or []):
            parts.append(section.get("text", ""))
            for item in (section.get("content") or []):
                parts.append(strip_html(str(item)))
        description = " ".join(parts)

        cats      = post.get("categories") or {}
        location  = cats.get("location", "")
        apply_url = post.get("hostedUrl") or post.get("applyUrl") or ""

        if not is_us_location(location):
            continue

        ts        = post.get("createdAt")
        posted_at = (
            datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            if ts else None
        )

        jobs.append(build_job(
            title=title, company=company_name, location=location,
            description=description, apply_url=apply_url,
            posted_at=posted_at, source="lever_api",
        ))

    logger.info(f"  ✓ Lever [{company_name}]: {len(jobs)} matching roles")
    return jobs


# ─────────────────────────────────────────────────────────────
# SOURCE 3 — JSEARCH
# ─────────────────────────────────────────────────────────────

JSEARCH_URL     = "https://jsearch.p.rapidapi.com/search"
JSEARCH_DAY_CAP = 5

# Known aggregator domains — prefer employer direct links over these
AGGREGATOR_DOMAINS = {
    "lensa.com", "ziprecruiter.com", "indeed.com", "glassdoor.com",
    "monster.com", "careerbuilder.com", "simplyhired.com", "jooble.org",
    "talent.com", "jobrapido.com", "adzuna.com", "recruit.net",
    "jobs2careers.com", "whatjobs.com", "neuvoo.com", "trovit.com",
}

def best_apply_url(job_data: Dict) -> str:
    """
    Return the most direct apply URL from JSearch job data.
    Prefers employer_website or non-aggregator links.
    """
    candidates = [
        job_data.get("job_apply_link", ""),
        job_data.get("job_google_link", ""),
    ]
    # Also check if employer website + job ID can be constructed
    employer_website = job_data.get("employer_website") or ""

    for url in candidates:
        if not url:
            continue
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc.lower().lstrip("www.")
            if not any(agg in domain for agg in AGGREGATOR_DOMAINS):
                return url  # Direct employer link
        except Exception:
            pass

    # All candidates are aggregators — return the first non-empty one anyway
    # (better than nothing, and Gemini scoring still works on description)
    for url in candidates:
        if url:
            return url

    return ""


def fetch_jsearch(query: str, api_key: str) -> List[Dict]:
    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query":       query,
        "page":        "1",
        "num_pages":   "2",
        "date_posted": "week",
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
        title       = job.get("job_title")       or ""
        description = job.get("job_description") or ""
        employer    = job.get("employer_name")   or ""

        if not is_intern_role(title, description):
            continue

        # JSearch country filter
        country = (job.get("job_country") or "").upper()
        if country and country not in ("US", "USA", "UNITED STATES", ""):
            continue

        apply_url = best_apply_url(job)
        city      = job.get("job_city")  or ""
        state     = job.get("job_state") or ""
        location  = ", ".join(filter(None, [city, state]))

        jobs.append(build_job(
            title=title, company=employer, location=location,
            description=description, apply_url=apply_url,
            posted_at=job.get("job_posted_at_datetime_utc"),
            source="jsearch",
        ))

    logger.info(f"  ✓ JSearch ['{query[:40]}']: {len(jobs)} matching roles")
    return jobs


def build_jsearch_queries(job_titles: List[str], general_companies: List[str]) -> List[str]:
    return [
        "business analyst intern 2026",
        "data analyst intern 2026",
        "data science intern summer 2026",
        "operations analyst intern OR strategy intern 2026",
        "business intelligence intern OR marketing analyst intern 2026",
    ]


# ─────────────────────────────────────────────────────────────
# SOURCE 4 — ADZUNA
# ─────────────────────────────────────────────────────────────

ADZUNA_URL     = "https://api.adzuna.com/v1/api/jobs/us/search/1"
ADZUNA_DAY_CAP = 12


def fetch_adzuna(query: str, app_id: str, app_key: str) -> List[Dict]:
    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "what":             query,
        "max_days_old":     7,
        "results_per_page": 20,
        "sort_by":          "date",
        "content-type":     "application/json",
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
        title       = job.get("title", "")       or ""
        description = job.get("description", "") or ""

        if not is_intern_role(title, description):
            continue

        loc_obj  = job.get("location") or {}
        location = loc_obj.get("display_name", "") if isinstance(loc_obj, dict) else ""
        co_obj   = job.get("company") or {}
        company  = co_obj.get("display_name", "") if isinstance(co_obj, dict) else ""

        # Adzuna /us/ endpoint is already US-only, but double-check
        if not is_us_location(location) and location:
            continue

        jobs.append(build_job(
            title=title, company=company, location=location,
            description=description,
            apply_url=job.get("redirect_url", ""),
            posted_at=job.get("created"),
            source="adzuna",
        ))

    logger.info(f"  ✓ Adzuna ['{query[:40]}']: {len(jobs)} matching roles")
    return jobs


def build_adzuna_queries(job_titles: List[str], general_companies: List[str]) -> List[str]:
    base_queries = [
        "business analyst intern",
        "data analyst intern",
        "data science intern",
        "strategy intern",
        "business intelligence intern",
        "operations analyst intern",
        "marketing analyst intern",
    ]
    # A few company-specific searches for target companies
    company_queries = [
        f"analyst intern {c}" for c in general_companies[:5]
    ]
    return (base_queries + company_queries)[:ADZUNA_DAY_CAP]


# ─────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────

def load_seen_ids(path: str = "data/seen_jobs.json") -> set:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            try:    return set(json.load(f))
            except: return set()
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
    viable  = [j for j in jobs if j["cpt_signal"] != "negative"]
    flagged = [j for j in jobs if j["cpt_signal"] == "negative"]
    return viable, flagged


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

class JobFetcher:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            self.settings = json.load(f)
        with open(f"{config_dir}/job_titles.json") as f:
            self.job_titles = json.load(f)["titles"]
        with open(f"{config_dir}/target_companies.json") as f:
            companies        = json.load(f)
            self.greenhouse  = companies.get("greenhouse", {})
            self.lever       = companies.get("lever", {})
            self.general     = companies.get("general", [])

        self.title_keywords = list({
            t.lower()
             .replace(" intern", "")
             .replace(" internship", "")
             .strip()
            for t in self.job_titles
        })

        self.jsearch_key = os.environ.get("JSEARCH_API_KEY", "")
        self.adzuna_id   = os.environ.get("ADZUNA_APP_ID",   "")
        self.adzuna_key  = os.environ.get("ADZUNA_APP_KEY",  "")

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("JOB FETCHER — starting run")
        logger.info(f"Targeting {len(self.job_titles)} roles | "
                    f"US-only | intern titles only")
        logger.info("═" * 60)

        all_jobs: List[Dict] = []

        # 1. Greenhouse
        if self.greenhouse:
            logger.info(f"\n[1/4] Greenhouse API ({len(self.greenhouse)} companies)")
            for name, token in self.greenhouse.items():
                jobs = fetch_greenhouse(token, name, self.title_keywords)
                all_jobs.extend(jobs)
                time.sleep(1)

        # 2. Lever
        if self.lever:
            logger.info(f"\n[2/4] Lever API ({len(self.lever)} companies)")
            for name, slug in self.lever.items():
                jobs = fetch_lever(slug, name, self.title_keywords)
                all_jobs.extend(jobs)
                time.sleep(1)

        # 3. JSearch
        if self.jsearch_key:
            logger.info(f"\n[3/4] JSearch API (max {JSEARCH_DAY_CAP} queries)")
            for q in build_jsearch_queries(self.job_titles, self.general)[:JSEARCH_DAY_CAP]:
                jobs = fetch_jsearch(q, self.jsearch_key)
                all_jobs.extend(jobs)
                time.sleep(2)
        else:
            logger.info("\n[3/4] JSearch skipped — key not set")

        # 4. Adzuna
        if self.adzuna_id and self.adzuna_key:
            logger.info(f"\n[4/4] Adzuna API (max {ADZUNA_DAY_CAP} queries)")
            for q in build_adzuna_queries(self.job_titles, self.general)[:ADZUNA_DAY_CAP]:
                jobs = fetch_adzuna(q, self.adzuna_id, self.adzuna_key)
                all_jobs.extend(jobs)
                time.sleep(1)
        else:
            logger.info("\n[4/4] Adzuna skipped — credentials not set")

        # Dedup + CPT split
        seen             = load_seen_ids()
        fresh            = deduplicate(all_jobs, seen)
        viable, flagged  = split_by_cpt(fresh)

        # Cap at MAX_JOBS_TO_SCORE so Gemini doesn't take 2+ hours
        # Prioritise: CPT positive first, then neutral
        cpt_pos     = [j for j in viable if j["cpt_signal"] == "positive"]
        cpt_neutral = [j for j in viable if j["cpt_signal"] == "neutral"]
        viable_capped = (cpt_pos + cpt_neutral)[:MAX_JOBS_TO_SCORE]

        save_seen_ids(seen | {j["id"] for j in fresh})

        output = {
            "run_date": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_fetched":  len(all_jobs),
                "new_unique":     len(fresh),
                "viable":         len(viable_capped),
                "cpt_flagged":    len(flagged),
                "capped_from":    len(viable),
            },
            "viable_jobs":      viable_capped,
            "cpt_flagged_jobs": flagged,
        }

        out_path = Path("data/raw_jobs.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(f"DONE — {len(viable_capped)} viable (capped from {len(viable)}) "
                    f"| {len(flagged)} CPT-flagged | {len(all_jobs)} total fetched")
        logger.info("═" * 60)
        return output
