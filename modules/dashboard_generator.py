"""
Module 5b: Dashboard Generator
──────────────────────────────────────────────────────────────
Reads:   data/top_jobs.json
Reads:   data/feedback_history.json
Writes:  docs/index.html   (GitHub Pages serves from /docs)

The dashboard is a single self-contained HTML file with:
  - Summary stats bar
  - Filterable, sortable job cards
  - Apply / Save / Skip buttons (write back to feedback_history.json
    via a small commit — or locally via localStorage for instant UX)
  - Connection flags + CPT badges
  - Direct apply links
──────────────────────────────────────────────────────────────
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def build_dashboard(top_jobs: List[Dict], run_date: str) -> str:
    """Generate the full single-file HTML dashboard."""

    jobs_json = json.dumps(top_jobs, default=str)

    try:
        dt = datetime.fromisoformat(run_date.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y · %I:%M %p UTC")
    except Exception:
        date_str = run_date

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Hunter Dashboard · Ahrar Karim</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --brand:      #2E5FA3;
    --brand-dark: #1A1A2E;
    --green:      #27ae60;
    --yellow:     #f39c12;
    --red:        #e74c3c;
    --bg:         #f0f2f5;
    --card:       #ffffff;
    --text:       #1a1a2e;
    --muted:      #6c757d;
    --border:     #e0e4ea;
    --radius:     10px;
  }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
          background: var(--bg); color: var(--text); min-height: 100vh; }}

  /* ── Top bar ── */
  header {{ background: var(--brand-dark); color: #fff; padding: 20px 32px;
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
  header h1 {{ font-size: 20px; font-weight: 700; }}
  header .meta {{ font-size: 12px; color: #9aaac8; margin-top: 4px; }}
  .stat-pills {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .pill {{ background: rgba(255,255,255,.1); border-radius: 8px; padding: 8px 14px;
           text-align: center; min-width: 80px; }}
  .pill .num  {{ font-size: 22px; font-weight: 700; }}
  .pill .lbl  {{ font-size: 11px; color: #9aaac8; margin-top: 2px; }}

  /* ── Filters ── */
  .filters {{ background: var(--card); border-bottom: 1px solid var(--border);
              padding: 14px 32px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .filters input {{ flex: 1; min-width: 200px; padding: 8px 14px; border: 1px solid var(--border);
                    border-radius: 6px; font-size: 14px; outline: none; }}
  .filters input:focus {{ border-color: var(--brand); }}
  .filter-btn {{ padding: 7px 14px; border: 1px solid var(--border); background: #fff;
                 border-radius: 6px; font-size: 13px; cursor: pointer; transition: all .15s; }}
  .filter-btn:hover, .filter-btn.active {{ background: var(--brand); color: #fff; border-color: var(--brand); }}
  select {{ padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px;
            font-size: 13px; background: #fff; cursor: pointer; }}

  /* ── Job grid ── */
  .grid {{ max-width: 900px; margin: 24px auto; padding: 0 20px; display: flex;
           flex-direction: column; gap: 16px; }}
  .empty {{ text-align: center; padding: 60px; color: var(--muted); font-size: 15px; }}

  /* ── Job card ── */
  .card {{ background: var(--card); border-radius: var(--radius); padding: 20px 22px;
           border-left: 5px solid var(--border); box-shadow: 0 1px 4px rgba(0,0,0,.06);
           transition: box-shadow .15s; }}
  .card:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.10); }}
  .card.connected-1  {{ border-left-color: var(--green); }}
  .card.connected-2  {{ border-left-color: var(--yellow); }}
  .card.status-applied {{ opacity: .55; }}
  .card.status-skipped {{ display: none; }}

  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
  .card-rank {{ font-size: 12px; color: var(--muted); font-weight: 600; margin-right: 6px; }}
  .card-title {{ font-size: 17px; font-weight: 700; color: var(--brand-dark); }}
  .card-company {{ font-size: 13px; color: var(--muted); margin-top: 3px; }}
  .card-company strong {{ color: var(--text); }}

  /* Score bar */
  .score-wrap {{ display: flex; align-items: center; gap: 8px; flex-shrink: 0; }}
  .score-bar {{ width: 72px; height: 7px; background: #e9ecef; border-radius: 4px; overflow: hidden; }}
  .score-fill {{ height: 100%; border-radius: 4px; }}
  .score-num {{ font-size: 12px; font-weight: 700; color: var(--muted); }}

  /* Badges */
  .badges {{ display: flex; gap: 7px; flex-wrap: wrap; margin-top: 10px; }}
  .badge {{ padding: 2px 9px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #fff; }}
  .badge-green  {{ background: var(--green); }}
  .badge-yellow {{ background: var(--yellow); }}
  .badge-red    {{ background: var(--red); }}
  .badge-gray   {{ background: #adb5bd; }}
  .badge-blue   {{ background: var(--brand); }}

  /* Match reason */
  .match {{ margin-top: 10px; font-size: 13px; color: var(--muted); font-style: italic; }}

  /* Skill pills */
  .skills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
  .skill-pill {{ background: #e8f0fe; color: var(--brand); padding: 2px 8px;
                 border-radius: 3px; font-size: 11px; }}

  /* Action row */
  .actions {{ display: flex; gap: 10px; align-items: center; margin-top: 14px; flex-wrap: wrap; }}
  .btn-apply {{ background: var(--brand); color: #fff; padding: 7px 18px; border-radius: 6px;
                text-decoration: none; font-size: 13px; font-weight: 600; transition: background .15s; }}
  .btn-apply:hover {{ background: #1e4080; }}
  .btn-action {{ padding: 6px 14px; border: 1px solid var(--border); background: #fff;
                 border-radius: 6px; font-size: 12px; cursor: pointer; transition: all .15s; }}
  .btn-action:hover {{ border-color: var(--brand); color: var(--brand); }}
  .btn-action.active-applied {{ background: var(--green); color: #fff; border-color: var(--green); }}
  .btn-action.active-saved   {{ background: var(--yellow); color: #fff; border-color: var(--yellow); }}
  .btn-action.active-skipped {{ background: #adb5bd; color: #fff; border-color: #adb5bd; }}

  .url-preview {{ font-size: 11px; color: var(--muted); flex: 1; overflow: hidden;
                  text-overflow: ellipsis; white-space: nowrap; }}
  .resume-link {{ font-size: 12px; color: var(--green); }}

  /* Connections list */
  .connections {{ margin-top: 8px; font-size: 12px; color: var(--muted); }}
  .conn-item {{ display: inline-block; background: #f0f4ff; color: var(--brand);
                border-radius: 4px; padding: 2px 7px; margin: 2px; }}

  /* Status toast */
  #toast {{ position: fixed; bottom: 24px; right: 24px; background: var(--brand-dark);
            color: #fff; padding: 10px 18px; border-radius: 8px; font-size: 13px;
            opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 999; }}
  #toast.show {{ opacity: 1; }}

  footer {{ text-align: center; color: var(--muted); font-size: 12px;
            padding: 30px; }}
</style>
</head>
<body>

<header>
  <div>
    <h1>🎯 Job Hunter Dashboard</h1>
    <div class="meta">Ahrar Karim · MS Business Analytics · Boston University · Last run: {date_str}</div>
  </div>
  <div class="stat-pills" id="stat-pills"></div>
</header>

<div class="filters">
  <input type="text" id="search" placeholder="Search title, company, skill..." oninput="applyFilters()">
  <select id="sort" onchange="applyFilters()">
    <option value="score">Sort: Relevance</option>
    <option value="connection">Sort: Connections First</option>
    <option value="cpt">Sort: CPT Friendly First</option>
  </select>
  <button class="filter-btn active" data-filter="all"     onclick="setFilter(this)">All</button>
  <button class="filter-btn"       data-filter="connected" onclick="setFilter(this)">🔗 Connections</button>
  <button class="filter-btn"       data-filter="cpt"       onclick="setFilter(this)">✓ CPT</button>
  <button class="filter-btn"       data-filter="new"       onclick="setFilter(this)">New Only</button>
</div>

<div class="grid" id="grid"></div>
<div id="toast"></div>
<footer>Automated daily · Powered by Job Hunter Bot · <a href="https://github.com" style="color:var(--brand)">View repo</a></footer>

<script>
const ALL_JOBS = {jobs_json};

// ── Feedback persistence (localStorage for instant UX) ───────
function getStatus(id) {{
  return localStorage.getItem('job_status_' + id) || 'new';
}}
function setStatus(id, status) {{
  localStorage.setItem('job_status_' + id, status);
}}

// ── Score color ───────────────────────────────────────────────
function scoreColor(s) {{
  return s >= 75 ? '#27ae60' : s >= 55 ? '#f39c12' : '#e74c3c';
}}

// ── Render one card ───────────────────────────────────────────
function renderCard(job, rank) {{
  const status = getStatus(job.id);
  const connClass = job.connection_flag === '1st_degree' ? 'connected-1'
                  : job.connection_flag === 'possible_2nd' ? 'connected-2' : '';
  const score = job.relevance_score || 0;
  const col   = scoreColor(score);

  // CPT badge
  const cptBadge = job.cpt_signal === 'positive'
    ? '<span class="badge badge-green">✓ CPT Friendly</span>'
    : job.cpt_signal === 'negative'
    ? '<span class="badge badge-red">✗ No Sponsorship</span>'
    : '<span class="badge badge-yellow">? CPT Unconfirmed</span>';

  // Connection badge
  const connBadge = job.connection_flag === '1st_degree'
    ? `<span class="badge badge-green">🔗 1st Degree</span>`
    : job.connection_flag === 'possible_2nd'
    ? `<span class="badge badge-yellow">🔗 Possible Connection</span>`
    : `<span class="badge badge-gray">No Connection</span>`;

  const sourceMap = {{ greenhouse_api: 'Greenhouse', lever_api: 'Lever', jsearch: 'JSearch', adzuna: 'Adzuna' }};
  const sourceLabel = sourceMap[job.source] || job.source;

  const skillsHtml = (job.skill_matches || []).slice(0, 6).map(s =>
    `<span class="skill-pill">${{s}}</span>`).join('');

  const connectionsHtml = (job.connections || []).length > 0
    ? `<div class="connections">Connections: ${{
        (job.connections || []).slice(0, 4).map(c =>
          `<span class="conn-item">👤 ${{c.name}}${{c.position ? ' · ' + c.position : ''}}</span>`
        ).join('')
      }}</div>` : '';

  const resumeHtml = job.resume_path
    ? `<span class="resume-link">📄 Resume ready</span>` : '';

  const url = job.apply_url || '#';
  const urlPreview = url.length > 55 ? url.slice(0, 55) + '…' : url;

  const btnClass = status === 'new' ? '' :
    status === 'applied' ? 'active-applied' :
    status === 'saved'   ? 'active-saved'   : 'active-skipped';

  return `
  <div class="card ${{connClass}} status-${{status}}"
       id="card-${{job.id}}"
       data-score="${{score}}"
       data-connection="${{job.connection_flag}}"
       data-cpt="${{job.cpt_signal}}"
       data-status="${{status}}"
       data-search="${{[job.title, job.company, job.location, ...(job.skill_matches||[])].join(' ').toLowerCase()}}">

    <div class="card-top">
      <div style="flex:1">
        <div>
          <span class="card-rank">#${{rank}}</span>
          <span class="card-title">${{job.title}}</span>
        </div>
        <div class="card-company">
          <strong>${{job.company}}</strong>
          &nbsp;·&nbsp;${{job.location || 'Remote / TBD'}}
          &nbsp;·&nbsp;<span style="font-size:11px;color:#9aaac8">via ${{sourceLabel}}</span>
        </div>
      </div>
      <div class="score-wrap">
        <div class="score-bar">
          <div class="score-fill" style="width:${{score}}%;background:${{col}}"></div>
        </div>
        <span class="score-num">${{score}}</span>
      </div>
    </div>

    <div class="badges">
      ${{cptBadge}}
      ${{connBadge}}
    </div>

    ${{job.match_reason ? `<div class="match">"${{job.match_reason}}"</div>` : ''}}

    ${{skillsHtml ? `<div class="skills">${{skillsHtml}}</div>` : ''}}
    ${{connectionsHtml}}
    ${{job.concern ? `<div style="margin-top:6px;font-size:12px;color:#adb5bd">⚠ ${{job.concern}}</div>` : ''}}

    <div class="actions">
      <a href="${{url}}" target="_blank" class="btn-apply">Apply Now →</a>
      ${{resumeHtml}}
      <button class="btn-action ${{status==='applied'?'active-applied':''}}"
              onclick="markJob('${{job.id}}','applied')">✓ Applied</button>
      <button class="btn-action ${{status==='saved'?'active-saved':''}}"
              onclick="markJob('${{job.id}}','saved')">⭐ Save</button>
      <button class="btn-action ${{status==='skipped'?'active-skipped':''}}"
              onclick="markJob('${{job.id}}','skipped')">✕ Skip</button>
      <span class="url-preview">${{urlPreview}}</span>
    </div>
  </div>`;
}}

// ── Render all cards ──────────────────────────────────────────
function renderAll(jobs) {{
  const grid = document.getElementById('grid');
  if (!jobs.length) {{
    grid.innerHTML = '<div class="empty">No jobs match the current filters.</div>';
    return;
  }}
  grid.innerHTML = jobs.map((j, i) => renderCard(j, i + 1)).join('');
  updateStats(jobs);
}}

// ── Stats pills ───────────────────────────────────────────────
function updateStats(jobs) {{
  const total     = jobs.length;
  const connected = jobs.filter(j => j.connection_flag !== 'none').length;
  const cptPos    = jobs.filter(j => j.cpt_signal === 'positive').length;
  const applied   = jobs.filter(j => getStatus(j.id) === 'applied').length;

  document.getElementById('stat-pills').innerHTML = `
    <div class="pill"><div class="num">${{total}}</div><div class="lbl">Roles</div></div>
    <div class="pill"><div class="num">${{connected}}</div><div class="lbl">Connections</div></div>
    <div class="pill"><div class="num">${{cptPos}}</div><div class="lbl">CPT ✓</div></div>
    <div class="pill"><div class="num">${{applied}}</div><div class="lbl">Applied</div></div>
  `;
}}

// ── Filter & sort ─────────────────────────────────────────────
let activeFilter = 'all';
function setFilter(btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeFilter = btn.dataset.filter;
  applyFilters();
}}

function applyFilters() {{
  const q      = document.getElementById('search').value.toLowerCase();
  const sort   = document.getElementById('sort').value;

  let jobs = [...ALL_JOBS];

  // Filter
  if (activeFilter === 'connected') jobs = jobs.filter(j => j.connection_flag !== 'none');
  if (activeFilter === 'cpt')       jobs = jobs.filter(j => j.cpt_signal === 'positive');
  if (activeFilter === 'new')       jobs = jobs.filter(j => getStatus(j.id) === 'new');

  // Search
  if (q) {{
    jobs = jobs.filter(j => {{
      const haystack = [j.title, j.company, j.location, ...(j.skill_matches || [])].join(' ').toLowerCase();
      return haystack.includes(q);
    }});
  }}

  // Sort
  if (sort === 'score') {{
    jobs.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
  }} else if (sort === 'connection') {{
    const deg = {{ '1st_degree': 0, 'possible_2nd': 1, 'none': 2 }};
    jobs.sort((a, b) => (deg[a.connection_flag] || 2) - (deg[b.connection_flag] || 2)
                      || (b.relevance_score || 0) - (a.relevance_score || 0));
  }} else if (sort === 'cpt') {{
    const cptOrder = {{ positive: 0, neutral: 1, negative: 2 }};
    jobs.sort((a, b) => (cptOrder[a.cpt_signal] || 1) - (cptOrder[b.cpt_signal] || 1)
                      || (b.relevance_score || 0) - (a.relevance_score || 0));
  }}

  renderAll(jobs);
}}

// ── Mark job status ───────────────────────────────────────────
function markJob(id, status) {{
  setStatus(id, status);

  const card = document.getElementById('card-' + id);
  if (card) {{
    card.dataset.status = status;
    // Update button states
    card.querySelectorAll('.btn-action').forEach(b => {{
      b.classList.remove('active-applied', 'active-saved', 'active-skipped');
    }});
    const btnMap = {{ applied: 0, saved: 1, skipped: 2 }};
    const idx = btnMap[status];
    const btns = card.querySelectorAll('.btn-action');
    if (btns[idx]) btns[idx].classList.add('active-' + status);
    if (status === 'applied') card.classList.add('status-applied');
    else card.classList.remove('status-applied');
    if (status === 'skipped') card.style.display = 'none';
  }}

  showToast(status === 'applied' ? '✓ Marked as Applied!'
           : status === 'saved'   ? '⭐ Saved!'
           : '✕ Skipped');
  updateStats(ALL_JOBS);
}}

// ── Toast ─────────────────────────────────────────────────────
function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}}

// ── Init ──────────────────────────────────────────────────────
applyFilters();
</script>
</body>
</html>"""


# ── Orchestrator ──────────────────────────────────────────────

class DashboardGenerator:
    def run(self) -> Dict:
        logger.info("═" * 60)
        logger.info("DASHBOARD GENERATOR — starting")
        logger.info("═" * 60)

        top_path = Path("data/top_jobs.json")
        if not top_path.exists():
            logger.error("data/top_jobs.json not found")
            return {}

        with open(top_path) as f:
            top_data = json.load(f)

        top_jobs = top_data.get("top_jobs", [])
        run_date = top_data.get("run_date", datetime.now(timezone.utc).isoformat())

        Path("docs").mkdir(exist_ok=True)
        html = build_dashboard(top_jobs, run_date)

        out_path = Path("docs/index.html")
        with open(out_path, "w") as f:
            f.write(html)

        logger.info(f"  ✓ Dashboard written to {out_path}")
        logger.info(f"  → Enable GitHub Pages (Settings → Pages → /docs) to access it online")
        logger.info("═" * 60)

        return {"path": str(out_path), "job_count": len(top_jobs)}
