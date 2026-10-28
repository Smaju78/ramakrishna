"""Work out the Sri Ma Trust reference (Volume / Section / Chapter) and date for each English passage.

The Trust asked (2026-10) for the reference as printed in their book: e.g. "Vol. 2, Section III, Chapter V",
with the date of the conversation. Their PDF text marks every section and chapter with a heading on its own
line ("Section III", "Chapter V"; the Vol. 1 introduction uses "Chapter One"...). We follow those headings in
reading order and look up where each extracted passage starts.

Inputs : cache/srimatrust/english_pages.json, data/english_srimatrust.json   (both gitignored)
Output : data/english_refs.json   {ref: {vol, section, chapter, date_iso, label}}   (numbers and dates only)
Run    : python3 english_refs.py        -> prints a report; anything odd is listed at the end.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
PAGES = ROOT / "cache" / "srimatrust" / "english_pages.json"
ENGLISH = ROOT / "data" / "english_srimatrust.json"
OUT = ROOT / "data" / "english_refs.json"

WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}
APPENDIX = re.compile(r"^Appendix(?:\s+([IVXL]+))?\s*$")
HEAD = re.compile(r"^(Section|Chapter)\s+([IVXL]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve)\s*$")


def roman_to_int(s):
    n = 0
    for i, c in enumerate(s):
        v = ROMAN[c]
        n += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return n


def int_to_roman(n):
    out = ""
    for v, r in ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += r
            n -= v
    return out


def value(token):
    return WORDS.index(token) if token in WORDS else roman_to_int(token)


def volume_index(pages, vol, notes):
    """(flat text, page offsets, heading events) for one volume, like english_extract.volume_text."""
    parts, offsets, events, pos = [], {}, [], 0
    sec, ch = 0, 0
    for p in sorted((p for p in pages if p["vol"] == vol), key=lambda p: p["page"]):
        offsets[p["page"]] = pos
        text = re.sub(r"-\n(?=[a-z])", "-", p["text"])
        for line in text.split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            a = APPENDIX.match(line)
            if a and sec:  # appendices follow the numbered sections
                events.append((pos, "A", a.group(1) or ""))
                ch, sec = 0, 10 ** 6  # no more numbered sections
                parts.append(line + " ")
                pos += len(line) + 1
                continue
            m = HEAD.match(line)
            if m:
                kind, n = m.group(1), value(m.group(2))
                if kind == "Section" and n == sec + 1:
                    sec, ch = n, 0
                    events.append((pos, "S", sec))
                elif kind == "Chapter" and n == ch + 1:
                    ch = n
                    events.append((pos, "C", ch))
                elif kind == "Chapter" and sec == 0 and n == 1 and not ch:
                    ch = 1
                    events.append((pos, "C", 1))
                else:
                    notes.append(f"vol {vol} p{p['page']}: ignored heading {line!r} (after section {sec}, chapter {ch})")
            parts.append(line + " ")
            pos += len(line) + 1
    return "".join(parts), offsets, events


def main():
    pages = json.loads(PAGES.read_text(encoding="utf-8"))
    english = json.loads(ENGLISH.read_text(encoding="utf-8"))
    by_page = {(p["vol"], p["page"]): p for p in pages}
    notes, out, index = [], {}, {}
    for ref, e in english.items():
        vol = e["vol"]
        if vol not in index:
            index[vol] = volume_index(pages, vol, notes)
        text, offsets, events = index[vol]
        probe = re.sub(r"\s+", " ", e["text"]).strip()[:70]
        start = text.find(probe, max(0, offsets[e["page"]] - 3000))
        if start < 0:
            notes.append(f"{ref}: passage start not found in vol {vol}")
            continue
        sec = ch = app = None
        for pos, kind, n in events:
            if pos > start:
                break
            if kind == "S":
                sec, ch, app = n, None, None
            elif kind == "A":
                sec, ch, app = None, None, n or "(single)"
            else:
                ch = n
        date = by_page[(vol, e["page"])]["date_iso"]
        if app is not None:
            name = "Appendix" if app == "(single)" else f"Appendix {app}"
            label = f"Vol. {vol}, {name}" + (f", Chapter {int_to_roman(ch)}" if ch else "")
        elif sec is None:
            label = f"Vol. {vol}, Introduction" + (f", Chapter {WORDS[ch]}" if ch else "")
        else:
            label = f"Vol. {vol}, Section {int_to_roman(sec)}" + (f", Chapter {int_to_roman(ch)}" if ch else "")
        out[ref] = {"vol": vol, "section": sec, "appendix": app, "chapter": ch, "date_iso": date, "label": label}
        if ch is None:
            notes.append(f"{ref}: no chapter heading before the passage ({label})")
        if not date:
            notes.append(f"{ref}: no date for page {e['page']}")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} of {len(english)} references written to {OUT.name}")
    for n in notes:
        print("  NOTE:", n)


if __name__ == "__main__":
    main()
