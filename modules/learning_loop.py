"""
Module 6: Learning Loop
──────────────────────────────────────────────────────────────
Reads:   data/feedback_history.json   (your apply/save/skip signals)
Reads:   data/top_jobs.json           (current run's jobs)
Reads:   config/job_titles.json       (current target titles)
Reads:   config/target_companies.json (current company list)

What it learns:
  1. Which job TITLES you apply to most → boosts those titles in
     future searches (already used by Module 2 scorer)
  2. Which COMPANIES you keep targeting → promotes them in queries
  3. Which SKILL KEYWORDS appear in roles you applied to →
     improves JSearch/Adzuna query construction
  4. Which roles you always skip → avoids those patterns

Writes:  data/learning_profile.json  (read by Modules 1 & 2)
Updates: config/job_titles.json      (if a new popular title emerges)
──────────────────────────────────────────────────────────────
"""

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


# ── Text tools ────────────────────────────────────────────────

STOP_WORDS = {
    "intern", "internship", "summer", "2026", "the", "and", "for",
    "with", "our", "you", "will", "are", "this", "that", "have",
    "from", "your", "able", "work", "team", "role", "join",
}

SKILL_PATTERNS = [
    "python", "sql", "tableau", "power bi", "excel", "r ", "java",
    "machine learning", "ml", "data analysis", "analytics", "bigquery",
    "spark", "airflow", "dbt", "looker", "powerbi", "pandas", "numpy",
    "a/b testing", "statistics", "forecasting", "modeling", "etl",
    "visualization", "dashboard", "reporting", "snowflake", "databricks",
    "aws", "gcp", "azure", "figma", "jira", "agile", "scrum", "excel",
    "vba", "alteryx", "sas", "spss", "google analytics", "mixpanel",
]


def extract_skill_signals(description: str) -> List[str]:
    desc = description.lower()
    return [s for s in SKILL_PATTERNS if re.search(r'\b' + re.escape(s) + r'\b', desc)]


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\b(intern(ship)?|summer|202\d)\b", "", t)
    t = re.sub(r"[^a-z\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


# ── Learning profile builder ──────────────────────────────────

class LearningLoop:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.feedback_path = Path("data/feedback_history.json")
        self.profile_path = Path("data/learning_profile.json")

        # Load configs
        with open(f"{config_dir}/job_titles.json") as f:
            self.titles_cfg = json.load(f)

        with open(f"{config_dir}/target_companies.json") as f:
            self.companies_cfg = json.load(f)

        # Load current top_jobs for syncing feedback
        self.top_jobs: List[Dict] = []
        top_path = Path("data/top_jobs.json")
        if top_path.exists():
            with open(top_path) as f:
                self.top_jobs = json.load(f).get("top_jobs", [])

    def sync_dashboard_feedback(self):
        """
        Pull in any feedback that was recorded via the dashboard's
        localStorage (which writes to data/feedback_history.json
        when the GitHub Action runs). Merges without duplicates.
        """
        if not self.feedback_path.exists():
            return

        with open(self.feedback_path) as f:
            existing: List[Dict] = json.load(f)

        existing_ids = {e["job_id"] for e in existing}
        new_entries = []

        for job in self.top_jobs:
            job_id = job.get("id")
            status = job.get("status", "new")
            if status in ("applied", "saved", "skipped") and job_id not in existing_ids:
                new_entries.append({
                    "job_id":   job_id,
                    "title":    job.get("title", ""),
                    "company":  job.get("company", ""),
                    "source":   job.get("source", ""),
                    "status":   status,
                    "score":    job.get("relevance_score"),
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                })

        if new_entries:
            combined = existing + new_entries
            with open(self.feedback_path, "w") as f:
                json.dump(combined, f, indent=2)
            logger.info(f"  Synced {len(new_entries)} new feedback entries")

    def load_feedback(self) -> List[Dict]:
        if not self.feedback_path.exists():
            return []
        with open(self.feedback_path) as f:
            return json.load(f)

    def compute_profile(self, feedback: List[Dict]) -> Dict:
        """Derive weighted signals from feedback history."""
        applied  = [f for f in feedback if f.get("status") == "applied"]
        saved    = [f for f in feedback if f.get("status") == "saved"]
        skipped  = [f for f in feedback if f.get("status") == "skipped"]

        # ── Title signals ─────────────────────────────────────
        title_counter: Counter = Counter()
        for entry in applied + saved:
            norm = normalize_title(entry.get("title", ""))
            if norm:
                weight = 2 if entry["status"] == "applied" else 1
                title_counter[norm] += weight
        for entry in skipped:
            norm = normalize_title(entry.get("title", ""))
            if norm:
                title_counter[norm] -= 1

        # ── Company signals ───────────────────────────────────
        company_counter: Counter = Counter()
        for entry in applied + saved:
            co = entry.get("company", "").strip()
            if co:
                weight = 2 if entry["status"] == "applied" else 1
                company_counter[co] += weight
        for entry in skipped:
            co = entry.get("company", "").strip()
            if co:
                company_counter[co] -= 1

        # ── Skill signals from descriptions ───────────────────
        # We don't store descriptions in feedback, so we look them
        # up from top_jobs in memory
        job_map = {j["id"]: j for j in self.top_jobs}
        skill_counter: Counter = Counter()
        for entry in applied + saved:
            jid = entry.get("job_id", "")
            job = job_map.get(jid)
            if job:
                skills = extract_skill_signals(job.get("description", ""))
                weight = 2 if entry["status"] == "applied" else 1
                for s in skills:
                    skill_counter[s] += weight

        # ── Derive boosted / avoided lists ───────────────────
        top_titles    = [t for t, c in title_counter.most_common(10) if c > 0]
        avoid_titles  = [t for t, c in title_counter.most_common() if c < 0]
        top_companies = [c for c, v in company_counter.most_common(15) if v > 0]
        top_skills    = [s for s, c in skill_counter.most_common(12) if c > 0]

        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_applied": len(applied),
            "total_saved":   len(saved),
            "total_skipped": len(skipped),
            "preferred_titles": top_titles,
            "avoided_titles":   avoid_titles,
            "preferred_companies": top_companies,
            "top_skills": top_skills,
            # Raw weights for Module 2 scorer
            "company_weights": dict(company_counter),
            "title_weights": dict(title_counter),
        }

    def maybe_update_titles(self, profile: Dict):
        """
        If a new title emerges strongly from feedback that isn't in
        job_titles.json yet, add it automatically.
        """
        current_titles_norm = {normalize_title(t) for t in self.titles_cfg.get("titles", [])}
        existing_titles: List[str] = self.titles_cfg.get("titles", [])

        added = []
        for title in profile.get("preferred_titles", []):
            if title not in current_titles_norm and len(title) > 4:
                # Format: capitalize words + " Intern"
                new_title = " ".join(w.capitalize() for w in title.split()) + " Intern"
                existing_titles.append(new_title)
                added.append(new_title)
                logger.info(f"  → Auto-added new title to job_titles.json: '{new_title}'")

        if added:
            self.titles_cfg["titles"] = existing_titles
            with open(f"{self.config_dir}/job_titles.json", "w") as f:
                json.dump(self.titles_cfg, f, indent=2)

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("LEARNING LOOP — starting")
        logger.info("═" * 60)

        # Step 1: sync any feedback from dashboard
        self.sync_dashboard_feedback()

        # Step 2: load and analyse all feedback
        feedback = self.load_feedback()
        if not feedback:
            logger.info("  No feedback history yet — learning loop will activate after you")
            logger.info("  start marking jobs as Applied / Saved / Skipped in the dashboard.")
            profile = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_applied": 0, "total_saved": 0, "total_skipped": 0,
                "preferred_titles": [], "avoided_titles": [],
                "preferred_companies": [], "top_skills": [],
                "company_weights": {}, "title_weights": {},
            }
        else:
            logger.info(f"  Analysing {len(feedback)} feedback entries...")
            profile = self.compute_profile(feedback)

            logger.info(f"  Applied: {profile['total_applied']} | "
                       f"Saved: {profile['total_saved']} | "
                       f"Skipped: {profile['total_skipped']}")

            if profile["preferred_titles"]:
                logger.info(f"  Top titles:     {', '.join(profile['preferred_titles'][:5])}")
            if profile["preferred_companies"]:
                logger.info(f"  Top companies:  {', '.join(profile['preferred_companies'][:5])}")
            if profile["top_skills"]:
                logger.info(f"  Top skills:     {', '.join(profile['top_skills'][:6])}")

            # Step 3: maybe add new titles
            self.maybe_update_titles(profile)

        # Step 4: save profile
        with open(self.profile_path, "w") as f:
            json.dump(profile, f, indent=2)

        logger.info(f"  Learning profile saved to {self.profile_path}")
        logger.info("═" * 60)
        logger.info("DONE — profile will improve Module 1 queries and Module 2 scoring")
        logger.info("═" * 60)

        return profile
