# Job Hunter — Complete Setup Guide
### Full Pipeline: Modules 1–6

---

## What Runs Each Day at 7 AM

```
Module 1 → Fetch jobs        (Greenhouse + Lever + JSearch + Adzuna)
Module 2 → Score & rank      (Gemini scores each job vs. your profile)
Module 3 → Tailor resumes    (Gemini rewrites bullets per JD → .docx)
Module 4 → Match connections (cross-reference your LinkedIn CSV)
Module 5 → Notify you        (GitHub Pages dashboard + Gmail digest)
Module 6 → Learn             (improves future searches from your feedback)
```

Estimated run time: ~8–12 minutes depending on number of jobs found.

---

## One-Time Setup (~30 minutes total)

### Step 1 — Free API Keys (15 min)

Get all 4 keys. All are free tier.

| Service | Link | Free Tier | Used By |
|---|---|---|---|
| **JSearch** (RapidAPI) | https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch | 200 req/month | Module 1 |
| **Adzuna** | https://developer.adzuna.com/ | 1,000 req/month | Module 1 |
| **Google Gemini** | https://aistudio.google.com/app/apikey | 1,500 req/day | Modules 2 & 3 |
| **Gmail App Password** | myaccount.google.com → Security → App Passwords | Free | Module 5 |

> **Gmail App Password:** Turn on 2-Step Verification first, then create an App Password named "Job Hunter". You'll get a 16-character code — that's your password. Do NOT use your real Gmail password.

---

### Step 2 — GitHub Repository (5 min)

1. Go to https://github.com/new
2. Create a **private** repo named `job-hunter`
3. On your computer, open Terminal:

```bash
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
# Copy all project files into this folder
git add .
git commit -m "Initial setup"
git push origin main
```

---

### Step 3 — GitHub Secrets (5 min)

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these 6 secrets:

| Secret Name | Where to get it |
|---|---|
| `JSEARCH_API_KEY` | RapidAPI dashboard |
| `ADZUNA_APP_ID` | Adzuna developer dashboard |
| `ADZUNA_APP_KEY` | Adzuna developer dashboard |
| `GEMINI_API_KEY` | Google AI Studio |
| `GMAIL_ADDRESS` | Your Gmail address (ahrar@bu.edu) |
| `GMAIL_APP_PASSWORD` | The 16-char App Password you created |

---

### Step 4 — Enable GitHub Pages (2 min)

1. Go to your repo → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` | Folder: `/docs`
4. Click **Save**

Your dashboard URL will be:
`https://YOUR_USERNAME.github.io/job-hunter/`

It goes live after the first automated run.

---

### Step 5 — Install Node.js `docx` Package Locally (for testing)

```bash
npm install -g docx
```

This runs automatically in GitHub Actions. Only needed locally if you want to test resume generation on your machine.

---

### Step 6 — Test the Full Pipeline Locally (optional but recommended)

```bash
cd job-hunter
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Open .env in any text editor and fill in your keys

# Run the pipeline
python main.py
```

Expected output after ~8 minutes:
```
▶ MODULE 1 — Job Fetcher
   ✓ 23 viable jobs | 3 CPT-flagged excluded
▶ MODULE 2 — Relevance Scorer
   ✓ Top 20 jobs selected from 23 scored
▶ MODULE 3 — Resume Tailor
   ✓ 20/20 resumes generated
▶ MODULE 4 — LinkedIn Matcher
   ✓ 4 jobs with connections found
▶ MODULE 5a — Dashboard Generator
   ✓ Dashboard written to docs/index.html
▶ MODULE 5b — Email Digest
   ✓ Email sent (20 jobs)
▶ MODULE 6 — Learning Loop
   ✓ 0 applied | 0 saved | 0 skipped

Top 5 Today:
  🟢 🔗 [88] Google               Data Analyst Intern
  🟡    [82] Microsoft            Business Analyst Intern
  🟢    [79] OpenAI               Strategy Intern
  🟡 🔗 [74] DoorDash             Operations Analyst Intern
  🟡    [71] Meta                 Marketing Analyst Intern
```

---

### Step 7 — Enable the Daily Schedule

1. GitHub repo → **Actions** tab
2. Click **"Daily Job Hunter"** → **"Enable workflow"**
3. To test immediately: click **"Run workflow"** → **"Run workflow"**

The schedule is set to `0 12 * * *` (12:00 UTC = 7:00 AM EST).
To change the time, edit `.github/workflows/daily_run.yml` line 7.

---

## Daily Usage

### Your Morning Routine (5 minutes)
1. Open the email digest in your inbox
2. Review jobs highlighted with 🔗 (connections) first — reach out for referrals
3. Click "Apply Now" links → your tailored resume is in the `resumes/` folder
4. Open the dashboard to mark jobs as Applied / Saved / Skip

### Dashboard Features
- **Filter buttons**: All | Connections | CPT ✓ | New Only
- **Sort**: by Relevance, Connections First, or CPT Friendly First  
- **Apply / Save / Skip** buttons → stored in your browser, fed back into the learning loop

### CPT Signal Guide
| Badge | Meaning | Action |
|---|---|---|
| 🟢 CPT Friendly | JD explicitly mentions CPT/OPT/F-1 | Apply with confidence |
| 🟡 CPT Unconfirmed | No mention either way | Check JD manually before applying |
| 🔴 No Sponsorship | Explicitly says "no sponsorship" | Auto-excluded from your list |

---

## Updating Your Setup

### Update your resume
Edit `data/master_resume.json` whenever you update your resume.
This is the single source of truth — all tailored resumes come from it.

### Add new target companies
Edit `config/target_companies.json`.

To check if a company uses Greenhouse ATS:
```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/COMPANY_NAME/jobs" | python -m json.tool | head -5
```
If it returns jobs, add to the `greenhouse` section. Otherwise add to `general`.

### Add/remove job titles
Edit `config/job_titles.json`. The learning loop will also auto-add titles
that appear repeatedly in jobs you apply to.

### Update LinkedIn connections
1. LinkedIn → Settings → Data Privacy → Get a copy of your data → Connections
2. Download the CSV
3. Save as `data/linkedin_connections.csv` in your repo

---

## Project File Map

```
job-hunter/
│
├── main.py                          ← Orchestrator (runs all modules)
│
├── modules/
│   ├── job_fetcher.py               ← Module 1: fetch from APIs + ATS
│   ├── relevance_scorer.py          ← Module 2: Gemini scores each job
│   ├── resume_tailor.py             ← Module 3: Gemini tailors resume
│   ├── linkedin_matcher.py          ← Module 4: CSV connection lookup
│   ├── email_digest.py              ← Module 5b: Gmail HTML digest
│   ├── dashboard_generator.py       ← Module 5a: GitHub Pages dashboard
│   ├── learning_loop.py             ← Module 6: feedback → better searches
│   └── gemini_helper.py             ← Shared Gemini API wrapper
│
├── scripts/
│   └── generate_resume.js           ← Node.js .docx builder
│
├── config/
│   ├── settings.json                ← Your profile + schedule settings
│   ├── job_titles.json              ← Target role titles (auto-updated)
│   └── target_companies.json        ← Company list with ATS routing
│
├── data/
│   ├── master_resume.json           ← Your master resume (update this)
│   ├── raw_jobs.json                ← Module 1 output (all fetched jobs)
│   ├── top_jobs.json                ← Module 2 output (ranked top 20)
│   ├── seen_jobs.json               ← Dedup history (never show same job twice)
│   ├── feedback_history.json        ← Your apply/save/skip history
│   ├── learning_profile.json        ← Module 6 output (derived weights)
│   └── linkedin_connections.csv     ← YOUR EXPORT (add manually)
│
├── resumes/                         ← Tailored .docx resumes (auto-generated)
│
├── docs/
│   └── index.html                   ← Dashboard (auto-generated, served by GitHub Pages)
│
├── .github/workflows/
│   └── daily_run.yml                ← GitHub Actions daily scheduler
│
├── requirements.txt
├── .env.example                     ← Copy to .env locally (never commit .env)
└── .gitignore
```

---

## Troubleshooting

| Issue | Likely cause | Fix |
|---|---|---|
| No jobs found | Too early in season / narrow queries | Normal before Jan 2026; broaden dates |
| Gemini scoring fails | API key wrong or rate limited | Check `GEMINI_API_KEY` secret |
| No resumes generated | Node.js or `docx` not installed | Add `npm install -g docx` to workflow |
| Email not received | Gmail credentials wrong | Recreate App Password; check spam |
| Dashboard shows placeholder | First run hasn't triggered yet | Click "Run workflow" manually |
| LinkedIn CSV not matching | Column name differs | Open CSV and check exact column headers |

---

## API Usage Summary (per day)

| Service | Calls Used | Free Limit | Safety Margin |
|---|---|---|---|
| JSearch | 5 | 7/day (200/month) | Comfortable |
| Adzuna | 15 | 33/day (1,000/month) | Comfortable |
| Gemini (scoring) | ~25 | 1,500/day | Large margin |
| Gemini (tailoring) | ~20 | 1,500/day | Large margin |
| Greenhouse/Lever | Unlimited | Free, no key | No limit |
| Gmail SMTP | 1 | 500/day | No concern |
