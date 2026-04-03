"""
Module 2: Relevance Scorer — uses Claude API (Anthropic)
Scores in chunks of 10 → fast, reliable, no rate limit issues.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional

from modules.llm_helper import call_claude_json

logger = logging.getLogger(__name__)

TOP_N      = 20
CHUNK_SIZE = 10
MIN_SCORE  = 60   # Jobs below this score are excluded from the dashboard


def build_profile_summary(resume: Dict) -> str:
    skills = resume.get("skills", {})
    all_skills = (
        skills.get("data_visualization", [])
        + skills.get("programming", [])
        + skills.get("tools_and_methods", [])
    )
    ed          = resume.get("education", [{}])[0]
    degree      = ed.get("degree", "")
    school      = ed.get("school", "")
    graduation  = ed.get("graduation", "")
    projects    = "; ".join(p["title"] for p in resume.get("projects", []))
    experience  = "; ".join(
        e["title"] + " at " + e["company"] for e in resume.get("experience", [])
    )
    skills_str  = ", ".join(all_skills)
    return (
        "Degree: " + degree + ", " + school + " (graduating " + graduation + ")\n"
        "Visa: F-1 on CPT — CANNOT work at roles requiring US Citizenship or Permanent Residency\n"
        "Skills: " + skills_str + "\n"
        "Projects: " + projects + "\n"
        "Experience: " + experience
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
        if company:
            cw[company] = cw.get(company, 0) + delta
        if title:
            tw[title] = tw.get(title, 0) + delta
    return {"companies": cw, "titles": tw}


def apply_feedback_boost(score: int, job: Dict, boosts: Dict) -> int:
    boost = boosts["companies"].get(job.get("company", "").lower(), 0)
    for known, w in boosts["titles"].items():
        if known in job.get("title", "").lower():
            boost += w
            break
    return max(0, min(100, score + boost))


CHUNK_PROMPT = """You are scoring internship postings for fit with a specific candidate.

CANDIDATE PROFILE:
{profile}

SCORING RUBRIC (be generous — this candidate is broadly qualified for analytics/data/business roles):

90-100: Perfect match — role explicitly mentions multiple candidate skills (Python, SQL, Tableau, Power BI, BigQuery), is an analytics/data/business analyst internship, and is in a preferred location or remote. Sponsor-friendly.
80-89:  Strong match — good skill overlap with the role, relevant analytics/data/business domain, reasonable location. Minor gaps are fine.
70-79:  Good match — the role is in a related field (operations, strategy, marketing analytics, BI, consulting, product) and the candidate could perform well. At least some skill overlap.
55-69:  Partial match — some relevance but the role leans into a different domain (e.g., pure finance, supply chain, or a niche area where the candidate has limited experience).
30-54:  Weak match — role is in an unrelated domain, requires skills the candidate doesn't have, or is not an analytics/data role at all.
1-29:   Poor match — fundamentally wrong domain (engineering, cybersecurity, mechanical, etc.) or the role title was misleading.
0:      ONLY score 0 if the job description EXPLICITLY states it requires US Citizenship, Permanent Residency, security clearance, or explicitly excludes F-1/CPT/OPT candidates. Do NOT score 0 just because visa status is unmentioned — most internships accept CPT.

IMPORTANT: If the job description is short or vague, score based on title and company fit. Do NOT penalize for lack of detail. A "Business Analyst Intern" at a reputable company with a vague description should still score 70+.

JOBS TO SCORE:
{jobs_json}

Return ONLY a JSON array of exactly {n} objects in the same order:
[{{"score": <0-100>, "match_reason": "<1 sentence>", "skill_matches": ["skill1"], "concern": "<or empty>"}}]
No markdown, no explanation."""


def score_chunk(jobs: List[Dict], profile: str) -> List[Optional[Dict]]:
    compact = [
        {
            "idx": i,
            "title": j["title"],
            "company": j["company"],
            "location": j["location"],
            "description": j["description"][:400],
        }
        for i, j in enumerate(jobs)
    ]
    prompt = CHUNK_PROMPT.format(
        profile=profile,
        jobs_json=json.dumps(compact, indent=2),
        n=len(jobs),
    )
    result = call_claude_json(prompt, temperature=0.1, max_tokens=2000)
    if not isinstance(result, list):
        logger.warning("  Chunk scoring returned unexpected type: %s", type(result))
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
        logger.info("=" * 60)
        logger.info("RELEVANCE SCORER — Claude API, chunks of %d", CHUNK_SIZE)
        logger.info("=" * 60)

        raw_path = Path("data/raw_jobs.json")
        if not raw_path.exists():
            logger.error("data/raw_jobs.json not found")
            return {}

        with open(raw_path) as f:
            raw = json.load(f)

        jobs: List[Dict] = raw.get("viable_jobs", [])
        logger.info("Scoring %d jobs...", len(jobs))

        boosts     = load_feedback_boosts()
        all_scores = []

        chunks = [jobs[i:i + CHUNK_SIZE] for i in range(0, len(jobs), CHUNK_SIZE)]
        for ci, chunk in enumerate(chunks, 1):
            logger.info("  Chunk %d/%d (%d jobs)...", ci, len(chunks), len(chunk))
            scores = score_chunk(chunk, self.profile)
            all_scores.extend(scores)
            if ci < len(chunks):
                time.sleep(2)

        scored = []
        for job, scoring in zip(jobs, all_scores):
            if scoring is None:
                raw_score, match_reason, skill_matches, concern = 50, "Could not score", [], ""
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

        # Sort by: direct URLs first (at same score), then by score descending
        scored.sort(key=lambda j: (
            -(j["relevance_score"]),
            0 if j.get("apply_url_quality") == "direct" else 1,
        ))

        # Filter out low-quality matches
        min_score = self.settings.get("search", {}).get("min_score", MIN_SCORE)
        qualified = [j for j in scored if j["relevance_score"] >= min_score]
        logger.info("  %d/%d jobs meet minimum score threshold (%d)",
                     len(qualified), len(scored), min_score)

        # Warn about aggregator URLs
        agg_count = sum(1 for j in qualified if j.get("apply_url_quality") == "aggregator")
        if agg_count:
            logger.info("  ⚠ %d jobs have aggregator redirect URLs (may require account creation)",
                         agg_count)

        top_jobs = qualified[:self.top_n]

        output = {
            "run_date":       raw.get("run_date"),
            "total_scored":   len(scored),
            "top_n":          self.top_n,
            "top_jobs":       top_jobs,
            "remaining_jobs": scored[self.top_n:],
        }
        with open("data/top_jobs.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("\nDONE — top %d jobs selected", len(top_jobs))
        for job in top_jobs[:5]:
            logger.info("  [%3d] %s — %s", job["relevance_score"], job["company"], job["title"])
        if len(top_jobs) > 5:
            logger.info("  ... and %d more", len(top_jobs) - 5)
        return output
