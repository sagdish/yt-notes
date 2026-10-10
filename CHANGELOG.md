# Changelog

## 2.0.0 — 2026-09-29

- **Study visuals.** Optional diagrams, tables, comparisons and charts, chosen by a read-the-whole-
  text-first pass with an explicit cut step. Asked with the save question, or forced with
  `--visuals <url>`.
- **Visuals for any markdown file:** `--visuals <file>`. `visuals` replaces its own blocks on a
  re-run; `strip` removes them all.
- Every diagram must fit a reading column (~560px) at full size — Obsidian cuts off wider ones. The
  script estimates the width and refuses a diagram that won't fit, and label lines over 26 characters.
- Every Mermaid diagram is parsed with the real parser before saving; a chart may only show numbers
  the text says; the file's own text must stay byte-for-byte unchanged or nothing is written.
- **Anyone can use it:** save folders come from `setup` (`~/.config/yt-transcript/config.json`) or
  `$YT_TRANSCRIPT_ROOT` instead of hard-coded paths. `--outside-vault` is now `--anywhere`.
- Text-only output is unchanged from 1.0 — same bytes for the same video and headings.

## 1.0.0 — 2026-09-28

- Complete verbatim transcript from captions, section headings at the speaker's transitions,
  word-for-word check against the captions, duplicate-video warning.
