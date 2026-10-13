# Changelog

## 3.1.0 (2026-10-13)

- **Works on the first run with no setup:** notes go to `exports/` inside the skill's folder until
  you add a save folder of your own. Where to save is still asked every time.
- **The format is asked every time:** Markdown, PDF or HTML, with PDF as the default. The Markdown
  file is always written. `--md` means Markdown only; `setup --formats` changes the default.
- Exit code 3 (no save folder) is gone: there is always one.

## 3.0.0 (2026-10-13)

- **Renamed to yt-notes** (the command is `/yt-notes`). Settings and downloaded tools move over from
  the old yt-transcript folders on the first run, and the old `YT_TRANSCRIPT_*` variables still work.
- **Installable as a Claude Code plugin:** `/plugin install yt-notes --marketplace sagdish/yt-notes`.
- **Languages.**
  - The video's language comes from its original audio, its details or YouTube's speech
    recognition. Region codes match (`en-US` finds `en`), and the original audio wins over dubs.
  - Sentences split at the punctuation of every script. Captions without punctuation split where
    the speaker pauses, measured from YouTube's per-word timings.
  - Chinese, Japanese, Thai, Lao, Khmer and Burmese join without YouTube's line-break spaces and
    are checked character by character.
  - The words the skill writes into a file are in the file's language: 21 languages built in, Claude
    writes them for the rest.
  - PDF and HTML copies are right to left for Arabic, Hebrew, Persian and Urdu, with one font per script.
  - Chapter titles are the creator's own words from the description, not YouTube's translation of them.
  - Claude checks that the captions are in the video's real language before going on.
- **Translations:** `--lang` in another language than the video's uses human-made subtitles, or
  YouTube's machine translation, labelled in the file. Before, `--lang` quietly took the machine
  translation and called it the speaker's own captions. A refused translation (HTTP 429, common)
  gets its own message.
- **Caption fixes (polish):** obvious mishearings in automatic captions are fixed, each one marked
  with a footnote that keeps the caption words. The script limits a fix to 3 words, refuses any
  change to a number, undoes fixes before every check, and `strip --fixes` restores the exact
  captions. `setup --polish off` turns it off.
- **Whisper speech-to-text** for videos without captions, only with the user's agreement: a
  whisper.cpp the user installed, or faster-whisper installed by `whisper-install`. The audio is
  deleted after transcription. A video without captions exits with code 5 instead of 2.
- **Chart numbers in any language:** a chart number said in words of another language is tied to
  the exact phrase from its section.
- **Duplicate check** counts only a saved copy in the same language.
- **PDF and HTML copies** with diagrams drawn and visual boxes styled: `--pdf`, `--html`, the new
  `export` command, and a saved default (`setup --formats`). Paper size: `setup --paper`.
- **Creator chapters become the section headings** when the video has them (`chapters.json`).
- **Timestamp links** on every heading, pointing to that moment in the video.
- **Properties block** at the top of each file: title, channel, link, video id, upload date,
  length, caption track, tags.
- **yt-dlp installs itself** on first use, checksum-verified, into the cache. When a fetch fails for
  an unknown reason, a newer yt-dlp is installed and the fetch is retried once.
- **Clear messages** for bot checks, age-restricted, private and members-only videos, rate limits and
  connection problems. `--cookies-from-browser` for the cases that need a signed-in account.
- **One drawing engine** (Mermaid, Puppeteer and Marked, with a lockfile) replaces the parse-only
  checker: every diagram is drawn in a real browser and its real width is measured. The old width
  estimate missed labels written without quotes.
- **Visuals question** is now its own question with no default; new `--text-only` flag.
- **Visual styles:** `obsidian` callouts (default) or `plain` blockquotes (`--style`, `setup --style`).
- **Damaged visual blocks are refused** instead of stripped: an edited marker used to let `visuals`
  and `strip` delete the user's own text up to the next block.
- **Captions without punctuation** now get paragraph breaks instead of one paragraph per section.
- **Sounds like [Music]** are set in italics, apart from the speech.
- **Charts** must use numbers from their own section, written in digits or English words.
- **`verify`** re-downloads the captions and checks a saved file word for word. **`doctor`** checks
  every requirement. **`uninstall`** removes the downloaded tools and settings.
- **Plan file** (`plan.json`) carries the headings, the topic description and tags, so nothing passes
  through the shell. A bare headings list still works.
- `fetch --lang` without a value now gives a message instead of a Python error.
- Tests (offline unit tests with a stand-in yt-dlp and Whisper, and an engine smoke test) and a
  GitHub Actions workflow.

## 2.0.0 (2026-09-29)

- **Study visuals.** Optional diagrams, tables, comparisons and charts, chosen by a read-the-whole-
  text-first pass with an explicit cut step. Asked with the save question, or forced with
  `--visuals <url>`.
- **Visuals for any markdown file:** `--visuals <file>`. `visuals` replaces its own blocks on a
  re-run; `strip` removes them all.
- Every diagram must fit a reading column (~560px) at full size, because Obsidian cuts off wider ones. The
  script estimates the width and refuses a diagram that won't fit, and label lines over 26 characters.
- Every Mermaid diagram is parsed with the real parser before saving; a chart may only show numbers
  the text says; the file's own text must stay byte-for-byte unchanged or nothing is written.
- **Anyone can use it:** save folders come from `setup` (`~/.config/yt-transcript/config.json`) or
  `$YT_TRANSCRIPT_ROOT` instead of hard-coded paths. `--outside-vault` is now `--anywhere`.
- Text-only output is unchanged from 1.0: same bytes for the same video and headings.

## 1.0.0 (2026-09-28)

- Complete verbatim transcript from captions, section headings at the speaker's transitions,
  word-for-word check against the captions, duplicate-video warning.
