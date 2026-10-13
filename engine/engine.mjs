// Draws Mermaid diagrams in a headless browser. Run by yt_notes.py from its cache folder,
// never by hand. One JSON request on stdin, one JSON answer on stdout.
//
//   {"mode": "check", "diagrams": [{"id", "code"}]}
//       -> [{"id", "width", "height"} | {"id", "error"}]   real parse + layout, real pixel size
//   {"mode": "export", "markdown", "title", "lang", "rtl", "paper", "pdf": path|null, "html": path|null}
//       -> {"pdf": path|null, "html": path|null}           diagrams drawn, visual boxes and caption fixes styled
//
// Browser: $YT_NOTES_BROWSER, else an installed Chrome, Edge or Chromium, else the headless
// shell that yt_notes.py downloaded into $PUPPETEER_CACHE_DIR.
import { existsSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import puppeteer from "puppeteer";
import { Marked } from "marked";

const require = createRequire(import.meta.url);
const MERMAID_JS = require.resolve("mermaid/dist/mermaid.min.js");

const SYSTEM_BROWSERS = {
  darwin: [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ],
  linux: ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"],
  win32: [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ],
};

export function browserPath() {
  const chosen = process.env.YT_NOTES_BROWSER || process.env.YT_TRANSCRIPT_BROWSER;
  if (chosen) return chosen;
  return (SYSTEM_BROWSERS[process.platform] || []).find((p) => existsSync(p)) || null;
}

async function launch() {
  const executablePath = browserPath();
  // A temporary profile and a mock keychain: never the user's own browser profile, never an OS prompt.
  return puppeteer.launch(
    executablePath
      ? { executablePath, headless: true, args: ["--use-mock-keychain"] }
      : { browser: "chrome", headless: "shell" },
  );
}

async function pageWithMermaid(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 900, height: 1200 });
  await page.setContent("<!doctype html><html><body></body></html>");
  await page.addScriptTag({ path: MERMAID_JS });
  await page.evaluate(() => window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" }));
  return page;
}

async function check(browser, diagrams) {
  const page = await pageWithMermaid(browser);
  const out = [];
  for (const [i, d] of diagrams.entries()) {
    out.push(
      await page.evaluate(
        async (id, code, n) => {
          try {
            const { svg } = await window.mermaid.render(`check-${n}`, code);
            const vb = /viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"/.exec(svg);
            if (!vb) return { id, error: "the diagram drew nothing" };
            return { id, width: Math.round(+vb[3]), height: Math.round(+vb[4]) };
          } catch (e) {
            const msg = String((e && e.message) || e).split("\n").slice(0, 4).join(" ");
            return { id, error: msg.slice(0, 300) };
          } finally {
            document.querySelectorAll(`[id^="dcheck-${n}"], #check-${n}`).forEach((el) => el.remove());
          }
        },
        d.id,
        d.code,
        i,
      ),
    );
  }
  return out;
}

// ---------------------------------------------------------------- export
const BLOCK_RE = /^<!-- study-visual:start id=(\S+) kind=(\S+) -->\n([\s\S]*?)\n<!-- study-visual:end -->$/gm;
// A box's first line: "[!example] <label>: <title>" or "**<label>: <title>**". The label is in the
// file's language, so it is found by its position, never by its words.
const HEAD_RE = /^(?:\[!\w+\]\s*)?(?:\*\*)?(.*?)(?:\*\*)?\s*$/;
const FIX_DEF_RE = /^\[\^fix-(\d+)\]: (.*)$/gm;
const FIX_REF_RE = /\[\^fix-(\d+)\]/g;
const TIME_RE = /^\d{1,2}(?::\d{2}){1,2}$/;

const escapeHtml = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function markdownToHtml(markdown, rtl) {
  const marked = new Marked({ gfm: true });
  marked.use({
    renderer: {
      code({ text, lang }) {
        if ((lang || "").trim() === "mermaid") return `<pre class="mermaid">${escapeHtml(text)}</pre>\n`;
        return `<pre><code>${escapeHtml(text)}</code></pre>\n`;
      },
      link({ href, tokens }) {
        const text = this.parser.parseInline(tokens);
        const cls = TIME_RE.test(text) ? ' class="ts"' : "";
        return `<a href="${escapeHtml(href)}"${cls}>${text}</a>`;
      },
    },
  });
  // Frontmatter is for notes apps; the title line and source line already carry what a reader needs.
  let md = markdown.replace(/^---\n[\s\S]*?\n---\n/, "");
  // Caption fixes: footnotes "[^fix-N]: captions: "cash" → "cache"" become a numbered list at the end.
  const fixes = [];
  md = md.replace(FIX_DEF_RE, (_all, n, text) => {
    fixes.push([n, text]);
    return "";
  });
  md = md.replace(FIX_REF_RE, (_all, n) => `<sup class="fix"><a href="#fix-${n}" id="fixref-${n}">${n}</a></sup>`);
  const boxes = [];
  md = md.replace(BLOCK_RE, (_all, id, kind, inner) => {
    const lines = inner.split("\n").map((l) => l.replace(/^> ?/, ""));
    const head = (HEAD_RE.exec(lines[0] || "") || [])[1] || "";
    const cut = head.indexOf(": ");
    const [label, title] = cut > 0 ? [head.slice(0, cut), head.slice(cut + 2)] : ["", head];
    const body = lines.slice(1).join("\n").trim();
    boxes.push(
      `<aside class="visual" data-kind="${escapeHtml(kind)}" id="visual-${escapeHtml(id)}">` +
        `<p class="visual-title">${label ? `<span>${escapeHtml(label)}</span>` : ""}${escapeHtml(title)}</p>` +
        marked.parse(body) +
        `</aside>`,
    );
    return `\n\n<div data-box="${boxes.length - 1}"></div>\n\n`;
  });
  let html = marked.parse(md);
  html = html.replace(/<div data-box="(\d+)"><\/div>/g, (_m, n) => boxes[+n]);
  // The source line (first paragraph after the title) gets its own quieter style.
  html = html.replace(/(<\/h1>\s*)<p>/, '$1<p class="source">');
  if (fixes.length)
    html +=
      `<ol class="fixes">` +
      fixes
        // "from → to" reads backwards in a right-to-left line
        .map(([n, text]) => [n, rtl ? text.replace(/ → (?=")/, " ← ") : text])
        .map(([n, text]) => `<li id="fix-${n}" value="${n}">${escapeHtml(text)} <a href="#fixref-${n}">↩</a></li>`)
        .join("") +
      `</ol>`;
  return html;
}

const CSS = `
:root { --ink:#1d1f23; --muted:#5d636b; --line:#e3e1db; --wash:#f6f5f1; --accent:#3a6fd8; }
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: #fff; color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
/* One font per script: without these, kanji and kana (or Hangul, Arabic) come from different fallbacks. */
:lang(ja) body { font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", "Noto Sans CJK JP", "Noto Sans JP", sans-serif; }
:lang(zh) body { font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans SC", sans-serif; }
:lang(ko) body { font-family: "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", "Noto Sans KR", sans-serif; }
:lang(ar) body, :lang(fa) body, :lang(ur) body { font-family: "Geeza Pro", "Segoe UI", "Noto Naskh Arabic", "Noto Sans Arabic", sans-serif; }
:lang(he) body { font-family: "Arial Hebrew", "Segoe UI", "Noto Sans Hebrew", sans-serif; }
main { max-width: 720px; margin: 0 auto; padding: 48px 24px 72px; }
h1 { font-size: 30px; line-height: 1.2; letter-spacing: -0.01em; margin: 0 0 10px; }
h2 { font-size: 22px; line-height: 1.3; margin: 40px 0 10px; padding-top: 16px; border-top: 1px solid var(--line); }
h3 { font-size: 18px; line-height: 1.35; margin: 28px 0 8px; }
h2, h3 { break-after: avoid; }
p { margin: 0 0 14px; }
.source { color: var(--muted); font-size: 14px; margin-bottom: 28px; }
a { color: var(--accent); text-decoration: none; }
a.ts { font-size: 0.7em; font-weight: 500; color: var(--muted); margin-inline-start: 8px; vertical-align: 0.15em; }
em { color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: 6px 0 4px; font-size: 14px; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: start; vertical-align: top; }
th { background: var(--wash); }
pre { background: var(--wash); padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; }
.visual { margin: 18px 0 22px; padding: 14px 16px 12px; border: 1px solid var(--line); border-inline-start: 3px solid var(--accent);
  border-radius: 6px; background: var(--wash); break-inside: avoid; }
.visual-title { margin: 0 0 10px; font-weight: 600; font-size: 15px; }
.visual-title span { display: block; font-weight: 500; font-size: 12px; color: var(--muted); }
.visual pre.mermaid { background: transparent; padding: 0; margin: 0; text-align: center; overflow: visible; direction: ltr; }
sup.fix { font-size: 0.65em; line-height: 0; }
sup.fix a { color: var(--muted); }
ol.fixes { margin: 40px 0 0; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }
ol.fixes a { color: var(--muted); }
.visual pre.mermaid svg { max-width: 100%; height: auto; }
@page { margin: 18mm 16mm; }
@media print { main { max-width: none; padding: 0; } body { font-size: 11pt; } h1 { font-size: 22pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; } }
`;

async function exportDoc(browser, req) {
  const body = markdownToHtml(req.markdown, req.rtl);
  const doc =
    `<!doctype html><html lang="${escapeHtml(req.lang || "en")}"${req.rtl ? ' dir="rtl"' : ""}><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width, initial-scale=1">` +
    `<title>${escapeHtml(req.title || "Transcript")}</title><style>${CSS}</style></head>` +
    `<body><main>${body}</main></body></html>`;
  const page = await browser.newPage();
  await page.setContent(doc, { waitUntil: "load" });
  if (await page.$("pre.mermaid")) {
    await page.addScriptTag({ path: MERMAID_JS });
    await page.evaluate(async () => {
      // Neutral greys print well; Obsidian and GitHub apply their own theme to the .md file.
      window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
      await window.mermaid.run({ querySelector: "pre.mermaid" });
    });
    const failed = await page.$$eval("pre.mermaid:not([data-processed])", (els) => els.length);
    if (failed) throw new Error(`${failed} diagram(s) did not draw`);
  }
  const out = { pdf: null, html: null };
  if (req.html) {
    // A static page: the drawn diagrams stay as inline SVG, the script that drew them is removed.
    const html = await page.evaluate(() => {
      document.querySelectorAll("script").forEach((s) => s.remove());
      return "<!doctype html>\n" + document.documentElement.outerHTML;
    });
    writeFileSync(req.html, html);
    out.html = req.html;
  }
  if (req.pdf) {
    await page.pdf({ path: req.pdf, format: req.paper === "letter" ? "letter" : "a4", printBackground: true });
    out.pdf = req.pdf;
  }
  return out;
}

// ---------------------------------------------------------------- main
//   {"mode": "browser"} -> {"system": path|null, "shell": path|null}
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
if (req.mode === "browser") {
  // Which browser a launch would use; nothing is started.
  const shell = puppeteer.executablePath({ headless: "shell" });
  process.stdout.write(JSON.stringify({ system: browserPath(), shell: existsSync(shell) ? shell : null }));
  process.exit(0);
}
const browser = await launch();
try {
  const result = req.mode === "check" ? await check(browser, req.diagrams) : await exportDoc(browser, req);
  process.stdout.write(JSON.stringify(result));
} finally {
  await browser.close();
}
