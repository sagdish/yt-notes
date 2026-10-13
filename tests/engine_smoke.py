"""Engine smoke test: installs the drawing engine into a temporary cache, then draws, measures and
exports real diagrams. Needs Node.js 20+ and network access. Run: python3 tests/engine_smoke.py"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "yt_notes.py")

DOC = """# How a request travels

Notes · https://example.com · test file

## The path

A request goes from the client to the server, and the server reads the database.

## The split

Half of the requests are reads, so 50 percent are reads and 50 percent are writes.
"""

FLOW = {"id": "path", "section": "The path", "kind": "flow", "title": "Client to database",
        "why": "the three hops in order",
        "body": "```mermaid\nflowchart TB\n  C[\"client\"] --> S[\"server\"] --> D[\"database\"]\n```"}
CHART = {"id": "split", "section": "The split", "kind": "chart", "title": "Reads and writes",
         "why": "the even split at a glance",
         "body": "```mermaid\npie title Requests\n  \"reads\" : 50\n  \"writes\" : 50\n```"}
# A right-to-left file with a caption fix: the page must be mirrored, the fix listed at the end and
# the visual's label taken from the file, whatever its language.
ARABIC = """---
title: "قواعد البيانات"
language: ar
transcript: polished
---

# قواعد البيانات

قناة · https://example.com · 1:00 · نص

## البداية

الخادم يقرأ الكاش[^fix-1] ثم قاعدة البيانات.

[^fix-1]: في الترجمة النصية: "الكاش" → "الذاكرة المؤقتة"
"""
ARABIC_TABLE = {"id": "parts", "section": "البداية", "kind": "table", "title": "الأجزاء", "why": "w",
                "body": "| جزء | عمل |\n|---|---|\n| الخادم | يقرأ |"}

WIDE = {"id": "wide", "section": "The path", "kind": "flow", "title": "Too wide", "why": "must be refused",
        "body": "```mermaid\nflowchart LR\n  A[a label that is long on purpose] --> B[another label that is long on purpose] "
                "--> C[a third label that is long on purpose] --> D[a fourth label that is long on purpose]\n```"}


def main():
    tmp = tempfile.mkdtemp(prefix="yt-smoke-")
    env = dict(os.environ, XDG_CACHE_HOME=os.path.join(tmp, "cache"),
               YT_NOTES_CONFIG=os.path.join(tmp, "config.json"))
    doc = os.path.join(tmp, "request.md")
    with open(doc, "w", encoding="utf-8") as f:
        f.write(DOC)

    def run(*args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)

    def visuals(vs, *extra, target=doc):
        path = os.path.join(tmp, "v.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(vs, f, ensure_ascii=False)
        return run("visuals", target, path, *extra)

    r = visuals([WIDE])
    assert r.returncode == 1 and "wider than the reading column" in r.stderr, r.stderr
    r = visuals([FLOW, CHART], "--pdf", "--html")
    assert r.returncode == 0, r.stderr
    assert "diagrams drawn and measured: 2" in r.stdout, r.stdout
    html = open(os.path.join(tmp, "request.html"), encoding="utf-8").read()
    assert html.count("<svg") >= 2 and "<script" not in html, "HTML copy must hold drawn SVGs and no scripts"
    with open(os.path.join(tmp, "request.pdf"), "rb") as f:
        assert f.read(5) == b"%PDF-", "not a PDF"
    ar = os.path.join(tmp, "arabic.md")
    with open(ar, "w", encoding="utf-8") as f:
        f.write(ARABIC.replace("الكاش[^fix-1]", "الذاكرة المؤقتة[^fix-1]"))
    r = visuals([ARABIC_TABLE], "--html", target=ar)
    assert r.returncode == 0, r.stderr
    page = open(os.path.join(tmp, "arabic.html"), encoding="utf-8").read()
    assert 'dir="rtl"' in page, "an Arabic page must be right to left"
    assert '<span>عنصر بصري مضاف</span>' in page, "the visual's label comes from the file's language"
    assert '<sup class="fix">' in page and '<ol class="fixes">' in page and "[^fix-" not in page, "fixes are footnotes"
    print(f"ok: engine installed, diagrams drawn and measured, PDF and HTML exported, right-to-left page with a fix ({tmp})")


if __name__ == "__main__":
    main()
