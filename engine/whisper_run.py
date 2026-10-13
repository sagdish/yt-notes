"""Speech-to-text with faster-whisper. Run by yt_notes.py with the Python environment it installed
(whisper-install), never by hand.

  whisper_run.py download   -     <models dir> <model> auto   fetches the model once
  whisper_run.py transcribe <audio> <models dir> <model> <language|auto>
      -> stdout: {"language": "xx", "words": [[word, seconds], ...]}; progress on stderr. A word keeps
         Whisper's leading space: without one, it continues the word before it.
"""
import json, sys

from faster_whisper import WhisperModel

mode, audio, root, name, lang = sys.argv[1:6]
model = WhisperModel(name, device="cpu", compute_type="int8", download_root=root)
if mode == "download":
    sys.exit(0)
# vad_filter skips silence and music, where Whisper otherwise invents repeated lines
segments, info = model.transcribe(audio, language=None if lang == "auto" else lang,
                                  vad_filter=True, word_timestamps=True)
words, shown = [], 0
for seg in segments:
    words.extend([w.word, round(w.start, 2)] for w in seg.words or [] if w.word.strip())
    if info.duration and seg.end - shown >= 60:
        shown = seg.end
        print(f"  {int(seg.end // 60)} of {int(info.duration // 60)} min", file=sys.stderr, flush=True)
json.dump({"language": info.language, "words": words}, sys.stdout, ensure_ascii=False)
