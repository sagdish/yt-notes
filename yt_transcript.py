#!/usr/bin/env python3
"""YouTube transcript -> one markdown file, every word kept. Optional study visuals, for any .md file.

Every mechanical step lives here so no agent improvises it. The agent's judgment is limited to WHERE
the section headings go (headings.json), WHICH visuals earn a place (visuals.json), and WHERE the
file is saved (asked, never guessed).

  setup  <folder> [--label "..."]    remember a folder transcripts are saved under (repeatable)
  setup  --show                      the folders remembered so far
  where                              the save folders and the topic folders inside them
  fetch  <url> [--lang xx]           captions only (never the video) -> a work dir with the text
  build  <workdir> <headings.json> <out.md> [--blurb "..."] [--anywhere]
                                     writes the file, verifies it word for word, deletes the work dir
  visuals <file.md> <visuals.json>   adds visual blocks to ANY markdown file; replaces the ones it
                                     added before; refuses unless every other byte is unchanged
  strip  <file.md>                   removes every visual block, nothing else
  check  <file.md> <raw.txt>         the word-for-word check on its own
  discard <workdir>                  the user stopped before build: remove the work dir

Exit codes: 0 ok · 1 refused/failed check · 2 no captions / yt-dlp problem · 3 no save folder set up.
"""
import glob, html, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("YT_TRANSCRIPT_CONFIG") or os.path.expanduser("~/.config/yt-transcript/config.json")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "yt-transcript")
FILE_RE = re.compile(r"^[0-9A-Za-z._-]+\.md$")        # kebab-case: safe in every app, shell and URL
FOLDER_RE = re.compile(r"^[0-9A-Za-z_-][0-9A-Za-z._-]*$")
MAX_UNIT_WORDS = 60                                     # captions without punctuation get chunked
PARA_WORDS = 120                                        # paragraph break at the first sentence end past this

# The diagram checker's own versions. mermaid matches what current Obsidian ships (11.13).
CHECKER_DEPS = {"mermaid": "11.13.0", "jsdom": "26.1.0"}

VISUAL_KINDS = {"diagram", "flow", "table", "comparison", "formula", "tree", "pair", "chart"}
BLOCK_START = "<!-- study-visual:start"
BLOCK_END = "<!-- study-visual:end -->"
BLOCK_RE = re.compile(r"\n{0,2}<!-- study-visual:start [^\n]*-->\n.*?<!-- study-visual:end -->", re.S)


def die(msg, code=1):
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- save folders
def roots():
    """[{label, path}] — $YT_TRANSCRIPT_ROOT if set, else the config file."""
    env = os.environ.get("YT_TRANSCRIPT_ROOT")
    if env:
        return [{"label": "notes", "path": os.path.abspath(os.path.expanduser(env))}]
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        return [{"label": r.get("label") or "notes", "path": os.path.abspath(os.path.expanduser(r["path"]))}
                for r in cfg.get("roots", []) if r.get("path")]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def cmd_setup(args):
    if args == ["--show"]:
        rs = roots()
        print("\n".join(f"{r['label']}: {r['path']}" for r in rs) or "no save folder set up yet")
        return
    label = None
    if "--label" in args:
        k = args.index("--label")
        label = args[k + 1] if k + 1 < len(args) else die("--label needs a text")
        args = args[:k] + args[k + 2:]
    if len(args) != 1:
        die('usage: setup <folder> [--label "what goes there"]   or   setup --show')
    path = os.path.abspath(os.path.expanduser(args[0]))
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    rs = [r for r in cfg.get("roots", []) if os.path.abspath(os.path.expanduser(r.get("path", ""))) != path]
    rs.append({"label": label or os.path.basename(path) or "notes", "path": path})
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    json.dump({"roots": rs}, open(CONFIG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"saved: {rs[-1]['label']} -> {path}\nconfig: {CONFIG}")


def blurb(folder):
    try:
        for line in open(os.path.join(folder, "README.md"), encoding="utf-8"):
            s = line.strip()
            if s and s != "---" and not s.startswith("#") and not s.startswith("tags:"):
                return s
    except OSError:
        pass
    return "(no README one-liner)"


def cmd_where(_args):
    rs = roots()
    if not rs:
        print("NO SAVE FOLDER: ask the user which folder transcripts should live in, then run:\n"
              f"  python3 {os.path.abspath(__file__)} setup '<folder>' --label '<what goes there>'")
        sys.exit(3)
    for r in rs:
        print(f"\n{r['label']} -> {r['path']}/<topic>/")
        if not os.path.isdir(r["path"]):
            print("  (folder missing — disk not mounted?)")
            continue
        for name in sorted(os.listdir(r["path"])):
            p = os.path.join(r["path"], name)
            if os.path.isdir(p) and not name.startswith((".", "_")) and name != "inbox":
                print(f"  {name}/  — {blurb(p)}")


# ---------------------------------------------------------------- fetch
def ytdlp(*args):
    if not shutil.which("yt-dlp"):
        die("yt-dlp is not installed. Install it (macOS: brew install yt-dlp · anywhere: pipx install yt-dlp)", 2)
    r = subprocess.run(["yt-dlp", "--no-playlist", "--skip-download", *args], capture_output=True, text=True)
    if r.returncode != 0:
        die("yt-dlp failed:\n" + r.stderr.strip()[-1500:] +
            "\nIf YouTube changed something, updating yt-dlp usually fixes it.", 2)
    return r.stdout


def pick_track(info, want):
    """Human-made captions first, then YouTube's auto-captions in the video's own language."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}
    lang = want or info.get("language") or "en"
    for k in [lang] + sorted(k for k in manual if k.startswith(lang + "-")):
        if k in manual:
            return k, "manual"
    for k in (f"{lang}-orig", lang):
        if k in auto:
            return k, "auto"
    if not want and lang != "en":
        return None, f"no captions in the video's language ({lang}); manual tracks: {sorted(manual) or 'none'}"
    return None, f"no captions for '{lang}'; manual tracks: {sorted(manual) or 'none'}; auto-captions: {'yes' if auto else 'none'}"


def vtt_to_text(raw):
    """Auto-captions roll: every cue repeats the line before it and adds one new line, so the text
    is each cue's LAST line, skipping a repeat of the line just kept. Manual subtitles don't roll,
    so there every line is kept. Verified 2026-09-28: 0 word differences against a hand-checked
    transcript (the earlier 'keep only <c>-tagged lines' rule dropped one-word lines)."""
    raw = raw.replace("\r\n", "\n")
    rolling = "<c>" in raw
    out = []
    for cue in raw.split("\n\n"):
        lines = cue.split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        text = [html.unescape(re.sub(r"<[^>]+>", "", l)).strip() for l in lines[idx + 1:]]
        text = [t for t in text if t]
        for t in (text[-1:] if rolling else text):
            if not out or t != out[-1]:
                out.append(t)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def units_of(text):
    """Sentences, numbered. A run with no sentence ends (unpunctuated captions) is chunked."""
    units = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        w = s.split()
        while len(w) > MAX_UNIT_WORDS:
            units.append(" ".join(w[:40]))
            w = w[40:]
        if w:
            units.append(" ".join(w))
    return units


def kebab(s):
    s = re.sub(r"[^0-9A-Za-z]+", "-", s.lower()).strip("-")
    if len(s) > 70:
        s = s[:70].rsplit("-", 1)[0]
    return (s or "transcript") + ".md"


def already_saved(video_id):
    hits = []
    for r in roots():
        for p in glob.glob(os.path.join(r["path"], "*", "*.md")):
            try:
                if video_id in open(p, encoding="utf-8").read(4000):
                    hits.append(p)
            except OSError:
                pass
    return hits


def cmd_fetch(args):
    if not args:
        die("usage: fetch <url> [--lang xx]")
    url, want = args[0], (args[args.index("--lang") + 1] if "--lang" in args else None)
    if not re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)[\w-]{11}", url):
        die("that is not one video's link (watch?v=, youtu.be/, shorts/, live/) — a playlist or channel link won't do", 2)
    info = json.loads(ytdlp("-J", url))
    if info.get("_type") == "playlist":
        die("that link is a playlist, not one video — give one video's link", 2)
    code, kind = pick_track(info, want)
    if not code:
        die(kind + ". Nothing was written. Pass --lang <code> to pick another track.", 2)
    # a run the user stopped (duplicate, declined, abandoned) leaves its work dir; clear any older than a day
    for old in glob.glob(os.path.join(tempfile.gettempdir(), "yt-transcript-*")):
        if time.time() - os.path.getmtime(old) > 86400:
            shutil.rmtree(old, ignore_errors=True)
    work = tempfile.mkdtemp(prefix="yt-transcript-")
    ytdlp("--write-subs" if kind == "manual" else "--write-auto-subs", "--sub-langs", code,
          "--sub-format", "vtt", "-o", os.path.join(work, "sub.%(ext)s"), url)
    vtts = glob.glob(os.path.join(work, "*.vtt"))
    if not vtts:
        shutil.rmtree(work, ignore_errors=True)
        die(f"yt-dlp returned no .vtt for track '{code}'", 2)
    text = vtt_to_text(open(vtts[0], encoding="utf-8").read())
    for v in vtts:
        os.remove(v)
    units = units_of(text)
    meta = {
        "id": info.get("id"),
        "title": info.get("title") or "untitled",
        "creator": info.get("channel") or info.get("uploader") or "unknown",
        "url": f"https://www.youtube.com/watch?v={info.get('id')}",
        "length": info.get("duration_string") or "?",
        "track": code,
        "kind": kind,
        "suggested_file": kebab(info.get("title") or ""),
    }
    json.dump(meta, open(os.path.join(work, "meta.json"), "w"), indent=2, ensure_ascii=False)
    open(os.path.join(work, "raw.txt"), "w", encoding="utf-8").write(text)
    open(os.path.join(work, "units.txt"), "w", encoding="utf-8").write(
        "".join(f"{i}| {u}\n" for i, u in enumerate(units, 1)))
    print(f"workdir: {work}")
    for k in ("title", "creator", "url", "length", "track", "kind", "suggested_file"):
        print(f"{k}: {meta[k]}")
    print(f"words: {len(text.split())} · units: {len(units)} (read {work}/units.txt)")
    if not any(c in text for c in ".?!"):
        print("note: these captions have no punctuation — units are 40-word chunks, not sentences.")
    for h in already_saved(meta["id"]):
        print(f"ALREADY SAVED: {h} — tell the user before writing a second copy.")


# ---------------------------------------------------------------- build + check
def load_headings(path, n_units):
    try:
        hs = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"headings file unreadable: {e}")
    if not isinstance(hs, list) or not hs:
        die('headings must be a non-empty list of {"unit": N, "level": 2|3, "title": "..."}')
    last = (0, 1)
    for i, h in enumerate(hs):
        if not isinstance(h, dict) or set(h) - {"unit", "level", "title"}:
            die(f"heading {i}: only keys unit, level, title")
        u, lv, t = h.get("unit"), h.get("level"), str(h.get("title", "")).strip()
        if not isinstance(u, int) or not 1 <= u <= n_units:
            die(f"heading {i}: unit must be 1..{n_units}")
        if lv not in (2, 3):
            die(f"heading {i}: level must be 2 or 3")
        if not t or "\n" in t or t.startswith("#"):
            die(f"heading {i}: title must be one plain line")
        if i == 0 and (u != 1 or lv != 2):
            die("the first heading must be level 2 at unit 1 — text above the first ## would read as the file's header line")
        if (u, lv) < last or (u == last[0] and lv == last[1] and i > 0):
            die(f"heading {i}: units must go forward (a ### may share a unit with the ## just before it)")
        last = (u, lv)
        h["title"] = t
    return hs


def strip_blocks(md):
    return BLOCK_RE.sub("", md)


def body_words(md):
    """The file's words minus the H1, the source line, heading lines and any visual blocks."""
    lines = [l for l in strip_blocks(md).split("\n") if l.strip()]
    return " ".join(l for l in lines[2:] if not re.match(r"^#{1,6}\s", l)).split()


def check(md, raw):
    lines = [l for l in strip_blocks(md).split("\n") if l.strip()]
    if len(lines) < 3 or not lines[0].startswith("# "):
        return "line 1 must be '# <title>'"
    if " · http" not in lines[1]:
        return "line 2 must be the source line: creator · URL · length · ..."
    if not lines[2].startswith("## "):
        return "the first line after the source line must be a '## ' heading"
    a, b = body_words(md), raw.split()
    if a != b:
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        return (f"words differ from the captions at word {i}: file has {' '.join(a[i:i+8])!r}, "
                f"captions have {' '.join(b[i:i+8])!r} ({len(a)} vs {len(b)} words)")
    return None


def cmd_build(args):
    flags = {"--anywhere"}
    pos = [a for a in args if a not in flags]
    blurb_txt = None
    if "--blurb" in pos:
        k = pos.index("--blurb")
        blurb_txt = pos[k + 1] if k + 1 < len(pos) else die("--blurb needs a line")
        del pos[k:k + 2]
    if len(pos) != 3:
        die('usage: build <workdir> <headings.json> <out.md> [--blurb "one-liner"] [--anywhere]')
    work, hpath, out = pos[0], pos[1], os.path.abspath(os.path.expanduser(pos[2]))
    if not os.path.isfile(os.path.join(work, "meta.json")):
        die(f"{work} is not a fetch work dir (no meta.json) — run fetch first; a built file's work dir is already removed")
    meta = json.load(open(os.path.join(work, "meta.json"), encoding="utf-8"))
    raw = open(os.path.join(work, "raw.txt"), encoding="utf-8").read()
    units = [l.split("| ", 1)[1].rstrip("\n") for l in open(os.path.join(work, "units.txt"), encoding="utf-8")]

    # where it may go
    if not FILE_RE.match(os.path.basename(out)):
        die("filename must be kebab-case [0-9A-Za-z._-] ending in .md")
    if os.path.exists(out):
        die(f"{out} already exists — nothing overwritten; ask the user for another name")
    folder = os.path.dirname(out)
    if "--anywhere" not in args:
        rs = roots()
        if not rs:
            die("no save folder set up — run: setup '<folder>'", 3)
        parent = os.path.dirname(folder)
        if parent not in [r["path"] for r in rs] or not FOLDER_RE.match(os.path.basename(folder)):
            die("the file must sit one topic folder deep under a save folder: " +
                " or ".join(f"{r['path']}/<topic>/" for r in rs) + " (or pass --anywhere when the user named the path)")
        if not os.path.isdir(folder) and not blurb_txt:
            die(f"{folder} is a new topic folder: pass --blurb \"<one-line description>\" for its README")

    hs = load_headings(hpath, len(units))
    at = {}
    for h in hs:
        at.setdefault(h["unit"], []).append(h)
    parts = [f"# {meta['title']}", "",
             f"{meta['creator']} · {meta['url']} · {meta['length']} · verbatim "
             f"{'auto-caption' if meta['kind'] == 'auto' else 'caption'} transcript, "
             f"section headings added at the video's own transitions"]
    para, count = [], 0
    def flush():
        nonlocal para, count
        if para:
            parts.extend(["", " ".join(para)])
        para, count = [], 0
    for i, u in enumerate(units, 1):
        for h in at.get(i, []):
            flush()
            parts.extend(["", f"{'#' * h['level']} {h['title']}"])
        para.append(u)
        count += len(u.split())
        if count >= PARA_WORDS and u[-1:] in ".?!":
            flush()
    flush()
    md = "\n".join(parts) + "\n"

    err = check(md, raw)
    if err:
        die("the built file failed its own check (nothing written): " + err)
    if not os.path.isdir(folder):
        os.makedirs(folder)
        if blurb_txt and not os.path.exists(os.path.join(folder, "README.md")):
            open(os.path.join(folder, "README.md"), "w", encoding="utf-8").write(blurb_txt.strip() + "\n")
    open(out, "w", encoding="utf-8").write(md)
    shutil.rmtree(work, ignore_errors=True)
    n2 = sum(1 for h in hs if h["level"] == 2)
    print(f"written: {out}\nwords: {len(raw.split())} (identical to the captions) · {n2} sections · "
          f"{len(hs) - n2} sub-sections · {md.count(chr(10))} lines\nwork dir removed.")


# ---------------------------------------------------------------- visuals
def headings_of(text):
    """[(level, title, line_start, line_end)] for every markdown heading outside code fences and
    frontmatter. Offsets are character positions in `text`."""
    out, pos, fence, front = [], 0, None, text.startswith("---\n")
    for n, line in enumerate(text.split("\n")):
        start, end = pos, pos + len(line)
        pos = end + 1
        if front:
            if n > 0 and line.strip() == "---":
                front = False
            continue
        f = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if f:
            if fence is None:
                fence = f.group(1)[0]
            elif f.group(1)[0] == fence:
                fence = None
            continue
        if fence:
            continue
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), start, end))
    return out


def anchor_offset(text, heads, v, n):
    """Where visual n goes: the end of its section's text, or the end of the paragraph that holds
    `after_text` inside that section. Returns a character offset in `text`."""
    matches = [h for h in heads if h[1] == v["section"]]
    if not matches:
        die(f"visual {n} ({v['id']}): no heading named {v['section']!r} — headings are: " +
            " · ".join(h[1] for h in heads[:40]))
    nth = v.get("nth")
    if nth is None and len(matches) > 1:
        die(f"visual {n} ({v['id']}): {len(matches)} headings are named {v['section']!r} — add \"nth\": 1..{len(matches)}")
    nth = nth or 1
    if not isinstance(nth, int) or not 1 <= nth <= len(matches):
        die(f"visual {n} ({v['id']}): nth must be 1..{len(matches)}")
    h = matches[nth - 1]
    later = [x for x in heads if x[2] > h[2]]
    end = later[0][2] if later else len(text)
    if v.get("after_text"):
        at = text.find(v["after_text"], h[3], end)
        if at < 0:
            die(f"visual {n} ({v['id']}): after_text not found inside section {v['section']!r} — copy it exactly")
        brk = text.find("\n\n", at, end)
        para_end = brk if brk >= 0 else end
        return len(text[:para_end].rstrip())
    body = text[h[3]:end]
    return h[3] + len(body.rstrip()) if body.strip() else h[3]


def load_visuals(path):
    try:
        vs = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"visuals file unreadable: {e}")
    if not isinstance(vs, list):
        die("visuals must be a list (an empty list removes every visual)")
    allowed = {"id", "section", "nth", "after_text", "kind", "title", "why", "body"}
    seen = set()
    for n, v in enumerate(vs):
        if not isinstance(v, dict) or set(v) - allowed:
            die(f"visual {n}: only keys {sorted(allowed)}")
        vid = str(v.get("id", ""))
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,30}$", vid) or vid in seen:
            die(f"visual {n}: id must be unique, lowercase, [a-z0-9-]")
        seen.add(vid)
        if v.get("kind") not in VISUAL_KINDS:
            die(f"visual {n} ({vid}): kind must be one of {sorted(VISUAL_KINDS)}")
        for k, cap in (("section", 200), ("title", 80), ("why", 240)):
            s = str(v.get(k, "")).strip()
            if not s or "\n" in s or len(s) > cap:
                die(f"visual {n} ({vid}): {k} is required, one line, at most {cap} characters")
            v[k] = s
        body = str(v.get("body", "")).strip("\n")
        if not body.strip():
            die(f"visual {n} ({vid}): body is empty")
        if "study-visual" in body or "<!--" in body:
            die(f"visual {n} ({vid}): body may not contain HTML comments")
        if any(re.match(r"^\s{0,3}#{1,6}\s", l) for l in body.split("\n")):
            die(f"visual {n} ({vid}): no # headings inside a visual — they would join the file's outline")
        if len(re.findall(r"^\s{0,3}(?:```|~~~)", body, re.M)) % 2:
            die(f"visual {n} ({vid}): a code fence is not closed")
        rows = body.split("\n")
        for i, l in enumerate(rows):
            if l.lstrip().startswith("|") and (i == 0 or not rows[i - 1].lstrip().startswith("|")):
                if i + 1 >= len(rows) or not re.match(r"^\s*\|?\s*:?-{3,}", rows[i + 1]):
                    die(f"visual {n} ({vid}): a table needs a |---| line under its header row")
        v["body"] = body
    return vs


def check_numbers(vs, source):
    """A chart may only show numbers the source actually says."""
    said = set(re.findall(r"\d+(?:\.\d+)?", source))
    for v in vs:
        if v["kind"] != "chart":
            continue
        for l in v["body"].split("\n"):
            if re.match(r"^\s*(```|~~~|columns\b)", l):
                continue
            for num in re.findall(r"\d+(?:\.\d+)?", l):
                if num not in said:
                    die(f"visual {v['id']}: the chart shows {num}, which the text never says — "
                        "a chart needs the source's own numbers; show the structure instead")


MAX_LABEL = 26        # characters per label line (split longer ones with <br/>)
MAX_WIDTH = 560       # px: Obsidian's reading column inside a callout, measured 2026-09-29
CHAR_PX, BOX_PAD, GAP = 8.5, 40, 50   # mermaid's default 16px font; calibrated on a rendered tree (est. 798 = real 798)


def check_width(vid, code):
    """A diagram must fit a reading column at full size: Obsidian cuts off what is wider instead of
    shrinking it (seen 2026-09-29). So: short label lines, and an estimated width under MAX_WIDTH."""
    lines = [l.strip() for l in code.strip().split("\n") if l.strip() and not l.strip().startswith("%%")]
    if not lines:
        return
    for l in lines:
        for label in re.findall(r'"([^"]*)"', l):
            for part in re.split(r"<br\s*/?>", label):
                if len(part.strip()) > MAX_LABEL:
                    die(f"visual {vid}: the label line {part.strip()!r} is over {MAX_LABEL} characters — "
                        "shorten it or split it with <br/>, or the diagram gets too wide to read")
    head = lines[0].split()
    if head[0] in ("flowchart", "graph"):
        direction = head[1] if len(head) > 1 else "TB"
        box, children, order = {}, {}, []
        for l in lines[1:]:
            for nid, label in re.findall(r'([\w-]+)\s*(?:\[\[?|\(\(?|\{\{?)"([^"]*)"', l):
                box[nid] = max(len(p.strip()) for p in re.split(r"<br\s*/?>", label)) * CHAR_PX + BOX_PAD
            bare = re.sub(r'(\[\[?|\(\(?|\{\{?)"[^"]*"(\]\]?|\)\)?|\}\}?)', "", l)
            bare = re.sub(r"(\[\[?|\(\(?|\{\{?)[^\]\)\}]*(\]\]?|\)\)?|\}\}?)", "", bare)
            parts = [p.strip() for p in re.split(r"\s*(?:<-->|-->|---|==>|-\.->|~~~)\s*(?:\|[^|]*\|)?\s*", bare)]
            ids = [p for p in parts if re.match(r"^[\w-]+$", p)]
            order += [i for i in ids if i not in order]
            for a, b in zip(ids, ids[1:]):
                children.setdefault(a, []).append(b)
        # depth of each box = its row (TB) or column (LR)
        depth = {}
        targets = {b for c in children.values() for b in c}
        todo = [(n, 0) for n in order if n not in targets] or [(order[0], 0)] if order else []
        while todo:
            n, d = todo.pop(0)
            if depth.get(n, -1) >= d or d > 20:
                continue
            depth[n] = d
            todo += [(c, d + 1) for c in children.get(n, [])]
        levels = {}
        for n, d in depth.items():
            levels.setdefault(d, []).append(box.get(n, len(n) * CHAR_PX + BOX_PAD))
        if direction in ("LR", "RL"):
            width = sum(max(ws) for ws in levels.values()) + GAP * (len(levels) - 1)
        else:
            width = max(sum(ws) + GAP * (len(ws) - 1) for ws in levels.values())
        if width > MAX_WIDTH:
            die(f"visual {vid}: about {int(width)}px wide, over the {MAX_WIDTH}px a reading column has — "
                "fewer boxes side by side, shorter label lines, or turn it (TB <-> LR)")
    if head[0] == "block-beta":
        cols = re.search(r"^columns\s+(\d+)", "\n".join(lines), re.M)
        if cols and int(cols.group(1)) > 3:
            die(f"visual {vid}: {cols.group(1)} columns is too wide — at most 3")


def check_mermaid(vs):
    """Parse every ```mermaid block with the real parser. Installs the checker once, into the cache."""
    diagrams = []
    for v in vs:
        for code in re.findall(r"^\s*```mermaid\s*\n(.*?)^\s*```", v["body"], re.S | re.M):
            check_width(v["id"], code)
            diagrams.append({"id": v["id"], "code": code})
    if not diagrams:
        return 0
    if not shutil.which("node") or not shutil.which("npm"):
        die("diagrams need Node.js to be checked (nothing written) — install Node, or use tables and text only")
    home = os.path.join(CACHE, "mermaid-check")
    pkg = {"private": True, "type": "module", "dependencies": CHECKER_DEPS}
    pkg_path = os.path.join(home, "package.json")
    try:
        current = json.load(open(pkg_path, encoding="utf-8"))
    except (OSError, ValueError):
        current = None
    if current != pkg or not os.path.isdir(os.path.join(home, "node_modules", "mermaid")):
        os.makedirs(home, exist_ok=True)
        json.dump(pkg, open(pkg_path, "w", encoding="utf-8"), indent=2)
        print(f"first run: installing the diagram checker into {home} (about 180 MB, once)…", file=sys.stderr)
        r = subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=home,
                           capture_output=True, text=True)
        if r.returncode != 0:
            die("could not install the diagram checker (nothing written):\n" + r.stderr.strip()[-800:])
    shutil.copy(os.path.join(HERE, "check_mermaid.mjs"), os.path.join(home, "check_mermaid.mjs"))
    r = subprocess.run(["node", "check_mermaid.mjs"], cwd=home, input=json.dumps(diagrams),
                       capture_output=True, text=True)
    if r.returncode != 0:
        die("the diagram checker crashed (nothing written):\n" + r.stderr.strip()[-800:])
    errors = json.loads(r.stdout or "[]")
    if errors:
        die("these diagrams do not parse (nothing written):\n" +
            "\n".join(f"  {e['id']}: {e['error']}" for e in errors))
    return len(diagrams)


def block_text(v):
    quoted = "\n".join(f"> {l}" if l.strip() else ">" for l in v["body"].split("\n"))
    return (f"{BLOCK_START} id={v['id']} kind={v['kind']} -->\n"
            f"> [!example] Added visual · {v['title']}\n>\n{quoted}\n\n{BLOCK_END}")


def write_atomic(path, text):
    tmp = f"{path}.yt-transcript-tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


def cmd_visuals(args):
    if len(args) != 2:
        die("usage: visuals <file.md> <visuals.json>")
    path = os.path.abspath(os.path.expanduser(args[0]))
    if not path.endswith(".md") or not os.path.isfile(path):
        die(f"{path} is not an existing .md file")
    original = open(path, encoding="utf-8").read()
    base = strip_blocks(original)          # a re-run replaces every block it added before
    replaced = original.count(BLOCK_START)
    vs = load_visuals(args[1])
    check_numbers(vs, base)
    diagrams = check_mermaid(vs)

    heads = headings_of(base)
    spots = [(anchor_offset(base, heads, v, n), n, v) for n, v in enumerate(vs)]
    text = base
    for off, _n, v in sorted(spots, key=lambda s: (s[0], s[1]), reverse=True):
        text = text[:off] + "\n\n" + block_text(v) + text[off:]

    if strip_blocks(text) != base:
        die("inserting the visuals would change the file's own text (nothing written)")
    if text.count(BLOCK_START) != len(vs):
        die("block count mismatch after inserting (nothing written)")
    write_atomic(path, text)
    print(f"written: {path}\nvisuals: {len(vs)} ({', '.join(v['id'] + ' ' + v['kind'] for v in vs) or 'none'})"
          f"{f' · {replaced} earlier ones replaced' if replaced else ''} · diagrams parsed: {diagrams}\n"
          "the file's own text is unchanged, byte for byte")


def cmd_strip(args):
    if len(args) != 1:
        die("usage: strip <file.md>")
    path = os.path.abspath(os.path.expanduser(args[0]))
    text = open(path, encoding="utf-8").read()
    n = text.count(BLOCK_START)
    if not n:
        print("no visuals in this file — nothing changed")
        return
    write_atomic(path, strip_blocks(text))
    print(f"removed {n} visual{'s' if n != 1 else ''} from {path}; nothing else changed")


def cmd_discard(args):
    if len(args) != 1 or not os.path.basename(os.path.normpath(args[0])).startswith("yt-transcript-"):
        die("usage: discard <workdir from fetch>")
    shutil.rmtree(args[0], ignore_errors=True)
    print("work dir removed; nothing was written.")


def cmd_check(args):
    if len(args) != 2:
        die("usage: check <file.md> <raw.txt>")
    err = check(open(args[0], encoding="utf-8").read(), open(args[1], encoding="utf-8").read())
    print("ok — every word matches the captions" if not err else f"FAIL: {err}")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    cmds = {"setup": cmd_setup, "where": cmd_where, "fetch": cmd_fetch, "build": cmd_build,
            "visuals": cmd_visuals, "strip": cmd_strip, "check": cmd_check, "discard": cmd_discard}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]](sys.argv[2:])
