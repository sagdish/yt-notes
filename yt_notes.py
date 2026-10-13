#!/usr/bin/env python3
"""YouTube video -> one markdown file, every word kept. Optional study visuals for any .md file,
optional PDF / HTML copies with the diagrams drawn, and Whisper speech-to-text for videos that
have no captions.

Every mechanical step lives here so no agent improvises it. The agent's judgment is limited to WHERE
the file is saved (asked, never guessed), WHERE the section headings go and WHICH caption mistakes
to fix (plan.json), and WHICH visuals earn a place (visuals.json).

  setup  <folder> [--label "..."]     remember a folder transcripts are saved under (repeatable)
  setup  --show                       the saved settings
  setup  --style obsidian|plain       how visual boxes are written (default: obsidian)
  setup  --formats md[,pdf][,html]    which copies every build writes (default: md)
  setup  --paper a4|letter            PDF paper size (default: a4)
  setup  --polish on|off              fix obvious caption mistakes, each one marked (default: on)
  setup  --whisper-model NAME         tiny | base | small | medium | large-v3-turbo (default: small)
  where                               the save folders and the topic folders inside them
  fetch  <url> [--lang xx] [--whisper] [--cookies-from-browser NAME]
                                      captions (never the video) -> a work dir with the text.
                                      --lang in another language than the video's = a translation.
                                      --whisper = speech-to-text of the audio, for videos without captions
  build  <workdir> <plan.json> <out.md> [--anywhere] [--pdf] [--html]
                                      writes the file, verifies it word for word, deletes the work dir
  visuals <file.md> <visuals.json> [--style obsidian|plain] [--lang xx] [--label "..."] [--pdf] [--html]
                                      adds visual blocks to ANY markdown file; replaces the ones it
                                      added before; refuses unless every other byte is unchanged
  export <file.md> [--pdf] [--html] [--paper a4|letter]
                                      writes <file>.pdf / <file>.html next to it, diagrams drawn
  strip  <file.md> [--visuals | --fixes]
                                      removes the added visuals and caption fixes (default: both)
  verify <file.md> [--cookies-from-browser NAME]
                                      re-downloads the captions and checks the file word for word
  check  <file.md> <raw.txt>          the word-for-word check against a captions text file
  discard <workdir>                   the user stopped before build: remove the work dir
  whisper-install [--model NAME]      installs Whisper (faster-whisper) into this tool's cache
  doctor                              checks everything this tool needs
  uninstall [--yes]                   removes the downloaded tools and the settings (never your notes)

Exit codes: 0 ok · 1 refused / check failed · 2 YouTube or yt-dlp problem · 3 no save folder set up ·
4 a required tool is missing or could not be installed · 5 no captions in the video's language.
"""
import glob, hashlib, html, json, os, platform, re, shutil, subprocess, sys, tempfile, time
import urllib.request

VERSION = "3.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))


def env(name):
    """$YT_NOTES_<name>, or the variable's name from before the rename ($YT_TRANSCRIPT_<name>)."""
    return os.environ.get(f"YT_NOTES_{name}") or os.environ.get(f"YT_TRANSCRIPT_{name}")


XDG_CACHE = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
CONFIG = env("CONFIG") or os.path.expanduser("~/.config/yt-notes/config.json")
CACHE = os.path.join(XDG_CACHE, "yt-notes")
OLD_CONFIG = os.path.expanduser("~/.config/yt-transcript/config.json")   # before the rename
OLD_CACHE = os.path.join(XDG_CACHE, "yt-transcript")
YTDLP_HOME = os.path.join(CACHE, "yt-dlp")
ENGINE_HOME = os.path.join(CACHE, "engine")
BROWSERS = os.path.join(CACHE, "browsers")
WHISPER_HOME = os.path.join(CACHE, "whisper")
WORK_PREFIXES = ("yt-notes-", "yt-transcript-")
RELEASES = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
NODE_MIN = 20
WHISPER_PACKAGES = ("faster-whisper==1.2.1", "av<19")      # PyAV 19 breaks faster-whisper 1.2.1
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3-turbo")
GGML_TREE = "https://huggingface.co/api/models/ggerganov/whisper.cpp/tree/main"
GGML_FILE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

FILE_RE = re.compile(r"^[0-9A-Za-z._-]+\.md$")        # kebab-case: safe in every app, shell and URL
FOLDER_RE = re.compile(r"^[0-9A-Za-z_-][0-9A-Za-z._-]*$")
TAG_NAME_RE = re.compile(r"^[0-9A-Za-z_/-]{1,40}$")
MIN_UNIT, MAX_UNIT, MAX_SENTENCE = 8, 45, 60            # unit sizes in words (CJK: characters / 2.5)
PAUSE = 0.9                                             # s: a pause this long ends an unpunctuated unit
                                                        # (or the video's 95th-percentile pause, if shorter)
PARA_WORDS = 120                                        # paragraph break at the first unit end past this
LONG_VIDEO_UNITS = 600                                  # past this, the agent reads units.txt in parts
MAX_WIDTH = 560                                         # px: Obsidian's reading column inside a callout
END_PUNCT = ".!?。！？।॥؟۔։።။។"                        # sentence ends, in every script captions use
TIGHT_END = "。！？"
# Scripts written without spaces between words: Thai, Lao, Burmese, Tibetan, Khmer, Chinese, Japanese.
TIGHT_RANGES = ((0x0E00, 0x0EFF), (0x0F00, 0x0FFF), (0x1000, 0x109F), (0x1780, 0x17FF), (0x2E80, 0x2FFF),
                (0x3000, 0x31FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF),
                (0x20000, 0x2FA1F))

VISUAL_KINDS = {"diagram", "flow", "table", "comparison", "formula", "tree", "pair", "chart"}
STYLES = ("obsidian", "plain")
BLOCK_START = "<!-- study-visual:start"
BLOCK_END = "<!-- study-visual:end -->"
START_RE = re.compile(r"^<!-- study-visual:start id=[a-z0-9-]+ kind=\w+ -->$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
TS_LINK_RE = re.compile(r"\s*\[\d{1,2}(?::\d{2}){1,2}\]\([^)\s]+\)\s*$")   # "[12:34](...&t=754s)"
TAG_RE = re.compile(r"\[(?!\^)[^\[\]\n]{1,40}\]")                               # [Music], [Applause]
TAG_WRAPPED_RE = re.compile(r"\*(\[(?!\^)[^\[\]\n]{1,40}\])\*")
MERMAID_RE = re.compile(r"^\s*```mermaid\s*\n(.*?)^\s*```", re.S | re.M)
TIME_TAG_RE = re.compile(r"<(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})>")
FIX_REF_RE = re.compile(r"\[\^fix-(\d+)\]")
FIX_DEF_RE = re.compile(r'^\[\^fix-(\d+)\]: (.+?): ("(?:[^"\\]|\\.)*") → ("(?:[^"\\]|\\.)*")$')
FIX_BAD_CHARS = set("[]^*<>|#`\n\\")

# The fixed words the script writes into a file, in the file's own language. Keys: visual (a visual
# box's label), one description per caption source, headings and polished (joined with sep into the
# line under the title), captions / speech (a fix's footnote: captions: "cash" → "cache").
LABEL_KEYS = ("visual", "manual", "auto", "manual_other", "translated", "whisper", "headings", "polished",
              "captions", "speech", "sep")
LABELS = {
    "en": ["Added visual", "verbatim caption transcript", "verbatim auto-caption transcript",
           "verbatim transcript of human-made subtitles (video language: {spoken})",
           "YouTube machine translation of the captions (video language: {spoken})",
           "speech-to-text by Whisper, not checked against captions",
           "section headings added at the video's own transitions", "obvious mistakes corrected, each one marked",
           "captions", "Whisper", ", "],
    "ru": ["Добавленная визуализация", "дословная расшифровка субтитров", "дословная расшифровка автосубтитров",
           "дословная расшифровка субтитров, сделанных людьми (язык видео: {spoken})",
           "машинный перевод субтитров YouTube (язык видео: {spoken})",
           "распознавание речи Whisper, не сверено с субтитрами",
           "заголовки разделов добавлены на переходах в самом видео", "очевидные ошибки исправлены, каждая отмечена",
           "в субтитрах", "Whisper", ", "],
    "uk": ["Додана візуалізація", "дослівна розшифровка субтитрів", "дослівна розшифровка автосубтитрів",
           "дослівна розшифровка субтитрів, створених людьми (мова відео: {spoken})",
           "машинний переклад субтитрів YouTube (мова відео: {spoken})",
           "розпізнавання мовлення Whisper, не звірено із субтитрами",
           "заголовки розділів додано на переходах у самому відео", "очевидні помилки виправлено, кожну позначено",
           "у субтитрах", "Whisper", ", "],
    "uz": ["Qoʻshilgan koʻrgazma", "subtitrlarning soʻzma-soʻz matni", "avtomatik subtitrlarning soʻzma-soʻz matni",
           "odamlar tayyorlagan subtitrlarning soʻzma-soʻz matni (video tili: {spoken})",
           "YouTube subtitrlarining mashina tarjimasi (video tili: {spoken})",
           "Whisper nutqni aniqlash natijasi, subtitrlar bilan solishtirilmagan",
           "boʻlim sarlavhalari videoning oʻz oʻtishlarida qoʻshilgan", "aniq xatolar tuzatilgan, har biri belgilangan",
           "subtitrlarda", "Whisper", ", "],
    "es": ["Visual añadido", "transcripción literal de los subtítulos",
           "transcripción literal de los subtítulos automáticos",
           "transcripción literal de subtítulos hechos por personas (idioma del video: {spoken})",
           "traducción automática de YouTube de los subtítulos (idioma del video: {spoken})",
           "reconocimiento de voz con Whisper, sin cotejar con subtítulos",
           "encabezados de sección añadidos en las transiciones del propio video",
           "errores evidentes corregidos, cada uno marcado", "subtítulos", "Whisper", ", "],
    "pt": ["Recurso visual adicionado", "transcrição literal das legendas", "transcrição literal das legendas automáticas",
           "transcrição literal de legendas feitas por pessoas (idioma do vídeo: {spoken})",
           "tradução automática das legendas pelo YouTube (idioma do vídeo: {spoken})",
           "reconhecimento de fala pelo Whisper, não conferido com legendas",
           "títulos de seção adicionados nas transições do próprio vídeo", "erros evidentes corrigidos, cada um marcado",
           "legendas", "Whisper", ", "],
    "fr": ["Visuel ajouté", "transcription mot pour mot des sous-titres",
           "transcription mot pour mot des sous-titres automatiques",
           "transcription mot pour mot de sous-titres faits par des personnes (langue de la vidéo : {spoken})",
           "traduction automatique des sous-titres par YouTube (langue de la vidéo : {spoken})",
           "reconnaissance vocale par Whisper, non vérifiée avec des sous-titres",
           "titres de section ajoutés aux transitions de la vidéo", "erreurs évidentes corrigées, chacune signalée",
           "sous-titres", "Whisper", ", "],
    "de": ["Hinzugefügte Visualisierung", "wörtliches Transkript der Untertitel",
           "wörtliches Transkript der automatischen Untertitel",
           "wörtliches Transkript von Menschen erstellter Untertitel (Sprache des Videos: {spoken})",
           "maschinelle Übersetzung der Untertitel durch YouTube (Sprache des Videos: {spoken})",
           "Spracherkennung mit Whisper, nicht mit Untertiteln abgeglichen",
           "Abschnittsüberschriften an den Übergängen des Videos eingefügt",
           "offensichtliche Fehler korrigiert, jeder markiert", "Untertitel", "Whisper", ", "],
    "it": ["Elemento visivo aggiunto", "trascrizione letterale dei sottotitoli",
           "trascrizione letterale dei sottotitoli automatici",
           "trascrizione letterale di sottotitoli creati da persone (lingua del video: {spoken})",
           "traduzione automatica dei sottotitoli di YouTube (lingua del video: {spoken})",
           "riconoscimento vocale con Whisper, non confrontato con i sottotitoli",
           "titoli di sezione aggiunti nei passaggi del video stesso", "errori evidenti corretti, ognuno segnalato",
           "sottotitoli", "Whisper", ", "],
    "tr": ["Eklenen görsel", "altyazıların birebir dökümü", "otomatik altyazıların birebir dökümü",
           "insanlarca hazırlanmış altyazıların birebir dökümü (video dili: {spoken})",
           "altyazıların YouTube makine çevirisi (video dili: {spoken})",
           "Whisper ile konuşma tanıma, altyazılarla karşılaştırılmadı",
           "bölüm başlıkları videonun kendi geçişlerine eklendi", "bariz hatalar düzeltildi, her biri işaretlendi",
           "altyazıda", "Whisper", ", "],
    "pl": ["Dodana wizualizacja", "dosłowna transkrypcja napisów", "dosłowna transkrypcja napisów automatycznych",
           "dosłowna transkrypcja napisów przygotowanych przez ludzi (język filmu: {spoken})",
           "tłumaczenie maszynowe napisów przez YouTube (język filmu: {spoken})",
           "rozpoznawanie mowy przez Whisper, nie sprawdzone z napisami",
           "nagłówki sekcji dodane w miejscach przejść w filmie", "oczywiste błędy poprawione, każdy oznaczony",
           "w napisach", "Whisper", ", "],
    "nl": ["Toegevoegde visual", "letterlijke transcriptie van de ondertiteling",
           "letterlijke transcriptie van de automatische ondertiteling",
           "letterlijke transcriptie van door mensen gemaakte ondertiteling (taal van de video: {spoken})",
           "machinevertaling van de ondertiteling door YouTube (taal van de video: {spoken})",
           "spraakherkenning met Whisper, niet gecontroleerd tegen ondertiteling",
           "sectiekoppen toegevoegd bij de overgangen in de video zelf", "duidelijke fouten verbeterd, elk gemarkeerd",
           "ondertiteling", "Whisper", ", "],
    "id": ["Visual tambahan", "transkrip kata demi kata dari subtitel", "transkrip kata demi kata dari subtitel otomatis",
           "transkrip kata demi kata dari subtitel buatan manusia (bahasa video: {spoken})",
           "terjemahan mesin YouTube dari subtitel (bahasa video: {spoken})",
           "pengenalan suara oleh Whisper, tidak dicocokkan dengan subtitel",
           "judul bagian ditambahkan pada peralihan di video itu sendiri",
           "kesalahan yang jelas diperbaiki, masing-masing ditandai", "subtitel", "Whisper", ", "],
    "vi": ["Hình minh họa bổ sung", "bản chép nguyên văn phụ đề", "bản chép nguyên văn phụ đề tự động",
           "bản chép nguyên văn phụ đề do người làm (ngôn ngữ video: {spoken})",
           "bản dịch máy phụ đề của YouTube (ngôn ngữ video: {spoken})",
           "nhận dạng giọng nói bằng Whisper, chưa đối chiếu với phụ đề",
           "tiêu đề mục được thêm tại các chỗ chuyển ý của chính video",
           "các lỗi rõ ràng đã được sửa, mỗi lỗi đều được đánh dấu", "phụ đề", "Whisper", ", "],
    "ar": ["عنصر بصري مضاف", "نص حرفي للترجمة النصية", "نص حرفي للترجمة النصية المنشأة تلقائيًا",
           "نص حرفي لترجمة نصية أعدّها أشخاص (لغة الفيديو: {spoken})",
           "ترجمة آلية من YouTube للترجمة النصية (لغة الفيديو: {spoken})",
           "تعرّف على الكلام بواسطة Whisper، غير مُطابَق مع ترجمة نصية",
           "أُضيفت عناوين الأقسام عند انتقالات الفيديو نفسه", "صُحّحت الأخطاء الواضحة، وعُلّم كل منها",
           "في الترجمة النصية", "Whisper", "، "],
    "fa": ["عنصر دیداری افزوده", "متن کلمه‌به‌کلمه زیرنویس", "متن کلمه‌به‌کلمه زیرنویس خودکار",
           "متن کلمه‌به‌کلمه زیرنویسی که افراد تهیه کرده‌اند (زبان ویدیو: {spoken})",
           "ترجمه ماشینی زیرنویس توسط YouTube (زبان ویدیو: {spoken})",
           "تشخیص گفتار با Whisper، با زیرنویس تطبیق داده نشده",
           "عنوان بخش‌ها در جاهای گذار خود ویدیو افزوده شده", "خطاهای آشکار اصلاح شده و هر کدام علامت خورده",
           "در زیرنویس", "Whisper", "، "],
    "he": ["רכיב חזותי שנוסף", "תמלול מילה במילה של הכתוביות", "תמלול מילה במילה של הכתוביות האוטומטיות",
           "תמלול מילה במילה של כתוביות שהכינו אנשים (שפת הסרטון: {spoken})",
           "תרגום מכונה של YouTube לכתוביות (שפת הסרטון: {spoken})",
           "זיהוי דיבור באמצעות Whisper, לא הושווה לכתוביות",
           "כותרות הפרקים נוספו במעברים של הסרטון עצמו", "טעויות ברורות תוקנו, כל אחת מסומנת",
           "בכתוביות", "Whisper", ", "],
    "hi": ["जोड़ा गया विज़ुअल", "कैप्शन का शब्दशः ट्रांसक्रिप्ट", "ऑटो-कैप्शन का शब्दशः ट्रांसक्रिप्ट",
           "लोगों द्वारा बनाए गए सबटाइटल का शब्दशः ट्रांसक्रिप्ट (वीडियो की भाषा: {spoken})",
           "कैप्शन का YouTube मशीन अनुवाद (वीडियो की भाषा: {spoken})",
           "Whisper द्वारा स्पीच-टू-टेक्स्ट, कैप्शन से मिलान नहीं किया गया",
           "सेक्शन शीर्षक वीडियो के अपने बदलावों पर जोड़े गए", "स्पष्ट गलतियाँ ठीक की गईं, हर एक चिह्नित",
           "कैप्शन में", "Whisper", ", "],
    "ja": ["追加した図解", "字幕の逐語書き起こし", "自動字幕の逐語書き起こし",
           "人が作成した字幕の逐語書き起こし（動画の言語: {spoken}）",
           "YouTube による字幕の機械翻訳（動画の言語: {spoken}）",
           "Whisper による音声認識（字幕との照合なし）",
           "見出しは動画自体の区切りに追加", "明らかな誤りを修正し、それぞれに印を付けた",
           "字幕", "Whisper", "、"],
    "zh": ["补充图示", "字幕逐字稿", "自动字幕逐字稿", "人工字幕逐字稿（视频语言：{spoken}）",
           "YouTube 字幕机器翻译（视频语言：{spoken}）", "Whisper 语音识别，未与字幕核对",
           "章节标题添加在视频本身的转折处", "已更正明显错误，每处均有标注", "字幕", "Whisper", "，"],
    "ko": ["추가한 시각 자료", "자막 그대로 옮긴 전사본", "자동 자막 그대로 옮긴 전사본",
           "사람이 만든 자막 그대로 옮긴 전사본 (동영상 언어: {spoken})",
           "YouTube 자막 기계 번역 (동영상 언어: {spoken})", "Whisper 음성 인식, 자막과 대조하지 않음",
           "섹션 제목은 동영상 자체의 전환 지점에 추가", "명백한 오류를 바로잡고 각각 표시함", "자막", "Whisper", ", "],
}


def die(msg, code=1):
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg):
    print(msg, file=sys.stderr, flush=True)


def opt(args, name):
    """Pull `name value` out of args. Returns (value or None, remaining args)."""
    if name not in args:
        return None, args
    k = args.index(name)
    if k + 1 >= len(args) or args[k + 1].startswith("--"):
        die(f"{name} needs a value")
    return args[k + 1], args[:k] + args[k + 2:]


def flag(args, name):
    return name in args, [a for a in args if a != name]


def fmt_time(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_atomic(path, text):
    tmp = f"{path}.yt-notes-tmp"
    write(tmp, text)
    os.replace(tmp, path)


def existing_md(arg):
    path = os.path.abspath(os.path.expanduser(arg))
    if not path.endswith(".md") or not os.path.isfile(path):
        die(f"{path} is not an existing .md file")
    return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def migrate():
    """Until 3.0 this tool was called yt-transcript: move its settings and downloads once."""
    moved = []
    if not env("CONFIG") and not os.path.exists(CONFIG) and os.path.isfile(OLD_CONFIG):
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        shutil.move(OLD_CONFIG, CONFIG)
        try:
            os.rmdir(os.path.dirname(OLD_CONFIG))
        except OSError:
            pass
        moved.append(f"settings to {CONFIG}")
    if os.path.isdir(OLD_CACHE):
        if os.path.exists(CACHE):
            shutil.rmtree(OLD_CACHE, ignore_errors=True)
        else:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            shutil.move(OLD_CACHE, CACHE)
            moved.append(f"downloads to {CACHE}")
    if moved:
        note("yt-transcript is now yt-notes: moved " + " and ".join(moved))


# ---------------------------------------------------------------- languages
LANG_ALIASES = {"iw": "he", "in": "id", "ji": "yi", "jw": "jv", "mo": "ro"}
RTL = {"ar", "he", "fa", "ur", "ps", "sd", "yi", "ug", "dv", "ckb"}


def base(code):
    """'en-US' -> 'en', 'iw' -> 'he': the language without region or old codes."""
    b = re.split(r"[-_]", str(code or "").strip().lower(), maxsplit=1)[0]
    return LANG_ALIASES.get(b, b)


def labels_for(lang, override=None):
    out = dict(zip(LABEL_KEYS, LABELS.get(base(lang)) or LABELS["en"]))
    out.update(override or {})
    return out


def describe(meta, labels, polished):
    """The words after 'creator · url · length · ' on the line under the title."""
    kind = meta.get("kind")
    key = {"auto": "auto", "translated": "translated", "whisper": "whisper"}.get(kind, "manual")
    if key == "manual" and meta.get("spoken") and base(meta.get("lang")) != base(meta["spoken"]):
        key = "manual_other"
    parts = [labels[key].replace("{spoken}", str(meta.get("spoken") or "?")), labels["headings"]]
    if polished:
        parts.append(labels["polished"])
    return labels["sep"].join(parts)


def is_tight(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in TIGHT_RANGES)


def tight_text(text):
    """True for text mostly in scripts written without spaces (Chinese, Japanese, Thai, ...)."""
    letters = [c for c in text[:20000] if c.isalpha()]
    return bool(letters) and sum(map(is_tight, letters)) / len(letters) >= 0.3


def join_words(words, tight):
    """Caption pieces -> text. Spaced scripts: one space between words. Tight scripts: no space
    between two tight characters (YouTube breaks their lines mid-word), a space next to Latin words."""
    if not tight:
        return " ".join(words)
    out = ""
    for w in words:
        if out and not (is_tight(out[-1]) and is_tight(w[0])):
            out += " "
        out += w
    return out


def size_of(text, tight):
    """Length in words; for tight scripts, characters / 2.5."""
    return len(re.sub(r"\s", "", text)) / 2.5 if tight else len(text.split())


def has_sentences(words, tight):
    ends = sum(1 for w, _ in words if w[-1:] in END_PUNCT)
    total = sum(size_of(w, tight) for w, _ in words)
    return ends > 0 and total / ends <= MAX_SENTENCE


def make_units(words, tight):
    """[(text, seconds)] numbered units for the agent to place headings at. Captions with sentence
    ends: one unit per sentence. Captions without them (many auto-captions): units end where the
    speaker pauses. A unit that runs too long is cut at its longest pause."""
    if tight:          # a tight-script piece can hold a sentence end mid-piece: cut after it
        split = []
        for w, t in words:
            split.extend((p, t) for p in re.split(f"(?<=[{TIGHT_END}])", w) if p)
        words = split
    punctuated = has_sentences(words, tight)
    # Caption times mark where each word starts, so the time to the next word includes saying this
    # one. Subtract the video's usual time per character to keep only the silence after it.
    starts = [words[i + 1][1] - words[i][1] for i in range(len(words) - 1)] + [0]
    per_char = sorted(g / max(1, len(w)) for (w, _), g in zip(words, starts) if g > 0)
    rate = per_char[len(per_char) // 2] if per_char else 0
    gaps = [g - rate * len(w) for (w, _), g in zip(words, starts)]
    ranked = sorted(gaps)
    pause = min(PAUSE, max(0.35, ranked[int(len(ranked) * 0.95)])) if ranked else PAUSE
    limit = MAX_SENTENCE if punctuated else MAX_UNIT
    units, cur = [], []                          # cur: [(word, seconds, gap after it, size so far)]
    for (w, t), gap in zip(words, gaps):
        size = (cur[-1][3] if cur else 0) + size_of(w, tight)
        cur.append((w, t, gap, size))
        if punctuated and w[-1:] in END_PUNCT or (size >= (MAX_UNIT if punctuated else MIN_UNIT) and gap >= pause):
            units.append(cur)
            cur = []
        elif size >= limit:
            # the longest pause past the first MIN_UNIT words (the latest one on a tie)
            k = max((j for j, x in enumerate(cur) if x[3] >= MIN_UNIT), key=lambda j: (cur[j][2], j))
            units.append(cur[:k + 1])
            done = cur[k][3]
            cur = [(x[0], x[1], x[2], x[3] - done) for x in cur[k + 1:]]
    if cur:
        units.append(cur)
    return [(join_words([x[0] for x in u], tight), u[0][1]) for u in units], punctuated


# ---------------------------------------------------------------- settings
def load_config():
    try:
        cfg = json.loads(read(CONFIG))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    write_atomic(CONFIG, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def roots():
    """[{label, path}]: $YT_NOTES_ROOT if set, else the config file."""
    root = env("ROOT")
    if root:
        return [{"label": "notes", "path": os.path.abspath(os.path.expanduser(root))}]
    return [{"label": r.get("label") or "notes", "path": os.path.abspath(os.path.expanduser(r["path"]))}
            for r in load_config().get("roots", []) if isinstance(r, dict) and r.get("path")]


def setting(name, default):
    v = load_config().get(name)
    return default if v is None or v == "" else v


def cmd_setup(args):
    cfg = load_config()
    if args == ["--show"]:
        rs = roots()
        print("\n".join(f"save folder: {r['label']} -> {r['path']}" for r in rs) or "no save folder set up yet")
        print(f"style: {cfg.get('style', 'obsidian')}\nformats: {','.join(cfg.get('formats', ['md']))}\n"
              f"paper: {cfg.get('paper', 'a4')}\npolish: {cfg.get('polish', 'on')}\n"
              f"whisper model: {cfg.get('whisper_model', 'small')}\nconfig: {CONFIG}")
        return
    style, args = opt(args, "--style")
    formats, args = opt(args, "--formats")
    paper, args = opt(args, "--paper")
    polish, args = opt(args, "--polish")
    model, args = opt(args, "--whisper-model")
    label, args = opt(args, "--label")
    changed = []
    if style:
        if style not in STYLES:
            die(f"--style is one of: {', '.join(STYLES)}")
        cfg["style"] = style
        changed.append(f"style: {style}")
    if formats:
        fs = [f.strip() for f in formats.split(",") if f.strip()]
        if not fs or set(fs) - {"md", "pdf", "html"} or "md" not in fs:
            die("--formats is md, optionally with pdf and html: md · md,pdf · md,html · md,pdf,html")
        cfg["formats"] = fs
        changed.append(f"formats: {','.join(fs)}")
    if paper:
        if paper not in ("a4", "letter"):
            die("--paper is a4 or letter")
        cfg["paper"] = paper
        changed.append(f"paper: {paper}")
    if polish:
        if polish not in ("on", "off"):
            die("--polish is on or off")
        cfg["polish"] = polish
        changed.append(f"polish: {polish}")
    if model:
        if model not in WHISPER_MODELS:
            die(f"--whisper-model is one of: {', '.join(WHISPER_MODELS)}")
        cfg["whisper_model"] = model
        changed.append(f"whisper model: {model}")
    if len(args) > 1 or (not args and not changed) or (label and not args):
        die('usage: setup <folder> [--label "what goes there"] · setup --show · '
            "setup --style obsidian|plain · setup --formats md[,pdf][,html] · setup --paper a4|letter · "
            "setup --polish on|off · setup --whisper-model " + "|".join(WHISPER_MODELS))
    if args:
        path = os.path.abspath(os.path.expanduser(args[0]))
        rs = [r for r in cfg.get("roots", [])
              if os.path.abspath(os.path.expanduser(r.get("path", ""))) != path]
        rs.append({"label": label or os.path.basename(path) or "notes", "path": path})
        os.makedirs(path, exist_ok=True)
        cfg["roots"] = rs
        changed.append(f"save folder: {rs[-1]['label']} -> {path}")
    save_config(cfg)
    print("saved: " + " · ".join(changed) + f"\nconfig: {CONFIG}")


def blurb(folder):
    try:
        for line in read(os.path.join(folder, "README.md")).split("\n"):
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
            print("  (folder missing: is the disk mounted?)")
            continue
        for name in sorted(os.listdir(r["path"])):
            p = os.path.join(r["path"], name)
            if os.path.isdir(p) and not name.startswith((".", "_")) and name != "inbox":
                print(f"  {name}/  ({blurb(p)})")
    print(f"\ndefaults: formats {','.join(setting('formats', ['md']))} · style {setting('style', 'obsidian')} · "
          f"polish {setting('polish', 'on')}")


# ---------------------------------------------------------------- downloads
def download(url, dest):
    """Raises RuntimeError with a readable reason; callers decide whether that is fatal."""
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return
    except Exception as e:                       # some Python builds ship without certificates
        first = e
    if not shutil.which("curl"):
        raise RuntimeError(f"could not download {url}: {first}")
    r = subprocess.run(["curl", "-fsSL", "-o", dest, url], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"could not download {url}: {r.stderr.strip() or first}")


def python310():
    """An interpreter that is Python 3.10+ (the yt-dlp zipapp needs it), or None."""
    if sys.version_info >= (3, 10):
        return sys.executable
    for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        p = shutil.which(name)
        if p and subprocess.run([p, "-c", "import sys; sys.exit(sys.version_info < (3, 10))"],
                                capture_output=True).returncode == 0:
            return p
    return None


# ---------------------------------------------------------------- yt-dlp: found, or installed once
def ytdlp_asset():
    """(release file, kind) for this machine: the zipapp when Python 3.10+ is around, else the
    platform's own build. None when yt-dlp publishes nothing for this system."""
    if python310():
        return "yt-dlp", "zipapp"
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "yt-dlp_macos.zip", "macos"          # the folder build: starts in 0.3 s, not 12 s
    if sys.platform.startswith("linux"):
        return ("yt-dlp_linux_aarch64" if machine in ("aarch64", "arm64") else "yt-dlp_linux"), "binary"
    if sys.platform == "win32":
        return ("yt-dlp_arm64.exe" if "arm" in machine else "yt-dlp.exe"), "binary"
    return None


def installed_ytdlp():
    try:
        return json.loads(read(os.path.join(YTDLP_HOME, "installed.json")))
    except (OSError, ValueError):
        return None


def published_sha(name):
    """The checksum yt-dlp publishes for `name` in its latest release, or None if unreachable."""
    tmp = tempfile.mkdtemp(prefix="yt-notes-dl-")
    try:
        download(RELEASES + "SHA2-256SUMS", os.path.join(tmp, "sums"))
        for line in read(os.path.join(tmp, "sums")).split("\n"):
            parts = line.split()
            if len(parts) == 2 and parts[1] == name:
                return parts[0]
    except RuntimeError:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def install_ytdlp(reason):
    if env("NO_INSTALL"):
        die("yt-dlp is not installed and automatic install is off (YT_NOTES_NO_INSTALL). "
            "Install it: https://github.com/yt-dlp/yt-dlp#installation", 4)
    asset = ytdlp_asset() or die("yt-dlp publishes no build for this system. "
                                 "Install it yourself: https://github.com/yt-dlp/yt-dlp#installation", 4)
    name, kind = asset
    note(f"{reason}: installing yt-dlp into {YTDLP_HOME} (once, {'3' if kind == 'zipapp' else 'up to 125'} MB)…")
    want = published_sha(name) or die("could not reach GitHub to download yt-dlp. Check the internet "
                                       "connection and try again", 4)
    os.makedirs(CACHE, exist_ok=True)
    stage = tempfile.mkdtemp(prefix="yt-dlp-new-", dir=CACHE)
    try:
        path = os.path.join(stage, name)
        try:
            download(RELEASES + name, path)
        except RuntimeError as e:
            die(f"{e}. Nothing installed", 4)
        if sha256(path) != want:
            die("the yt-dlp download does not match its published checksum; nothing installed", 4)
        if kind == "macos":
            # ditto keeps the build's permissions and links, which Python's zipfile drops
            r = subprocess.run(["/usr/bin/ditto", "-x", "-k", path, stage], capture_output=True, text=True)
            if r.returncode != 0:
                die(f"could not unpack yt-dlp: {r.stderr.strip()}", 4)
            os.remove(path)
            exe = os.path.join("yt-dlp_macos", "yt-dlp_macos")
            if not os.path.isfile(os.path.join(stage, exe)):
                found = glob.glob(os.path.join(stage, "**", "yt-dlp_macos"), recursive=True)
                found = [f for f in found if os.path.isfile(f)]
                if not found:
                    die("the unpacked yt-dlp has no yt-dlp_macos program", 4)
                exe = os.path.relpath(found[0], stage)
        else:
            exe = name
        os.chmod(os.path.join(stage, exe), 0o755)
        write(os.path.join(stage, "installed.json"),
              json.dumps({"asset": name, "kind": kind, "exe": exe, "sha256": want, "at": int(time.time())}))
        shutil.rmtree(YTDLP_HOME, ignore_errors=True)
        os.replace(stage, YTDLP_HOME)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if kind == "macos":
        note("yt-dlp installed. Its very first start takes a few seconds while macOS checks it.")


def ytdlp_cmd():
    """(command list, managed): the yt-dlp on PATH, else the copy in the cache (installed on first use)."""
    system = shutil.which("yt-dlp")
    if system:
        return [system], False
    if not installed_ytdlp():
        install_ytdlp("first run")
    info = installed_ytdlp()
    exe = os.path.join(YTDLP_HOME, info["exe"])
    if info["kind"] == "zipapp":
        py = python310() or die("the installed yt-dlp needs Python 3.10+, which is gone; "
                                f"run: python3 {os.path.abspath(__file__)} uninstall --yes, then try again", 4)
        return [py, exe], True
    return [exe], True


def ytdlp_failure(stderr):
    """A plain sentence for the failures people actually hit, or None for anything else."""
    e = stderr.lower()
    if "confirm you" in e and "not a bot" in e:
        return ("YouTube wants this network to sign in (\"confirm you're not a bot\"). Try again later. "
                "If the user agrees, fetch again with --cookies-from-browser <browser> to use their "
                "YouTube login from that browser.")
    if "confirm your age" in e or "age-restricted" in e or "inappropriate for some users" in e:
        return ("this video is age-restricted. It needs a signed-in account: if the user agrees, fetch "
                "again with --cookies-from-browser <browser>.")
    if "private video" in e:
        return "this video is private."
    if "members-only" in e or "join this channel" in e:
        return "this video is for channel members only."
    if "http error 429" in e or "too many requests" in e:
        return "YouTube is rate-limiting this network (HTTP 429). Wait a while and try again."
    if any(s in e for s in ("nodename nor servname", "name or service not known", "temporary failure in name",
                            "network is unreachable", "timed out", "connection refused", "connection reset")):
        return "no connection to YouTube. Check the internet connection and try again."
    if "video unavailable" in e or "this video has been removed" in e or "is not available" in e:
        return "this video is unavailable: removed, blocked in this country, or the link is wrong."
    return None


def update_hint(cmd):
    real = os.path.realpath(cmd[0])
    if "homebrew" in real or "/Cellar/" in real or "linuxbrew" in real:
        return "brew upgrade yt-dlp"
    if "pipx" in real:
        return "pipx upgrade yt-dlp"
    return "yt-dlp -U"


def ytdlp(*args, media=False, on_known=None):
    """Runs yt-dlp (never downloading video or audio unless media=True) and returns its output.
    on_known(sentence) may replace the message for a known failure."""
    cmd, managed = ytdlp_cmd()
    retried = False
    while True:
        r = subprocess.run(cmd + ["--no-playlist"] + ([] if media else ["--skip-download"]) + list(args),
                           capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        known = ytdlp_failure(r.stderr)
        if known:
            die((on_known(known) if on_known else None) or known, 2)
        if managed and not retried:
            # Unknown failures are usually YouTube changing something; a newer yt-dlp often fixes it.
            info = installed_ytdlp() or {}
            latest = published_sha(info.get("asset", ""))
            if latest and latest != info.get("sha256"):
                install_ytdlp("yt-dlp failed and a newer version exists")
                cmd, _ = ytdlp_cmd()
                retried = True
                continue
        tail = r.stderr.strip()[-1200:]
        hint = ("this is already the latest yt-dlp." if managed else
                f"Update yt-dlp ({update_hint(cmd)}) and try again.")
        die(f"yt-dlp failed:\n{tail}\n{hint}", 2)


# ---------------------------------------------------------------- captions
def is_translation(formats):
    """YouTube's machine translations are served with a tlang= parameter."""
    return any("tlang=" in (f.get("url") or "") for f in formats or [])


def spoken_language(info):
    """(language, how we know) for the language the video is spoken in."""
    for f in info.get("formats") or []:
        if f.get("acodec") not in (None, "none") and f.get("language") and \
                ("original" in (f.get("format_note") or "").lower() or (f.get("language_preference") or -1) >= 10):
            return base(f["language"]), "original audio"
    if info.get("language"):
        return base(info["language"]), "video details"
    origs = {base(k[:-5]) for k in (info.get("automatic_captions") or {}) if k.endswith("-orig")}
    if len(origs) == 1:
        return origs.pop(), "speech recognition"
    return None, None


def pick_track(info, want=None):
    """{code, kind, lang, spoken, how} for the captions to use, or {error, others}.
    In the video's language: human-made captions first, then YouTube's speech recognition.
    In another language (want): human-made subtitles first, then YouTube's machine translation."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}
    spoken, how = spoken_language(info)
    target = base(want) if want else spoken
    if target is None:
        langs = sorted({base(k) for k in manual})
        if len(langs) == 1:
            target = spoken = langs[0]
            how = "its only captions"

    def ranked(keys):          # the exact code asked for, then the bare language, then regional variants
        hits = [k for k in keys if base(k) == target]
        return sorted(hits, key=lambda k: (k != want, k != target, len(k), k))

    track = {"lang": target, "spoken": spoken, "how": how}
    if target:
        m = ranked(manual)
        if m:
            return dict(track, code=m[0], kind="manual")
        if spoken is None or target == spoken:
            asr = ranked(k for k in auto if k.endswith("-orig") and base(k[:-5]) == target) or \
                ranked(k for k in auto if not k.endswith("-orig") and not is_translation(auto[k]))
            if asr:
                return dict(track, code=asr[0], kind="auto")
        else:
            tr = ranked(k for k in auto if not k.endswith("-orig") and is_translation(auto[k]))
            if tr:
                return dict(track, code=tr[0], kind="translated")
    others = other_captions(info)
    if want and target != spoken:
        err = f"no captions in '{want}', human-made or translated"
    elif target:
        err = f"this video has no captions in its language ({target})"
    else:
        err = "this video has no captions, and nothing says which language it is in"
    return dict(track, error=err, others=others)


def other_captions(info):
    manual = sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat")
    auto = info.get("automatic_captions") or {}
    return (f"human-made: {', '.join(manual)}" if manual else "human-made: none") + \
        (" · machine translations: yes" if any(is_translation(v) for v in auto.values()) else "")


def cue_seconds(stamp):
    parts = stamp.replace(",", ".").split(":")
    try:
        return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))
    except ValueError:
        return 0.0


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def vtt_words(raw):
    """[(word, seconds)] in caption order. Auto-captions roll: every cue repeats the line before it
    and adds one new line, so the text is each cue's LAST line, skipping a repeat of the line just
    kept. Manual subtitles don't roll, so there every line is kept. Auto-captions time every word
    (<00:00:01.234> tags); elsewhere a word gets the start of the cue that first shows it.
    Verified 2026-09-28: 0 word differences against a hand-checked transcript."""
    raw = raw.replace("\r\n", "\n")
    rolling = "<c>" in raw
    kept, words = [], []
    for cue in raw.split("\n\n"):
        lines = cue.split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        start = cue_seconds(lines[idx].split("-->")[0].strip())
        shown = [l for l in lines[idx + 1:] if clean(l).strip()]
        for line in (shown[-1:] if rolling else shown):
            text = clean(line).strip()
            if kept and text == kept[-1]:
                continue
            kept.append(text)
            parts = TIME_TAG_RE.split(line)          # text, time, text, time, text ...
            segs = [(parts[0], start)] + [(parts[k + 1], cue_seconds(parts[k])) for k in range(1, len(parts) - 1, 2)]
            words.extend((w, t) for s, t in segs for w in clean(s).split())
    return words


def kebab(s):
    s = re.sub(r"[^0-9A-Za-z]+", "-", s.lower()).strip("-")
    if len(s) > 70:
        s = s[:70].rsplit("-", 1)[0]
    return (s or "transcript") + ".md"


def already_saved(video_id):
    """[(path, language)] of saved transcripts of this video."""
    hits = []
    for r in roots():
        for p in glob.glob(os.path.join(r["path"], "*", "*.md")):
            try:
                with open(p, encoding="utf-8") as f:
                    head = f.read(4000)
            except OSError:
                continue
            if video_id in head:
                fields = frontmatter_fields(head)
                hits.append((p, base(fields.get("language") or fields.get("caption_track") or "")))
    return hits


def new_workdir():
    # a run the user stopped (duplicate, declined, abandoned) leaves its work dir; clear any older than a day
    for prefix in WORK_PREFIXES:
        for old in glob.glob(os.path.join(tempfile.gettempdir(), prefix + "*")):
            try:
                if time.time() - os.path.getmtime(old) > 86400:
                    shutil.rmtree(old, ignore_errors=True)
            except OSError:
                pass
    return tempfile.mkdtemp(prefix=WORK_PREFIXES[0])


def download_captions(url, track, cookie_args, work=None):
    """(work dir, words) for one caption track. A machine translation YouTube refuses gets its own
    sentence: it happens often, and the original language still works."""
    work = work or new_workdir()
    sub = tempfile.mkdtemp(prefix="sub-", dir=work)

    def refused(known):
        if track["kind"] == "translated" and "429" in known:
            return (f"YouTube refused its machine translation into '{track['code']}' (HTTP 429). It often does; "
                    f"the captions in the video's own language still work (fetch without --lang). Nothing was written.")
        return None

    try:
        ytdlp("--write-subs" if track["kind"] == "manual" else "--write-auto-subs", "--sub-langs", track["code"],
              "--sub-format", "vtt", "-o", os.path.join(sub, "sub.%(ext)s"), *cookie_args, url, on_known=refused)
        vtts = glob.glob(os.path.join(sub, "*.vtt"))
        if not vtts:
            die(f"yt-dlp returned no captions file for track '{track['code']}'", 2)
        return work, vtt_words(read(vtts[0]))
    finally:
        shutil.rmtree(sub, ignore_errors=True)


VIDEO_LINK_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})")


def write_units(work, name, units):
    write(os.path.join(work, name), "".join(f"{i}| {fmt_time(t)}| {u}\n" for i, (u, t) in enumerate(units, 1)))


def cmd_fetch(args):
    want, args = opt(args, "--lang")
    cookies, args = opt(args, "--cookies-from-browser")
    speech, args = flag(args, "--whisper")
    if len(args) != 1:
        die("usage: fetch '<url>' [--lang xx] [--whisper] [--cookies-from-browser NAME]")
    url = args[0]
    cookie_args = ["--cookies-from-browser", cookies] if cookies else []
    if not VIDEO_LINK_RE.search(url):
        die("that is not one video's link (watch?v=, youtu.be/, shorts/, live/); a playlist or channel link won't do", 2)
    info = json.loads(ytdlp("-J", *cookie_args, url))
    if info.get("_type") == "playlist":
        die("that link is a playlist, not one video; give one video's link", 2)
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        die("this video is live or hasn't started yet; captions exist only after it ends", 2)
    if speech:
        track, work, words = whisper_fetch(info, url, want, cookie_args)
    else:
        track = pick_track(info, want)
        if track.get("error"):
            print(f"NO CAPTIONS: {track['error']}. Nothing was written.\n"
                  f"video_language: {track['spoken'] or 'unknown'}"
                  f"{' (' + track['how'] + ')' if track['how'] else ''}\n"
                  f"other captions: {track['others']}\n"
                  f"speech-to-text: fetch again with --whisper --lang <the video's language> to transcribe "
                  f"the audio with Whisper (only if the user agrees)")
            sys.exit(5)
        work, words = download_captions(url, track, cookie_args)
    if not words:
        shutil.rmtree(work, ignore_errors=True)
        die("the captions are empty; nothing was written", 2)
    tight = tight_text(" ".join(w for w, _ in words[:400]))
    units, punctuated = make_units(words, tight)
    text = join_words([w for w, _ in words], tight)
    up = str(info.get("upload_date") or "")
    meta = {
        "id": info.get("id"),
        "title": info.get("title") or "untitled",
        "creator": info.get("channel") or info.get("uploader") or "unknown",
        "url": f"https://www.youtube.com/watch?v={info.get('id')}",
        "length": info.get("duration_string") or "?",
        "published": f"{up[:4]}-{up[4:6]}-{up[6:8]}" if re.match(r"^\d{8}$", up) else None,
        "track": track["code"],
        "kind": track["kind"],
        "lang": track["lang"],
        "spoken": track["spoken"],
        "punctuated": punctuated,
        "tight": tight,
        "suggested_file": kebab(info.get("title") or ""),
    }
    write(os.path.join(work, "meta.json"), json.dumps(meta, indent=2, ensure_ascii=False))
    write(os.path.join(work, "raw.txt"), text)
    write(os.path.join(work, "units.json"), json.dumps([{"t": int(t), "text": u} for u, t in units], ensure_ascii=False))
    write_units(work, "units.txt", units)
    times = [int(t) for _, t in units]
    chapters = chapter_headings(info.get("chapters"), times, info.get("description"))
    if chapters:
        write(os.path.join(work, "chapters.json"), json.dumps(chapters, indent=1, ensure_ascii=False))
    original = None
    if meta["kind"] == "translated" or (meta["kind"] == "manual" and meta["spoken"] and meta["lang"] != meta["spoken"]):
        # the video's own captions, so caption fixes in the translation can be checked against them
        src = pick_track(info, None)
        if not src.get("error"):
            try:
                _, owords = download_captions(url, src, cookie_args, work)
                otight = tight_text(" ".join(w for w, _ in owords[:400]))
                write_units(work, "original.txt", make_units(owords, otight)[0])
                original = os.path.join(work, "original.txt")
            except SystemExit:
                print("note: the video's own captions could not be downloaded, so caption fixes in this "
                      "translation can't be checked against them")
    print(f"workdir: {work}")
    for k in ("title", "creator", "url", "length", "published", "track", "kind", "suggested_file"):
        print(f"{k}: {meta[k]}")
    print(f"captions_language: {meta['lang']} · video_language: {meta['spoken'] or 'unknown'}"
          f"{' (' + track['how'] + ')' if track.get('how') else ''}")
    if not speech:
        print(f"other captions: {other_captions(info)}")
    print(f"words: {len(words)} · units: {len(units)} (read {work}/units.txt)")
    if chapters:
        print(f"chapters: {len(chapters)} from the creator (start from {work}/chapters.json)")
    else:
        print("chapters: none (place the headings from units.txt)")
    if len(units) > LONG_VIDEO_UNITS:
        print("long video: read units.txt in parts of about 300 lines")
    if not punctuated:
        print("note: these captions have no punctuation; units end where the speaker pauses.")
    if TAG_RE.search(text):
        print("note: the captions mark sounds like [Music]; the file shows them in italics, apart from the speech.")
    if meta["kind"] == "manual":
        print("polish: off (human-made captions are not polished)")
    elif setting("polish", "on") == "on":
        print("polish: on (fix obvious caption mistakes in plan.json \"fixes\")" +
              (f"; the video's own captions are in {original}" if original else ""))
    else:
        print("polish: off (setting)")
    if base(meta["lang"]) in LABELS:
        print(f"labels: built in ({base(meta['lang'])})")
    else:
        print(f"labels: none built in for '{meta['lang']}': add \"labels\" to plan.json with keys "
              f"{', '.join(LABEL_KEYS)}, written in the file's language. English: "
              f"{json.dumps(dict(zip(LABEL_KEYS, LABELS['en'])), ensure_ascii=False)}")
    for path, lang in already_saved(meta["id"]):
        if not lang or lang == base(meta["lang"]):
            print(f"ALREADY SAVED: {path} (tell the user before writing a second copy)")
        else:
            print(f"saved before in another language ({lang}): {path}")


def description_chapters(description):
    """{seconds: title} from the creator's own timestamp lines ("02:38 How it works"). YouTube serves
    chapter titles translated into the viewer's language; these lines keep the creator's words."""
    out = {}
    for line in (description or "").split("\n"):
        m = re.match(r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-–—:|.)]*\s*(.+?)\s*$", line)
        if m:
            out[int(cue_seconds(m.group(1)))] = m.group(2)
    return out


def chapter_headings(chapters, times, description=""):
    """The creator's chapters as level-2 headings, each at the first unit that starts inside it."""
    hs, last = [], 0
    own = description_chapters(description)
    for i, c in enumerate(chapters or []):
        title = own.get(int(float(c.get("start_time") or 0))) or str(c.get("title") or "")
        title = re.sub(r"\s+", " ", title).strip().lstrip("#").strip() or f"Part {i + 1}"
        if i == 0:
            u = 1
        else:
            start = float(c.get("start_time") or 0)
            u = next((k for k, t in enumerate(times, 1) if t >= start - 1), None)
            if u is None:
                break
            u = max(u, last + 1)
            if u > len(times):
                break
        hs.append({"unit": u, "level": 2, "title": title})
        last = u
    return hs


# ---------------------------------------------------------------- Whisper (videos without captions)
def venv_python():
    return os.path.join(WHISPER_HOME, "venv", "Scripts" if sys.platform == "win32" else "bin",
                        "python.exe" if sys.platform == "win32" else "python")


def whisper_engine():
    """("cpp", path) for a whisper.cpp the user installed, ("managed", python) for the copy this
    tool installed, or None."""
    for name in ("whisper-cli", "whisper-cpp"):
        p = shutil.which(name)
        if p:
            return "cpp", p
    if os.path.isfile(venv_python()) and os.path.isfile(os.path.join(WHISPER_HOME, ".stamp")):
        return "managed", venv_python()
    return None


def ggml_model(model):
    """whisper.cpp's model file, downloaded once into the cache and checked against its published checksum."""
    path = os.path.join(WHISPER_HOME, "models", f"ggml-{model}.bin")
    if os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="ggml-", dir=os.path.dirname(path))
    try:
        try:
            download(GGML_TREE, os.path.join(tmp, "tree.json"))
            entry = next(e for e in json.loads(read(os.path.join(tmp, "tree.json"))) if e.get("path") == f"ggml-{model}.bin")
        except (RuntimeError, ValueError, StopIteration) as e:
            die(f"could not look up the Whisper model ggml-{model}.bin on Hugging Face: {e}", 4)
        size = (entry.get("lfs") or {}).get("size") or entry.get("size") or 0
        want = (entry.get("lfs") or {}).get("oid")
        note(f"first run of this model: downloading ggml-{model}.bin ({size // (1 << 20)} MB) into {os.path.dirname(path)}…")
        part = os.path.join(tmp, "model.bin")
        try:
            download(GGML_FILE + f"ggml-{model}.bin", part)
        except RuntimeError as e:
            die(f"{e}. Nothing installed", 4)
        if not want or sha256(part) != want:
            die("the Whisper model download does not match its published checksum; nothing installed", 4)
        os.replace(part, path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return path


def run_whisper(audio, lang, model, work):
    """[(word, seconds)], language: speech-to-text of the audio file, in `lang` (None = detect)."""
    found = whisper_engine()
    if not found:
        die("NO WHISPER: no speech-to-text tool on this machine. Either the user installs whisper.cpp "
            "(macOS and Linux: brew install whisper-cpp ffmpeg), or, if they agree, run: "
            f"python3 {os.path.abspath(__file__)} whisper-install (faster-whisper into this tool's cache: "
            f"about 230 MB, plus the {model} model: about 470 MB for small)", 4)
    kind, path = found
    started = time.time()
    if kind == "cpp":
        ffmpeg = shutil.which("ffmpeg") or die("whisper.cpp needs ffmpeg to read the audio (brew install ffmpeg)", 4)
        wav = os.path.join(work, "audio.wav")
        r = subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", audio, "-ar", "16000", "-ac", "1",
                            "-c:a", "pcm_s16le", wav], capture_output=True, text=True)
        if r.returncode != 0:
            die(f"ffmpeg could not read the audio: {r.stderr.strip()[-400:]}", 4)
        out = os.path.join(work, "whisper")
        note(f"transcribing with whisper.cpp ({model})…")
        r = subprocess.run([path, "-m", ggml_model(model), "-f", wav, "-l", lang or "auto", "-oj", "-of", out, "-np"],
                           capture_output=True, text=True)
        os.remove(wav)
        if r.returncode != 0 or not os.path.isfile(out + ".json"):
            die(f"whisper.cpp failed: {(r.stderr or r.stdout).strip()[-600:]}", 4)
        data = json.loads(read(out + ".json"))
        os.remove(out + ".json")
        words = [(w, seg["offsets"]["from"] / 1000) for seg in data.get("transcription", [])
                 for w in seg.get("text", "").split()]
        detected = (data.get("result") or {}).get("language")
    else:
        note(f"transcribing with faster-whisper ({model}); this takes a while…")
        r = subprocess.run([path, "-I", os.path.join(HERE, "engine", "whisper_run.py"), "transcribe", audio,
                            os.path.join(WHISPER_HOME, "models"), model, lang or "auto"],
                           stdout=subprocess.PIPE, text=True)
        if r.returncode != 0:
            die("faster-whisper failed (its message is above)", 4)
        data = json.loads(r.stdout)
        words = whisper_words(data["words"])
        detected = data.get("language")
    note(f"speech-to-text took {int(time.time() - started)} s")
    return words, base(lang or detected or "")


def whisper_words(raw):
    """Whisper's pieces -> [(word, seconds)]. A piece without a leading space continues the word before
    it ("L", "in", "ux" -> "Linux"; a comma joins its word), except between characters of scripts
    written without spaces, which stay separate pieces so pauses between them can still be found."""
    words = []
    for text, t in raw:
        piece = text.strip()
        glued = not piece[0].isalnum() or not (is_tight(words[-1][0][-1]) or is_tight(piece[0])) if words else False
        if glued and not text[:1].isspace():
            words[-1] = (words[-1][0] + piece, words[-1][1])
        else:
            words.extend((p, t) for p in piece.split())
    return words


def whisper_fetch(info, url, want, cookie_args):
    """(track, work dir, words) from the video's audio: downloaded, transcribed, deleted."""
    spoken, how = spoken_language(info)
    lang = base(want) if want else spoken
    model = setting("whisper_model", "small")
    work = new_workdir()
    try:
        note("downloading the audio (deleted after transcription)…")
        ytdlp("-f", "ba[ext=m4a]/ba", "-o", os.path.join(work, "audio.%(ext)s"), *cookie_args, url, media=True)
        audio = next(iter(glob.glob(os.path.join(work, "audio.*"))), None) or die("yt-dlp saved no audio", 2)
        words, lang = run_whisper(audio, lang, model, work)
    except SystemExit:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        for f in glob.glob(os.path.join(work, "audio.*")):
            os.remove(f)
    return {"code": f"whisper-{model}", "kind": "whisper", "lang": lang, "spoken": lang,
            "how": "chosen" if want else how}, work, words


def cmd_whisper_install(args):
    model, args = opt(args, "--model")
    model = model or setting("whisper_model", "small")
    if args or model not in WHISPER_MODELS:
        die(f"usage: whisper-install [--model {'|'.join(WHISPER_MODELS)}]")
    py = python310() or sys.executable
    venv = os.path.join(WHISPER_HOME, "venv")
    note(f"installing {' '.join(WHISPER_PACKAGES)} into {venv}, then the {model} model (once)…")
    shutil.rmtree(venv, ignore_errors=True)
    try:
        os.remove(os.path.join(WHISPER_HOME, ".stamp"))
    except OSError:
        pass
    os.makedirs(WHISPER_HOME, exist_ok=True)
    for cmd in ([py, "-m", "venv", venv],
                [venv_python(), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-input",
                 *WHISPER_PACKAGES],
                [venv_python(), "-I", os.path.join(HERE, "engine", "whisper_run.py"), "download", "-",
                 os.path.join(WHISPER_HOME, "models"), model, "auto"]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            die("could not install Whisper (nothing usable was left):\n" + (r.stderr or r.stdout).strip()[-800:], 4)
    write(os.path.join(WHISPER_HOME, ".stamp"), " ".join(WHISPER_PACKAGES) + "\n")
    print(f"installed: {WHISPER_PACKAGES[0]} with the {model} model in {WHISPER_HOME} "
          f"({folder_size(WHISPER_HOME) // (1 << 20)} MB)")


# ---------------------------------------------------------------- the file format
def split_frontmatter(md):
    """(frontmatter including its --- lines, the rest). Frontmatter only counts at the very top."""
    if md.startswith("---\n"):
        end = md.find("\n---\n", 4)
        if end >= 0:
            return md[:end + 5], md[end + 5:]
    return "", md


def frontmatter_fields(md):
    fm, _ = split_frontmatter(md)
    out = {}
    for line in fm.split("\n")[1:-2]:
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if v.startswith('"'):
                try:
                    v = json.loads(v)
                except ValueError:
                    pass
            out[m.group(1)] = v
    return out


def yaml_str(s):
    return json.dumps(str(s), ensure_ascii=False)        # a JSON string is a valid YAML double-quoted scalar


def find_blocks(text):
    """[(start, end)] character spans of every visual block outside code fences. A span starts at
    the blank lines insertion put before the start marker and ends after the end marker. Raises
    ValueError when the markers don't pair up: a damaged block must never take the user's text with it."""
    spans, pos, fence, open_at, open_line = [], 0, None, None, 0
    for n, line in enumerate(text.split("\n"), 1):
        start, end = pos, pos + len(line)
        pos = end + 1
        s = line.strip()
        if open_at is None:
            f = FENCE_RE.match(line)
            if f:
                fence = f.group(1)[0] if fence is None else (None if f.group(1)[0] == fence else fence)
                continue
            if fence:
                continue
        if s.startswith(BLOCK_START):
            if open_at is not None:
                raise ValueError(f"the visual block that starts on line {open_line} has no end marker "
                                 f"(another one starts on line {n})")
            if not START_RE.match(s):
                raise ValueError(f"line {n} is a damaged visual start marker")
            open_at, open_line = start, n
        elif s == BLOCK_END:
            if open_at is None:
                raise ValueError(f"line {n} ends a visual block that never started")
            b, k = open_at, 0
            while k < 2 and b > 0 and text[b - 1] == "\n":
                b, k = b - 1, k + 1
            spans.append((b, end))
            open_at = None
    if open_at is not None:
        raise ValueError(f"the visual block that starts on line {open_line} has no end marker")
    return spans


def strip_blocks(text):
    out, last = [], 0
    for a, b in find_blocks(text):
        out.append(text[last:a])
        last = b
    out.append(text[last:])
    return "".join(out)


def fix_def(n, frm, to, label):
    return f"[^fix-{n}]: {label}: {json.dumps(frm, ensure_ascii=False)} → {json.dumps(to, ensure_ascii=False)}"


def undo_fixes(text):
    """(text with every caption fix undone and its footnote removed, number of fixes). Raises
    ValueError when a fix and its footnote don't match: a damaged fix is never guessed at."""
    defs, kept = {}, []
    for n, line in enumerate(text.split("\n"), 1):
        m = FIX_DEF_RE.match(line)
        if m:
            defs[int(m.group(1))] = (json.loads(m.group(3)), json.loads(m.group(4)))
        elif line.startswith("[^fix-"):
            raise ValueError(f"line {n} is a damaged caption-fix footnote")
        else:
            kept.append(line)
    if not defs and not FIX_REF_RE.search(text):
        return text, 0
    if kept[-1:] == [""]:              # the footnotes block sits at the end after one blank line
        while len(kept) > 1 and kept[-1] == "" and kept[-2] == "":
            kept.pop()
    out = "\n".join(kept)
    refs = list(FIX_REF_RE.finditer(out))
    if sorted(int(m.group(1)) for m in refs) != sorted(defs):
        raise ValueError("the caption fixes and their footnotes don't match up (one was edited or deleted)")
    for m in reversed(refs):
        frm, to = defs[int(m.group(1))]
        if not out[:m.start()].endswith(to):
            raise ValueError(f"caption fix {m.group(1)} is damaged: the text before it is no longer {to!r}")
        out = out[:m.start() - len(to)] + frm + out[m.end():]
    return out, len(defs)


def plain_body(md):
    """The file after its frontmatter, with visuals removed and caption fixes undone."""
    _, rest = split_frontmatter(md)
    return undo_fixes(strip_blocks(rest))[0]


def body_words(md):
    """The file's words minus the frontmatter, the H1, the source line, heading lines, visual blocks
    and caption fixes."""
    lines = [l for l in plain_body(md).split("\n") if l.strip()]
    text = " ".join(l for l in lines[2:] if not re.match(r"^#{1,6}\s", l))
    return TAG_WRAPPED_RE.sub(r"\1", text).split()


def check(md, raw):
    try:
        lines = [l for l in plain_body(md).split("\n") if l.strip()]
    except ValueError as e:
        return str(e)
    if len(lines) < 3 or not lines[0].startswith("# "):
        return "the first line (after any frontmatter) must be '# <title>'"
    if " · http" not in lines[1]:
        return "the line after the title must be the source line: creator · URL · length · ..."
    if not lines[2].startswith("## "):
        return "the first line after the source line must be a '## ' heading"
    a, b = body_words(md), raw.split()
    if tight_text(raw):                # scripts without spaces: compare the characters, spacing aside
        a, b = list("".join(a)), list("".join(b))
        unit, sep = "character", ""
    else:
        unit, sep = "word", " "
    if a != b:
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        n = 20 if sep == "" else 8
        return (f"{unit}s differ from the captions at {unit} {i}: file has {sep.join(a[i:i+n])!r}, "
                f"captions have {sep.join(b[i:i+n])!r} ({len(a)} vs {len(b)} {unit}s)")
    return None


# ---------------------------------------------------------------- build
def load_plan(path, units, meta):
    """plan.json: {"headings": [...], "blurb", "tags", "fixes", "labels"} or just the headings list."""
    try:
        plan = json.loads(read(path))
    except (OSError, ValueError) as e:
        die(f"plan file unreadable: {e}")
    if isinstance(plan, list):
        plan = {"headings": plan}
    if not isinstance(plan, dict) or set(plan) - {"headings", "blurb", "tags", "fixes", "labels"}:
        die('the plan is {"headings": [...], "blurb": "...", "tags": [...], "fixes": [...], "labels": {...}} '
            "(all but headings optional)")
    n_units = len(units)
    hs = plan.get("headings")
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
            die("the first heading must be level 2 at unit 1: text above the first ## would read as the file's header line")
        if (u, lv) < last or (u == last[0] and lv == last[1] and i > 0):
            die(f"heading {i}: units must go forward (a ### may share a unit with the ## just before it)")
        last = (u, lv)
        h["title"] = t
    b = plan.get("blurb")
    if b is not None and (not isinstance(b, str) or not b.strip() or "\n" in b.strip()):
        die("blurb must be one line of text")
    tags = plan.get("tags") or []
    if not isinstance(tags, list) or any(not isinstance(t, str) or not TAG_NAME_RE.match(t) for t in tags):
        die("tags must be a list of single words ([0-9A-Za-z_/-], no spaces)")
    labels = plan.get("labels") or {}
    if not isinstance(labels, dict) or set(labels) - set(LABEL_KEYS) or \
            any(not isinstance(v, str) or not v.strip() or "\n" in v or len(v) > 200 for v in labels.values()):
        die(f"labels must be {{key: one line}} with keys from: {', '.join(LABEL_KEYS)}")
    fixes = place_fixes(plan.get("fixes") or [], units, meta)
    return hs, (b.strip() if b else None), tags, fixes, labels


def place_fixes(fixes, units, meta):
    """Validates the caption fixes and finds each one in its unit: [(unit index, start, end, from, to)]
    in reading order. A fix is a few words the captions misheard, never a rewrite."""
    if not fixes:
        return []
    if not isinstance(fixes, list):
        die('fixes must be a list of {"unit": N, "from": "words in the captions", "to": "the right words"}')
    if meta.get("kind") == "manual":
        die("these are human-made captions: they are not polished (remove \"fixes\" from the plan)")
    tight = meta.get("tight", False)
    placed = []
    for i, f in enumerate(fixes):
        if not isinstance(f, dict) or set(f) - {"unit", "from", "to", "nth"} or not {"unit", "from", "to"} <= set(f):
            die(f"fix {i}: keys unit, from, to (and nth when the words appear more than once in the unit)")
        u, frm, to = f["unit"], f["from"], f["to"]
        if not isinstance(u, int) or not 1 <= u <= len(units):
            die(f"fix {i}: unit must be 1..{len(units)}")
        if not isinstance(frm, str) or not isinstance(to, str) or not frm.strip() or not to.strip() or frm != frm.strip() \
                or to != to.strip() or frm == to:
            die(f"fix {i}: from and to are different, non-empty words without spaces around them")
        limit = (lambda s: len(s) <= 12) if tight else (lambda s: len(s.split()) <= 3)
        if not limit(frm) or not limit(to):
            die(f"fix {i}: a fix is at most {'12 characters' if tight else '3 words'} on each side; "
                "anything longer is a rewrite, and the transcript is never rewritten")
        if FIX_BAD_CHARS & set(to) or FIX_BAD_CHARS & set(frm):
            die(f"fix {i}: no markdown characters ([ ] ^ * < > | # ` \\) in a fix")
        if re.findall(r"\d+", frm) != re.findall(r"\d+", to) or numbers_said(frm) != numbers_said(to):
            die(f"fix {i}: a fix never changes a number")
        text = units[u - 1]["text"]
        pattern = re.escape(frm) if tight else r"(?<!\w)" + re.escape(frm) + r"(?!\w)"
        hits = [m.start() for m in re.finditer(pattern, text)]
        nth = f.get("nth")
        if not hits:
            die(f"fix {i}: {frm!r} is not in unit {u}: {text[:160]!r}")
        if len(hits) > 1 and nth is None:
            die(f"fix {i}: {frm!r} appears {len(hits)} times in unit {u}; add \"nth\": 1..{len(hits)}")
        nth = nth or 1
        if not isinstance(nth, int) or not 1 <= nth <= len(hits):
            die(f"fix {i}: nth must be 1..{len(hits)}")
        s = hits[nth - 1]
        placed.append((u - 1, s, s + len(frm), frm, to))
    placed.sort()
    for a, b in zip(placed, placed[1:]):
        if a[0] == b[0] and b[1] < a[2]:
            die(f"two fixes overlap in unit {a[0] + 1}")
    return placed


def wrap_tags(paragraph):
    return TAG_RE.sub(lambda m: f"*{m.group(0)}*", paragraph)


def formats_from(args):
    """(set of extra formats, remaining args): --pdf / --html, else the saved default."""
    pdf, args = flag(args, "--pdf")
    htm, args = flag(args, "--html")
    chosen = {f for f, on in (("pdf", pdf), ("html", htm)) if on}
    return (chosen or set(setting("formats", ["md"])) - {"md"}), args


def render(meta, units, hs, fixes, labels, tags):
    """The whole file. Paragraph breaks depend on the captions only, so a file without its fixes is
    byte for byte the file built without them."""
    tight = meta.get("tight", False)
    at = {}
    for h in hs:
        at.setdefault(h["unit"], []).append(h)
    by_unit = {}
    for n, (u, s, e, frm, to) in enumerate(fixes, 1):
        by_unit.setdefault(u, []).append((s, e, to, n))
    lang = base(meta.get("lang") or (meta.get("track") or "en"))
    fm = ["---", f"title: {yaml_str(meta['title'])}", f"channel: {yaml_str(meta['creator'])}",
          f"url: {meta['url']}", f"video_id: {meta['id']}"]
    if meta.get("published"):
        fm.append(f"published: {meta['published']}")
    fm += [f"duration: {yaml_str(meta['length'])}", f"caption_track: {meta['track']}",
           f"caption_kind: {meta['kind']}"] + ([f"language: {lang}"] if lang else [])
    if lang and meta.get("spoken") and base(meta["spoken"]) != lang:
        fm.append(f"video_language: {base(meta['spoken'])}")
    fm += [f"transcript: {'polished' if fixes else 'verbatim'}",
           f"tags: {json.dumps(['youtube'] + [t for t in tags if t != 'youtube'], ensure_ascii=False)}", "---"]
    parts = fm + ["", f"# {meta['title']}", "",
                  f"{meta['creator']} · {meta['url']} · {meta['length']} · {describe(meta, labels, bool(fixes))}"]
    para, count = [], 0.0          # para: [(the unit's caption text, the same with its fixes)]

    def flush():
        nonlocal para, count
        if para:
            text = para[0][1]
            for (prev, _), (_, cur) in zip(para, para[1:]):
                text += ("" if tight and prev[-1:] in TIGHT_END else " ") + cur
            parts.extend(["", wrap_tags(text)])
        para, count = [], 0.0

    for i, u in enumerate(units, 1):
        for h in at.get(i, []):
            flush()
            parts.extend(["", f"{'#' * h['level']} {h['title']} [{fmt_time(u['t'])}]({meta['url']}&t={u['t']}s)"])
        text = u["text"]
        for s, e, to, n in sorted(by_unit.get(i - 1, []), reverse=True):
            text = text[:s] + to + f"[^fix-{n}]" + text[e:]
        para.append((u["text"], text))
        count += size_of(u["text"], tight)
        if count >= PARA_WORDS and (u["text"][-1:] in END_PUNCT or not meta.get("punctuated", True)):
            flush()
    flush()
    if fixes:
        source = labels["speech"] if meta.get("kind") == "whisper" else labels["captions"]
        parts.append("")
        parts.extend(fix_def(n, frm, to, source) for n, (_u, _s, _e, frm, to) in enumerate(fixes, 1))
    return "\n".join(parts) + "\n"


def cmd_build(args):
    anywhere, args = flag(args, "--anywhere")
    blurb_flag, args = opt(args, "--blurb")
    formats, args = formats_from(args)
    if len(args) != 3:
        die("usage: build <workdir> <plan.json> <out.md> [--anywhere] [--pdf] [--html]")
    work, ppath, out = args[0], args[1], os.path.abspath(os.path.expanduser(args[2]))
    if not os.path.isfile(os.path.join(work, "meta.json")):
        die(f"{work} is not a fetch work dir (no meta.json): run fetch first; a built file's work dir is already removed")
    meta = json.loads(read(os.path.join(work, "meta.json")))
    raw = read(os.path.join(work, "raw.txt"))
    units = json.loads(read(os.path.join(work, "units.json")))

    if not FILE_RE.match(os.path.basename(out)):
        die("filename must be kebab-case [0-9A-Za-z._-] ending in .md")
    if os.path.exists(out):
        die(f"{out} already exists; nothing overwritten. Ask the user for another name")
    hs, blurb_txt, tags, fixes, label_override = load_plan(ppath, units, meta)
    blurb_txt = blurb_txt or blurb_flag
    folder = os.path.dirname(out)
    if not anywhere:
        rs = roots()
        if not rs:
            die("no save folder set up: run setup '<folder>'", 3)
        if os.path.dirname(folder) not in [r["path"] for r in rs] or not FOLDER_RE.match(os.path.basename(folder)):
            die("the file must sit one topic folder deep under a save folder: " +
                " or ".join(f"{r['path']}/<topic>/" for r in rs) + " (or pass --anywhere when the user named the path)")
        if not os.path.isdir(folder) and not blurb_txt:
            die(f"{folder} is a new topic folder: add \"blurb\": \"<one-line description>\" to the plan for its README")

    labels = labels_for(meta.get("lang") or meta.get("track") or "en", label_override)
    md = render(meta, units, hs, fixes, labels, tags)
    err = check(md, raw)
    if err:
        die("the built file failed its own check (nothing written): " + err)
    if not os.path.isdir(folder):
        os.makedirs(folder)
        if blurb_txt and not os.path.exists(os.path.join(folder, "README.md")):
            write(os.path.join(folder, "README.md"), blurb_txt + "\n")
    write(out, md)
    shutil.rmtree(work, ignore_errors=True)
    n2 = sum(1 for h in hs if h["level"] == 2)
    unit = "characters" if meta.get("tight") else "words"
    total = len(re.sub(r"\s", "", raw)) if meta.get("tight") else len(raw.split())
    print(f"written: {out}\n{unit}: {total} (identical to the {'speech-to-text' if meta.get('kind') == 'whisper' else 'captions'}"
          f"{', with ' + str(len(fixes)) + ' marked fixes' if fixes else ''}) · {n2} sections · "
          f"{len(hs) - n2} sub-sections · {md.count(chr(10))} lines\nwork dir removed.")
    for n, (u, _s, _e, frm, to) in enumerate(fixes, 1):
        print(f"fix {n} (unit {u + 1}): {frm!r} → {to!r}")
    if formats:
        export(out, formats, setting("paper", "a4"))


# ---------------------------------------------------------------- visuals
def title_key(t):
    return TS_LINK_RE.sub("", t).strip()


def headings_of(text):
    """[(level, title, line_start, line_end)] for every markdown heading outside code fences and
    frontmatter. Offsets are character positions in `text`. Titles drop a trailing timestamp link."""
    out, pos, fence = [], 0, None
    fm, _ = split_frontmatter(text)
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        pos = end + 1
        if start < len(fm):
            continue
        f = FENCE_RE.match(line)
        if f:
            fence = f.group(1)[0] if fence is None else (None if f.group(1)[0] == fence else fence)
            continue
        if fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), title_key(m.group(2)), start, end))
    return out


def text_end(text):
    """Where the file's own text ends: before the caption-fix footnotes at the bottom, if any."""
    m = re.search(r"(?:\n\[\^fix-\d+\]: [^\n]*)+\n*\Z", text)
    return m.start() if m else len(text)


def find_heading(heads, v, n):
    matches = [h for h in heads if h[1] == title_key(v["section"])]
    if not matches:
        die(f"visual {n} ({v['id']}): no heading named {v['section']!r}; headings are: " +
            " · ".join(h[1] for h in heads[:40]))
    nth = v.get("nth")
    if nth is None and len(matches) > 1:
        die(f"visual {n} ({v['id']}): {len(matches)} headings are named {v['section']!r}; add \"nth\": 1..{len(matches)}")
    nth = nth or 1
    if not isinstance(nth, int) or not 1 <= nth <= len(matches):
        die(f"visual {n} ({v['id']}): nth must be 1..{len(matches)}")
    return matches[nth - 1]


def phrase_re(phrase):
    """A phrase as the reader sees it: caption-fix markers may sit anywhere inside it."""
    ref = r"(?:\[\^fix-\d+\])?"
    return re.compile(ref.join(r"\s+" if t.isspace() else ref.join(map(re.escape, t))
                               for t in re.split(r"(\s+)", phrase.strip()) if t))


def anchor_offset(text, heads, v, n):
    """Where visual n goes: the end of its section's own text, or the end of the paragraph that
    holds `after_text` inside that section. Returns a character offset in `text`."""
    h = find_heading(heads, v, n)
    later = [x for x in heads if x[2] > h[2]]
    end = later[0][2] if later else text_end(text)
    if v.get("after_text"):
        m = phrase_re(v["after_text"]).search(text, h[3], end)
        if not m:
            die(f"visual {n} ({v['id']}): after_text not found inside section {v['section']!r}; copy it exactly")
        brk = text.find("\n\n", m.start(), end)
        para_end = brk if brk >= 0 else end
        return len(text[:para_end].rstrip())
    body = text[h[3]:end]
    return h[3] + len(body.rstrip()) if body.strip() else h[3]


def section_text(text, heads, h):
    """A section's own words including its sub-sections, without caption-fix markers or footnotes."""
    later = [x for x in heads if x[2] > h[2] and x[0] <= h[0]]
    s = text[h[3]:later[0][2] if later else text_end(text)]
    return FIX_REF_RE.sub("", s)


def load_visuals(path):
    try:
        vs = json.loads(read(path))
    except (OSError, ValueError) as e:
        die(f"visuals file unreadable: {e}")
    if not isinstance(vs, list):
        die("visuals must be a list (an empty list removes every visual)")
    allowed = {"id", "section", "nth", "after_text", "kind", "title", "why", "body", "numbers"}
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
        if "study-visual" in body or "<!--" in body or "[^fix-" in body:
            die(f"visual {n} ({vid}): body may not contain HTML comments or caption-fix markers")
        if any(re.match(r"^\s{0,3}#{1,6}\s", l) for l in body.split("\n")):
            die(f"visual {n} ({vid}): no # headings inside a visual; they would join the file's outline")
        if len(re.findall(r"^\s{0,3}(?:```|~~~)", body, re.M)) % 2:
            die(f"visual {n} ({vid}): a code fence is not closed")
        rows = body.split("\n")
        for i, l in enumerate(rows):
            if l.lstrip().startswith("|") and (i == 0 or not rows[i - 1].lstrip().startswith("|")):
                if i + 1 >= len(rows) or not re.match(r"^\s*\|?\s*:?-{3,}", rows[i + 1]):
                    die(f"visual {n} ({vid}): a table needs a |---| line under its header row")
        nums = v.get("numbers")
        if nums is not None:
            if v["kind"] != "chart" or not isinstance(nums, dict) or any(
                    not re.match(r"^\d[\d,]*(?:\.\d+)?$", str(k)) or not isinstance(q, str) or not q.strip()
                    or len(q) > 300 for k, q in nums.items()):
                die(f"visual {n} ({vid}): numbers is only for charts: {{\"45\": \"the exact phrase in its section that says it\"}}")
        v["body"] = body
    return vs


ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                   "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
SCALES = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}


def numbers_said(text):
    """Every number the text says, as digits ("1,200", "3.5") or in English words ("twenty five",
    "two hundred", "1.5 million")."""
    said = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            said.add(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    tokens = re.findall(r"[a-z]+|\d[\d,]*(?:\.\d+)?", text.lower().replace("-", " "))
    total, current, active, prev = 0, 0, False, None
    for tok in tokens + [""]:
        if tok in SCALES and prev is not None and not active:          # "1.5 million", "200 thousand"
            said.add(prev * SCALES[tok])
        if tok in ONES or tok in TENS:
            current += ONES[tok] if tok in ONES else TENS[tok]
            active = True
        elif tok in SCALES and active:
            if tok == "hundred":
                current = (current or 1) * 100
            else:
                total, current = total + (current or 1) * SCALES[tok], 0
        elif not (tok == "and" and active):                             # "two hundred and five"
            if active:
                said.add(float(total + current))
            total, current, active = 0, 0, False
        prev = float(tok.replace(",", "")) if tok[:1].isdigit() else None
    return said


def check_numbers(vs, base_text, heads):
    """A chart may only show numbers its own section says: in digits or English words, or tied to
    the exact phrase that says it (any language) in "numbers". Returns the quoted ones for the report."""
    quoted = []
    for n, v in enumerate(vs):
        if v["kind"] != "chart":
            continue
        section = section_text(base_text, heads, find_heading(heads, v, n))
        said = numbers_said(section)
        flat = re.sub(r"\s+", " ", section)
        quotes = {float(str(k).replace(",", "")): q for k, q in (v.get("numbers") or {}).items()}
        for l in v["body"].split("\n"):
            if re.match(r"^\s*(```|~~~|columns\b)", l):
                continue
            for num in re.findall(r"\d[\d,]*(?:\.\d+)?", l):
                x = float(num.replace(",", ""))
                if x in said:
                    continue
                q = quotes.get(x)
                if q is None:
                    die(f"visual {v['id']}: the chart shows {num}, which its section never says in digits or "
                        "English words. If the section says it in words of another language, add "
                        f"\"numbers\": {{\"{num}\": \"<the exact phrase>\"}}; otherwise show the structure instead")
                if re.sub(r"\s+", " ", q.strip()) not in flat:
                    die(f"visual {v['id']}: the phrase quoted for {num} is not in its section; copy it exactly: {q!r}")
                digits = [float(d.replace(",", "")) for d in re.findall(r"\d[\d,]*(?:\.\d+)?", q)]
                if digits and x not in digits:
                    die(f"visual {v['id']}: the phrase quoted for {num} says {', '.join(re.findall(r'[0-9][0-9,.]*', q))}")
                quoted.append(f"{v['id']}: {num} ← {q!r}")
    return quoted


def check_diagrams(vs):
    """Draw every ```mermaid block in a real browser: it must parse, lay out, and fit the column."""
    diagrams = [{"id": v["id"] if k == 0 else f"{v['id']} #{k + 1}", "code": code}
                for v in vs for k, code in enumerate(MERMAID_RE.findall(v["body"]))]
    if not diagrams:
        return 0
    results = engine({"mode": "check", "diagrams": diagrams}, "checking the diagrams")
    errors = [r for r in results if r.get("error")]
    if errors:
        die("these diagrams do not draw (nothing written):\n" +
            "\n".join(f"  {e['id']}: {e['error']}" for e in errors))
    wide = [r for r in results if r["width"] > MAX_WIDTH]
    if wide:
        die("these diagrams are wider than the reading column (" + str(MAX_WIDTH) + "px), and Obsidian "
            "cuts off what doesn't fit (nothing written):\n" +
            "\n".join(f"  {r['id']}: {r['width']}px" for r in wide) +
            "\nPut fewer boxes side by side, shorten the labels, or turn it (TB <-> LR).")
    return len(diagrams)


def block_text(v, style, label):
    quoted = "\n".join(f"> {l}" if l.strip() else ">" for l in v["body"].split("\n"))
    head = (f"> [!example] {label}: {v['title']}" if style == "obsidian" else f"> **{label}: {v['title']}**")
    return f"{BLOCK_START} id={v['id']} kind={v['kind']} -->\n{head}\n>\n{quoted}\n\n{BLOCK_END}"


def cmd_visuals(args):
    style, args = opt(args, "--style")
    style = style or setting("style", "obsidian")
    if style not in STYLES:
        die(f"--style is one of: {', '.join(STYLES)}")
    lang, args = opt(args, "--lang")
    label, args = opt(args, "--label")
    formats, args = formats_from(args)
    if len(args) != 2:
        die("usage: visuals <file.md> <visuals.json> [--style obsidian|plain] [--lang xx] [--label \"...\"] [--pdf] [--html]")
    path = existing_md(args[0])
    original = read(path)
    try:
        base_text = strip_blocks(original)          # a re-run replaces every block it added before
    except ValueError as e:
        die(f"{e}. Nothing written: repair or delete that block by hand first")
    if label is not None and (not label.strip() or "\n" in label or ":" in label or len(label) > 60):
        die("--label is one short line without a colon")
    fields = frontmatter_fields(original)
    label = (label or labels_for(lang or fields.get("language") or fields.get("caption_track") or "en")["visual"]).strip()
    replaced = original.count(BLOCK_START)
    vs = load_visuals(args[1])
    heads = headings_of(base_text)
    spots = [(anchor_offset(base_text, heads, v, n), n, v) for n, v in enumerate(vs)]
    quoted = check_numbers(vs, base_text, heads)
    diagrams = check_diagrams(vs)

    text = base_text
    for off, _n, v in sorted(spots, key=lambda s: (s[0], s[1]), reverse=True):
        text = text[:off] + "\n\n" + block_text(v, style, label) + text[off:]
    if strip_blocks(text) != base_text:
        die("inserting the visuals would change the file's own text (nothing written)")
    if len(find_blocks(text)) != len(vs):
        die("block count mismatch after inserting (nothing written)")
    write_atomic(path, text)
    print(f"written: {path}\nvisuals: {len(vs)} ({', '.join(v['id'] + ' ' + v['kind'] for v in vs) or 'none'})"
          f"{f' · {replaced} earlier ones replaced' if replaced else ''} · diagrams drawn and measured: {diagrams}\n"
          "the file's own text is unchanged, byte for byte")
    for q in quoted:
        print(f"chart number from a quote (tell the user): {q}")
    if formats:
        export(path, formats, setting("paper", "a4"))


def cmd_strip(args):
    only_visuals, args = flag(args, "--visuals")
    only_fixes, args = flag(args, "--fixes")
    if len(args) != 1 or (only_visuals and only_fixes):
        die("usage: strip <file.md> [--visuals | --fixes]")
    path = existing_md(args[0])
    text = read(path)
    done = []
    try:
        if not only_fixes:
            spans = find_blocks(text)
            if spans:
                text = strip_blocks(text)
                done.append(f"{len(spans)} visual{'s' if len(spans) != 1 else ''}")
        if not only_visuals:
            fm, rest = split_frontmatter(text)
            rest, n = undo_fixes(rest)
            if n:
                fields = frontmatter_fields(text)
                labels = labels_for(fields.get("language") or fields.get("caption_track") or "en")
                suffix = labels["sep"] + labels["polished"]
                lines = rest.split("\n")
                k = next((i for i, l in enumerate(lines) if " · http" in l), None)
                if k is not None and lines[k].endswith(suffix):
                    lines[k] = lines[k][:-len(suffix)]
                fm = fm.replace("\ntranscript: polished\n", "\ntranscript: verbatim\n", 1)
                text = fm + "\n".join(lines)
                done.append(f"{n} caption fix{'es' if n != 1 else ''}")
    except ValueError as e:
        die(f"{e}. Nothing changed: repair or delete it by hand first")
    if not done:
        print("nothing to remove; nothing changed")
        return
    write_atomic(path, text)
    print(f"removed {' and '.join(done)} from {path}; nothing else changed")


# ---------------------------------------------------------------- the browser engine (diagrams, PDF, HTML)
def node_major():
    if not shutil.which("node"):
        return None
    r = subprocess.run(["node", "--version"], capture_output=True, text=True)
    m = re.match(r"v(\d+)", r.stdout.strip())
    return int(m.group(1)) if m else None


def engine_stamp():
    h = hashlib.sha256()
    for f in ("package.json", "package-lock.json"):
        with open(os.path.join(HERE, "engine", f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def engine_ready():
    try:
        return read(os.path.join(ENGINE_HOME, ".stamp")) == engine_stamp() and \
            os.path.isdir(os.path.join(ENGINE_HOME, "node_modules", "puppeteer"))
    except OSError:
        return False


def run_engine(request, env_vars):
    return subprocess.run(["node", "engine.mjs"], cwd=ENGINE_HOME, input=json.dumps(request),
                          capture_output=True, text=True, env=env_vars, timeout=600)


def ensure_engine():
    major = node_major()
    if major is None or not shutil.which("npm"):
        die(f"diagrams, PDF and HTML need Node.js {NODE_MIN}+ with npm (https://nodejs.org). "
            "Tables and text work without it", 4)
    if major < NODE_MIN:
        die(f"diagrams, PDF and HTML need Node.js {NODE_MIN}+; this machine has Node {major}", 4)
    env_vars = dict(os.environ, PUPPETEER_CACHE_DIR=BROWSERS, PUPPETEER_SKIP_DOWNLOAD="true")
    if not engine_ready():
        note(f"first run: installing the diagram engine into {ENGINE_HOME} (once, about 180 MB)…")
        os.makedirs(ENGINE_HOME, exist_ok=True)
        for f in ("package.json", "package-lock.json"):
            shutil.copy(os.path.join(HERE, "engine", f), os.path.join(ENGINE_HOME, f))
        r = subprocess.run(["npm", "ci", "--no-audit", "--no-fund", "--silent"], cwd=ENGINE_HOME,
                           capture_output=True, text=True, env=env_vars)
        if r.returncode != 0:
            die("could not install the diagram engine (nothing written):\n" + r.stderr.strip()[-800:], 4)
        write(os.path.join(ENGINE_HOME, ".stamp"), engine_stamp())
        shutil.rmtree(os.path.join(CACHE, "mermaid-check"), ignore_errors=True)   # the 2.x checker
    shutil.copy(os.path.join(HERE, "engine", "engine.mjs"), os.path.join(ENGINE_HOME, "engine.mjs"))
    r = run_engine({"mode": "browser"}, env_vars)
    found = json.loads(r.stdout or "{}") if r.returncode == 0 else {}
    if not found.get("system") and not found.get("shell"):
        note(f"first run: no Chrome, Edge or Chromium found; downloading a headless browser into {BROWSERS} "
             "(once, about 190 MB)…")
        r = subprocess.run(["npx", "--no-install", "puppeteer", "browsers", "install", "chrome-headless-shell"],
                           cwd=ENGINE_HOME, capture_output=True, text=True,
                           env=dict(env_vars, PUPPETEER_SKIP_DOWNLOAD="false"))
        if r.returncode != 0:
            die("could not download the headless browser (nothing written):\n" + r.stderr.strip()[-800:], 4)
    return env_vars


def engine(request, purpose):
    env_vars = ensure_engine()
    r = run_engine(request, env_vars)
    if r.returncode != 0:
        die(f"the diagram engine failed while {purpose} (nothing written):\n" + r.stderr.strip()[-800:], 4)
    return json.loads(r.stdout)


def export(path, formats, paper):
    md = read(path)
    try:
        find_blocks(md)
        undo_fixes(split_frontmatter(md)[1])
    except ValueError as e:
        die(f"{e}. Nothing exported")
    m = re.search(r"^# (.+)$", split_frontmatter(md)[1], re.M)
    fields = frontmatter_fields(md)
    lang = base(fields.get("language") or fields.get("caption_track") or "en")
    stem = path[:-3]
    req = {"mode": "export", "markdown": md, "title": m.group(1) if m else os.path.basename(stem),
           "lang": lang, "rtl": lang in RTL, "paper": paper,
           "pdf": stem + ".pdf" if "pdf" in formats else None,
           "html": stem + ".html" if "html" in formats else None}
    out = engine(req, "exporting")
    for k in ("pdf", "html"):
        if out.get(k):
            print(f"exported: {out[k]}")


def cmd_export(args):
    paper, args = opt(args, "--paper")
    paper = paper or setting("paper", "a4")
    if paper not in ("a4", "letter"):
        die("--paper is a4 or letter")
    pdf, args = flag(args, "--pdf")
    htm, args = flag(args, "--html")
    if len(args) != 1:
        die("usage: export <file.md> [--pdf] [--html] [--paper a4|letter]")
    formats = {f for f, on in (("pdf", pdf), ("html", htm)) if on} or set(setting("formats", ["md"])) - {"md"}
    if not formats:
        die("say which copy to write: --pdf, --html, or both")
    path = existing_md(args[0])
    export(path, formats, paper)


# ---------------------------------------------------------------- verify, check, discard
def cmd_verify(args):
    cookies, args = opt(args, "--cookies-from-browser")
    if len(args) != 1:
        die("usage: verify <file.md> [--cookies-from-browser NAME]")
    path = existing_md(args[0])
    md = read(path)
    fields = frontmatter_fields(md)
    if fields.get("caption_kind") == "whisper":
        die("this transcript came from speech-to-text (Whisper): there are no captions to check it against")
    vid = fields.get("video_id")
    if not vid:
        m = VIDEO_LINK_RE.search(md[:4000])
        vid = m.group(1) if m else die("no video id in this file (no frontmatter, no source link)")
    url = f"https://www.youtube.com/watch?v={vid}"
    cookie_args = ["--cookies-from-browser", cookies] if cookies else []
    code, kind = fields.get("caption_track"), fields.get("caption_kind")
    if code and kind in ("manual", "auto", "translated"):
        track = {"code": code, "kind": kind}
    else:
        track = pick_track(json.loads(ytdlp("-J", *cookie_args, url)), None)
        if track.get("error"):
            die(track["error"], 2)
    work, words = download_captions(url, track, cookie_args)
    shutil.rmtree(work, ignore_errors=True)
    err = check(md, join_words([w for w, _ in words], tight_text(" ".join(w for w, _ in words[:400]))))
    if err:
        why = (" YouTube regenerates automatic captions and translations from time to time, so a difference "
               "can come from YouTube's side." if track["kind"] != "manual" else "")
        print(f"FAIL: {err}.{why}")
        sys.exit(1)
    print(f"ok: every word matches today's captions ({track['code']}, {track['kind']})")


def cmd_check(args):
    if len(args) != 2:
        die("usage: check <file.md> <raw.txt>")
    if not os.path.isfile(args[1]):
        die(f"{args[1]} is not an existing file")
    err = check(read(existing_md(args[0])), read(args[1]))
    print("ok: every word matches the captions" if not err else f"FAIL: {err}")
    sys.exit(1 if err else 0)


def cmd_discard(args):
    if len(args) != 1 or not os.path.basename(os.path.normpath(args[0])).startswith(WORK_PREFIXES):
        die("usage: discard <workdir from fetch>")
    shutil.rmtree(args[0], ignore_errors=True)
    print("work dir removed; nothing was written.")


# ---------------------------------------------------------------- doctor, uninstall
def folder_size(path):
    total = 0
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            try:
                total += os.lstat(os.path.join(dp, fn)).st_size
            except OSError:
                pass
    return total


def cmd_doctor(_args):
    ok = True
    print(f"yt-notes {VERSION}")
    print(f"  python   {platform.python_version()}  ok")
    system = shutil.which("yt-dlp")
    inst = installed_ytdlp()
    if system:
        v = subprocess.run([system, "--version"], capture_output=True, text=True).stdout.strip()
        print(f"  yt-dlp   {v or '?'}  {system}  (update with: {update_hint([system])})")
    elif inst:
        cmd, _ = ytdlp_cmd()
        v = subprocess.run(cmd + ["--version"], capture_output=True, text=True).stdout.strip()
        print(f"  yt-dlp   {v or '?'}  installed by this tool in {YTDLP_HOME} (updates itself when a fetch fails)")
    elif ytdlp_asset():
        print("  yt-dlp   not installed yet: the first fetch installs it")
    else:
        print("  yt-dlp   MISSING: no build for this system; install it yourself")
        ok = False
    print(f"  deno     {'found' if shutil.which('deno') else 'not found (optional: yt-dlp can use it for some YouTube pages)'}")
    major = node_major()
    if major is None:
        print(f"  node     not found: needed only for diagrams, PDF and HTML (Node {NODE_MIN}+)")
    else:
        print(f"  node     v{major}  {'ok' if major >= NODE_MIN and shutil.which('npm') else f'needs {NODE_MIN}+ with npm for diagrams, PDF and HTML'}")
    if engine_ready():
        r = run_engine({"mode": "browser"}, dict(os.environ, PUPPETEER_CACHE_DIR=BROWSERS))
        found = json.loads(r.stdout or "{}") if r.returncode == 0 else {}
        browser = found.get("system") or found.get("shell") or "none yet (downloads on first use)"
        print(f"  engine   installed  browser: {browser}")
    else:
        print("  engine   not installed yet: the first diagram, PDF or HTML installs it")
    w = whisper_engine()
    model = setting("whisper_model", "small")
    if not w:
        print("  whisper  not installed (optional, for videos without captions: brew install whisper-cpp ffmpeg, or whisper-install)")
    elif w[0] == "cpp":
        have = os.path.isfile(os.path.join(WHISPER_HOME, "models", f"ggml-{model}.bin"))
        print(f"  whisper  whisper.cpp  {w[1]}  model {model}: {'downloaded' if have else 'downloads on first use'}"
              f"{'' if shutil.which('ffmpeg') else '  NEEDS ffmpeg (brew install ffmpeg)'}")
    else:
        print(f"  whisper  faster-whisper installed by this tool in {WHISPER_HOME}")
    rs = roots()
    if not rs:
        print("  folders  none yet: the first run asks where transcripts go")
    for r in rs:
        state = "ok" if os.path.isdir(r["path"]) and os.access(r["path"], os.W_OK) else "MISSING or not writable"
        ok = ok and state == "ok"
        print(f"  folder   {r['label']} -> {r['path']}  {state}")
    print(f"  settings {CONFIG}  (polish {setting('polish', 'on')} · whisper model {model})")
    size = folder_size(CACHE) if os.path.isdir(CACHE) else 0
    print(f"  cache    {CACHE}  ({size // (1 << 20)} MB)")
    sys.exit(0 if ok else 4)


def cmd_uninstall(args):
    yes, args = flag(args, "--yes")
    if args:
        die("usage: uninstall [--yes]")
    custom_config = bool(env("CONFIG"))
    targets = [p for p in (CACHE, OLD_CACHE, CONFIG if custom_config else os.path.dirname(CONFIG),
                           None if custom_config else os.path.dirname(OLD_CONFIG)) if p and os.path.exists(p)]
    if not targets:
        print("nothing to remove: no downloaded tools and no settings")
        return
    if not yes:
        print("this removes:\n" + "\n".join(f"  {p}" for p in targets) +
              "\nYour saved transcripts and this skill's folder are not touched. Run again with --yes.")
        return
    for p in targets:
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    print("removed:\n" + "\n".join(f"  {p}" for p in targets) +
          "\nTo remove the skill itself, delete its folder: " + HERE)


if __name__ == "__main__":
    cmds = {"setup": cmd_setup, "where": cmd_where, "fetch": cmd_fetch, "build": cmd_build,
            "visuals": cmd_visuals, "export": cmd_export, "strip": cmd_strip, "verify": cmd_verify,
            "check": cmd_check, "discard": cmd_discard, "whisper-install": cmd_whisper_install,
            "doctor": cmd_doctor, "uninstall": cmd_uninstall}
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(VERSION)
        sys.exit(0)
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] != "uninstall":
        migrate()
    cmds[sys.argv[1]](sys.argv[2:])
