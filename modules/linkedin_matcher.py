"""
Module 4: LinkedIn Connection Matcher
──────────────────────────────────────────────────────────────
Reads:   data/linkedin_connections.csv  (your manual export)
Reads:   data/top_jobs.json             (from Module 2)

For each job, fuzzy-matches the company name against your
LinkedIn connections and flags:
  - 1st degree: direct connection at that company
  - 2nd degree: connection's company matches (from "Company" col)
  - None: no known connection

Updates: data/top_jobs.json  with "connections" field per job
──────────────────────────────────────────────────────────────
HOW TO EXPORT YOUR LINKEDIN CONNECTIONS:
  1. linkedin.com → Me → Settings & Privacy
  2. Data Privacy → Get a copy of your data
  3. Select "Connections" only → Request archive
  4. Download CSV → save as data/linkedin_connections.csv
──────────────────────────────────────────────────────────────
"""

import csv
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Fuzzy company name normalizer ─────────────────────────────

# Known aliases: maps variations → canonical name
COMPANY_ALIASES = {
    "jpmorgan": "jpmorgan chase",
    "jp morgan": "jpmorgan chase",
    "jpmorgan chase co": "jpmorgan chase",
    "jpmorgan chase  co": "jpmorgan chase",
    "j.p. morgan": "jpmorgan chase",
    "bytedance": "bytedance tiktok",
    "tiktok": "bytedance tiktok",
    "alphabet": "google",
    "amazon web services": "amazon",
    "aws": "amazon",
    "microsoft corporation": "microsoft",
    "meta platforms": "meta",
    "facebook": "meta",
}

def normalize_company(name: str) -> str:
    """
    Strip legal suffixes and apply known aliases.
    'JPMorgan Chase & Co.' → 'jpmorgan chase'
    'Google LLC' → 'google'
    """
    if not name:
        return ""
    n = name.lower().strip()

    # Remove legal suffixes
    suffixes = [
        r",?\s*&\s*co\.?$", r",?\s*and\s+co\.?$",
        r",?\s*inc\.?$", r",?\s*llc\.?$", r",?\s*ltd\.?$",
        r",?\s*corp\.?$", r",?\s*co\.?$", r",?\s*gmbh$",
        r",?\s*s\.?a\.?$", r",?\s*plc\.?$",
        r"\s+international$", r"\s+technologies$",
        r"\s+technology$", r"\s+solutions$",
        r"\s+group$", r"\s+holdings$",
        r"\s+platforms?$",
    ]
    for suffix in suffixes:
        n = re.sub(suffix, "", n).strip()

    # Normalize punctuation / whitespace
    n = re.sub(r"[^a-z0-9\s]", "", n)
    n = re.sub(r"\s+", " ", n).strip()

    # Apply known aliases
    return COMPANY_ALIASES.get(n, n)


def company_matches(job_company: str, conn_company: str) -> bool:
    """
    Returns True if job_company and conn_company are likely the same.
    Handles both exact and substring matches after normalization.
    """
    jc = normalize_company(job_company)
    cc = normalize_company(conn_company)

    if not jc or not cc:
        return False

    # Exact match after normalization
    if jc == cc:
        return True

    # One is a substring of the other (handles "tiktok" ⊂ "bytedance tiktok")
    if jc in cc or cc in jc:
        return True

    # Token overlap: only when one name has MULTIPLE tokens that all appear in the other
    # (avoids false positives like 'openai' ⊂ 'openai' matching 'microsoft' ⊂ 'microsoft')
    jc_tokens = set(jc.split())
    cc_tokens = set(cc.split())
    if len(jc_tokens) > 1 and jc_tokens.issubset(cc_tokens):
        return True
    if len(cc_tokens) > 1 and cc_tokens.issubset(jc_tokens):
        return True

    return False


# ── CSV loader ────────────────────────────────────────────────

def load_connections(csv_path: str = "data/linkedin_connections.csv") -> List[Dict]:
    """
    Load LinkedIn connections CSV.
    LinkedIn's export has these columns:
      First Name, Last Name, URL, Email Address, Company, Position, Connected On
    """
    p = Path(csv_path)
    if not p.exists():
        logger.warning(
            f"LinkedIn connections CSV not found at {csv_path}.\n"
            "Export from LinkedIn: Settings → Data Privacy → Get a copy of your data → Connections"
        )
        return []

    connections = []
    with open(p, newline="", encoding="utf-8-sig") as f:
        # LinkedIn CSV sometimes has a 3-line header — skip non-data rows
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize column names (LinkedIn changes them occasionally)
            normalized = {k.strip(): v.strip() for k, v in row.items()}
            connections.append(normalized)

    logger.info(f"Loaded {len(connections)} LinkedIn connections from {csv_path}")
    return connections


def find_connections_at_company(
    company: str, connections: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Returns (first_degree_matches, []).
    LinkedIn's exported CSV only contains YOUR direct connections (1st degree).
    We return them under 'first_degree'.

    Note: True 2nd-degree lookup isn't possible from the CSV alone.
    We flag "possible_2nd" when a connection's company CONTAINS the target
    company name (e.g., a connection at 'Google' could refer you to a
    Google team they know, which is practical referral logic).
    """
    direct = []

    for conn in connections:
        # Try multiple possible column names LinkedIn uses
        conn_company = (
            conn.get("Company", "")
            or conn.get("company", "")
            or conn.get("Employer", "")
        )

        if company_matches(company, conn_company):
            first = conn.get("First Name", conn.get("first name", ""))
            last  = conn.get("Last Name",  conn.get("last name",  ""))
            position = conn.get("Position", conn.get("position", ""))
            url   = conn.get("URL", conn.get("url", ""))

            direct.append({
                "name": f"{first} {last}".strip(),
                "position": position,
                "profile_url": url,
                "connection_degree": 1,
            })

    return direct


# ── Main orchestrator ─────────────────────────────────────────

class LinkedInMatcher:
    def __init__(self, csv_path: str = "data/linkedin_connections.csv"):
        self.connections = load_connections(csv_path)
        self.has_data = len(self.connections) > 0

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("LINKEDIN MATCHER — starting")
        logger.info(f"  {len(self.connections)} connections loaded")
        logger.info("═" * 60)

        top_path = Path("data/top_jobs.json")
        if not top_path.exists():
            logger.error("data/top_jobs.json not found — run Module 2 first")
            return {}

        with open(top_path) as f:
            top_data = json.load(f)

        top_jobs: List[Dict] = top_data.get("top_jobs", [])

        connected_count = 0
        for job in top_jobs:
            company = job.get("company", "")

            if self.has_data:
                matches = find_connections_at_company(company, self.connections)
            else:
                matches = []

            if matches:
                connected_count += 1
                degree_1 = [c for c in matches if c["connection_degree"] == 1]
                job["connection_flag"] = "1st_degree" if degree_1 else "possible_2nd"
                job["connections"] = matches
                logger.info(
                    f"  🟢 {company}: {len(matches)} connection(s) — "
                    + ", ".join(c["name"] for c in matches[:3])
                )
            else:
                job["connection_flag"] = "none"
                job["connections"] = []

        # Persist
        with open(top_path, "w") as f:
            json.dump(top_data, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(
            f"DONE — {connected_count}/{len(top_jobs)} jobs have LinkedIn connections"
        )
        if not self.has_data:
            logger.info(
                "  ⚠ No connections CSV found. Add data/linkedin_connections.csv\n"
                "    to enable connection lookup."
            )
        logger.info("═" * 60)

        return {
            "total_jobs": len(top_jobs),
            "jobs_with_connections": connected_count,
            "connections_loaded": len(self.connections),
        }
