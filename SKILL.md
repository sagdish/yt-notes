---
name: yt-notes
description: Save the complete transcript of a YouTube video as a Markdown study file in any language, every word checked against the captions, with section headings and timestamp links, plus optional study visuals (diagrams, tables, comparisons, charts), optional PDF or HTML copies, YouTube's translation into another language, obvious caption mistakes fixed and marked, and Whisper speech-to-text for videos without captions. Also adds visuals to, or exports, any existing Markdown file. Use when the user gives a YouTube link and asks for its transcript, subtitles, captions or "the text of this video", wants to save a video for study, wants it in another language, or asks to add visuals or diagrams to a transcript, article or notes (`/yt-notes [--visuals | --text-only] [--md | --pdf | --html] <url|file>`).
---

# YouTube video to Markdown notes

One script does every mechanical step: `yt_notes.py`, next to this file.
`S=<this skill's folder>/yt_notes.py`. **Always single-quote a link** (zsh reads `?` as a pattern).

Your judgment covers four things only: **where the file goes (ask the user)**, **where the section
headings go**, **which caption mistakes are obvious enough to fix**, and **which visuals earn a
place**. Never write your own fetch, conversion, insertion or export code, and never change the
transcript's words except through marked fixes.

**Talk to the user in the language they write in**, questions included.

## Which way in

| The user gave | Do |
|---|---|
| a link, no visuals flag | Checklist A. Ask the visuals question in step 2. |
| `--visuals <link>` | Checklist A with visuals: yes. Don't ask the visuals question. |
| `--text-only <link>` | Checklist A with visuals: no. Don't ask the visuals question. |
| a link and a language ("in English", "translate it to Spanish") | Checklist A, fetch with `--lang <code>`. |
| `--visuals <file>`, or "add visuals to this file" | Checklist B only. No fetch, no save question. |
| `--md`, `--pdf` and/or `--html` with any of the above | That is the format: pass the same flags on (see step 5). Don't ask the format question. |
| "export this file as a PDF / HTML" | `python3 $S export '<file>' --pdf` (or `--html`). Then report the path. |
| "stop fixing captions" / "fix captions again" | `python3 $S setup --polish off` (or `on`). |

## Checklist A: a video

- [ ] **1. Fetch.** `python3 $S fetch '<link>'` (add `--lang <code>` when the user asked for a language).
  - `first run: installing yt-dlp` = a one-time setup; mention it in one line.
  - **Exit 5, `NO CAPTIONS`** = say plainly that the video has no captions in its language. Then offer
    speech-to-text in one message: "I can transcribe the audio on your machine with Whisper. It
    downloads the audio (deleted afterwards), downloads a speech model the first time, and takes
    about 15 seconds per minute of video. The text can't be checked against captions. Go ahead?"
    If `other captions` lists human-made subtitles in the user's language, mention them in the same
    message as the other option. No = stop. Yes = `fetch '<link>' --whisper --lang <code>`, where
    the code is the language the video is spoken in (`video_language`, or the title and description).
  - **Exit 4, `NO WHISPER`** = ask: "Do you want to install Whisper yourself (`brew install
    whisper-cpp ffmpeg`), or should I install it into this skill's cache (about 230 MB plus a 470 MB
    speech model)?" Default: they install it. "Install it for me" = `python3 $S whisper-install`, then fetch
    again with `--whisper`.
  - **`refused its machine translation`** (exit 2) = YouTube often refuses these. Tell the user and
    offer the transcript in the video's own language instead.
  - Other exit 2 = stop. Tell the user the sentence it printed. Don't run fixes and don't try another
    tool. If the sentence offers `--cookies-from-browser`, run that only after the user agrees and
    names their browser.
  - Other exit 4 = a required tool is missing or failed to install. Tell the user the sentence. Stop.
  - `ALREADY SAVED: <path>` = tell the user and ask whether they want a second copy. Stop until they
    answer. (`saved before in another language` is only information.)
  - Note the `workdir:` line; every later step needs it.
  - Whenever the user stops or declines before step 4: `python3 $S discard <workdir>`.
- [ ] **2. Check the language.** Read the first 30 lines of `<workdir>/units.txt` and compare them with
  the title and the chapter titles. If the captions are not real sentences in `captions_language`
  (YouTube sometimes recognizes speech in the wrong language: an Uzbek video captioned as Turkish
  reads as Turkish-looking words that make no sense, under an Uzbek title), stop: tell the user
  YouTube's captions are in the wrong language, run `discard`, and offer Whisper in the language the
  video is really spoken in, exactly as for exit 5.
- [ ] **3. Ask, then stop.** Run `python3 $S where`.
  - `where` lists the save folders, their topic folders and the default formats.
  - **Exit 3 = first run** (no save folder yet): question 1 also asks which folder their notes go
    in, suggesting the folder `where` printed. Once they answer, run
    `python3 $S setup '<folder>' --label '<what goes there>'` before building; it is remembered.
    Never save inside this skill's folder: a plugin update replaces it. If `where` printed notes
    saved by version 3.1, tell the user where they are.
  - A folder the user names that isn't a save folder: save there with `--anywhere` (step 5).
  - Send ONE message with up to four questions:
    1. **Where:** the topic folder and filename (on the first run, the notes folder too). Offer a default: the existing topic that fits, and
       `suggested_file` or a shorter kebab-case name (for a title in another script, a short
       English or transliterated name). A new topic folder needs a one-line description (it becomes
       that folder's README).
    2. **Visuals** (skip when `--visuals` or `--text-only` was given): "Add study visuals (diagrams
       and tables where they help), or text only?" Offer no default.
    3. **Format** (skip when `--md`, `--pdf` or `--html` was given): "Markdown, PDF or HTML? The
       Markdown file is always written; a PDF or HTML copy is made from it." Default: the
       `formats` on `where`'s `defaults:` line (`md,pdf` = PDF, `md` = Markdown, `md,html` = HTML).
    4. **Language** (only when `captions_language` differs from the language the user writes in, and
       they didn't ask for one): "The video is in <language>. Keep it, or a translation into
       <their language>?" Say whether `other captions` has human-made subtitles in that language;
       otherwise the translation is YouTube's machine translation. Default: keep it.
  - Wait. "ok" or "yes" accepts your defaults for 1, 3 and 4 but does **not** answer 2: if the
    visuals question is still open, ask it again in one line and wait.
  - A translation: `discard` the work dir and fetch again with `--lang <code>`.
  - "Always PDF" / "always Markdown" (or similar) = `python3 $S setup --formats md,pdf` (or `md`,
    `md,html`) once, then carry on. The format question is still asked; this changes its default.
- [ ] **4. Plan.** Write `<workdir>/plan.json`:
  ```json
  {"headings": [{"unit": 1, "level": 2, "title": "Why queries get slow"},
                {"unit": 24, "level": 2, "title": "How an index works"},
                {"unit": 31, "level": 3, "title": "B-trees"}],
   "fixes": [{"unit": 12, "from": "cash", "to": "cache"}],
   "blurb": "Databases and data engineering",
   "tags": ["databases"]}
  ```
  - **Fetch printed `chapters:`** = the creator's chapters are the level-2 headings. Start from
    `<workdir>/chapters.json` and keep its titles exactly as written. When the captions have no
    punctuation, you may move a chapter by one or two units so it starts where a sentence starts.
    Add a level-3 heading only where a chapter has clearly named sub-parts.
  - **No chapters** = read `<workdir>/units.txt` (`N| m:ss| text`) in full and place level-2 headings
    at the speaker's own transitions ("first, let's…", "now let's talk about…"), roughly one per
    2 to 4 minutes of video. Level 3 = named sub-parts inside one section.
  - **`long video`** = read `units.txt` in parts of about 300 lines, placing headings part by part.
  - The first heading is level 2 at unit 1. Units only go forward. Your own titles: short, in the
    file's language.
  - **`fixes`** only when fetch printed `polish: on`. While reading, note words the captions clearly
    misheard and fix only those you are sure of:
    - it sounds like what was said ("cash" for "cache", "my sequel" for "MySQL"), and
    - something proves the right word: the title, the chapters, the same term written correctly
      elsewhere, or the one term that fits the topic.
    - Never grammar, punctuation, filler words, word order, style, numbers, or a name you can't
      confirm. At most 3 words on each side (12 characters in Chinese, Japanese or Thai). When in
      doubt, leave it: the captions stay as they are.
    - For a translation, fetch also wrote `original.txt` (the video's own captions): check a fix
      against it.
    - `from` is copied exactly from that unit; add `"nth": 2` when it appears more than once there.
  - `labels` only when fetch printed `labels: none built in`: write the keys it lists in the file's
    language.
  - `blurb` only for a new topic folder. `tags` is optional: single words, no spaces.
- [ ] **5. Build.** `python3 $S build <workdir> <workdir>/plan.json '<save folder>/<topic>/<file>.md'`
  - Add the format from step 3: `--md` (Markdown only), or `--pdf` and/or `--html`. **When visuals
    are coming**, build with `--md` and give the format flags to the `visuals` run in Checklist B
    instead, so the copies include the visuals.
  - A path the user named outside the save folders: add `--anywhere`.
  - It writes the file (properties, title, source line, headings with timestamp links, each fix
    marked with a footnote), checks every word against the captions underneath the fixes and
    deletes the work dir. `REFUSED:` = nothing written; fix what it names and re-run.
- [ ] **6. Visuals**: only if the user said yes. Checklist B on the file just written.
- [ ] **7. Report** in plain words, in the user's language: the path of every file written; words,
  sections and sub-sections; whether the headings came from the creator's chapters; where the text
  came from when it isn't the video's own captions (a translation, Whisper); each fix (`from → to`);
  and, with visuals, the visuals report from Checklist B. When fixes were made, add one line:
  "Fixes are marked; say 'stop fixing captions' to keep files exactly as captioned." No summary of
  the video, no next steps.

## Checklist B: visuals for a file

The goal: the file reads like study material, not a wall of text. A visual is **support**, never
decoration. Zero visuals is a valid, honest result.

- [ ] **1. Read the whole file first.** Decide nothing until you've read to the end: ideas that are
  introduced in one section and broken down later are only visible from the whole.
- [ ] **2. Is it worth drawing at all?** Study material, articles, how-tos and explainers (anything with
  parts, steps, comparisons, numbers or processes): go on. Mostly story, opinion, chat or feeling
  with no structure: tell the user there is nothing worth drawing, add nothing, stop.
- [ ] **3. Walk it section by section** and ask: *"If I were teaching this to someone, would I stop and
  draw here?"* Only a real shape in the text earns a visual:

  | The text has… | Draw | Format |
  |---|---|---|
  | parts that relate to each other (the sides of a marketplace, a system's components) | diagram | Mermaid `block-beta` (fixed layouts, such as a triangle) or `flowchart` |
  | steps in order (a framework, a journey, a process) | flow | Mermaid `flowchart TB` (`LR` only for 2 or 3 short steps) |
  | several things described on the same points | table / comparison | Markdown table |
  | a whole broken into pieces, a formula | tree / formula | Mermaid `flowchart LR` (root left, parts stacked right), or a table |
  | a trade-off, a cause and its guard | pair | two- or three-column table |
  | real numbers the source says | chart | Mermaid `pie` / `xychart-beta` |

- [ ] **4. Look across sections.** An idea spread over several sections is drawn ONCE: as a map at the
  start of the part that explains it, or where it's first introduced. Never one visual per section.
- [ ] **5. Write candidates, then cut.** For each: section, kind, what it shows, and `why` (the one thing
  the reader gets faster from the visual than from the paragraph). Cut it if:
  - it restates one or two sentences (the text is already easy),
  - it needs anything the text doesn't say: no invented numbers, examples, labels or links between things,
  - it's too big to take in at a glance (split it or drop it),
  - it's decoration: emoji, colour for its own sake, a title that repeats the heading.

  **Every diagram must fit a reading column (560px) at full size**, because Obsidian cuts off a wider
  diagram instead of shrinking it. Keep label lines short (split them with `<br/>`), and never put
  many boxes side by side: long flows run top to bottom; a whole-and-parts tree runs left to right
  with the parts stacked. The script draws each diagram in a real browser, measures it and refuses
  one that doesn't fit; turn it or shorten it rather than dropping content.
- [ ] **6. Write `visuals.json`** (next to the file or in a temp folder):
  ```json
  [{"id": "three-sides", "section": "How the marketplace works", "nth": 1,
    "kind": "diagram", "title": "A three-sided marketplace",
    "why": "three parties all connected through one platform, seen at once",
    "body": "```mermaid\nblock-beta\n  columns 3\n  space B[\"buyers\"] space\n  space P((\"platform\")) space\n  S[\"sellers\"] space C[\"couriers\"]\n  B --- S\n  B --- C\n  S --- C\n```"}]
  ```
  - `section` = a heading's text (without its timestamp); `nth` only when several headings share it.
    The visual goes at the end of that section's own text (before its first sub-heading).
    `after_text` (an exact phrase) puts it after that paragraph instead.
  - `kind`: `diagram flow table comparison formula tree pair chart`. `title` short; `why` one line.
  - `body`: Markdown: a table, a fenced ```` ```mermaid ```` block, or short text. No `#` headings.
  - Labels, titles and text use the source's own terms and language.
  - A chart's numbers must be said in its section. Digits and English number words are found
    automatically; for numbers said in words of another language, add
    `"numbers": {"45": "сорок пять процентов"}` with the exact phrase from that section.
- [ ] **7. Run** `python3 $S visuals '<file>' <visuals.json>` (add the format from Checklist A step 3:
  `--md`, or `--pdf` and/or `--html`; for a file the user brought, `--md` unless they asked for a
  copy; for a file that isn't a transcript, add `--lang <code>` of the file's language so the box
  label is in it). The first diagram installs the drawing engine once (needs Node.js 20+). It
  refuses a chart number its section doesn't say, a diagram that doesn't draw or doesn't fit, and
  anything that would change one byte of the file's own text. `REFUSED:` = nothing written; fix what
  it names and re-run. Running it again replaces the visuals it added before (never duplicates);
  `python3 $S strip '<file>' --visuals` removes them all.
- [ ] **8. Report in chat only** (never into the file): "considered N, kept M", then one line per kept
  visual (what it shows) and one line per cut (why). List any `chart number from a quote` lines the
  script printed. Then stop.

## Rules

- The transcript's words are never edited, summarized or "cleaned". The only change is a marked fix
  (step 4), and the original caption words stay in its footnote. `build`, `check` and `verify` undo
  the fixes and refuse any file whose words differ from the captions. `strip --fixes` gives back the
  exact captions. Visual blocks are skipped by that check and marked in the file as added.
- Captions only, unless the user agreed to Whisper for a video without usable captions. Never keep
  audio or `.vtt`/`.srt` files.
- Never overwrite a transcript: an existing filename is refused; ask for another. PDF and HTML copies
  are derived from the `.md` and are replaced when exported again.
- One video per run. Several links = Checklist A once per link, with one question covering all of them.
- Something looks broken (a tool, a folder, the browser): `python3 $S doctor` and tell the user what it says.
