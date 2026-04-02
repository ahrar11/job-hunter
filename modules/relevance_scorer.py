"""
Module 2: Relevance Scorer
──────────────────────────────────────────────────────────────
Reads:   data/raw_jobs.json
Reads:   data/master_resume.json
Reads:   data/feedback_history.json

BATCH SCORING: sends all jobs to Gemini in ONE API call instead
of one call per job. Reduces runtime from ~40min to ~30 seconds.

Writes:  data/top_jobs.json
──────────────────────────────────────────────────────────────
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional

from modules.gemini_helper import call_gemini_json, call_gemini

logger = logging.getLogger(__name__)

TOP_N = 20

# ── Profile builder ───────────────────────────────────────────

def build_profile_summary(resume: Dict) -> str:
    skills = resume.get("skills", {})
    all_skills = (
        skills.get("data_visualization", [])
        + skills.get("programming", [])
        + skills.get("tools_and_methods", [])
    )
    project_titles = [p["title"] for p in resume.get("projects", [])]
    exp_titles     = [f"{e['title']} at {e['company']}" for e in resume.get("experience", [])]
    ed  = resume.get("education", [{}])[0]
    return (
        f"Degree: {ed.get('degree','')}, {ed.get('school','')} (graduating {ed.get('graduation','')})\n"
        f"Visa: F-1 CPT eligible — CANNOT work at roles requiring US Citizenship or Permanent Residency\n"
        f"Skills: {', '.join(all_skills)}\n"
        f"Projects: {'; '.join(project_titles)}\n"
        f"Experience: {'; '.join(exp_titles)}"
    )

# ── Feedback boosts ───────────────────────────────────────────

def load_feedback_boosts(path: str = "data/feedback_history.json") -> Dict:
    p = Path(path)
    if not p.exists():
        return {"companies": {}, "titles": {}}
    with open(p) as f:
        history = json.load(f)
    cw, tw = {}, {}
    for entry in history:
        status  = entry.get("status", "")
        company = entry.get("company", "").lower()
        title   = entry.get("title",   "").lower()
        delta   = 10 if status == "applied" else (-5 if status == "skipped" else 0)
        if company: cw[company] = cw.get(company, 0) + delta
        if title:   tw[title]   = tw.get(title,   0) + delta
    return {"companies": cw, "titles": tw}


def apply_feedback_boost(score: int, job: Dict, boosts: Dict) -> int:
    boost = boosts["companies"].get(job.get("company","").lower(), 0)
    title_key = job.get("title","").lower()
    for known, weight in boosts["titles"].items():
        if known in title_key or title_key in known:
            boost += weight
            break
    return max(0, min(100, score + boost))

# ── BATCH scorer — one Gemini call for all jobs ───────────────

BATCH_PROMPT = """
You are a career coach scoring internship job postings for a specific candidate.

CANDIDATE PROFILE:
{profile}

Score EACH job below from 0-100 for fit with this candidate.
Rules:
- Any role requiring US Citizenship or Permanent Residency → score 0
- Strong skill match (Python, SQL, Tableau, Power BI, BigQuery, ML) → higher score
- Business/Data/Analytics/Strategy/BI/Marketing roles → prefer over others
- Roles at well-known tech/finance companies → slight boost
- Roles clearly mismatched (wrong domain, wrong level) → low score

JOBS TO SCORE (JSON array):
{jobs_json}

Return ONLY a valid JSON array with exactly {n} objects in the same order:
[
  {{"score": <0-100>, "match_reason": "<1 sentence>", "skill_matches": ["skill1"], "concern": "<or empty>"}},
  ...
]
No markdown, no explanation, just the JSON array.
"""

def batch_score_jobs(jobs: List[Dict], profile_summary: str) -> List[Optional[Dict]]:
    """
    Score all jobs in a single Gemini call.
    Returns list of scoring dicts (same length as jobs), None entries on failure.
    """
    if not jobs:
        return []

    # Build compact job list for prompt (title + company + first 300 chars of description)
    jobs_compact = [
        {
            "idx":         i,
            "title":       j["title"],
            "company":     j["company"],
            "location":    j["location"],
            "description": j["description"][:400],
        }
        for i, j in enumerate(jobs)
    ]

    prompt = BATCH_PROMPT.format(
        profile=profile_summary,
        jobs_json=json.dumps(jobs_compact, indent=2),
        n=len(jobs),
    )

    logger.info(f"  Sending {len(jobs)} jobs to Gemini in one batch call...")
    result = call_gemini_json(prompt, temperature=0.1, max_tokens=4000)

    if result is None:
        logger.error("  Batch scoring failed — Gemini returned nothing")
        return [None] * len(jobs)

    if not isinstance(result, list):
        logger.error(f"  Batch scoring returned wrong type: {type(result)}")
        return [None] * len(jobs)

    # Pad or trim to match job count
    while len(result) < len(jobs):
        result.append(None)

    logger.info(f"  Batch scored {len(jobs)} jobs successfully")
    return result[:len(jobs)]


# ── Main orchestrator ─────────────────────────────────────────

class RelevanceScorer:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            self.settings = json.load(f)
        with open("data/master_resume.json") as f:
            self.resume = json.load(f)
        self.profile_summary = build_profile_summary(self.resume)
        self.top_n = self.settings.get("search", {}).get("top_n_jobs", TOP_N)

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("RELEVANCE SCORER — batch mode (1 Gemini call total)")
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

        # Batch score all jobs in one call
        scores = batch_score_jobs(viable_jobs, self.profile_summary)

        scored: List[Dict] = []
        for job, scoring in zip(viable_jobs, scores):
            if scoring is None:
                raw_score = 50
                match_reason  = "Could not score (API unavailable)"
                skill_matches = []
                concern       = ""
            else:
                raw_score     = int(scoring.get("score", 50))
                match_reason  = scoring.get("match_reason", "")
                skill_matches = scoring.get("skill_matches", [])
                concern       = scoring.get("concern", "")

            boosted = apply_feedback_boost(raw_score, job, boosts)

            scored.append({
                **job,
                "relevance_score": boosted,
                "raw_score":       raw_score,
                "match_reason":    match_reason,
                "skill_matches":   skill_matches,
                "concern":         concern,
            })

        # Sort by score, take top N
        scored.sort(key=lambda j: j["relevance_score"], reverse=True)
        top_jobs = scored[:self.top_n]

        output = {
            "run_date":      raw.get("run_date"),
            "total_scored":  len(scored),
            "top_n":         self.top_n,
            "top_jobs":      top_jobs,
            "remaining_jobs": scored[self.top_n:],
        }

        out_path = Path("data/top_jobs.json")
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(f"DONE — top {len(top_jobs)} jobs selected")
        for job in top_jobs[:5]:
            logger.info(f"  [{job['relevance_score']:3d}] {job['company']} — {job['title']}")
        if len(top_jobs) > 5:
            logger.info(f"  ... and {len(top_jobs)-5} more")
        logger.info("═" * 60)
        return output
