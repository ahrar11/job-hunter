"""
Module 2: Relevance Scorer
──────────────────────────────────────────────────────────────
Scores jobs in chunks of 10 — each chunk = 1 Gemini call.
31 jobs = 3-4 API calls instead of 31. ~30s total instead of 40min.
──────────────────────────────────────────────────────────────
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional

from modules.gemini_helper import call_gemini_json

logger = logging.getLogger(__name__)

TOP_N      = 20
CHUNK_SIZE = 10   # Jobs per Gemini call — fits easily in free tier

def build_profile_summary(resume: Dict) -> str:
    skills = resume.get("skills", {})
    all_skills = (
        skills.get("data_visualization", [])
        + skills.get("programming", [])
        + skills.get("tools_and_methods", [])
    )
    project_titles = [p["title"] for p in resume.get("projects", [])]
    exp_titles     = [f"{e['title']} at {e['company']}" for e in resume.get("experience", [])]
    ed = resume.get("education", [{}])[0]
    return (
        f"Degree: {ed.get('degree','')}, {ed.get('school','')} (graduating {ed.get('graduation','')})\n"
        f"Visa: F-1 student on CPT — CANNOT work at roles requiring US Citizenship or Permanent Residency\n"
        f"Skills: {', '.join(all_skills)}\n"
        f"Projects: {'; '.join(project_titles)}\n"
        f"Experience: {'; '.join(exp_titles)}"
    )

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
    for known, w in boosts["titles"].items():
        if known in job.get("title","").lower():
            boost += w; break
    return max(0, min(100, score + boost))

CHUNK_PROMPT = """
You are scoring internship job postings for an MS Business Analytics student.

CANDIDATE:
{profile}

Score EACH job 0-100. Rules:
- Score 0 if role requires US Citizenship or Permanent Residency
- Score 0 if role is clearly wrong domain (cybersecurity, engineering, etc.)
- High scores (75+) for strong skill match: Python, SQL, Tableau, Power BI, BigQuery, analytics
- Medium (50-74) for partial match or unknown company
- Low (<50) for weak match

JOBS:
{jobs_json}

Return a JSON array of exactly {n} objects (same order):
[{{"score":<int>,"match_reason":"<1 sentence>","skill_matches":["skill1"],"concern":"<or empty>"}}]
JSON only, no markdown.
"""

def score_chunk(jobs: List[Dict], profile: str) -> List[Optional[Dict]]:
    compact = [
        {"idx": i, "title": j["title"], "company": j["company"],
         "location": j["location"], "description": j["description"][:350]}
        for i, j in enumerate(jobs)
    ]
    prompt = CHUNK_PROMPT.format(
        profile=profile,
        jobs_json=json.dumps(compact, indent=2),
        n=len(jobs)
    )
    result = call_gemini_json(prompt, temperature=0.1, max_tokens=2000)
    if not isinstance(result, list):
        return [None] * len(jobs)
    while len(result) < len(jobs):
        result.append(None)
    return result[:len(jobs)]

class RelevanceScorer:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            self.settings = json.load(f)
        with open("data/master_resume.json") as f:
            self.resume = json.load(f)
        self.profile = build_profile_summary(self.resume)
        self.top_n   = self.settings.get("search", {}).get("top_n_jobs", TOP_N)

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info(f"RELEVANCE SCORER — chunked ({CHUNK_SIZE} jobs/call)")
        logger.info("═" * 60)

        raw_path = Path("data/raw_jobs.json")
        if not raw_path.exists():
            logger.error("data/raw_jobs.json not found")
            return {}

        with open(raw_path) as f:
            raw = json.load(f)

        jobs: List[Dict] = raw.get("viable_jobs", [])
        logger.info(f"Scoring {len(jobs)} jobs in chunks of {CHUNK_SIZE}...")

        boosts  = load_feedback_boosts()
        all_scores: List[Optional[Dict]] = []

        # Process in chunks
        chunks = [jobs[i:i+CHUNK_SIZE] for i in range(0, len(jobs), CHUNK_SIZE)]
        for ci, chunk in enumerate(chunks, 1):
            logger.info(f"  Chunk {ci}/{len(chunks)} ({len(chunk)} jobs)...")
            scores = score_chunk(chunk, self.profile)
            all_scores.extend(scores)
            if ci < len(chunks):
                time.sleep(5)   # Brief pause between chunks

        # Merge scores back into jobs
        scored: List[Dict] = []
        for job, scoring in zip(jobs, all_scores):
            if scoring is None:
                raw_score, match_reason, skill_matches, concern = 50, "Could not score", [], ""
            else:
                raw_score     = int(scoring.get("score", 50))
                match_reason  = scoring.get("match_reason", "")
                skill_matches = scoring.get("skill_matches", [])
                concern       = scoring.get("concern", "")

            boosted = apply_feedback_boost(raw_score, job, boosts)
            scored.append({**job,
                "relevance_score": boosted, "raw_score": raw_score,
                "match_reason": match_reason, "skill_matches": skill_matches,
                "concern": concern,
            })

        scored.sort(key=lambda j: j["relevance_score"], reverse=True)
        top_jobs = scored[:self.top_n]

        output = {
            "run_date":       raw.get("run_date"),
            "total_scored":   len(scored),
            "top_n":          self.top_n,
            "top_jobs":       top_jobs,
            "remaining_jobs": scored[self.top_n:],
        }
        out_path = Path("data/top_jobs.json")
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info(f"\nDONE — top {len(top_jobs)} jobs selected")
        for job in top_jobs[:5]:
            logger.info(f"  [{job['relevance_score']:3d}] {job['company']} — {job['title']}")
        if len(top_jobs) > 5:
            logger.info(f"  ... and {len(top_jobs)-5} more")
        return output
