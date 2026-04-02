"""
Module 3: Resume Tailor
──────────────────────────────────────────────────────────────
Reads:   data/top_jobs.json       (from Module 2)
Reads:   data/master_resume.json  (source of truth)

For each top job:
  1. Calls Gemini to select the most relevant sections and
     rewrite bullet points to mirror the JD's language.
     NO fabrication — only existing content is used.
  2. Passes the tailored JSON to a Node.js script that
     produces a clean, ATS-friendly .docx file.

Writes:  resumes/{job_id}_{Company}_{Title}.docx
Updates: data/top_jobs.json  with "resume_path" field per job
──────────────────────────────────────────────────────────────
"""

import json
import time
import logging
import subprocess
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from modules.llm_helper import call_claude_json as call_gemini_json

logger = logging.getLogger(__name__)

# ── Tailoring prompt ──────────────────────────────────────────

TAILOR_PROMPT = """
You are a professional resume writer helping an MS Business Analytics student
tailor their resume for a specific internship. Your job is to CURATE and REWRITE
— never invent skills, tools, or experiences that don't exist in the source.

MASTER RESUME (source of truth — all available content):
{master_resume_json}

TARGET JOB:
Title:    {title}
Company:  {company}
Description:
{description}

INSTRUCTIONS:
1. Select the 3–4 most relevant PROJECTS (from the projects array). Rank by fit.
2. Select the most relevant EXPERIENCE bullets. If the experience is not relevant
   to this specific role, you may reduce it to 1 bullet or omit it.
3. For each selected project/experience bullet, REWRITE it to:
   - Use keywords and phrases from the job description naturally
   - Lead with the most impressive quantifiable impact
   - Keep all numbers/percentages/data points from the original
   - Do NOT add new skills, tools, or achievements not in the original
4. Select which SKILLS subcategories to emphasize (reorder, but keep all 3 groups)
5. Write a 2-line SUMMARY tailored to this role (based only on what's in the resume)

Return ONLY valid JSON, no markdown fences, matching this exact structure:
{{
  "summary": "<2-line professional summary for this role>",
  "skills": {{
    "data_visualization": ["<tool1>", "<tool2>"],
    "programming": ["<lang1>", "<lang2>"],
    "tools_and_methods": ["<tool1>", "<tool2>"]
  }},
  "projects": [
    {{
      "id": "<original project id>",
      "title": "<original title>",
      "date": "<original date>",
      "bullets": ["<rewritten bullet 1>", "<rewritten bullet 2>"]
    }}
  ],
  "experience": [
    {{
      "id": "<original experience id>",
      "title": "<original title>",
      "company": "<original company>",
      "dates": "<original dates>",
      "bullets": ["<rewritten bullet 1>"]
    }}
  ]
}}
"""

# ── Tailor one job ────────────────────────────────────────────

def tailor_resume_for_job(job: Dict, master_resume: Dict) -> Optional[Dict]:
    """
    Ask Gemini to produce a tailored resume JSON for this specific job.
    Returns the tailored dict or None on failure.
    """
    # Compress master resume for the prompt (keeps tokens low)
    compact_resume = {
        "personal": master_resume.get("personal", {}),
        "education": master_resume.get("education", []),
        "skills": master_resume.get("skills", {}),
        "projects": [
            {
                "id": p["id"],
                "title": p["title"],
                "date": p["date"],
                "tags": p["tags"],
                "bullets": p["bullets"],
            }
            for p in master_resume.get("projects", [])
        ],
        "experience": master_resume.get("experience", []),
    }

    prompt = TAILOR_PROMPT.format(
        master_resume_json=json.dumps(compact_resume, indent=2),
        title=job["title"],
        company=job["company"],
        description=job["description"][:2000],
    )

    result = call_gemini_json(prompt, temperature=0.2, max_tokens=2500)
    return result


# ── Node.js docx generator ────────────────────────────────────

GENERATE_SCRIPT = Path("scripts/generate_resume.js")


def generate_docx(tailored_data: Dict, personal: Dict, education: List, output_path: str) -> bool:
    """
    Calls the Node.js resume generator script with the tailored JSON.
    Returns True on success.
    """
    if not GENERATE_SCRIPT.exists():
        logger.error(f"generate_resume.js not found at {GENERATE_SCRIPT}")
        return False

    import os as _os
    abs_output = _os.path.abspath(output_path)

    payload = {
        "personal": personal,
        "education": education,
        "tailored": tailored_data,
        "output_path": abs_output,    # absolute path so Node writes to right place
    }

    payload_str = json.dumps(payload)

    try:
        result = subprocess.run(
            ["node", GENERATE_SCRIPT.name],
            input=payload_str,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(GENERATE_SCRIPT.parent),  # Run from scripts/ so node_modules is found
        )
        if result.returncode != 0:
            logger.error(f"Node.js resume gen failed:\n{result.stderr[:500]}")
            return False
        logger.info(f"  ✓ Resume generated: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Node.js call error: {e}")
        return False


def safe_filename(text: str) -> str:
    """Convert to a safe filename fragment."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:30]


# ── Main orchestrator ─────────────────────────────────────────

class ResumeTailor:
    def __init__(self):
        with open("data/master_resume.json") as f:
            self.master = json.load(f)

        Path("resumes").mkdir(exist_ok=True)

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("RESUME TAILOR — starting")
        logger.info("═" * 60)

        top_path = Path("data/top_jobs.json")
        if not top_path.exists():
            logger.error("data/top_jobs.json not found — run Module 2 first")
            return {}

        with open(top_path) as f:
            top_data = json.load(f)

        top_jobs: List[Dict] = top_data.get("top_jobs", [])
        logger.info(f"Tailoring resumes for {len(top_jobs)} jobs...")

        personal = self.master.get("personal", {})
        education = self.master.get("education", [])

        success_count = 0

        for i, job in enumerate(top_jobs, 1):
            company_safe = safe_filename(job["company"])
            title_safe = safe_filename(job["title"])
            filename = f"resumes/{job['id']}_{company_safe}_{title_safe}.docx"

            logger.info(f"\n  [{i}/{len(top_jobs)}] {job['company']} — {job['title']}")
            logger.info(f"  Score: {job['relevance_score']} | {job.get('match_reason','')}")

            # Skip if already generated (re-run protection)
            if Path(filename).exists():
                logger.info(f"  ↩ Resume already exists, skipping")
                job["resume_path"] = filename
                continue

            # Step 1: Gemini tailors the content
            tailored = tailor_resume_for_job(job, self.master)
            if tailored is None:
                logger.warning(f"  ✗ Tailoring failed — using untailored resume")
                # Fallback: use master resume content as-is
                tailored = {
                    "summary": f"MS Business Analytics student seeking {job['title']} at {job['company']}.",
                    "skills": self.master.get("skills", {}),
                    "projects": [
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "date": p["date"],
                            "bullets": p["bullets"],
                        }
                        for p in self.master.get("projects", [])[:4]
                    ],
                    "experience": self.master.get("experience", []),
                }

            # Step 2: Node.js generates the .docx
            ok = generate_docx(tailored, personal, education, filename)
            if ok:
                job["resume_path"] = filename
                job["resume_tailored"] = True
                success_count += 1
            else:
                job["resume_path"] = None
                job["resume_tailored"] = False

            # Pace Gemini calls: 4.5s gap → safe at 15 req/min
            time.sleep(4.5)

        # Persist updated top_jobs with resume paths
        with open(top_path, "w") as f:
            json.dump(top_data, f, indent=2, default=str)

        logger.info("\n" + "═" * 60)
        logger.info(f"DONE — {success_count}/{len(top_jobs)} resumes generated")
        logger.info("═" * 60)

        return {"success": success_count, "total": len(top_jobs)}
