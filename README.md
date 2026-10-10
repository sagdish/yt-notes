# yt-transcript

A [Claude Code](https://claude.com/claude-code) skill that turns a YouTube video into a markdown
study file: the **complete transcript, every word exactly as captioned**, split into sections at the
speaker's own transitions — and, if you want, **study visuals** (diagrams, tables, comparisons,
charts) placed where a teacher would stop and draw.

It can also add visuals to **any markdown file you already have**: an old transcript, a saved
article, your notes.

```
/yt-transcript 'https://youtu.be/r79tLZB2S_Y'
/yt-transcript --visuals 'https://youtu.be/r79tLZB2S_Y'
/yt-transcript --visuals ~/notes/some-article.md
```

## What you get

**Text only** — a readable transcript instead of a caption dump:

```markdown
# How to Answer Success Metrics Questions for Product Manager (PM) Interview

Racheal Ou · https://www.youtube.com/watch?v=r79tLZB2S_Y · 10:21 · verbatim auto-caption transcript, …

## The framework

With that being said, let's jump into the framework that you can use to tackle this question. …

### Company and product

First, we want to talk about the company and the product. …
```

**With visuals** — the same text, untouched, plus boxes like this under the sections they explain:

```markdown
<!-- study-visual:start id=three-sides kind=diagram -->
> [!example] Added visual · A three-sided marketplace
>
> ```mermaid
> block-beta
>   columns 3
>   space C["customers"] space
>   space U(("Uber Eats")) space
>   R["restaurants"] space K["couriers"]
>   C --- R
>   C --- K
>   R --- K
> ```

<!-- study-visual:end -->
```

In Obsidian (and GitHub, and any Mermaid-aware viewer) that box draws as a triangle: customers,
restaurants and couriers around Uber Eats. A 10-minute interview-prep video got six: the answer's
four steps as a flow, that triangle, each side's journey as a table, the north-star metric as a
tree of levers, supporting metrics and counter metrics as tables.

### How visuals are chosen — support, not decoration

The agent reads the whole text first, then asks of every section: *would a teacher stop and draw
here?* Only a real shape in the text earns a visual — parts that relate, steps in order, several
things compared on the same points, a whole broken into pieces, a trade-off, or real numbers. Then
it cuts anything that restates a sentence, needs facts the text doesn't give, or is too big to take
in at a glance. It tells you what it considered, what it kept and why it cut the rest. Zero visuals
is a valid answer: a story or an opinion piece usually gets none.

## Guarantees — checked by the script, not by trust

- **The words are the captions', exactly.** `build` refuses to write a transcript whose words differ
  from the captions in any way. Caption mistakes stay; nothing is summarized or "cleaned".
- **Visuals never touch the text.** `visuals` refuses to save unless the file with the visual blocks
  removed is byte-for-byte the file before. Each block is labelled *Added visual*, so nothing added
  passes as the source's words.
- **No invented numbers.** A chart whose numbers the text never says is refused.
- **No broken diagrams.** Every Mermaid block is parsed with the real Mermaid parser before saving.
- **Undo any time.** Running `visuals` again replaces its own blocks (never duplicates);
  `strip` removes them all and gives you back the plain file.
- **Captions only.** The video and audio are never downloaded; no `.vtt`/`.srt` files are kept.
- **Nothing overwritten.** An existing filename is refused.

## Install

```bash
git clone https://github.com/sagdish/yt-notes ~/.claude/skills/yt-transcript
```

Needs:

- **Python 3** (no packages)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — `brew install yt-dlp` or `pipx install yt-dlp`.
  If YouTube changes something, updating yt-dlp usually fixes it.
- **Node.js** — only for visuals with diagrams. The first time, the diagram checker installs
  `mermaid` and `jsdom` into `~/.cache/yt-transcript/` (about 180 MB, once).

The first run asks where your notes live and remembers it in `~/.config/yt-transcript/config.json`.
You can keep several folders with a label each (say, "PM material" and "everything else"):

```bash
python3 ~/.claude/skills/yt-transcript/yt_transcript.py setup ~/notes/learning --label "study notes"
```

Transcripts go one topic folder deep: `<folder>/<topic>/<file>.md`. `YT_TRANSCRIPT_ROOT=<folder>`
overrides the config for one run.

## Files

| File | What it is |
|---|---|
| `SKILL.md` | what the agent follows: two checklists (a video · visuals for a file) and the rules for choosing visuals |
| `yt_transcript.py` | every mechanical step: `setup` · `where` · `fetch` · `build` · `visuals` · `strip` · `check` · `discard` |
| `check_mermaid.mjs` | parses diagrams with the real Mermaid parser, no browser |

## Where visuals render

Any viewer that draws ```` ```mermaid ```` blocks with Mermaid 11 or newer — checked in Obsidian
1.13 (which ships Mermaid 11.13). An older Mermaid may not know `block-beta`, the layout used for
fixed shapes like the triangle, and shows that one as code. Tables render everywhere.

## Limits

- One video per run; a playlist or channel link is refused.
- Auto-captions keep their mistakes ("queers" for "couriers"). A visual's labels may use the right
  word; the text never changes.
- A video with no captions in its language can't be transcribed (`--lang xx` picks another track).

## License

MIT — see [LICENSE](LICENSE).
