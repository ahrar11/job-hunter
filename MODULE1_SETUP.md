# Job Hunter — Module 1 Setup Guide
### "Job Fetcher" | Sources: Greenhouse · Lever · JSearch · Adzuna

---

## What This Module Does

Every day at 7 AM EST it:
1. Scrapes **Greenhouse & Lever** ATS job boards for your target companies (free, no key needed)
2. Queries **JSearch** (via RapidAPI) for broad internship searches (5 queries/day)
3. Queries **Adzuna** for targeted title + company searches (15 queries/day)
4. Filters results: internship roles only, CPT-negative excluded, deduplicates against past runs
5. Writes `data/raw_jobs.json` with all viable roles + metadata

---

## Step 1 — Get Your Free API Keys (15 minutes)

### A. JSearch (RapidAPI) — 200 requests/month free
1. Go to https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
2. Click **"Subscribe to Test"** → choose the **Basic (Free)** plan
3. Copy your API key from the dashboard (under "X-RapidAPI-Key")

### B. Adzuna — 1,000 requests/month free
1. Go to https://developer.adzuna.com/
2. Click **"Register"** → create a free account
3. Go to your dashboard → **"Create App"**
4. Copy your **App ID** and **App Key**

### C. Google Gemini — 1,500 requests/day free (needed for Module 3)
1. Go to https://aistudio.google.com/app/apikey
2. Click **"Create API Key"**
3. Save it — you'll need this for Module 3 (resume tailoring)

---

## Step 2 — Set Up the GitHub Repository (10 minutes)

1. Go to https://github.com/new
2. Create a **private** repository named `job-hunter`
3. On your computer, open Terminal and run:

```bash
cd ~/Desktop          # or wherever you want the folder
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
```

4. Copy all the project files into this folder (drag & drop from wherever you saved them, or unzip the project folder)

5. Push to GitHub:
```bash
git add .
git commit -m "Initial setup"
git push origin main
```

---

## Step 3 — Add API Keys as GitHub Secrets (5 minutes)

Your API keys must NEVER go in the code files. GitHub Secrets keeps them safe.

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"** and add each of the following:

| Secret Name | Value |
|---|---|
| `JSEARCH_API_KEY` | Your RapidAPI key |
| `ADZUNA_APP_ID` | Your Adzuna App ID |
| `ADZUNA_APP_KEY` | Your Adzuna App Key |
| `GEMINI_API_KEY` | Your Gemini key (for Module 3) |
| `GMAIL_ADDRESS` | ahrar@bu.edu |
| `GMAIL_APP_PASSWORD` | Your Gmail app password (see note below) |

> **Gmail App Password:** Go to myaccount.google.com → Security → 2-Step Verification → App Passwords. Create one named "Job Hunter". Use that 16-character password here — NOT your real Gmail password.

---

## Step 4 — Configure Your Target Companies

Open `config/target_companies.json` and customize:

- **`greenhouse`** section: Companies using Greenhouse ATS. To verify a company uses Greenhouse, visit `https://boards.greenhouse.io/{company_name}` (e.g., `boards.greenhouse.io/openai`). If it loads with job listings, add it.
- **`lever`** section: Companies using Lever. Visit `https://jobs.lever.co/{company_slug}` to verify.
- **`general`** section: All other companies. These are searched via JSearch/Adzuna.

**Your provided company list has been pre-filled.** Here's how each was routed:

| Company | Route | Why |
|---|---|---|
| OpenAI | Greenhouse API | Uses Greenhouse (boards.greenhouse.io/openai) |
| DoorDash | Greenhouse API | Uses Greenhouse |
| Zipline | Lever API | Uses Lever (jobs.lever.co/flyzipline) |
| Microsoft | General (JSearch/Adzuna) | Uses Workday — no free API |
| Google | General (JSearch/Adzuna) | Custom ATS |
| Meta | General (JSearch/Adzuna) | Custom ATS |
| ByteDance/TikTok | General (JSearch/Adzuna) | Custom ATS |
| eBay | General (JSearch/Adzuna) | Uses Workday |

---

## Step 5 — Run It Manually to Test (2 minutes)

Before scheduling, test locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Create your .env file from the template
cp .env.example .env
# Open .env and fill in your keys

# Load env and run
python -m dotenv run python main.py
```

Expected output:
```
[INFO] JOB HUNTER — DAILY RUN START
[INFO] MODULE 1: Fetching jobs...
[INFO] ✓ Greenhouse [OpenAI]: 3 matching roles
[INFO] ✓ Greenhouse [DoorDash]: 1 matching roles
[INFO] ✓ Lever [Zipline]: 2 matching roles
[INFO] ✓ JSearch [...]: 7 matching roles
[INFO] ✓ Adzuna [...]: 5 matching roles
[INFO] DONE — 18 viable jobs | 2 CPT-flagged | 23 total fetched
```

Results are written to `data/raw_jobs.json`.

---

## Step 6 — Enable the Daily Schedule

1. On GitHub, go to your repo → **Actions** tab
2. You should see "Daily Job Hunter" workflow listed
3. Click it → click **"Enable workflow"**
4. To run it immediately, click **"Run workflow"** → **"Run workflow"**

It will now run automatically every day at **7:00 AM EST**.

To change the time, edit `.github/workflows/daily_run.yml`:
```yaml
- cron: "0 12 * * *"   # 12:00 UTC = 7:00 AM EST (12:00 - 5:00)
                        # 13:00 UTC = 8:00 AM EST
                        # 14:00 UTC = 9:00 AM EST
```

---

## Understanding `data/raw_jobs.json`

After each run, check this file to see what was found:

```json
{
  "run_date": "2026-03-30T12:00:00+00:00",
  "stats": {
    "total_fetched": 23,
    "new_unique": 18,
    "viable": 16,
    "cpt_flagged": 2
  },
  "viable_jobs": [
    {
      "id": "abc123def456",
      "title": "Business Analyst Intern",
      "company": "Google",
      "location": "Mountain View, CA",
      "apply_url": "https://careers.google.com/jobs/...",
      "cpt_signal": "neutral",     // neutral = no explicit mention
      "summer_2026_mentioned": true,
      "source": "jsearch",
      ...
    }
  ],
  "cpt_flagged_jobs": [...]          // Roles excluded (said "no sponsorship")
}
```

**CPT Signal key:**
- 🟢 `positive` — explicitly says CPT/OPT friendly → apply with confidence
- 🟡 `neutral` — no mention either way → verify manually before applying  
- 🔴 `negative` — says "no sponsorship" → excluded automatically

---

## Updating Your Company List

Add new companies anytime by editing `config/target_companies.json`:

```bash
# Quick check if company uses Greenhouse:
curl -s "https://boards-api.greenhouse.io/v1/boards/COMPANY_NAME/jobs" | python -m json.tool | head -20

# Quick check if company uses Lever:
curl -s "https://api.lever.co/v0/postings/COMPANY_SLUG?mode=json" | python -m json.tool | head -20
```

If both return errors, add the company to the `general` list.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `JSEARCH_API_KEY not set` | Add secret to GitHub or `.env` locally |
| `Greenhouse 404` | The board token is wrong — re-verify at boards.greenhouse.io |
| `0 jobs found` | Try running a wider date range; summer 2026 roles may not be posted yet |
| `rate limit error` | You've hit the free tier limit — wait until next month or upgrade |

---

## What's Next

Once you confirm Module 1 is working and finding jobs, we'll build:

- **Module 2** — Gemini API scores each job against your profile, picks top 15–20
- **Module 3** — Auto-tailors your resume per job description (no fabrication)
- **Module 4** — Cross-references your LinkedIn connections CSV
- **Module 5** — Builds the GitHub Pages dashboard + sends your email digest
- **Module 6** — Learns from your apply/skip feedback to improve future runs
