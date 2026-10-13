"""Offline tests: sample caption files in, files out. Run: python3 -m unittest discover tests
A fake yt-dlp, whisper-cli and ffmpeg (tests/fakes) stand in for the network and the real tools."""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, types, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "yt_notes.py")
FAKES = os.path.join(ROOT, "tests", "fakes")
spec = importlib.util.spec_from_file_location("yt", SCRIPT)
yt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yt)

# Real auto-captions put a line holding one space above each new line; written with escapes so
# no editor trims it.
ROLLING_VTT = (
    "WEBVTT\nKind: captions\nLanguage: en\n\n"
    "00:00:00.000 --> 00:00:02.000 align:start position:0%\n \n[Music]\n\n"
    "00:00:02.000 --> 00:00:04.000 align:start position:0%\n \n"
    "Every<00:00:02.500><c> system</c><00:00:03.000><c> has</c><00:00:03.500><c> parts.</c>\n\n"
    "00:00:04.000 --> 00:00:04.010 align:start position:0%\nEvery system has parts.\n \n\n"
    "00:00:04.010 --> 00:00:06.000 align:start position:0%\nEvery system has parts.\n"
    "The<00:00:04.500><c> client</c><00:00:05.000><c> asks.</c>\n"
)

MANUAL_VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
The server answers
in two lines.

00:01:05.500 --> 00:01:07.000
Then &amp; only then it stops.
"""

# Japanese auto-captions: no spaces, no punctuation, and the caption line breaks mid-word.
JA_VTT = (
    "WEBVTT\n\n"
    "00:00:00.100 --> 00:00:02.400 align:start position:0%\n \n"
    "はい<00:00:00.600><c>こんにちは</c><00:00:00.800><c>今回</c><00:00:01.700><c>の</c><00:00:01.900><c>テー</c>\n\n"
    "00:00:02.400 --> 00:00:02.410 align:start position:0%\nはいこんにちは今回のテー\n \n\n"
    "00:00:02.410 --> 00:00:04.600 align:start position:0%\nはいこんにちは今回のテー\n"
    "マは<00:00:03.400><c>データベース</c><00:00:03.800><c>です</c>\n\n"
    "00:00:06.000 --> 00:00:08.000 align:start position:0%\nマはデータベースです\n"
    "Python<00:00:06.500><c>の</c><00:00:06.800><c>話</c>\n"
)


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(*args, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)


def words_at(text, start=0.0, step=0.3, pause_after=()):
    """[(word, seconds)] with a long pause after the word indexes in pause_after."""
    out, t = [], start
    for i, w in enumerate(text.split()):
        out.append((w, round(t, 2)))
        t += step + (1.5 if i in pause_after else 0)
    return out


class Captions(unittest.TestCase):
    def test_rolling_auto_captions_keep_each_line_once_with_word_times(self):
        words = yt.vtt_words(ROLLING_VTT)
        self.assertEqual(" ".join(w for w, _ in words), "[Music] Every system has parts. The client asks.")
        self.assertEqual(words[1:4], [("Every", 2.0), ("system", 2.5), ("has", 3.0)])
        self.assertEqual(words[-1], ("asks.", 5.0))

    def test_manual_captions_keep_every_line(self):
        words = yt.vtt_words(MANUAL_VTT)
        self.assertEqual(" ".join(w for w, _ in words), "The server answers in two lines. Then & only then it stops.")
        self.assertEqual(words[-1][1], 65.5)

    def test_sentences_become_units_with_their_times(self):
        units, punctuated = yt.make_units(yt.vtt_words(MANUAL_VTT), False)
        self.assertTrue(punctuated)
        self.assertEqual(units, [("The server answers in two lines.", 1.0), ("Then & only then it stops.", 65.5)])

    def test_unpunctuated_captions_are_cut_at_pauses(self):
        words = words_at(" ".join(f"w{i:02d}" for i in range(30)), pause_after=(11, 19))
        units, punctuated = yt.make_units(words, False)
        self.assertFalse(punctuated)
        self.assertEqual([len(u.split()) for u, _ in units], [12, 8, 10])

    def test_unpunctuated_captions_without_pauses_are_cut_at_45_words(self):
        units, _ = yt.make_units(words_at(" ".join(f"w{i:02d}" for i in range(100))), False)
        self.assertEqual([len(u.split()) for u, _ in units], [45, 45, 10])

    def test_sentence_ends_in_other_scripts(self):
        units, punctuated = yt.make_units(words_at("क्या यह सही है। हाँ यह सही है। ठीक؟ نعم."), False)
        self.assertTrue(punctuated)
        self.assertEqual([u for u, _ in units], ["क्या यह सही है।", "हाँ यह सही है।", "ठीक؟", "نعم."])

    def test_tight_scripts_join_without_spaces_but_keep_latin_words_apart(self):
        words = yt.vtt_words(JA_VTT)
        self.assertTrue(yt.tight_text(" ".join(w for w, _ in words)))
        self.assertEqual(yt.join_words([w for w, _ in words], True),
                         "はいこんにちは今回のテーマはデータベースです Python の話")
        units, punctuated = yt.make_units(words, True)
        self.assertFalse(punctuated)
        self.assertEqual(units[0], ("はいこんにちは今回のテーマはデータベースです", 0.1))

    def test_tight_scripts_split_after_their_own_sentence_ends(self):
        units, punctuated = yt.make_units([("今日は晴れです。明日は雨です。", 0.0), ("また明日。", 4.0)], True)
        self.assertTrue(punctuated)
        self.assertEqual([u for u, _ in units], ["今日は晴れです。", "明日は雨です。", "また明日。"])

    def test_chapters_map_to_units_and_never_collide(self):
        times = [0, 5, 10, 20, 30]
        chapters = [{"start_time": 0, "title": "Start"}, {"start_time": 9, "title": "B"},
                    {"start_time": 9.5, "title": "C"}, {"start_time": 999, "title": "Gone"}]
        hs = yt.chapter_headings(chapters, times)
        self.assertEqual([(h["unit"], h["title"]) for h in hs], [(1, "Start"), (3, "B"), (4, "C")])

    def test_chapter_titles_come_from_the_creator_not_youtube_translation(self):
        chapters = [{"start_time": 0, "title": "This theme"}, {"start_time": 158, "title": "Know the structure"}]
        desc = "Links below\n00:00 今回のテーマ\n02:38 - データベースの構造を知る　\nhttps://example.com"
        hs = yt.chapter_headings(chapters, [0, 100, 160], desc)
        self.assertEqual([(h["unit"], h["title"]) for h in hs], [(1, "今回のテーマ"), (3, "データベースの構造を知る")])

    def test_an_overlong_unit_is_cut_at_its_longest_pause(self):
        words = [(f"w{i}", i * 0.2 + (0.6 if i > 20 else 0)) for i in range(60)]   # one 0.8 s gap after w20
        units, _ = yt.make_units(words, False)
        self.assertEqual(len(units[0][0].split()), 21)

    def test_whisper_pieces_rejoin_into_words(self):
        raw = [["你好", 0], [",", 0.2], [" 我是", 0.4], ["S", 1], ["Q", 1.1], ["L", 1.2], ["一位", 1.5], [" Linux", 2],
               [" The", 3], [" client", 3.2], [" ask", 3.4], ["s.", 3.5]]
        words = yt.whisper_words(raw)
        self.assertEqual([w for w, _ in words], ["你好,", "我是", "SQL", "一位", "Linux", "The", "client", "asks."])
        self.assertEqual(yt.join_words([w for w, _ in words[:4]], True), "你好, 我是 SQL 一位")

    def test_kebab(self):
        self.assertEqual(yt.kebab("How Databases Work: Part 1"), "how-databases-work-part-1.md")

    def test_numbers_said(self):
        said = yt.numbers_said("about twenty five people, two hundred and five days, 1.5 million users, 1,200 items")
        for n in (25, 205, 1.5e6, 1200, 1.5):
            self.assertIn(float(n), said)

    def test_failure_messages(self):
        self.assertIn("not a bot", yt.ytdlp_failure("ERROR: Sign in to confirm you’re not a bot"))
        self.assertIn("private", yt.ytdlp_failure("ERROR: [youtube] x: Private video"))
        self.assertIn("429", yt.ytdlp_failure("HTTP Error 429: Too Many Requests"))
        self.assertIsNone(yt.ytdlp_failure("ERROR: something new"))

    def test_language_codes(self):
        self.assertEqual([yt.base(c) for c in ("en-US", "es_419", "iw", "zh-Hans", "PT-br")], ["en", "es", "he", "zh", "pt"])


def caption(url=""):
    return [{"ext": "vtt", "url": url}]


def video(language="en", manual=(), auto=(), translated=(), formats=None, chapters=None):
    """A yt-dlp -J answer. auto = speech-recognition keys (like en-orig), translated = machine-translation keys."""
    a = {k: caption("https://youtube/timedtext?lang=x") for k in auto}
    a.update({k: caption(f"https://youtube/timedtext?lang=x&tlang={k}") for k in translated})
    return {"id": "abcdefghijk", "title": "How Systems Work", "channel": "Example Channel", "duration_string": "10:00",
            "upload_date": "20240131", "language": language, "subtitles": {k: caption() for k in manual},
            "automatic_captions": a, "formats": formats or [], "chapters": chapters}


class Tracks(unittest.TestCase):
    def test_region_tags_match_the_language(self):
        t = yt.pick_track(video("en-US", auto=["en-orig"], translated=["ru", "de"]))
        self.assertEqual((t["code"], t["kind"], t["lang"]), ("en-orig", "auto", "en"))
        t = yt.pick_track(video("es-US", auto=["es-orig"]))
        self.assertEqual((t["code"], t["kind"]), ("es-orig", "auto"))

    def test_human_captions_come_first(self):
        t = yt.pick_track(video("en", manual=["en-GB", "en"], auto=["en-orig"]))
        self.assertEqual((t["code"], t["kind"]), ("en", "manual"))

    def test_original_audio_wins_over_dubs_and_details(self):
        formats = [{"acodec": "opus", "language": "en-US", "format_note": "English (US), medium", "language_preference": -1},
                   {"acodec": "opus", "language": "ru", "format_note": "Russian original (default), medium",
                    "language_preference": 10}]
        t = yt.pick_track(video(None, auto=["en-US-orig", "ru-orig"], formats=formats))
        self.assertEqual((t["code"], t["spoken"], t["how"]), ("ru-orig", "ru", "original audio"))

    def test_another_language_prefers_human_subtitles(self):
        t = yt.pick_track(video("en", manual=["en", "ru"], auto=["en-orig"], translated=["ru"]), "ru")
        self.assertEqual((t["code"], t["kind"], t["spoken"]), ("ru", "manual", "en"))

    def test_another_language_is_a_labelled_machine_translation(self):
        # before 3.0, --lang ru took this track and called it the speaker's own auto-captions
        t = yt.pick_track(video("en", auto=["en-orig"], translated=["ru"]), "ru")
        self.assertEqual((t["code"], t["kind"]), ("ru", "translated"))

    def test_no_captions_in_the_video_language(self):
        t = yt.pick_track(video("uz", manual=["en"]))
        self.assertIn("no captions in its language (uz)", t["error"])
        self.assertIn("human-made: en", t["others"])
        t = yt.pick_track(video(None))
        self.assertIn("nothing says which language", t["error"])

    def test_only_one_human_track_and_no_language(self):
        t = yt.pick_track(video(None, manual=["fr"]))
        self.assertEqual((t["code"], t["spoken"]), ("fr", "fr"))


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notes = os.path.join(self.tmp, "notes")
        os.makedirs(self.notes)
        self.env = dict(os.environ, YT_NOTES_CONFIG=os.path.join(self.tmp, "config.json"),
                        YT_NOTES_ROOT=self.notes, XDG_CACHE_HOME=os.path.join(self.tmp, "cache"),
                        TMPDIR=self.tmp, PATH=FAKES + os.pathsep + os.environ.get("PATH", ""),
                        FAKE_VIDEO=os.path.join(self.tmp, "video.json"))
        for k in ("YT_TRANSCRIPT_CONFIG", "YT_TRANSCRIPT_ROOT"):
            self.env.pop(k, None)
        write(self.env["YT_NOTES_CONFIG"], json.dumps({"formats": ["md"]}))   # PDFs: tests/engine_smoke.py

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def json_file(self, obj):
        p = os.path.join(self.tmp, f"f{len(os.listdir(self.tmp))}.json")
        write(p, json.dumps(obj, ensure_ascii=False))
        return p


class Files(Env):
    def workdir(self, units, punctuated=True, kind="auto", lang="en", spoken="en", tight=False, track="en"):
        work = tempfile.mkdtemp(prefix="yt-notes-", dir=self.tmp)
        meta = {"id": "abcdefghijk", "title": "How Systems Work: a test", "creator": "Example Channel",
                "url": "https://www.youtube.com/watch?v=abcdefghijk", "length": "10:00",
                "published": "2024-01-31", "track": track, "kind": kind, "lang": lang, "spoken": spoken,
                "punctuated": punctuated, "tight": tight, "suggested_file": "how-systems-work.md"}
        write(os.path.join(work, "meta.json"), json.dumps(meta))
        write(os.path.join(work, "raw.txt"), yt.join_words([u for _, u in units], tight))
        write(os.path.join(work, "units.json"), json.dumps([{"t": t, "text": u} for t, u in units], ensure_ascii=False))
        return work

    UNITS = [(0, "[Music] Every system has parts."), (5, "The client asks for the cash."),
             (75, "The server answers with fifty percent of the data."), (3700, "Then it stops.")]
    HEADINGS = [{"unit": 1, "level": 2, "title": "Intro"}, {"unit": 3, "level": 2, "title": "The server"},
                {"unit": 4, "level": 3, "title": "Ending"}]

    def build(self, units=None, headings=None, name="how-systems-work.md", plan=None, **meta):
        out = os.path.join(self.notes, "systems", name)
        p = {"headings": headings or self.HEADINGS, "blurb": "Systems", "tags": ["systems"]}
        p.update(plan or {})
        r = run("build", self.workdir(units or self.UNITS, **meta), self.json_file(p), out, env=self.env)
        return r, out

    def test_build_writes_frontmatter_timestamps_and_tags(self):
        r, out = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(out)
        self.assertTrue(md.startswith('---\ntitle: "How Systems Work: a test"\n'))
        self.assertIn("published: 2024-01-31", md)
        self.assertIn("caption_kind: auto\nlanguage: en\ntranscript: verbatim\n", md)
        self.assertIn('tags: ["youtube", "systems"]', md)
        self.assertIn("· 10:00 · verbatim auto-caption transcript, section headings added at the video's own transitions\n", md)
        self.assertIn("## Intro [0:00](https://www.youtube.com/watch?v=abcdefghijk&t=0s)", md)
        self.assertIn("### Ending [1:01:40](https://www.youtube.com/watch?v=abcdefghijk&t=3700s)", md)
        self.assertIn("*[Music]* Every system has parts.", md)
        self.assertEqual(read(os.path.join(self.notes, "systems", "README.md")), "Systems\n")
        self.assertIsNone(yt.check(md, " ".join(u for _, u in self.UNITS)))

    def test_never_overwrites_and_new_topic_needs_a_blurb(self):
        self.build()
        r, _ = self.build()
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stderr)
        out = os.path.join(self.notes, "other", "x.md")
        r = run("build", self.workdir([(0, "Hi.")]), self.json_file([{"unit": 1, "level": 2, "title": "A"}]), out,
                env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("blurb", r.stderr)

    def test_unpunctuated_captions_still_get_paragraphs(self):
        units = [(i * 10, " ".join(f"word{i}x{k}" for k in range(40))) for i in range(10)]
        r, out = self.build(units=units, headings=[{"unit": 1, "level": 2, "title": "All"}], punctuated=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = read(out).split("## All", 1)[1]
        self.assertGreaterEqual(len([p for p in body.split("\n\n") if p.strip()]), 3)

    def test_labels_follow_the_file_language(self):
        units = [(0, "Каждая система состоит из частей."), (5, "Клиент спрашивает.")]
        r, out = self.build(units=units, headings=[{"unit": 1, "level": 2, "title": "Начало"}], lang="ru", spoken="ru",
                            track="ru-orig")
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(out)
        self.assertIn("· дословная расшифровка автосубтитров, заголовки разделов добавлены на переходах в самом видео\n", md)
        self.assertIn("language: ru\n", md)
        r = self.visuals(out, [dict(self.TABLE, section="Начало")])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("> [!example] Добавленная визуализация: The parts", read(out))

    def test_a_translation_says_so(self):
        r, out = self.build(units=self.UNITS[:2], headings=[{"unit": 1, "level": 2, "title": "A"}], kind="translated",
                            lang="en", spoken="ru")
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(out)
        self.assertIn("· YouTube machine translation of the captions (video language: ru), section headings", md)
        self.assertIn("caption_kind: translated\nlanguage: en\nvideo_language: ru\n", md)

    def test_labels_for_a_language_without_built_in_ones(self):
        r, out = self.build(units=self.UNITS[:2], headings=[{"unit": 1, "level": 2, "title": "A"}], lang="sw", spoken="sw",
                            plan={"labels": {"auto": "nakala ya manukuu ya kiotomatiki", "headings": "vichwa vimeongezwa"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("· nakala ya manukuu ya kiotomatiki, vichwa vimeongezwa\n", read(out))

    FIXES = {"fixes": [{"unit": 2, "from": "cash", "to": "cache"}]}

    def test_polish_marks_each_fix_and_strip_restores_the_verbatim_file_byte_for_byte(self):
        r, plain = self.build(name="plain.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        r, polished = self.build(name="polished.md", plan=self.FIXES)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fix 1 (unit 2): 'cash' → 'cache'", r.stdout)
        md = read(polished)
        self.assertIn("The client asks for the cache[^fix-1].", md)
        self.assertTrue(md.endswith('\n\n[^fix-1]: captions: "cash" → "cache"\n'))
        self.assertIn("transcript: polished\n", md)
        self.assertIn("transitions, obvious mistakes corrected, each one marked\n", md)
        self.assertIsNone(yt.check(md, " ".join(u for _, u in self.UNITS)))      # the captions are still underneath
        r = run("strip", polished, "--fixes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read(polished), read(plain))

    def test_fixes_are_small_and_never_touch_numbers_or_human_captions(self):
        cases = [({"unit": 2, "from": "asks for the cash", "to": "wants the cache"}, "at most 3 words"),
                 ({"unit": 3, "from": "fifty percent", "to": "fifteen percent"}, "never changes a number"),
                 ({"unit": 3, "from": "with fifty", "to": "with"}, "never changes a number"),
                 ({"unit": 3, "from": "answers", "to": "replies"}, None),
                 ({"unit": 2, "from": "money", "to": "cache"}, "is not in unit 2"),
                 ({"unit": 2, "from": "cash", "to": "ca[c]he"}, "markdown characters")]
        for fix, err in cases:
            r, _ = self.build(name="x.md", plan={"fixes": [fix]})
            if err:
                self.assertEqual(r.returncode, 1, fix)
                self.assertIn(err, r.stderr)
            else:
                self.assertEqual(r.returncode, 0, r.stderr)
                os.remove(os.path.join(self.notes, "systems", "x.md"))
        u = [(0, "It costs 50 dollars.")]
        r, _ = self.build(units=u, headings=[{"unit": 1, "level": 2, "title": "A"}], name="y.md",
                          plan={"fixes": [{"unit": 1, "from": "50 dollars", "to": "15 dollars"}]})
        self.assertIn("never changes a number", r.stderr)
        r, _ = self.build(name="z.md", plan=self.FIXES, kind="manual")
        self.assertIn("human-made captions", r.stderr)

    def test_a_damaged_fix_fails_the_check_instead_of_being_guessed(self):
        _, out = self.build(plan=self.FIXES)
        damaged = read(out).replace("cache[^fix-1]", "money[^fix-1]")
        write(out, damaged)
        self.assertIn("caption fix 1 is damaged", yt.check(damaged, " ".join(u for _, u in self.UNITS)))
        self.assertEqual(run("strip", out, env=self.env).returncode, 1)
        self.assertEqual(read(out), damaged)

    def visuals(self, path, vs, *extra):
        return run("visuals", path, self.json_file(vs), *extra, env=self.env)

    TABLE = {"id": "parts", "section": "Intro", "kind": "table", "title": "The parts", "why": "two roles side by side",
             "body": "| part | job |\n|---|---|\n| client | asks |\n| server | answers |"}

    def test_visuals_insert_replace_and_strip_round_trip(self):
        _, out = self.build()
        before = read(out)
        r = self.visuals(out, [self.TABLE])
        self.assertEqual(r.returncode, 0, r.stderr)
        once = read(out)
        self.assertIn("> [!example] Added visual: The parts", once)
        self.assertEqual(self.visuals(out, [self.TABLE]).returncode, 0)
        self.assertEqual(read(out), once)            # re-run replaces, never duplicates
        self.assertEqual(run("strip", out, env=self.env).returncode, 0)
        self.assertEqual(read(out), before)

    def test_visuals_on_a_polished_file_find_text_across_fix_markers_and_go_before_the_footnotes(self):
        _, out = self.build(plan=self.FIXES)
        polished = read(out)
        last = dict(self.TABLE, id="end", section="Ending")
        mid = dict(self.TABLE, id="mid", after_text="asks for the cache.")
        r = self.visuals(out, [mid, last])
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(out)
        self.assertLess(md.index("id=mid"), md.index("## The server"))
        self.assertLess(md.index("id=end"), md.index("[^fix-1]: captions"))
        r = run("strip", out, "--visuals", env=self.env)
        self.assertEqual(read(out), polished)

    def test_plain_style(self):
        _, out = self.build()
        r = self.visuals(out, [self.TABLE], "--style", "plain")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("> **Added visual: The parts**", read(out))

    def test_damaged_marker_never_eats_text(self):
        _, out = self.build()
        self.visuals(out, [self.TABLE])
        damaged = read(out).replace(yt.BLOCK_END, "", 1) + "\nMy own note that must survive.\n"
        write(out, damaged)
        r = self.visuals(out, [self.TABLE])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no end marker", r.stderr)
        self.assertEqual(run("strip", out, env=self.env).returncode, 1)
        self.assertEqual(read(out), damaged)

    def test_markers_inside_code_fences_are_text(self):
        text = "# Doc\n\n## A\n\n```\n<!-- study-visual:start id=x kind=table -->\n```\n"
        self.assertEqual(yt.find_blocks(text), [])

    CHART = {"id": "c", "section": "A", "kind": "chart", "title": "t", "why": "w",
             "body": "```mermaid\npie title Share\n  \"yes\" : 45\n  \"no\" : 55\n```"}

    def test_chart_numbers_must_come_from_its_section(self):
        base = "# T\n\nsrc · http://x\n\n## A\n\nIt was forty five percent against fifty five.\n\n## B\n\nNothing here.\n"
        heads = yt.headings_of(base)
        yt.check_numbers([self.CHART], base, heads)            # said in English words: allowed
        with self.assertRaises(SystemExit):
            yt.check_numbers([dict(self.CHART, section="B")], base, heads)

    def test_chart_numbers_in_any_language_need_the_exact_phrase(self):
        base = "# T\n\nsrc · http://x\n\n## A\n\nЭто сорок пять процентов, а остальные пятьдесят пять.\n"
        heads = yt.headings_of(base)
        good = dict(self.CHART, numbers={"45": "сорок пять процентов", "55": "пятьдесят пять"})
        self.assertEqual(len(yt.check_numbers([good], base, heads)), 2)
        for bad in ({"45": "сорок шесть процентов", "55": "пятьдесят пять"}, {"45": "сорок пять процентов"}):
            with self.assertRaises(SystemExit):
                yt.check_numbers([dict(self.CHART, numbers=bad)], base, heads)
        digits = "# T\n\nsrc · http://x\n\n## A\n\nСначала 40%, потом 55.\n"
        with self.assertRaises(SystemExit):                     # a quote with digits must hold the number
            yt.check_numbers([dict(self.CHART, numbers={"45": "Сначала 40%"})], digits, yt.headings_of(digits))

    def test_bad_arguments_get_a_sentence_not_a_traceback(self):
        r = run("fetch", "https://youtu.be/abcdefghijk", "--lang", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--lang needs a value", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r = run("setup", "--formats", "pdf", env=self.env)
        self.assertIn("--formats", r.stderr)
        r = run("setup", "--polish", "maybe", env=self.env)
        self.assertIn("on or off", r.stderr)

    def test_legacy_headings_list_and_frontmatter_fields(self):
        r = run("build", self.workdir(self.UNITS), self.json_file([{"unit": 1, "level": 2, "title": "A"}]),
                os.path.join(self.notes, "systems", "l.md"), "--blurb", "Systems", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        f = yt.frontmatter_fields(read(os.path.join(self.notes, "systems", "l.md")))
        self.assertEqual((f["video_id"], f["caption_track"], f["caption_kind"], f["language"]),
                         ("abcdefghijk", "en", "auto", "en"))

    def test_tight_script_build_checks_characters(self):
        units = [(0, "はいこんにちは今回のテーマはデータベースです"), (6, "Python の話")]
        r, out = self.build(units=units, headings=[{"unit": 1, "level": 2, "title": "はじめに"}], lang="ja", spoken="ja",
                            tight=True, punctuated=False, plan={"fixes": [{"unit": 1, "from": "テーマ", "to": "主題"}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("characters: ", r.stdout)
        md = read(out)
        self.assertIn("主題[^fix-1]", md)
        self.assertIn("自動字幕の逐語書き起こし、見出しは動画自体の区切りに追加、明らかな誤りを修正し", md)


class Fetch(Env):
    """fetch against the fake yt-dlp: no network."""

    def fake(self, info, vtt=None, refuse=()):
        write(self.env["FAKE_VIDEO"], json.dumps({"info": info, "vtt": vtt or {}, "refuse": list(refuse)}))

    def workdir_of(self, out):
        return next(l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("workdir: "))

    def test_fetch_writes_units_meta_and_reports_polish(self):
        self.fake(video("en-US", auto=["en-orig"], translated=["ru"]), {"en-orig": ROLLING_VTT})
        r = run("fetch", "https://youtu.be/abcdefghijk", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("captions_language: en · video_language: en (video details)", r.stdout)
        self.assertIn("polish: on", r.stdout)
        self.assertIn("labels: built in (en)", r.stdout)
        work = self.workdir_of(r.stdout)
        self.assertEqual(read(os.path.join(work, "units.txt")),
                         "1| 0:00| [Music] Every system has parts.\n2| 0:04| The client asks.\n")
        meta = json.loads(read(os.path.join(work, "meta.json")))
        self.assertEqual((meta["track"], meta["kind"], meta["lang"], meta["tight"]), ("en-orig", "auto", "en", False))

    def test_no_captions_exits_5_and_offers_speech_to_text(self):
        self.fake(video("uz", manual=["en"]))
        r = run("fetch", "https://youtu.be/abcdefghijk", env=self.env)
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertIn("NO CAPTIONS: this video has no captions in its language (uz)", r.stdout)
        self.assertIn("other captions: human-made: en", r.stdout)
        self.assertIn("--whisper", r.stdout)

    def test_a_refused_translation_says_the_original_still_works(self):
        self.fake(video("en", auto=["en-orig"], translated=["ru"]), {"en-orig": ROLLING_VTT}, refuse=["ru"])
        r = run("fetch", "https://youtu.be/abcdefghijk", "--lang", "ru", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("refused its machine translation", r.stderr)
        self.assertIn("own language still work", r.stderr)

    def test_a_translation_brings_the_original_for_fix_checking(self):
        self.fake(video("en", auto=["en-orig"], translated=["ru"]),
                  {"en-orig": ROLLING_VTT, "ru": MANUAL_VTT.replace("The server", "Сервер")})
        r = run("fetch", "https://youtu.be/abcdefghijk", "--lang", "ru", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind: translated", r.stdout)
        work = self.workdir_of(r.stdout)
        self.assertIn("Every system has parts.", read(os.path.join(work, "original.txt")))

    def test_already_saved_counts_only_the_same_language(self):
        os.makedirs(os.path.join(self.notes, "t"))
        write(os.path.join(self.notes, "t", "a.md"), "---\nvideo_id: abcdefghijk\nlanguage: ru\n---\n")
        self.fake(video("en", auto=["en-orig"]), {"en-orig": ROLLING_VTT})
        r = run("fetch", "https://youtu.be/abcdefghijk", env=self.env)
        self.assertNotIn("ALREADY SAVED", r.stdout)
        self.assertIn("saved before in another language (ru)", r.stdout)
        write(os.path.join(self.notes, "t", "b.md"), "---\nvideo_id: abcdefghijk\nlanguage: en\n---\n")
        r = run("fetch", "https://youtu.be/abcdefghijk", env=self.env)
        self.assertIn("ALREADY SAVED", r.stdout)

    def test_speech_to_text_with_whisper_cpp(self):
        models = os.path.join(self.tmp, "cache", "yt-notes", "whisper", "models")
        os.makedirs(models)
        write(os.path.join(models, "ggml-small.bin"), "model")      # no download in tests
        self.fake(video(None))
        r = run("fetch", "https://youtu.be/abcdefghijk", "--whisper", "--lang", "en", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind: whisper", r.stdout)
        work = self.workdir_of(r.stdout)
        self.assertEqual(read(os.path.join(work, "units.txt")),
                         "1| 0:00| Every system has parts.\n2| 0:02| The client asks the server.\n")
        self.assertEqual(glob_audio(work), [])                      # the audio is deleted
        out = os.path.join(self.notes, "t", "w.md")
        r = run("build", work, self.json_file({"headings": [{"unit": 1, "level": 2, "title": "A"}], "blurb": "T"}), out,
                env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("speech-to-text by Whisper, not checked against captions", read(out))
        r = run("verify", out, env=self.env)
        self.assertIn("no captions to check it against", r.stderr)

    def test_no_whisper_says_how_to_get_one(self):
        self.fake(video(None))
        env = dict(self.env, PATH=os.path.join(self.tmp, "bin") + os.pathsep + "/usr/bin:/bin")
        os.makedirs(os.path.join(self.tmp, "bin"))
        os.symlink(os.path.join(FAKES, "yt-dlp"), os.path.join(self.tmp, "bin", "yt-dlp"))
        r = run("fetch", "https://youtu.be/abcdefghijk", "--whisper", env=env)
        self.assertEqual(r.returncode, 4)
        self.assertIn("brew install whisper-cpp", r.stderr)
        self.assertIn("whisper-install", r.stderr)


def glob_audio(work):
    return [f for f in os.listdir(work) if f.startswith("audio")]


class Lifecycle(Env):
    def test_uninstall_asks_first_then_removes_only_its_own_files(self):
        cache = os.path.join(self.tmp, "cache", "yt-notes")
        os.makedirs(cache)
        run("setup", "--style", "plain", env=self.env)
        r = run("uninstall", env=self.env)
        self.assertIn("--yes", r.stdout)
        self.assertTrue(os.path.isdir(cache))
        run("uninstall", "--yes", env=self.env)
        self.assertFalse(os.path.exists(cache))
        self.assertFalse(os.path.exists(self.env["YT_NOTES_CONFIG"]))
        self.assertTrue(os.path.isdir(self.notes))

    def test_settings_and_downloads_move_over_from_the_old_name(self):
        home = os.path.join(self.tmp, "home")
        old_cfg = os.path.join(home, ".config", "yt-transcript", "config.json")
        os.makedirs(os.path.dirname(old_cfg))
        write(old_cfg, json.dumps({"roots": [{"label": "notes", "path": self.notes}], "style": "plain"}))
        os.makedirs(os.path.join(self.tmp, "cache", "yt-transcript", "yt-dlp"))
        env = dict(self.env, HOME=home)
        for k in ("YT_NOTES_CONFIG", "YT_NOTES_ROOT"):
            env.pop(k)
        r = run("setup", "--show", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("yt-transcript is now yt-notes", r.stderr)
        self.assertIn("style: plain", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(home, ".config", "yt-notes", "config.json")))
        self.assertFalse(os.path.exists(old_cfg))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "cache", "yt-notes", "yt-dlp")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "cache", "yt-transcript")))

    def test_old_variable_names_still_work(self):
        env = dict(self.env, YT_TRANSCRIPT_ROOT=self.notes)
        env.pop("YT_NOTES_ROOT")
        r = run("where", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.notes, r.stdout)

    def test_a_fresh_install_saves_to_exports_in_the_skill_and_defaults_to_pdf(self):
        os.remove(self.env["YT_NOTES_CONFIG"])
        env = dict(self.env)
        env.pop("YT_NOTES_ROOT")
        r = run("where", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(os.path.join(ROOT, "exports") + "/<topic>/", r.stdout)
        self.assertIn("the default", r.stdout)
        self.assertIn("formats md,pdf", r.stdout)
        r = run("setup", "--show", env=env)
        self.assertIn(os.path.join(ROOT, "exports") + " (default)", r.stdout)
        self.assertIn("formats: md,pdf", r.stdout)
        self.assertFalse(os.path.exists(self.env["YT_NOTES_CONFIG"]))
        with mock.patch.dict(os.environ, {"YT_NOTES_ROOT": "", "YT_TRANSCRIPT_ROOT": ""}), \
                mock.patch.object(yt, "CONFIG", self.env["YT_NOTES_CONFIG"]):
            self.assertEqual(yt.roots(), [{"label": "exports", "path": yt.EXPORTS, "default": True}])
            self.assertEqual(yt.formats_from([]), ({"pdf"}, []))
        r = run("setup", self.notes, env=env)
        self.assertNotIn("exports", run("where", env=env).stdout)

    def test_md_means_markdown_only_even_with_a_pdf_default(self):
        run("setup", "--formats", "md,pdf", env=self.env)
        with mock.patch.object(yt, "CONFIG", self.env["YT_NOTES_CONFIG"]):
            self.assertEqual(yt.formats_from(["--md", "x"]), (set(), ["x"]))
            self.assertEqual(yt.formats_from(["--html"]), ({"html"}, []))
            self.assertEqual(yt.formats_from([]), ({"pdf"}, []))
        r = run("build", "w", "p.json", "o.md", "--md", "--pdf", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--md means Markdown only", r.stderr)


class Updates(unittest.TestCase):
    """yt-dlp failures: known ones get a sentence, unknown ones get one update and one retry."""

    def fake_runs(self, results):
        calls = []

        def run_(cmd, **_kw):
            calls.append(cmd)
            code, err = results[min(len(calls), len(results)) - 1]
            return types.SimpleNamespace(returncode=code, stdout="out", stderr=err)
        return calls, run_

    def patched(self, run_, published="new"):
        return [mock.patch.object(yt, "ytdlp_cmd", return_value=(["yt-dlp"], True)),
                mock.patch.object(yt, "installed_ytdlp", return_value={"asset": "yt-dlp", "sha256": "old"}),
                mock.patch.object(yt, "published_sha", return_value=published),
                mock.patch.object(yt.subprocess, "run", side_effect=run_)]

    def attempt(self, results, published="new", expect_exit=None):
        calls, run_ = self.fake_runs(results)
        with mock.patch.object(yt, "install_ytdlp") as install:
            ps = self.patched(run_, published)
            for p in ps:
                p.start()
            try:
                if expect_exit is None:
                    self.assertEqual(yt.ytdlp("-J", "x"), "out")
                else:
                    with self.assertRaises(SystemExit) as e:
                        yt.ytdlp("-J", "x")
                    self.assertEqual(e.exception.code, expect_exit)
            finally:
                for p in ps:
                    p.stop()
        return calls, install

    def test_unknown_failure_updates_once_then_retries(self):
        calls, install = self.attempt([(1, "ERROR: something new"), (0, "")])
        install.assert_called_once()
        self.assertEqual(len(calls), 2)

    def test_no_retry_when_already_latest(self):
        calls, install = self.attempt([(1, "ERROR: something new")], published="old", expect_exit=2)
        install.assert_not_called()
        self.assertEqual(len(calls), 1)

    def test_known_failure_never_retries(self):
        calls, install = self.attempt([(1, "ERROR: Sign in to confirm you're not a bot")], expect_exit=2)
        install.assert_not_called()
        self.assertEqual(len(calls), 1)

    def test_offline_update_check_keeps_the_real_error(self):
        _, install = self.attempt([(1, "ERROR: something new")], published=None, expect_exit=2)
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
