# yt-notes

A [Claude Code](https://claude.com/claude-code) skill that turns a YouTube video into a complete,
checked transcript in Markdown, in any language: organized into sections, with a timestamp link on
every heading, optional study visuals, and optional PDF or HTML copies with the diagrams drawn.

```
/yt-notes https://www.youtube.com/watch?v=VIDEO_ID
```

## Highlights

- **Complete and checked.** Every word is compared with the video's captions before the file is
  saved. Nothing is summarized or rewritten.
- **Obvious caption mistakes fixed, each one marked.** When automatic captions mishear a word
  ("cash" for "cache"), Claude fixes it only when the context proves the right word. Every fix is a
  footnote that keeps the original caption words, and one command removes them all.
- **Any language.** Captions in the video's own language, sentences split correctly in every script
  (including Chinese, Japanese and Thai, which use no spaces), labels in the file's language, and
  right-to-left layout for Arabic, Hebrew, Persian and Urdu in PDF and HTML.
- **Translations.** Ask for another language and you get human-made subtitles when the video has
  them, or YouTube's machine translation, clearly labelled.
- **Videos without captions.** With your agreement, Whisper transcribes the audio on your machine.
- **Organized.** Sections follow the creator's own chapters when the video has them, and the
  speaker's transitions when it doesn't. Each heading links to that moment in the video.
- **Study visuals, only where they help.** Diagrams, flows, tables and charts are added where a
  teacher would stop and draw, and every one is checked before it is saved.
- **PDF and HTML.** Export any transcript, or any Markdown file, with the diagrams rendered.
- **Ready for your notes app.** Properties (title, channel, link, date, length, language, tags) for
  Obsidian and similar tools, and a plain style for apps that don't support callouts.
- **Sets itself up.** On first use it installs what it needs (yt-dlp, and the diagram engine if you
  use visuals) into its own cache folder.

## Install

As a plugin (Claude Code 2.1.275 or later):

```
/plugin install yt-notes --marketplace sagdish/yt-notes
```

Installed this way, the command is `/yt-notes:yt-notes`.

Or as a personal skill, which gives the shorter `/yt-notes`:

```bash
git clone https://github.com/sagdish/yt-notes ~/.claude/skills/yt-notes
```

Each run asks where to save the file (by default in `exports/` inside the skill's folder), the
format (Markdown, PDF or HTML; PDF by default) and whether you want study visuals, then writes it.
The first run also installs yt-dlp.

**Upgrading from yt-transcript:** the skill was renamed. Your settings and downloaded tools move
over automatically on the first run. If you cloned it into `~/.claude/skills/yt-transcript`, rename
that folder to `yt-notes`.

## Usage

| Command | Result |
|---|---|
| `/yt-notes <link>` | Transcript. Claude asks whether to add study visuals. |
| `/yt-notes --visuals <link>` | Transcript with study visuals. |
| `/yt-notes --text-only <link>` | Transcript only, no visuals question. |
| `/yt-notes --pdf <link>` | A PDF next to the Markdown file, without the format question. `--html` for an HTML copy, `--md` for Markdown only. |
| `/yt-notes <link>` "in English" | The transcript in another language (see [Languages](#languages)). |
| `/yt-notes --visuals <file.md>` | Adds study visuals to a Markdown file you already have. |
| "Export this file as a PDF" | Writes a PDF (or HTML) of any Markdown file, diagrams rendered. |

You can also describe what you want in plain words, for example "save the transcript of this video
with diagrams, and make a PDF".

## What you get

A transcript file looks like this:

```markdown
---
title: "How Database Indexes Work"
channel: "Example Channel"
url: https://www.youtube.com/watch?v=VIDEO_ID
video_id: VIDEO_ID
published: 2024-03-18
duration: "14:32"
caption_track: en-orig
caption_kind: auto
language: en
transcript: polished
tags: ["youtube", "databases"]
---

# How Database Indexes Work

Example Channel · https://www.youtube.com/watch?v=VIDEO_ID · 14:32 · verbatim auto-caption transcript, section headings added at the video's own transitions, obvious mistakes corrected, each one marked

## Why queries get slow [0:00](https://www.youtube.com/watch?v=VIDEO_ID&t=0s)

Every table starts small, and at first every query feels instant. The database keeps a cache[^fix-1]
of recent pages. …

## How an index works [3:12](https://www.youtube.com/watch?v=VIDEO_ID&t=192s)

### B-trees [5:40](https://www.youtube.com/watch?v=VIDEO_ID&t=340s)

…

[^fix-1]: captions: "cash" → "cache"
```

With visuals, boxes like this one are added under the sections they explain. The transcript text
around them is not changed:

```markdown
<!-- study-visual:start id=lookup kind=flow -->
> [!example] Added visual: How a lookup uses the index
>
> ```mermaid
> flowchart TB
>   Q["Query"] --> I["Index<br/>sorted keys"] --> R["Matching rows"]
> ```

<!-- study-visual:end -->
```

In Obsidian, or any viewer that renders Mermaid, the box shows as a three-step diagram. In a PDF or
HTML copy it is drawn as a labelled figure, and caption fixes are listed at the end.

### How visuals are chosen

Claude reads the whole text first, then asks of each section whether a teacher would stop and draw
there. A visual is added only for a real structure in the text: parts that relate to each other,
steps in order, several things compared on the same points, a whole broken into parts, a trade-off,
or numbers the speaker actually gives. Candidates that only repeat a sentence, need facts the text
doesn't contain, or are too large to read at a glance are cut. Claude then reports what it
considered, what it kept and why it cut the rest. A story or an opinion piece often gets no visuals,
and that is a valid result.

## Languages

- **The video's own language** is found from its original audio track, its details, or YouTube's
  speech recognition, in that order. Region codes are matched (`en-US` finds `en`), and on a video
  with dubbed audio the original language is used.
- **Sentences** are split at the punctuation of every script (`. ? ! 。 ？ । ؟ ۔` and others). Many
  automatic captions (Arabic, Spanish, Hindi and Japanese among them) have no punctuation at all;
  then the text is split where the speaker pauses, measured from YouTube's per-word timings.
- **Chinese, Japanese, Thai, Lao, Khmer and Burmese** are joined without the spaces YouTube puts at
  its line breaks, and checked character by character.
- **Labels** that the skill writes (the line under the title, "Added visual", fix footnotes) are in
  the file's language: built in for Arabic, Chinese, Dutch, English, French, German, Hebrew, Hindi,
  Indonesian, Italian, Japanese, Korean, Persian, Polish, Portuguese, Russian, Spanish, Turkish,
  Ukrainian, Uzbek and Vietnamese. For other languages Claude writes them.
- **Wrong-language captions.** YouTube sometimes recognizes speech in the wrong language (Uzbek
  videos often get Turkish captions that make no sense). Claude checks the captions against the
  title before going on, and offers Whisper in the right language instead.
- **Translations.** Ask for the transcript in another language. Human-made subtitles in that
  language are used when the video has them; otherwise YouTube's machine translation, labelled as
  such in the file. YouTube often refuses machine-translation downloads (HTTP 429); when it does,
  you are offered the original language instead. Claude never translates the transcript itself.
- **Chapter titles** are the creator's own words, read from the video description. YouTube serves
  them translated into the viewer's language, so they are never taken from there.

## Caption fixes (polish)

Automatic captions mishear words. With polish on (the default), Claude fixes a word only when both
are true: it sounds like what was said, and something proves the right word (the title, the
chapters, the same term spelled correctly elsewhere, or the one term that fits the topic).

The script enforces the limits: at most 3 words on each side (12 characters in Chinese, Japanese and
Thai), no change to any number, no markup, and never on human-made captions. Each fix becomes a
footnote that keeps the caption words. `build`, `check` and `verify` undo the fixes before comparing
with the captions, so the check stays word for word.

```bash
S=~/.claude/skills/yt-notes/yt_notes.py
python3 $S strip notes/databases/indexes.md --fixes    # back to the exact captions
python3 $S setup --polish off                           # keep every new file exactly as captioned
```

## Videos without captions (Whisper)

When a video has no captions in its language, the skill says so and stops. With your agreement it
can transcribe the audio with Whisper instead, on your machine:

- It downloads the video's audio, transcribes it, and deletes the audio.
- It takes about 15 seconds per minute of video with the default `small` model on an Apple Silicon
  Mac (measured: 73 seconds for a 5-minute video).
- The text cannot be checked against captions, and the file says so. `verify` refuses such a file.
- Whisper uses the language the video is spoken in.

You can install Whisper yourself, or let the skill install it:

| Option | Command | Size |
|---|---|---|
| whisper.cpp (yours) | `brew install whisper-cpp ffmpeg` | The skill downloads the model once (about 470 MB for `small`), checked against its published checksum. |
| faster-whisper (the skill's) | `python3 $S whisper-install` | About 230 MB in the cache, plus the model (about 470 MB for `small`). |

Models: `tiny`, `base`, `small` (default), `medium`, `large-v3-turbo`. Larger is more accurate and
slower: `python3 $S setup --whisper-model large-v3-turbo`.

## Guarantees

Each of these is enforced by the script, not left to the model:

- **The words match the captions.** `build` refuses to save a transcript whose words, with any fixes
  undone, differ from the captions in any way. `verify` re-downloads the captions later and checks a
  saved file again.
- **Fixes are small, marked and reversible.** A fix that is too long, changes a number, or doesn't
  match its footnote is refused. `strip --fixes` restores the exact captions, byte for byte.
- **Visuals never change the text.** `visuals` refuses to save unless the file, with the visual
  blocks removed, is byte for byte the file it started from. Each block is labelled as an added
  visual.
- **Chart numbers come from the text.** A chart is refused if a number does not appear in its own
  section, in digits or English words, or in an exact phrase from that section in any other language.
- **Diagrams render and fit.** Every Mermaid diagram is drawn in a real browser before saving. One
  that fails to render, or is wider than a reading column (560 px), is refused.
- **Damaged blocks are never guessed at.** If a visual block's markers or a fix's footnote have been
  edited by hand, the script stops and names the problem instead of removing anything.
- **Captions only, unless you choose Whisper.** No video is downloaded, and no caption or audio
  files are kept.
- **Nothing overwritten.** An existing transcript filename is refused.

## Output formats and styles

- **Markdown** is always written; it is the source for everything else.
- **Each run asks the format:** Markdown, PDF or HTML, with PDF as the default. A PDF or HTML copy
  is written next to the Markdown file with the same name. Exporting again replaces the earlier
  copy. HTML copies are single, self-contained files.
- **Visual style.** `obsidian` (default) writes visuals as Obsidian callouts. `plain` writes them as
  standard blockquotes that render correctly on GitHub and in most Markdown apps.

```bash
python3 $S setup --formats md        # make Markdown only the default answer (default: md,pdf)
python3 $S setup --style plain        # visuals as plain blockquotes
python3 $S setup --paper letter       # PDF paper size (default: a4)
```

## Requirements

| Requirement | Needed for | Notes |
|---|---|---|
| Python 3.9 or later | everything | The Python that ships with macOS works. No packages needed. |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | fetching captions | Installed automatically on first use, checksum-verified, into `~/.cache/yt-notes/`: 3 MB when Python 3.10+ is available, otherwise yt-dlp's standalone build (up to 125 MB). A yt-dlp already on your `PATH` is used instead. |
| Node.js 20 or later, with npm | diagrams, PDF, HTML | The drawing engine (Mermaid, Puppeteer, Marked, with locked versions) installs once into `~/.cache/yt-notes/engine/`, about 180 MB. Tables and text work without Node. |
| Chrome, Edge or Chromium | diagrams, PDF, HTML | An installed browser is used in headless mode with a temporary profile. If none is found, a headless browser (about 190 MB) is downloaded once. |
| Whisper | videos without captions only | See [Videos without captions](#videos-without-captions-whisper). whisper.cpp also needs ffmpeg. |
| [Deno](https://deno.com) | optional | yt-dlp can use it for some YouTube pages. |

Run `python3 ~/.claude/skills/yt-notes/yt_notes.py doctor` to check everything at once.

## Configuration

Notes go to `exports/` inside the skill's folder until you add a save folder of your own; then
yours are offered instead. Each run still asks where to save, and you can name any other folder
then. Settings are stored in `~/.config/yt-notes/config.json`. You can keep several save folders,
each with a label:

```bash
python3 $S setup ~/notes/learning --label "study notes"
python3 $S setup ~/notes/work --label "work research"
python3 $S setup --show
```

Transcripts are saved one topic folder deep: `<save folder>/<topic>/<file>.md`. A new topic folder
gets a one-line `README.md` describing it. Folders whose names start with `.` or `_`, and a folder
named `inbox`, are left out of the topic list.

| Environment variable | Effect |
|---|---|
| `YT_NOTES_ROOT` | Use this save folder for one run instead of the configured ones. |
| `YT_NOTES_CONFIG` | Use a different settings file. |
| `XDG_CACHE_HOME` | Move the cache (default `~/.cache`). |
| `YT_NOTES_BROWSER` | Path to a specific Chrome or Chromium for diagrams and exports. |
| `YT_NOTES_NO_INSTALL` | Never install yt-dlp automatically. |

The old `YT_TRANSCRIPT_*` names still work.

## Script reference

Claude runs these for you; they are listed for scripting and troubleshooting.

| Command | What it does |
|---|---|
| `setup <folder> [--label …]` | Adds a save folder. Also `--show`, `--style`, `--formats`, `--paper`, `--polish`, `--whisper-model`. |
| `where` | Lists the save folders (or the default `exports/`), the topic folders inside them and the default formats. |
| `fetch <link> [--lang xx] [--whisper] [--cookies-from-browser NAME]` | Downloads the captions (or, with `--whisper`, transcribes the audio) into a temporary work folder. |
| `build <workdir> <plan.json> <out.md> [--md \| --pdf \| --html] [--anywhere]` | Writes and checks the transcript. `--md` = Markdown only; with no format flag, the saved default. |
| `visuals <file.md> <visuals.json> [--style …] [--lang xx] [--label …] [--md \| --pdf \| --html]` | Adds or replaces study visuals in any Markdown file. |
| `export <file.md> [--pdf] [--html] [--paper a4\|letter]` | Writes PDF or HTML copies with diagrams drawn. |
| `strip <file.md> [--visuals \| --fixes]` | Removes the added visuals and caption fixes (both by default). |
| `verify <file.md>` | Re-downloads the captions and checks the file word for word. |
| `check <file.md> <captions.txt>` | Checks a file against a captions text file. |
| `discard <workdir>` | Removes a work folder that was not built. |
| `whisper-install [--model NAME]` | Installs faster-whisper and a model into the cache. |
| `doctor` | Checks Python, yt-dlp, Node.js, the engine, the browser, Whisper and the save folders. |
| `uninstall [--yes]` | Removes the downloaded tools and the settings. Never touches your notes. |

Exit codes: `0` success, `1` refused or check failed, `2` YouTube or yt-dlp problem, `4` a required
tool is missing or could not be installed, `5` no captions in the video's language.

## Troubleshooting

| Message | What to do |
|---|---|
| "confirm you're not a bot" | YouTube is limiting your network. Wait and try again, or ask Claude to fetch with `--cookies-from-browser <browser>` to use your YouTube login from that browser. |
| "no captions in its language" | Agree to Whisper, or ask for one of the other caption languages it lists. |
| "refused its machine translation" | YouTube limits these downloads. Save the original language, or try again later. |
| "yt-dlp failed" | The installed copy updates itself and retries once. A yt-dlp you installed yourself needs updating (`brew upgrade yt-dlp`, `pipx upgrade yt-dlp` or `yt-dlp -U`). |
| A diagram is refused as too wide | Claude reshapes it (fewer boxes side by side, shorter labels, or top to bottom). |
| `verify` reports a difference on an automatic or translated transcript | YouTube sometimes regenerates automatic captions and translations, so the difference can come from YouTube's side. |
| Anything else | Run `doctor`. |

## Uninstall

```bash
python3 ~/.claude/skills/yt-notes/yt_notes.py uninstall --yes
rm -rf ~/.claude/skills/yt-notes          # or: /plugin uninstall yt-notes
```

The first command removes the downloaded tools (including Whisper) and the settings. Your saved
transcripts are never touched.

## Limitations

- Tested on macOS. Linux and Windows are not tested yet.
- One video per run. Playlist and channel links are refused.
- A live stream can be transcribed only after it ends.
- Caption fixes are limited to obvious mishearings; other caption mistakes stay as they are.
- YouTube often refuses machine-translation downloads; human-made subtitles are not affected.
- Speech-to-text quality depends on the Whisper model and the language.
- Filenames and topic folders use Latin letters, digits, `-`, `_` and `.`.
- Visuals in the default style use Obsidian callouts. Other apps show them as quotes; use the
  `plain` style for those.
- Diagrams need a viewer with Mermaid 11 or later. Tables render everywhere.

## Privacy and copyright

The skill talks to YouTube (to read captions, or to download audio when you choose Whisper), to
GitHub and npm (to download its tools), and to PyPI and Hugging Face (only when Whisper is
installed). Speech-to-text runs on your machine. Nothing else leaves your machine. Transcripts are
intended for personal study. Respect the rights of the creators whose videos you transcribe, and
don't republish their words without permission.

## Development

```bash
python3 -m unittest discover tests      # offline tests, no network needed
python3 tests/engine_smoke.py           # draws diagrams and exports PDF and HTML (needs Node.js 20+)
claude plugin validate --strict .       # the plugin and marketplace manifests
```

## License

MIT. See [LICENSE](LICENSE).
