# Job Hunter — Complete Setup Guide
### All 6 Modules | ~45 minutes to set up | $0/month

---

## Overview

This system runs fully automatically every morning and:

1. **Fetches** internships from Greenhouse ATS, Lever ATS, JSearch, and Adzuna
2. **Scores** each role against your profile using Gemini AI
3. **Tailors** your resume per job description (no fabrication)
4. **Flags** roles where you have LinkedIn connections
5. **Sends** you an email digest + updates a live dashboard
6. **Learns** from your apply/skip feedback to improve over time

---

## Step 1 — Get Your Free API Keys (15 min)

Get each of these — all are free with no credit card required:

### A. JSearch (RapidAPI) — broad job search
1. Visit https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
2. Click **Subscribe to Test** → choose **Basic (Free)**
3. Copy the key shown under `X-RapidAPI-Key`

### B. Adzuna — additional job source
1. Visit https://developer.adzuna.com and register
2. Dashboard → **Create App** → copy **App ID** and **App Key**

### C. Google Gemini — AI scoring + resume tailoring
1. Visit https://aistudio.google.com/app/apikey
2. Click **Create API Key** → copy it
3. Free tier: 1,500 requests/day — more than enough

### D. Gmail App Password — email digest
1. Go to https://myaccount.google.com → Security → 2-Step Verification
2. Scroll down to **App Passwords** → Create one named "Job Hunter"
3. Copy the 16-character password (not your real Gmail password)

---

## Step 2 — Create Your GitHub Repository (10 min)

1. Go to https://github.com/new
2. Name it `job-hunter`, set to **Private**, click **Create repository**
3. On your computer, open Terminal:

```bash
# Navigate to where you want the project
cd ~/Desktop

# Clone your new empty repo
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
```

4. Copy all the project files from this download into the `job-hunter` folder
5. Push everything up:

```bash
git add .
git commit -m "Initial setup — Job Hunter"
git push origin main
```

---

## Step 3 — Add API Keys as GitHub Secrets (5 min)

**Never put API keys in code files.** GitHub Secrets keeps them safe and injects them at runtime.

1. Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each:

| Secret Name | Where to find it |
|---|---|
| `JSEARCH_API_KEY` | RapidAPI dashboard |
| `ADZUNA_APP_ID` | Adzuna developer dashboard |
| `ADZUNA_APP_KEY` | Adzuna developer dashboard |
| `GEMINI_API_KEY` | Google AI Studio |
| `GMAIL_ADDRESS` | Your Gmail address (e.g. ahrar@bu.edu) |
| `GMAIL_APP_PASSWORD` | The 16-char app password from Step 1D |

---

## Step 4 — Enable GitHub Pages for the Dashboard (3 min)

1. Go to your repo → **Settings** → **Pages**
2. Under **Source**, select **Deploy from a branch**
3. Branch: `main` | Folder: `/docs` → click **Save**
4. Your dashboard will be live at:
   `https://YOUR_USERNAME.github.io/job-hunter/`

After the first automated run, the dashboard will populate with real job cards.

---

## Step 5 — Export Your LinkedIn Connections (5 min)

Do this now and repeat weekly for best results.

1. Go to https://linkedin.com → **Me** (top right) → **Settings & Privacy**
2. **Data Privacy** → **Get a copy of your data**
3. Select **Connections only** → **Request archive**
4. Wait ~10 minutes, download the ZIP, extract it
5. Find the file named `Connections.csv`
6. Save it to your project as `data/linkedin_connections.csv`
7. Commit and push:

```bash
git add data/linkedin_connections.csv
git commit -m "Add LinkedIn connections"
git push
```

The matcher will now flag roles where you have 1st-degree connections at the company.

---

## Step 6 — Configure Your Target Companies (5 min)

Open `config/target_companies.json`. Your provided companies have been pre-filled.

To **add more companies**, first check which ATS they use:
```bash
# Check Greenhouse (most common):
curl -s "https://boards-api.greenhouse.io/v1/boards/COMPANY_NAME/jobs" | python -m json.tool | head -5

# Check Lever:
curl -s "https://api.lever.co/v0/postings/COMPANY_SLUG" | python -m json.tool | head -5
```

If the page loads with job data → add to that section (free, direct API, best results).
If not → add company name to the `general` list (searched via JSearch/Adzuna).

---

## Step 7 — Test Locally Before Going Live (5 min)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependency for resume generation
npm install -g docx

# Copy env template and fill in your keys
cp .env.example .env
# Open .env and paste your API keys

# Run the full pipeline
python -m dotenv run python main.py
```

Expected output:
```
JOB HUNTER — DAILY RUN START
▶  MODULE 1 — Job Fetcher
   ✓ 23 viable jobs | 3 CPT-flagged excluded
▶  MODULE 2 — Relevance Scorer
   ✓ Top 20 jobs selected from 23 scored
▶  MODULE 3 — Resume Tailor
   ✓ 20/20 resumes generated
▶  MODULE 4 — LinkedIn Matcher
   ✓ 4 jobs with connections found
▶  MODULE 5a — Dashboard Generator
   ✓ Dashboard written to docs/index.html
▶  MODULE 5b — Email Digest
   ✓ Email sent (20 jobs)
▶  MODULE 6 — Learning Loop
   ✓ 0 applied | 0 saved | 0 skipped

Top 5 Today:
  🟢 🔗 [92] Google              Data Analyst Intern
  🟢    [88] OpenAI              Business Analyst Intern
  🟡 🔗 [85] Meta                Strategy Intern
  🟢    [82] DoorDash            Operations Analyst Intern
  🟡    [79] Microsoft           Business Intelligence Intern
```

---

## Step 8 — Enable Daily Automation (2 min)

1. Go to your repo on GitHub → **Actions** tab
2. You'll see **Daily Job Hunter** listed — click **Enable workflow**
3. Click **Run workflow** → **Run workflow** to trigger an immediate test run
4. Watch it complete in the **Actions** tab (takes ~5–8 minutes)

The workflow runs automatically at **7:00 AM EST** every day.

To change the time, edit `.github/workflows/daily_run.yml`:
```yaml
- cron: "0 12 * * *"   # 12:00 UTC = 7:00 AM EST
                        # 13:00 UTC = 8:00 AM EST
                        # 11:00 UTC = 6:00 AM EST
```

---

## Daily Workflow — What You Do

Each morning:

1. **Check your email** for the digest (arrives ~7:05 AM)
2. **Open your dashboard** at `https://YOUR_USERNAME.github.io/job-hunter/`
3. For each role, click one of:
   - ✓ **Applied** — marks it done, trains the learning loop
   - ⭐ **Save** — bookmark for later
   - ✕ **Skip** — hides it, tells the system to avoid similar roles
4. For 🔗 **flagged roles** — message your connection on LinkedIn before applying

Your feedback is stored locally in the browser and synced to `data/feedback_history.json` on the next GitHub Actions run, which feeds Module 6's learning loop.

---

## Understanding Your Dashboard

| Icon | Meaning |
|---|---|
| 🟢 CPT Friendly | Job explicitly mentions CPT/OPT/F-1 welcome |
| 🟡 CPT Unconfirmed | No mention — verify before applying (most common) |
| 🔴 No Sponsorship | Explicitly excludes sponsorship — auto-filtered out |
| 🔗 1st Degree | You have a direct LinkedIn connection at this company |
| 🔗 Possible Connection | Partial match — worth checking manually |

Score bar shows relevance 0–100 based on your profile match.

---

## Keeping Your Resume Updated

When you update your resume:
1. Open `data/master_resume.json`
2. Edit the relevant bullets/skills/projects
3. Commit and push — the next run will use the updated content

The JSON structure mirrors your resume exactly. Each entry has an `id` field, tags, and bullets. Gemini selects from these — it cannot invent content that isn't in this file.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Module 3 fails with "generate_resume.js not found" | Run `npm install -g docx` on your machine; GitHub Actions does this automatically |
| No jobs found | Summer 2026 postings may not be live yet at some companies; broaden date filters in `config/settings.json` |
| Email not arriving | Check your Gmail App Password in GitHub Secrets; make sure 2-Step Verification is on |
| Dashboard shows placeholder | First automated run hasn't happened yet — trigger manually from Actions tab |
| JSearch rate limit | You've used all 200 free requests for the month; it resets on the 1st |
| LinkedIn CSV not matching | Check column names in your CSV — they sometimes change. Expected: `First Name`, `Last Name`, `Company`, `Position`, `URL` |

---

## File Reference

```
job-hunter/
├── main.py                         ← Runs all modules in sequence
├── requirements.txt                ← Python dependencies
├── .env.example                    ← API key template (copy to .env locally)
├── .gitignore
│
├── config/
│   ├── settings.json               ← Candidate info, schedule, email config
│   ├── job_titles.json             ← Target job titles (auto-updated by Module 6)
│   └── target_companies.json       ← Company list with ATS routing
│
├── data/
│   ├── master_resume.json          ← YOUR RESUME — update this when you update your CV
│   ├── linkedin_connections.csv    ← YOUR CONNECTIONS — re-export weekly
│   ├── raw_jobs.json               ← Module 1 output (all fetched jobs)
│   ├── top_jobs.json               ← Module 2 output (scored + ranked)
│   ├── seen_jobs.json              ← Dedup registry (never shows same job twice)
│   ├── feedback_history.json       ← Your apply/skip signals (feeds learning loop)
│   └── learning_profile.json       ← Module 6 output (query weights)
│
├── modules/
│   ├── job_fetcher.py              ← Module 1
│   ├── gemini_helper.py            ← Shared Gemini API utility
│   ├── relevance_scorer.py         ← Module 2
│   ├── resume_tailor.py            ← Module 3
│   ├── linkedin_matcher.py         ← Module 4
│   ├── email_digest.py             ← Module 5a
│   ├── dashboard_generator.py      ← Module 5b
│   └── learning_loop.py            ← Module 6
│
├── scripts/
│   └── generate_resume.js          ← Node.js .docx generator
│
├── resumes/                        ← Generated tailored resumes (gitignored)
├── docs/
│   └── index.html                  ← GitHub Pages dashboard (auto-generated daily)
│
└── .github/workflows/
    └── daily_run.yml               ← GitHub Actions cron schedule
```
