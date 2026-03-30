"""
Job Hunter — Main Orchestrator
────────────────────────────────────────────────────────────────
Runs all 6 modules in sequence every day via GitHub Actions.

Pipeline:
  Module 1 → Job Fetcher        (fetch raw jobs from APIs/ATS)
  Module 2 → Relevance Scorer   (rank by fit using Gemini)
  Module 3 → Resume Tailor      (per-job resume via Gemini + docx)
  Module 4 → LinkedIn Matcher   (flag connection opportunities)
  Module 5 → Dashboard + Email  (GitHub Pages UI + Gmail digest)
  Module 6 → Learning Loop      (refine from your feedback)
"""

import logging
import sys
import json
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/run_log.txt", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


def run():
    start = datetime.now()
    logger.info("╔══════════════════════════════════════════════════╗")
    logger.info("║         JOB HUNTER — DAILY RUN START            ║")
    logger.info(f"║  {start.strftime('%Y-%m-%d %H:%M UTC'):<44}║")
    logger.info("╚══════════════════════════════════════════════════╝")

    results = {}

    # MODULE 1
    logger.info("\n▶  MODULE 1 — Job Fetcher")
    try:
        from modules.job_fetcher import JobFetcher
        result = JobFetcher().run()
        stats = result.get("stats", {})
        results["module1"] = stats
        logger.info(f"   ✓ {stats.get('viable', 0)} viable jobs | {stats.get('cpt_flagged', 0)} CPT-flagged excluded")
    except Exception as e:
        logger.error(f"   ✗ Module 1 failed: {e}")

    # MODULE 2
    logger.info("\n▶  MODULE 2 — Relevance Scorer")
    try:
        from modules.relevance_scorer import RelevanceScorer
        result = RelevanceScorer().run()
        logger.info(f"   ✓ Top {result.get('top_n', 0)} jobs selected from {result.get('total_scored', 0)} scored")
    except Exception as e:
        logger.error(f"   ✗ Module 2 failed: {e}")

    # MODULE 3
    logger.info("\n▶  MODULE 3 — Resume Tailor")
    try:
        from modules.resume_tailor import ResumeTailor
        result = ResumeTailor().run()
        logger.info(f"   ✓ {result.get('success', 0)}/{result.get('total', 0)} resumes generated")
    except Exception as e:
        logger.error(f"   ✗ Module 3 failed: {e}")

    # MODULE 4
    logger.info("\n▶  MODULE 4 — LinkedIn Matcher")
    try:
        from modules.linkedin_matcher import LinkedInMatcher
        result = LinkedInMatcher().run()
        logger.info(f"   ✓ {result.get('jobs_with_connections', 0)} jobs with connections found")
    except Exception as e:
        logger.error(f"   ✗ Module 4 failed: {e}")

    # MODULE 5a
    logger.info("\n▶  MODULE 5a — Dashboard Generator")
    try:
        from modules.dashboard_generator import DashboardGenerator
        DashboardGenerator().run()
        logger.info("   ✓ Dashboard written to docs/index.html")
    except Exception as e:
        logger.error(f"   ✗ Dashboard failed: {e}")

    # MODULE 5b
    logger.info("\n▶  MODULE 5b — Email Digest")
    try:
        from modules.email_digest import EmailDigest
        result = EmailDigest().run()
        if result.get("sent"):
            logger.info(f"   ✓ Email sent ({result.get('jobs_count', 0)} jobs)")
        else:
            logger.info("   ℹ Email skipped (check GMAIL_* secrets)")
    except Exception as e:
        logger.error(f"   ✗ Email digest failed: {e}")

    # MODULE 6
    logger.info("\n▶  MODULE 6 — Learning Loop")
    try:
        from modules.learning_loop import LearningLoop
        result = LearningLoop().run()
        logger.info(f"   ✓ {result.get('total_applied',0)} applied | {result.get('total_saved',0)} saved | {result.get('total_skipped',0)} skipped")
    except Exception as e:
        logger.error(f"   ✗ Learning loop failed: {e}")

    # Summary
    elapsed = (datetime.now() - start).seconds
    logger.info("\n╔══════════════════════════════════════════════════╗")
    logger.info("║              DAILY RUN COMPLETE                 ║")
    logger.info(f"║  Completed in {elapsed}s                              ║")
    logger.info("╚══════════════════════════════════════════════════╝")

    top_path = Path("data/top_jobs.json")
    if top_path.exists():
        with open(top_path) as f:
            jobs = json.load(f).get("top_jobs", [])
        if jobs:
            logger.info("\nTop 5 Today:")
            for job in jobs[:5]:
                cpt = {"positive":"🟢","neutral":"🟡","negative":"🔴"}.get(job.get("cpt_signal"),"⚪")
                conn = "🔗" if job.get("connection_flag") != "none" else "  "
                score = job.get("relevance_score", 0)
                logger.info(f"  {cpt} {conn} [{score:3d}] {job['company']:<20} {job['title']}")


if __name__ == "__main__":
    run()
