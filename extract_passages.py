"""Extract Thakur's spoken passages from our copy of the Kathamrita (cache/).

Writes data/passages.json: one entry per paragraph where Thakur speaks, with a stable id
"<page file stem>#p<paragraph index>", chapter/section/date, and the text.
Also writes data/sections_text.json: the full main text of each section, for "read more".

Speaker rules (Kathamrita conventions):
  * "শ্রীরামকৃষ্ণ — ..." / "শ্রীরামকৃষ্ণ (মাস্টারের প্রতি) — ..." starts Thakur's speech.
  * "<Other name> — ..." starts someone else's speech.
  * A paragraph opening with “ and no speaker label continues the previous speaker.
  * Narration such as 'ঠাকুর বলিতেছেন, “...”' counts as Thakur's speech too.
Footnotes ("— প্র:") and the site's appendices are excluded (source-register.md).
"""
import html
import json
import re
import unicodedata
from pathlib import Path

import build_song_index as b

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"
NFC = lambda s: unicodedata.normalize("NFC", s)

SPEAKER = re.compile(NFC(r"^\s*([^\s—–“\"]{2,}(?:\s[^\s—–“\"]+){0,3}?)\s*(\([^)]*\))?\s*[—–]\s+"))
THAKUR_NAME = re.compile(NFC(r"^(শ্রীরামকৃষ্ণ|ঠাকুর|পরমহংসদেব)$"))
ASIDE = re.compile(NFC(r"^\s*\([^)]{2,40}\)\s*[—–]\s+"))
THAKUR_NARRATION = re.compile(NFC(r"ঠাকুর|শ্রীরামকৃষ্ণ"))
THAKUR_SAYS = re.compile(NFC(r"(ঠাকুর|শ্রীরামকৃষ্ণ)[^।“]{0,60}(বলিতেছেন|বলিলেন|বলছেন|কহিতেছেন|বলিয়াছিলেন)[^“]{0,20}“"))


def main():
    sections = json.loads((CACHE / "sections.json").read_text(encoding="utf-8"))
    passages, section_text = [], {}
    for sec in sections:
        text = html.unescape((CACHE / sec["file"]).read_bytes().decode("latin-1"))
        date_bn, date_iso, prec = b.parse_date(text)
        stem = sec["file"].rsplit(".", 1)[0]
        speaker = None
        full = []
        for i, (cls, raw) in enumerate(b.page_blocks(text)):
            t = NFC(b.one_line(b.strip_tags(raw)))
            if not t:
                continue
            if cls in ("beng", "song", "chaphead"):
                full.append({"i": i, "cls": cls, "text": b.strip_tags(raw) if cls == "song" else t})
            if cls != "beng":
                continue
            m = SPEAKER.match(t)
            aside = ASIDE.match(t)
            if aside:
                # "(ডাক্তারের প্রতি) — ..." is a stage direction: the current speaker
                # (in practice almost always Thakur) turns to someone. Not a new speaker.
                speaker = "thakur"
                body = t[aside.end():]
                m = None
            elif m and len(m.group(1)) < 40:
                speaker = "thakur" if THAKUR_NAME.match(m.group(1)) else "other"
                body = t[m.end():]
            elif t.startswith("“"):
                body = t  # continues the previous speaker
            else:
                speaker = "thakur" if THAKUR_SAYS.search(t) else None
                body = t
            if speaker == "thakur" and len(body) > 40:
                passages.append({
                    "id": f"{stem}#p{i}",
                    "file": stem, "para": i,
                    "chapter": sec["chapter"], "section": sec["section"],
                    "section_title": sec["section_title"], "chapter_title": sec["chapter_title"],
                    "date_bn": date_bn or "", "date_iso": date_iso or "",
                    "text": body,
                })
            if not t.startswith("“") and not m and not aside:
                # Narration about Thakur ("এই বলিয়া ঠাকুর গান ধরিলেন:") keeps him as the speaker
                # for the quoted paragraphs that follow; other narration ends the speech.
                speaker = "thakur" if THAKUR_NARRATION.search(t) else None
        section_text[stem] = {
            "chapter": sec["chapter"], "section": sec["section"],
            "chapter_title": sec["chapter_title"], "section_title": sec["section_title"],
            "date_bn": date_bn or "", "blocks": full,
        }
    DATA.mkdir(exist_ok=True)
    (DATA / "passages.json").write_text(json.dumps(passages, ensure_ascii=False, indent=0), encoding="utf-8")
    (DATA / "sections_text.json").write_text(json.dumps(section_text, ensure_ascii=False), encoding="utf-8")
    print(f"{len(passages)} Thakur passages, {sum(len(p['text']) for p in passages)} chars; "
          f"{len(section_text)} sections saved for read-more")


if __name__ == "__main__":
    main()
