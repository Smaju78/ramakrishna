"""Index the Sri Ma Trust English Kathamrita PDFs by page and visit date.

PRIVATE READING ONLY (source-register.md): the Trust's text never goes into the public
site. Inputs: cache/srimatrust/english-vol{1..5}.pdf. Output: cache/srimatrust/english_pages.json
[{vol, page, date_iso, text}] with running headers, footnotes and footnote markers removed.
Even pages carry the date in their header ("16 October, 1882"); odd pages inherit it.
"""
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent / "cache" / "srimatrust"
DATE = re.compile(r"^(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+([A-Z][a-z]+),?\s+(18\d\d)$")


def to_iso(m):
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def clean_page(lines, running_titles):
    # header: page number, book title, date, or this volume's running chapter title
    while lines and (not lines[0].strip() or lines[0].strip().isdigit()
                     or "Sri Sri Ramakrishna Kathamrita" in lines[0]
                     or DATE.match(lines[0].strip()) or lines[0].strip() in running_titles):
        lines = lines[1:]
    # footnotes: from the first line in the lower part of the page that is only a number,
    # or starts "1. " (Volume 1 style), to the end of the page
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.isdigit() or (i > len(lines) * 0.4 and re.match(r"^\d{1,2}\.\s+\S", s)):
            lines = lines[:i]
            break
    text = "\n".join(ln.rstrip() for ln in lines).strip()
    return re.sub(r"(?<=[A-Za-z’”\.,;:!?\)])\d{1,2}(?=[\s,\.;:!?’”\)]|$)", "", text)  # footnote markers


def main():
    out = []
    for vol in range(1, 6):
        pdf = DIR / f"english-vol{vol}.pdf"
        txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        pages = [p.split("\n") for p in txt.split("\f")]
        firsts = Counter(next((l.strip() for l in p if l.strip()), "") for p in pages)
        running = {t for t, n in firsts.items() if n >= 3 and len(t) < 90}  # repeated page headers
        date = None
        for n, lines in enumerate(pages, 1):
            for ln in lines[:6]:
                m = DATE.match(ln.strip())
                if m and to_iso(m):
                    date = to_iso(m)
                    break
            out.append({"vol": vol, "page": n, "date_iso": date, "text": clean_page(lines, running)})
    (DIR / "english_pages.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    dated = sum(1 for p in out if p["date_iso"])
    print(f"{len(out)} pages, {dated} dated, {len({p['date_iso'] for p in out if p['date_iso']})} distinct dates")


if __name__ == "__main__":
    main()
