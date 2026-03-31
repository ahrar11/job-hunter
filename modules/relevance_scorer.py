"""
Module 2: Relevance Scorer
──────────────────────────────────────────────────────────────
Reads:   data/raw_jobs.json       (from Module 1)
Reads:   data/master_resume.json  (your profile)
Reads:   data/feedback_history.json (past apply/skip signals)

Scores each viable job against your profile using Gemini,
applies feedback-based boosts, then selects the top N jobs.

Writes:  data/top_jobs.json
──────────────────────────────────────────────────────────────
"""

import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional

from modules.gemini_helper import call_gemini_json

logger = logging.getLogger(__name__)

# How many jobs to keep after scoring
TOP_N = 20

# ── Prompt ────────────────────────────────────────────────────

SCORE_PROMPT = """
You are a career coach helping an MS Business Analytics student find
the best-fit summer 2026 internships.

CANDIDATE PROFILE:
{profile_summary}

JOB POSTING:
Title:    {title}
Company:  {company}
Location: {location}
Description (first 1500 chars):
{description}

TASK:
Score this job posting for this candidate on a scale of 0–100.
Consider:
  - Skill alignment (Python, SQL, Tableau, Power BI, ML, BigQuery, etc.)
  - Role type fit (Business/Data Analyst, BI, Strategy, Operations, Data Science)
  - Seniority match (internship / entry-level only)
  - Company prestige / learning opportunity
  - Location / remote compatibility

Return ONLY a valid JSON object — no explanation, no markdown fences:
{{
  "score": <integer 0-100>,
  "match_reason": "<1 sentence on why this fits>",
  "skill_matches": ["<skill1>", "<skill2>"],
  "concern": "<one potential concern, or empty string>"
}}
"""

# ── Profile summary builder ───────────────────────────────────

def build_profile_summary(resume: Dict) -> str:
    """Compress the master resume into a concise text profile for the prompt."""
    skills = resume.get("skills", {})
    all_skills = (
        skills.get("data_visualization", [])
        + skills.get("programming", [])
        + skills.get("tools_and_methods", [])
    )

    project_titles = [p["title"] for p in resume.get("projects", [])]
    exp_titles = [f"{e['title']} at {e['company']}" for e in resume.get("experience", [])]

    ed = resume.get("education", [{}])[0]
    degree = ed.get("degree", "")
    school = ed.get("school", "")
    grad = ed.get("graduation", "")

    return (
        f"Degree: {degree}, {school} (graduating {grad})\n"
        f"Visa: F-1, eligible for CPT (Summer 2026)\n"
        f"Skills: {', '.join(all_skills)}\n"
        f"Recent projects: {'; '.join(project_titles)}\n"
        f"Experience: {'; '.join(exp_titles)}"
    )

# ── Feedback boost ────────────────────────────────────────────

def load_feedback_boosts(feedback_path: str = "data/feedback_history.json") -> Dict:
    """
    Returns dict of boost weights derived from past feedback.
    Companies / titles you applied to get a +10 score boost.
    Companies / titles you skipped get a -5 penalty.
    """
    p = Path(feedback_path)
    if not p.exists():
        return {"companies": {}, "titles": {}}

    with open(p) as f:
        history = json.load(f)

    company_weights: Dict[str, int] = {}
    title_weights: Dict[str, int] = {}

    for entry in history:
        status = entry.get("status", "")
        company = entry.get("company", "").lower()
        title = entry.get("title", "").lower()
        delta = 10 if status == "applied" else (-5 if status == "skipped" else 0)

        if company:
            company_weights[company] = company_weights.get(company, 0) + delta
        if title:
            title_weights[title] = title_weights.get(title, 0) + delta

    return {"companies": company_weights, "titles": title_weights}


def apply_feedback_boost(score: int, job: Dict, boosts: Dict) -> int:
    company_key = job.get("company", "").lower()
    title_key = job.get("title", "").lower()

    boost = boosts["companies"].get(company_key, 0)

    # Partial title match (e.g. "data analyst" in "data analyst intern")
    for known_title, weight in boosts["titles"].items():
        if known_title in title_key or title_key in known_title:
            boost += weight
            break

    return max(0, min(100, score + boost))

# ── Main scorer ───────────────────────────────────────────────

class RelevanceScorer:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            self.settings = json.load(f)

        with open("data/master_resume.json") as f:
            self.resume = json.load(f)

        self.profile_summary = build_profile_summary(self.resume)
        self.top_n = self.settings.get("search", {}).get("top_n_jobs", TOP_N)

    def score_job(self, job: Dict) -> Optional[Dict]:
        """Score a single job. Returns scoring metadata or None on API failure."""
        prompt = SCORE_PROMPT.format(
            profile_summary=self.profile_summary,
            title=job["title"],
            company=job["company"],
            location=job["location"],
            description=job["description"][:1500],
        )

        result = call_gemini_json(prompt, temperature=0.1, max_tokens=300)
        if result is None:
            logger.warning(f"  Scoring failed for [{job['company']}] {job['title']}")
            return None

        return {
            "score": int(result.get("score", 50)),
            "match_reason": result.get("match_reason", ""),
            "skill_matches": result.get("skill_matches", []),
            "concern": result.get("concern", ""),
        }

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("RELEVANCE SCORER — starting")
        logger.info("═" * 60)

        raw_path = Path("data/raw_jobs.json")
        if not raw_path.exists():
            logger.error("data/raw_jobs.json not found — run Module 1 first")
            return {}

        with open(raw_path) as f:
            raw = json.load(f)

        viable_jobs: List[Dict] = raw.get("viable_jobs", [])
        logger.info(f"Scoring {len(viable_jobs)} viable jobs...")

        boosts = load_feedback_boosts()
        scored: List[Dict] = []

        for i, job in enumerate(viable_jobs, 1):
            logger.info(f"  [{i}/{len(viable_jobs)}] {job['company']} — {job['title']}")

            scoring = self.score_job(job)
            if scoring is None:
                # Fallback: assign neutral score so job isn't lost
                scoring = {
                    "score": 50,
                    "match_reason": "Could not score (API unavailable)",
                    "skill_matches": [],
                    "concern": "",
                }

            raw_score = scoring["score"]
            boosted_score = apply_feedback_boost(raw_score, job, boosts)
            if boosted_score != raw_score:
                logger.info(f"    Score: {raw_score} → {boosted_score} (feedback boost applied)")

            job_scored = {
                **job,
                "relevance_score": boosted_score,
                "raw_score": raw_score,
                "match_reason": scoring["match_reason"],
                "skill_matches": scoring["skill_matches"],
                "concern": scoring["concern"],
            }
            scored.append(job_scored)

            # Respect Gemini free tier rate limit: 15 req/min
            time.sleep(4.5)

        # Sort by score descending, take top N
        scored.sort(key=lambda j: j["relevance_score"], reverse=True)
        top_jobs = scored[:self.top_n]

        # Save output
        output = {
            "run_date": raw.get("run_date"),
            "total_scored": len(scored),
            "top_n": self.top_n,
            "top_jobs": top_jobs,
            "remaining_jobs": scored[self.top_n:],  # Kept for reference, won't be processed
        }

        out_path = Path("data/top_jobs.json")
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(f"DONE — top {len(top_jobs)} jobs selected")
        for job in top_jobs[:5]:
            logger.info(f"  [{job['relevance_score']:3d}] {job['company']} — {job['title']}")
        if len(top_jobs) > 5:
            logger.info(f"  ... and {len(top_jobs) - 5} more")
        logger.info(f"Output written to {out_path}")
        logger.info("═" * 60)

        return output
