---
name: yt-transcript
description: Save the complete transcript of a YouTube video as one markdown file, every word verbatim, with section headings — and, on request, study visuals (diagrams, tables, comparisons, charts) placed where a teacher would draw them. Also adds visuals to any existing markdown file. Captions only — never downloads the video. Use when the user gives a YouTube link and asks for its transcript, subtitles, captions or "the text of this video", asks to save a video for study, or asks to add visuals/diagrams to a transcript, article or notes (`/yt-transcript --visuals <url|file>`).
---

# YouTube transcript → markdown, with optional study visuals

One script does every mechanical step: `yt_transcript.py`, next to this file.
`S=<this skill's folder>/yt_transcript.py`. **Always single-quote a link** (zsh reads `?` as a pattern).

Your judgment is limited to three things: **where the file goes (ask the user)**, **where the
section headings go**, and **which visuals earn a place**. Never write your own fetch, conversion
or insertion code, and never edit the transcript's words.

## Which way in

| The user gave | Do |
|---|---|
| a link, no flag | Checklist A. Ask the visuals question together with the save question. |
| `--visuals <link>` | Checklist A with visuals: yes. Don't ask the visuals question. |
| `--visuals <file>` (or "add visuals to this file") | Checklist B only. No fetch, no save question. |

## Checklist A — a video

- [ ] **1. Fetch.** `python3 $S fetch '<link>'` (add `--lang xx` only if the user asks for a language).
  - Exit 2 = stop. Tell the user the one line it printed. Don't run fixes, don't try another tool.
  - `ALREADY SAVED: <path>` = tell the user and ask whether they want a second copy. Stop until they answer.
  - Note the `workdir:` line — every later step needs it.
  - Whenever the user stops or declines before step 4: `python3 $S discard <workdir>`.
- [ ] **2. Ask, then stop.** Run `python3 $S where`.
  - Exit 3 (no save folder yet): ask which folder their notes live in, run
    `python3 $S setup '<folder>' --label '<what goes there>'`, then `where` again.
  - Ask ONE message: which topic folder and filename (offer a default: the existing topic that fits,
    `suggested_file` or a shorter kebab-case name), and — unless `--visuals` was given — "With study
    visuals, or text only?" A new topic folder needs a one-line description (it becomes its README).
  - Wait. "yes"/"ok" = your defaults, visuals included.
- [ ] **3. Headings.** Read `<workdir>/units.txt` in full (`N| sentence`). Write `<workdir>/headings.json`:
  ```json
  [{"unit": 1, "level": 2, "title": "Intro"},
   {"unit": 25, "level": 2, "title": "How AI products are built"},
   {"unit": 38, "level": 3, "title": "RAG"}]
  ```
  - `level 2` = the speaker's own section transitions ("first, let's…", "now let's talk about…").
    Aim for 6–12 in a 20–30 min video. `level 3` = named sub-parts inside one section.
  - The first heading is level 2 at unit 1. Units only go forward. Titles: short, in the video's terms.
- [ ] **4. Build.** `python3 $S build <workdir> <workdir>/headings.json '<save folder>/<topic>/<file>.md'`
  (new topic folder: add `--blurb "<one-liner>"`; a path the user named outside the save folders: `--anywhere`).
  It writes the file, re-checks every word against the captions, deletes the work dir.
  `REFUSED:` = nothing written; fix what it names and re-run.
- [ ] **5. Visuals** — only if the user said yes: Checklist B on the file just written.
- [ ] **6. Report** in plain words: it ran just now, the path, words · sections · sub-sections, and
  (with visuals) the visuals report from Checklist B. No summary of the video, no next steps.

## Checklist B — visuals for a file

The goal: the file reads like study material, not a wall of text. A visual is **support**, never
decoration. Zero visuals is a valid, honest result.

- [ ] **1. Read the whole file first.** Decide nothing until you've read to the end — ideas that
  are introduced in one section and broken down later are only visible from the whole.
- [ ] **2. Is it worth drawing at all?** Study material, articles, how-tos, explainers — anything with
  parts, steps, comparisons, numbers or processes: go on. Mostly story, opinion, chat or feeling
  with no structure: tell the user there is nothing worth drawing, add nothing, stop.
- [ ] **3. Walk it section by section** and ask: *"If I were teaching this to someone, would I stop and
  draw here?"* Only a real shape in the text earns a visual:

  | The text has… | Draw | Format |
  |---|---|---|
  | parts that relate to each other (a 3-sided marketplace, a system's pieces) | diagram | Mermaid `block-beta` (fixed layouts, e.g. a triangle) or `flowchart` |
  | steps in order (a framework, a journey, a process) | flow | Mermaid `flowchart TB` (`LR` only for 2–3 short steps) |
  | several things described on the same points | table / comparison | markdown table |
  | a whole broken into pieces, a formula | tree / formula | Mermaid `flowchart LR` (root left, parts stacked right), or a table |
  | a trade-off, a cause and its guard | pair | two- or three-column table |
  | real numbers the source says | chart | Mermaid `pie` / `xychart-beta` |

- [ ] **4. Look across sections.** An idea spread over several sections is drawn ONCE — as a map at
  the start of the part that explains it, or where it's first introduced. Never one visual per section.
- [ ] **5. Write candidates, then cut.** For each: section · kind · what it shows · `why` — the one thing
  the reader gets faster from the visual than from the paragraph. Cut it if:
  - it restates one or two sentences (the text is already easy),
  - it needs anything the text doesn't say — no invented numbers, examples, labels or links between things,
  - it's too big to take in at a glance (split it or drop it),
  - it's decoration: emoji, colour for its own sake, a title that repeats the heading.

  **Every diagram must fit a reading column (about 560px) at full size** — Obsidian cuts off a wider
  diagram instead of shrinking it. So: label lines of at most 26 characters (split with `<br/>`),
  and never many boxes side by side — long flows run top to bottom, a whole-and-parts tree runs
  left to right with the parts stacked. The script estimates the width and refuses a diagram that
  won't fit; turn it or shorten it rather than dropping content.
- [ ] **6. Write `visuals.json`** (next to the file or in a temp folder):
  ```json
  [{"id": "three-sides", "section": "Company and product", "nth": 2,
    "kind": "diagram", "title": "A three-sided marketplace",
    "why": "three parties all connected through one platform, seen at once",
    "body": "```mermaid\nblock-beta\n  columns 3\n  space C[\"customers\"] space\n  space U((\"Uber Eats\")) space\n  R[\"restaurants\"] space K[\"couriers\"]\n  C --- R\n  C --- K\n  R --- K\n```"}]
  ```
  - `section` = a heading's exact text; `nth` only when several headings share it. The visual goes at
    the end of that section's own text (before its first sub-heading). `after_text` (an exact phrase)
    puts it after that paragraph instead.
  - `kind`: `diagram flow table comparison formula tree pair chart`. `title` short; `why` one line.
  - `body`: markdown — a table, a fenced ```` ```mermaid ```` block, or short text. No `#` headings.
  - Labels use the source's own terms and language. A caption mistake ("queers" for couriers) may be
    written correctly in a label — never in the text.
- [ ] **7. Run** `python3 $S visuals '<file>' <visuals.json>`. It checks every diagram with the real
  Mermaid parser (first run installs the checker once, needs Node.js), refuses a chart whose numbers
  the text never says, inserts the blocks, and refuses unless the file's own text is byte-for-byte
  unchanged. `REFUSED:` = nothing written; fix what it names and re-run. Running it again replaces
  the visuals it added before (never duplicates); `python3 $S strip '<file>'` removes them all.
- [ ] **8. Report in chat only** (never into the file): "considered N, kept M", then one line per
  kept visual (what it shows) and one line per cut (why). Then stop.

## Rules

- The transcript's words are never edited, summarized, "cleaned" or fixed — caption mistakes stay.
  `build` and `check` refuse any file whose words differ from the captions; visual blocks are skipped
  by that check and marked in the file as added, so nothing added passes as the source's words.
- Captions only. Never download video or audio; never save `.vtt`/`.srt` files.
- Never overwrite: an existing filename is refused; ask for another.
- One video per run. Several links = Checklist A once per link, one question covering all of them.
