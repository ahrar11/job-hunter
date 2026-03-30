"""
Module 5a: Email Digest
──────────────────────────────────────────────────────────────
Reads:   data/top_jobs.json
Sends:   A rich HTML email via Gmail SMTP (free, app password)

Each job card shows:
  - Title, company, location, score, CPT signal
  - LinkedIn connection flag
  - Direct apply link
  - Top skill matches
  - Tailored resume path (if generated)
──────────────────────────────────────────────────────────────
"""

import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── Color tokens ───────────────────────────────────────────────
BRAND      = "#2E5FA3"
BRAND_DARK = "#1A1A2E"
GREEN      = "#27ae60"
YELLOW     = "#f39c12"
RED        = "#e74c3c"
GRAY_BG    = "#f4f6f9"
CARD_BG    = "#ffffff"
TEXT       = "#2d2d2d"
MUTED      = "#6c757d"

# ── HTML helpers ───────────────────────────────────────────────

def cpt_badge(signal: str) -> str:
    config = {
        "positive": (GREEN,  "✓ CPT Friendly"),
        "neutral":  (YELLOW, "? CPT Unconfirmed"),
        "negative": (RED,    "✗ No Sponsorship"),
    }
    color, label = config.get(signal, (GRAY_BG, "Unknown"))
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:11px;font-weight:600">{label}</span>'
    )


def connection_badge(flag: str, connections: List[Dict]) -> str:
    if flag == "1st_degree":
        names = ", ".join(c["name"] for c in connections[:2])
        extra = f" +{len(connections)-2}" if len(connections) > 2 else ""
        return (
            f'<span style="background:{GREEN};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:11px;font-weight:600">'
            f'🔗 1st Degree: {names}{extra}</span>'
        )
    elif flag == "possible_2nd":
        return (
            f'<span style="background:{YELLOW};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:11px;font-weight:600">'
            f'🔗 Possible Connection</span>'
        )
    return (
        f'<span style="background:#dee2e6;color:{MUTED};padding:2px 8px;'
        f'border-radius:4px;font-size:11px">No Connection Found</span>'
    )


def score_bar(score: int) -> str:
    """Mini horizontal score bar."""
    pct = max(0, min(100, score))
    color = GREEN if pct >= 75 else YELLOW if pct >= 55 else RED
    return (
        f'<div style="display:inline-block;width:80px;height:8px;'
        f'background:#e9ecef;border-radius:4px;vertical-align:middle;margin-right:6px">'
        f'<div style="width:{pct}%;height:100%;background:{color};border-radius:4px"></div>'
        f'</div>'
        f'<span style="font-size:12px;color:{MUTED};font-weight:600">{pct}/100</span>'
    )


def job_card(job: Dict, rank: int) -> str:
    title    = job.get("title", "")
    company  = job.get("company", "")
    location = job.get("location", "Not specified")
    url      = job.get("apply_url", "#")
    source   = job.get("source", "")
    score    = job.get("relevance_score", 0)
    cpt      = job.get("cpt_signal", "neutral")
    conn_flag = job.get("connection_flag", "none")
    connections = job.get("connections", [])
    match_reason = job.get("match_reason", "")
    skill_matches = job.get("skill_matches", [])
    concern      = job.get("concern", "")
    posted_at    = job.get("posted_at", "")
    resume_path  = job.get("resume_path", None)

    posted_str = ""
    if posted_at:
        try:
            dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            posted_str = f" · Posted {dt.strftime('%b %d')}"
        except Exception:
            pass

    skills_html = ""
    if skill_matches:
        pills = "".join(
            f'<span style="background:#e8f0fe;color:{BRAND};padding:2px 7px;'
            f'border-radius:3px;font-size:11px;margin-right:4px">{s}</span>'
            for s in skill_matches[:6]
        )
        skills_html = f'<div style="margin-top:8px">{pills}</div>'

    concern_html = ""
    if concern:
        concern_html = (
            f'<div style="margin-top:6px;font-size:12px;color:{MUTED}">'
            f'⚠ {concern}</div>'
        )

    resume_html = ""
    if resume_path:
        resume_html = (
            f'<div style="margin-top:6px;font-size:12px;color:{GREEN}">'
            f'📄 Tailored resume generated: {Path(resume_path).name}</div>'
        )

    # Determine border color by connection
    border_color = GREEN if conn_flag in ("1st_degree", "possible_2nd") else "#e0e0e0"

    return f"""
    <div style="background:{CARD_BG};border-radius:8px;padding:18px 20px;
                margin-bottom:16px;border-left:4px solid {border_color};
                box-shadow:0 1px 3px rgba(0,0,0,.08)">

      <!-- Rank + title row -->
      <div style="display:flex;align-items:flex-start;justify-content:space-between">
        <div>
          <span style="color:{MUTED};font-size:12px;font-weight:600">#{rank}</span>
          <span style="margin-left:8px;font-size:17px;font-weight:700;color:{BRAND_DARK}">{title}</span>
        </div>
        <div>{score_bar(score)}</div>
      </div>

      <!-- Company + meta -->
      <div style="margin-top:4px;font-size:13px;color:{MUTED}">
        <strong style="color:{TEXT}">{company}</strong>
        &nbsp;·&nbsp;{location}{posted_str}
        &nbsp;·&nbsp;<span style="font-size:11px">via {source}</span>
      </div>

      <!-- Badges -->
      <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
        {cpt_badge(cpt)}
        {connection_badge(conn_flag, connections)}
      </div>

      <!-- Match reason -->
      {"" if not match_reason else f'<div style="margin-top:10px;font-size:13px;color:{TEXT};font-style:italic">"{match_reason}"</div>'}

      <!-- Skill matches -->
      {skills_html}

      <!-- Concern -->
      {concern_html}

      <!-- Resume -->
      {resume_html}

      <!-- CTA -->
      <div style="margin-top:14px">
        <a href="{url}"
           style="background:{BRAND};color:#fff;padding:7px 16px;border-radius:5px;
                  text-decoration:none;font-size:13px;font-weight:600">
          Apply Now →
        </a>
        <span style="margin-left:12px;font-size:12px;color:{MUTED}">{url[:60]}{'...' if len(url)>60 else ''}</span>
      </div>
    </div>
    """


def build_html_email(top_jobs: List[Dict], run_date: str, stats: Dict) -> str:
    """Build the full HTML email body."""
    date_str = ""
    try:
        dt = datetime.fromisoformat(run_date.replace("Z", "+00:00"))
        date_str = dt.strftime("%A, %B %d %Y")
    except Exception:
        date_str = run_date

    connected_jobs  = [j for j in top_jobs if j.get("connection_flag") != "none"]
    cpt_positive    = [j for j in top_jobs if j.get("cpt_signal") == "positive"]

    # Sort: connections first, then by score
    sorted_jobs = sorted(top_jobs, key=lambda j: (
        0 if j.get("connection_flag") == "1st_degree" else
        1 if j.get("connection_flag") == "possible_2nd" else 2,
        -(j.get("relevance_score") or 0)
    ))

    cards_html = "".join(job_card(job, i+1) for i, job in enumerate(sorted_jobs))

    summary_pills = f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px">
      <div style="background:{BRAND};color:#fff;padding:8px 16px;border-radius:6px;text-align:center">
        <div style="font-size:22px;font-weight:700">{len(top_jobs)}</div>
        <div style="font-size:11px;margin-top:2px">New Roles</div>
      </div>
      <div style="background:{GREEN};color:#fff;padding:8px 16px;border-radius:6px;text-align:center">
        <div style="font-size:22px;font-weight:700">{len(connected_jobs)}</div>
        <div style="font-size:11px;margin-top:2px">With Connections</div>
      </div>
      <div style="background:{YELLOW};color:#fff;padding:8px 16px;border-radius:6px;text-align:center">
        <div style="font-size:22px;font-weight:700">{len(cpt_positive)}</div>
        <div style="font-size:11px;margin-top:2px">CPT Confirmed</div>
      </div>
    </div>
    """

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{GRAY_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
  <div style="max-width:680px;margin:24px auto;padding:0 12px">

    <!-- Header -->
    <div style="background:{BRAND_DARK};border-radius:10px 10px 0 0;padding:24px 28px">
      <div style="color:#fff;font-size:22px;font-weight:700">🎯 Job Hunter Daily Digest</div>
      <div style="color:#aab4d0;font-size:13px;margin-top:4px">{date_str} · Ahrar Karim · Boston University MSBA</div>
      {summary_pills}
    </div>

    <!-- Body -->
    <div style="background:{GRAY_BG};padding:20px 4px">

      {"" if not connected_jobs else
        f'<div style="color:{BRAND_DARK};font-size:13px;font-weight:700;margin-bottom:12px;padding:0 4px">'
        f'🔗 Roles with LinkedIn connections are listed first — consider reaching out for referrals!'
        f'</div>'}

      {cards_html}

    </div>

    <!-- Footer -->
    <div style="background:{BRAND_DARK};border-radius:0 0 10px 10px;padding:16px 28px;
                color:#aab4d0;font-size:12px;text-align:center">
      Automated by Job Hunter Bot · Runs daily at 7AM EST<br>
      Update feedback in your dashboard to improve future results.
    </div>

  </div>
</body>
</html>
"""


# ── Sender ─────────────────────────────────────────────────────

class EmailDigest:
    def __init__(self, config_dir: str = "config"):
        with open(f"{config_dir}/settings.json") as f:
            settings = json.load(f)
        self.email_cfg = settings.get("email", {})
        self.to_addr   = self.email_cfg.get("to", "")
        self.from_addr = os.environ.get("GMAIL_ADDRESS", self.email_cfg.get("from", ""))
        self.app_pass  = os.environ.get("GMAIL_APP_PASSWORD", "")
        self.prefix    = self.email_cfg.get("subject_prefix", "[Job Hunter]")

    def send(self, html: str, subject: str) -> bool:
        if not self.from_addr or not self.app_pass:
            logger.warning("Gmail credentials not set — skipping email send")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.from_addr
        msg["To"]      = self.to_addr
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.from_addr, self.app_pass)
                server.sendmail(self.from_addr, self.to_addr, msg.as_string())
            logger.info(f"  ✓ Email sent to {self.to_addr}")
            return True
        except Exception as e:
            logger.error(f"  ✗ Email send failed: {e}")
            return False

    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("EMAIL DIGEST — starting")
        logger.info("═" * 60)

        top_path = Path("data/top_jobs.json")
        if not top_path.exists():
            logger.error("data/top_jobs.json not found")
            return {}

        with open(top_path) as f:
            top_data = json.load(f)

        top_jobs = top_data.get("top_jobs", [])
        run_date = top_data.get("run_date", "")

        if not top_jobs:
            logger.info("No jobs to send — skipping email")
            return {"sent": False, "reason": "no_jobs"}

        stats = {
            "total": len(top_jobs),
            "connected": sum(1 for j in top_jobs if j.get("connection_flag") != "none"),
            "cpt_positive": sum(1 for j in top_jobs if j.get("cpt_signal") == "positive"),
        }

        html = build_html_email(top_jobs, run_date, stats)

        # Save HTML for dashboard too
        html_path = Path("data/digest.html")
        with open(html_path, "w") as f:
            f.write(html)
        logger.info(f"  Digest HTML saved to {html_path}")

        # Format subject
        top_score = max((j.get("relevance_score", 0) for j in top_jobs), default=0)
        top_company = next(
            (j["company"] for j in sorted(top_jobs, key=lambda x: x.get("relevance_score", 0), reverse=True)),
            ""
        )
        connected = stats["connected"]
        subject = (
            f"{self.prefix} {len(top_jobs)} new internships"
            f"{f' · {connected} connections' if connected else ''}"
            f"{f' · Top: {top_company} ({top_score})' if top_company else ''}"
        )

        ok = self.send(html, subject)

        logger.info("═" * 60)
        logger.info(f"DONE — email {'sent' if ok else 'skipped (check credentials)'}")
        logger.info("═" * 60)

        return {"sent": ok, "jobs_count": len(top_jobs), **stats}
