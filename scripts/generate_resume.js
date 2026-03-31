/**
 * generate_resume.js
 * ──────────────────────────────────────────────────────────────
 * Reads a JSON payload from stdin, generates a clean ATS-friendly
 * resume .docx using the docx npm package, and writes to the
 * path specified in the payload.
 *
 * Input JSON structure:
 * {
 *   personal: { name, email, phone, location, linkedin, github },
 *   education: [ { degree, school, location, graduation } ],
 *   tailored: {
 *     summary: "...",
 *     skills: { data_visualization: [], programming: [], tools_and_methods: [] },
 *     projects: [ { title, date, bullets: [] } ],
 *     experience: [ { title, company, dates, bullets: [] } ]
 *   },
 *   output_path: "resumes/abc_Google_DataAnalyst.docx"
 * }
 *
 * Install once:  npm install -g docx
 * ──────────────────────────────────────────────────────────────
 */

const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
  LevelFormat, BorderStyle, WidthType, TabStopType,
  TabStopPosition, ExternalHyperlink,
} = require("docx");
const fs = require("fs");

// ── Read stdin ─────────────────────────────────────────────────
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (raw += chunk));
process.stdin.on("end", () => {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    process.stderr.write("Invalid JSON payload: " + e.message + "\n");
    process.exit(1);
  }
  buildResume(payload)
    .then(() => process.exit(0))
    .catch((err) => {
      process.stderr.write("Resume build error: " + err.message + "\n");
      process.exit(1);
    });
});

// ── Color palette ──────────────────────────────────────────────
const COLORS = {
  name:       "1A1A2E",   // Near-black navy for name
  section:    "1A1A2E",   // Section headers
  rule:       "2E5FA3",   // Blue rule line under headers
  bullet:     "333333",   // Body text
  accent:     "2E5FA3",   // Company/school names
  meta:       "666666",   // Dates, locations (muted)
  link:       "2E5FA3",   // Hyperlinks
};

// ── Layout constants (US Letter, 0.6" margins) ────────────────
const PAGE_W    = 12240;
const MARGIN    = 864;    // 0.6 inch in DXA
const CONTENT_W = PAGE_W - 2 * MARGIN; // 10,512 DXA ≈ 7.3 in

// ── Font ───────────────────────────────────────────────────────
const FONT = "Calibri";

// ── Helpers ────────────────────────────────────────────────────

function run(text, opts = {}) {
  return new TextRun({ text, font: FONT, ...opts });
}

function emptyLine(spaceBefore = 0, spaceAfter = 0) {
  return new Paragraph({
    children: [],
    spacing: { before: spaceBefore, after: spaceAfter },
  });
}

/** Section header with blue bottom rule */
function sectionHeader(label) {
  return new Paragraph({
    children: [
      run(label.toUpperCase(), {
        bold: true,
        size: 22,           // 11pt
        color: COLORS.section,
        allCaps: false,
      }),
    ],
    spacing: { before: 140, after: 40 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 8, color: COLORS.rule, space: 2 },
    },
  });
}

/** Bullet point using docx numbering (no raw unicode) */
function bullet(text, bold_prefix = null) {
  const children = [];
  if (bold_prefix) {
    children.push(run(bold_prefix, { bold: true, size: 20, color: COLORS.bullet }));
    children.push(run(" ", { size: 20 }));
  }
  children.push(run(text, { size: 20, color: COLORS.bullet }));

  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children,
    spacing: { before: 20, after: 20 },
  });
}

/** Two-column row: left = bold label, right = muted right-aligned text */
function twoColRow(leftBold, leftNormal, rightText, leftSize = 22, rightSize = 20) {
  return new Paragraph({
    children: [
      run(leftBold, { bold: true, size: leftSize, color: COLORS.accent }),
      leftNormal ? run(" – " + leftNormal, { size: leftSize, color: COLORS.bullet }) : run("", {}),
      run("\t", { size: rightSize }),
      run(rightText || "", { size: rightSize, color: COLORS.meta }),
    ],
    tabStops: [
      { type: TabStopType.RIGHT, position: CONTENT_W },
    ],
    spacing: { before: 20, after: 0 },
  });
}

// ── Header: name + contact ─────────────────────────────────────

function buildHeader(personal) {
  const { name, email, phone, location, linkedin, github } = personal;

  // Contact line (plain text, no clickable links in header for ATS compat)
  const contactParts = [phone, email, location].filter(Boolean);
  if (linkedin) contactParts.push(linkedin.replace("linkedin.com/in/", "linkedin: "));
  if (github)   contactParts.push(github.replace("github.com/", "github: "));

  return [
    new Paragraph({
      children: [run(name, { bold: true, size: 36, color: COLORS.name })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 40 },
    }),
    new Paragraph({
      children: [run(contactParts.join("  |  "), { size: 18, color: COLORS.meta })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 0 },
    }),
  ];
}

// ── Summary ────────────────────────────────────────────────────

function buildSummary(summary) {
  if (!summary) return [];
  return [
    sectionHeader("Summary"),
    new Paragraph({
      children: [run(summary, { size: 20, color: COLORS.bullet, italics: true })],
      spacing: { before: 60, after: 20 },
    }),
  ];
}

// ── Education ─────────────────────────────────────────────────

function buildEducation(education) {
  const paras = [sectionHeader("Education")];
  for (const ed of education) {
    paras.push(twoColRow(ed.school || ed.degree, null, ed.graduation || "", 22));
    paras.push(
      new Paragraph({
        children: [run(ed.degree + (ed.location ? "  •  " + ed.location : ""), {
          size: 20, color: COLORS.bullet,
        })],
        spacing: { before: 0, after: 20 },
      })
    );
  }
  return paras;
}

// ── Skills ─────────────────────────────────────────────────────

function buildSkills(skills) {
  const paras = [sectionHeader("Skills")];
  const groups = [
    ["Data Visualization", skills.data_visualization],
    ["Programming", skills.programming],
    ["Tools & Methods", skills.tools_and_methods],
  ];
  for (const [label, items] of groups) {
    if (!items || items.length === 0) continue;
    paras.push(
      new Paragraph({
        children: [
          run(label + ": ", { bold: true, size: 20, color: COLORS.bullet }),
          run(items.join(", "), { size: 20, color: COLORS.bullet }),
        ],
        spacing: { before: 30, after: 20 },
      })
    );
  }
  return paras;
}

// ── Projects ──────────────────────────────────────────────────

function buildProjects(projects) {
  const paras = [sectionHeader("Projects")];
  for (const proj of projects) {
    paras.push(twoColRow(proj.title, null, proj.date || "", 22));
    for (const b of (proj.bullets || [])) {
      paras.push(bullet(b));
    }
    paras.push(emptyLine(20, 0));
  }
  return paras;
}

// ── Experience ────────────────────────────────────────────────

function buildExperience(experience) {
  const paras = [sectionHeader("Work Experience")];
  for (const exp of experience) {
    paras.push(twoColRow(exp.title, exp.company, exp.dates || "", 22));
    for (const b of (exp.bullets || [])) {
      paras.push(bullet(b));
    }
    paras.push(emptyLine(20, 0));
  }
  return paras;
}

// ── Main builder ──────────────────────────────────────────────

async function buildResume(payload) {
  const { personal, education, tailored, output_path } = payload;

  const children = [
    ...buildHeader(personal),
    emptyLine(60, 0),
    ...buildSummary(tailored.summary),
    emptyLine(40, 0),
    ...buildEducation(education),
    emptyLine(40, 0),
    ...buildSkills(tailored.skills),
    emptyLine(40, 0),
    ...buildProjects(tailored.projects || []),
    ...buildExperience(tailored.experience || []),
  ];

  const doc = new Document({
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "\u2022",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: { indent: { left: 360, hanging: 260 } },
              },
            },
          ],
        },
      ],
    },
    styles: {
      default: {
        document: { run: { font: FONT, size: 20 } },
      },
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: PAGE_W, height: 15840 },
            margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
          },
        },
        children,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);

  // Ensure output directory exists
  const dir = output_path.substring(0, output_path.lastIndexOf("/"));
  if (dir && !fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(output_path, buffer);
  process.stdout.write(`Generated: ${output_path}\n`);
}
